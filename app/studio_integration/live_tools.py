"""Live-data tools for Agent Studio on AI App Server.

Search opens recognised official retailer categories first, then uses key-free public RSS. Optional Brave or local SearXNG.
SQL tool never executes submitted SQL; it builds a bounded, parameterised SELECT
from server-discovered table/column identifiers. A SELECT-only SQL login is essential.
Credentials live in Python process memory only, never in workflow JSON.
"""
import datetime
import decimal
import json
import re
import html
import xml.etree.ElementTree as ET
import threading
from urllib import request, parse, error
from .web_research import research, direct_retailer_entries, ResearchError

LOCK = threading.RLock()
SETTINGS = {'provider': 'bing', 'brave_key': '', 'searx_url': 'http://127.0.0.1:8888',
            'sql_server': '', 'sql_database': '', 'sql_auth': 'windows',
            'sql_user': '', 'sql_password': '', 'sql_driver': 'ODBC Driver 18 for SQL Server',
            'sql_trust_cert': False}
LIMIT = 20
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
SERVER = re.compile(r'^[A-Za-z0-9_.\\,-]{1,150}$')
DRIVERS = {'ODBC Driver 18 for SQL Server', 'ODBC Driver 17 for SQL Server'}

class LiveToolError(ValueError):
    pass

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LiveToolError('Search provider redirect refused. Check the service configuration.')

_OPENER = request.build_opener(NoRedirect())


def searx_url(raw):
    if not isinstance(raw, str) or len(raw)>220:
        raise LiveToolError('Enter the local SearXNG address, e.g. http://127.0.0.1:8888.')
    url = parse.urlsplit(raw)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.username or url.password or url.query or url.fragment or url.path.rstrip('/') not in ('', '/search'):
        raise LiveToolError('SearXNG must be a local http://127.0.0.1:PORT instance.')
    if not url.port or not 1<=url.port<=65535:
        raise LiveToolError('SearXNG needs a port, such as 8888.')
    return f'http://127.0.0.1:{url.port}'


def configure(data):
    if not isinstance(data,dict):raise LiveToolError('Invalid connection settings.')
    changes={}
    if 'provider' in data:
        if data['provider'] not in ('bing','brave','searxng'):raise LiveToolError('Choose built-in search, Brave or SearXNG.')
        changes['provider']=data['provider']
    if 'brave_key' in data:
        val=data['brave_key']
        if not isinstance(val,str) or len(val)>256 or '\r' in val or '\n' in val:raise LiveToolError('Invalid Brave API key.')
        if val.strip():changes['brave_key']=val.strip()
    if data.get('clear_brave') is True:changes['brave_key']=''
    if 'searx_url' in data:changes['searx_url']=searx_url(data['searx_url'])
    if 'sql_server' in data:
        v=data['sql_server'].strip() if isinstance(data['sql_server'],str) else ''
        if v and not SERVER.fullmatch(v):raise LiveToolError('SQL Server name may contain letters, digits, dots, backslashes and instance/port separators.')
        changes['sql_server']=v
    if 'sql_database' in data:
        v=data['sql_database'].strip() if isinstance(data['sql_database'],str) else ''
        if v and not IDENT.fullmatch(v):raise LiveToolError('Database name must use letters, numbers and underscores.')
        changes['sql_database']=v
    if 'sql_auth' in data:
        if data['sql_auth'] not in ('windows','sql'):raise LiveToolError('Choose Windows or SQL authentication.')
        changes['sql_auth']=data['sql_auth']
    if 'sql_user' in data:
        v=data['sql_user'].strip() if isinstance(data['sql_user'],str) else ''
        if len(v)>120 or any(c in v for c in '{};\r\n'):raise LiveToolError('Invalid SQL user.')
        changes['sql_user']=v
    if 'sql_password' in data:
        v=data['sql_password']
        if not isinstance(v,str) or len(v)>300 or any(c in v for c in '{};\r\n'):raise LiveToolError('Invalid SQL password.')
        if v:changes['sql_password']=v
    if data.get('clear_sql_password') is True:changes['sql_password']=''
    if 'sql_driver' in data:
        if data['sql_driver'] not in DRIVERS:raise LiveToolError('Choose a supported Microsoft SQL Server ODBC driver.')
        changes['sql_driver']=data['sql_driver']
    if 'sql_trust_cert' in data:
        if not isinstance(data['sql_trust_cert'],bool):raise LiveToolError('Invalid certificate setting.')
        changes['sql_trust_cert']=data['sql_trust_cert']
    with LOCK:SETTINGS.update(changes)
    return status()


def _snapshot():
    with LOCK:return dict(SETTINGS)


def status():
    s=_snapshot()
    return {'webReady':True if s['provider']=='bing' else (bool(s['brave_key']) if s['provider']=='brave' else True),
            'webProvider':s['provider'], 'webKeySet':bool(s['brave_key']),
            'searxUrl':s['searx_url'], 'sqlReady':bool(s['sql_server'] and s['sql_database'] and (s['sql_auth']=='windows' or (s['sql_user'] and s['sql_password']))),
            'sqlServer':s['sql_server'], 'sqlDatabase':s['sql_database'], 'sqlAuth':s['sql_auth'],
            'sqlDriver':s['sql_driver'], 'sqlUser':s['sql_user'], 'sqlTrustCert':s['sql_trust_cert'],
            'credentialsStorage': 'memory only; cleared when this server exits'}


def _rss_results(blob):
    """Parse public RSS results without following the pages or executing HTML."""
    try:
        document=ET.fromstring(blob)
    except ET.ParseError as exc:
        raise LiveToolError('The public search service returned a page instead of RSS results. It may be temporarily blocking automated searches. Try again later.') from exc
    channel=document.find('channel')
    if document.tag!='rss' or channel is None:
        raise LiveToolError('The public search provider did not return RSS search results. Try again later.')
    results=[]
    for item in channel.findall('item')[:10]:
        link=(item.findtext('link') or '').strip()
        url=parse.urlsplit(link)
        if url.scheme!='https' or not url.hostname or url.username or url.password:
            continue
        def clean(value, limit):
            text=html.unescape(value or '')
            text=re.sub(r'<[^>]*>', ' ', text)
            return ' '.join(text.split())[:limit]
        results.append({'title':clean(item.findtext('title'),220),
                        'url':link[:750],
                        'description':clean(item.findtext('description'),600)})
    if not results:
        raise LiveToolError('Public search returned no usable website links. Try a more specific search or try again later. No search results were invented.')
    return results


def web_search(query, progress=None):
    if not isinstance(query,str) or not 1<=len(query.strip())<=500:raise LiveToolError('Web search needs a query of 1–500 characters.')
    q=query.strip();s=_snapshot()
    direct_result=None
    entries=direct_retailer_entries(q)
    if entries:
        if progress:progress('web_direct_retailer',message=f'Retailer identified. Trying {len(entries)} official category/navigation pages before public search.')
        try:
            direct_result=research(q,entries,progress=progress,discovery='retailer')
            if 'On-page GBP offers: 0' not in direct_result:
                return direct_result
            if progress:progress('web_direct_no_offers',message='Official pages yielded no readable product prices. Trying public search for additional product pages.')
        except ResearchError as exc:
            if progress:progress('web_direct_failed',message='Direct retailer navigation was unavailable: '+str(exc)[:160])

    if s['provider']=='bing':
        # A public RSS feed: no account, credential, local search service or package required.
        # Public RSS is best-effort. It may be unavailable/rate-limited and is not a guaranteed API.
        uri='https://www.bing.com/search?'+parse.urlencode({'q':q,'format':'rss','setlang':'en-GB'})
        headers={'Accept':'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8',
                 'User-Agent':'AgentStudio/2.1 (self-hosted local research application)'}
    elif s['provider']=='brave':
        if not s['brave_key']:raise LiveToolError('Brave is selected but no key is set. In Connections switch to Built-in Web Search for a free, no-key search.')
        uri='https://api.search.brave.com/res/v1/web/search?'+parse.urlencode({'q':q,'count':5,'country':'gb','search_lang':'en'})
        headers={'Accept':'application/json','X-Subscription-Token':s['brave_key']}
    else:
        uri=s['searx_url']+'/search?'+parse.urlencode({'q':q,'format':'json','safesearch':1})
        headers={'Accept':'application/json'}
    req=request.Request(uri,headers=headers)
    try:
        with _OPENER.open(req,timeout=12) as response:
            blob=response.read(256*1024+1)
            if len(blob)>256*1024:raise LiveToolError('Search response is too large.')
    except error.HTTPError as exc:
        if direct_result:
            return direct_result+'\nPublic search fallback returned HTTP '+str(exc.code)+'; no additional prices were verified.'
        if exc.code==403 and s['provider']=='searxng':raise LiveToolError('SearXNG JSON format is disabled; enable JSON in its search formats.') from exc
        if s['provider']=='bing':raise LiveToolError(f'Built-in public search returned HTTP {exc.code}. The public service may be restricting automated requests; try again later.') from exc
        raise LiveToolError(f'Search provider returned HTTP {exc.code}. Check its configuration or API allowance.') from exc
    except (error.URLError,TimeoutError,ConnectionError) as exc:
        if direct_result:
            return direct_result+'\nPublic search fallback could not be reached; no additional prices were verified.'
        if s['provider']=='bing':raise LiveToolError('Built-in Web Search could not reach the internet. Check this PC’s internet connection, DNS or firewall. No API key is required.') from exc
        raise LiveToolError('Cannot reach the search provider. Check internet or local SearXNG service.') from exc
    if s['provider']=='bing':
        try:results=_rss_results(blob)
        except LiveToolError:
            if direct_result:return direct_result+'\nPublic search fallback returned no usable listings.'
            raise
        source='public Bing RSS (no API key)'
    else:
        try: payload=json.loads(blob)
        except (ValueError,UnicodeDecodeError) as exc:raise LiveToolError('Search provider returned invalid JSON.') from exc
        if not isinstance(payload,dict):raise LiveToolError('Search response was invalid.')
        results=payload.get('web',{}).get('results',[]) if s['provider']=='brave' else payload.get('results',[])
        if not isinstance(results,list):raise LiveToolError('Search returned no valid result list.')
        source='Brave Search API' if s['provider']=='brave' else 'local SearXNG'
    if progress:progress('web_search_results',message=f'Search provider returned {len(results)} listings. Checking which ones match your question.')
    try:
        return research(q,results,progress=progress)
    except ResearchError as exc:
        if direct_result and ('unrelated' in str(exc) or 'invalid' in str(exc)):
            return direct_result+'\nPublic search fallback was unrelated to this retailer; its results were discarded.'
        if s['provider']!='bing' or 'unrelated' not in str(exc):
            raise LiveToolError(str(exc)) from exc
        # The key-free public feed sometimes responds with unrelated dictionary
        # entries. Try one simplified query, but never pass those wrong pages
        # to Ollama as product evidence.
        retry_q=re.sub(r'\b(?:UK|prices|buy|model|retailers|price)\b',' ',q,flags=re.I)
        retry_q=' '.join(retry_q.split())[:220]
        if not retry_q or retry_q.lower()==q.lower():raise LiveToolError(str(exc)) from exc
        if progress:progress('web_retry',message=f'The first search was unrelated. Trying a shorter query: {retry_q}')
        uri='https://www.bing.com/search?'+parse.urlencode({'q':retry_q,'format':'rss','setlang':'en-GB'})
        try:
            with _OPENER.open(request.Request(uri,headers=headers),timeout=12) as response:
                blob=response.read(256*1024+1)
                if len(blob)>256*1024:raise LiveToolError('Search response is too large.')
            retry_results=_rss_results(blob)
            return research(q,retry_results,progress=progress)
        except (error.HTTPError,error.URLError,TimeoutError,ConnectionError) as fetch_exc:
            if direct_result:return direct_result+'\nPublic search fallback was unavailable; no additional prices were verified.'
            raise LiveToolError('Both public search attempts failed. The free search feed may be unavailable. Try again later; no prices were invented.') from fetch_exc
        except ResearchError as retry_exc:
            if direct_result:return direct_result+'\nBoth public searches returned unrelated results, which were discarded. No additional prices verified.'
            raise LiveToolError(f'Both searches returned unrelated results for {q!r}. No products or prices were invented. Try an exact retailer or model name.') from retry_exc


def _import_pyodbc():
    try:import pyodbc
    except ImportError as exc:raise LiveToolError('SQL support is not installed. Double-click INSTALL SQL SUPPORT.bat, then restart Studio.') from exc
    return pyodbc


def sql_connection():
    s=_snapshot()
    if not s['sql_server'] or not s['sql_database']:
        raise LiveToolError('SQL Server is not configured. Open Connections → SQL Server.')
    if s['sql_auth']=='sql' and not (s['sql_user'] and s['sql_password']):
        raise LiveToolError('Enter the SQL read-only account and password in Connections.')
    pyodbc=_import_pyodbc()
    args=[f'DRIVER={{{s["sql_driver"]}}}',f'SERVER={s["sql_server"]}',f'DATABASE={s["sql_database"]}',
          'Encrypt=yes',f'TrustServerCertificate={"yes" if s["sql_trust_cert"] else "no"}',
          'ApplicationIntent=ReadOnly','APP=AgentStudioReadOnly','Connection Timeout=6']
    if s['sql_auth']=='windows':args.append('Trusted_Connection=yes')
    else:args.extend([f'UID={s["sql_user"]}',f'PWD={s["sql_password"]}'])
    try:return pyodbc.connect(';'.join(args),timeout=6,autocommit=False)
    except pyodbc.Error as exc:raise LiveToolError('SQL Server connection failed. Check server, driver, login permissions and TLS settings. '+str(exc)[:250]) from exc


def list_tables():
    conn=sql_connection()
    try:
        cursor=conn.cursor()
        cursor.timeout=8
        rows=cursor.execute("SELECT TABLE_SCHEMA,TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA,TABLE_NAME").fetchall()
        return [f'{schema}.{table}' for schema,table in rows if IDENT.fullmatch(schema) and IDENT.fullmatch(table)][:150]
    finally:
        try:conn.rollback()
        finally:conn.close()


def columns_for(table, cursor=None):
    if not isinstance(table,str) or table.count('.')!=1:raise LiveToolError('Choose a table from the list first (schema.table).')
    schema,name=table.split('.')
    if not IDENT.fullmatch(schema) or not IDENT.fullmatch(name):raise LiveToolError('Invalid table name.')
    if cursor is not None:
        rows=cursor.execute('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION',(schema,name)).fetchall()
        return [row[0] for row in rows if isinstance(row[0],str) and IDENT.fullmatch(row[0])][:200]
    conn=sql_connection()
    try:
        c=conn.cursor();c.timeout=8
        return columns_for(table,c)
    finally:
        try:conn.rollback()
        finally:conn.close()


def sql_readonly(table, limit=10, filter_column='', filter_value=''):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=LIMIT:raise LiveToolError('Choose 1–20 rows.')
    if not isinstance(filter_column,str) or not isinstance(filter_value,str) or len(filter_value)>1000:raise LiveToolError('Filter must be text up to 1,000 characters.')
    if filter_value and not filter_column:raise LiveToolError('Choose a filter column before entering a value.')
    conn=sql_connection()
    try:
        c=conn.cursor();c.timeout=8
        available=columns_for(table,c)
        if not available:raise LiveToolError('That table is not available to this login. Refresh the table list.')
        if filter_column and filter_column not in available:raise LiveToolError('Choose a valid filter column from this table.')
        schema,name=table.split('.')
        sql=f'SELECT TOP (?) '+','.join(f'[{column}]' for column in available[:30])+f' FROM [{schema}].[{name}]'
        args=[limit]
        if filter_column and filter_value:
            sql+=f' WHERE [{filter_column}]=?';args.append(filter_value)
        rows=c.execute(sql,tuple(args)).fetchall()
        formatted=[]
        for row in rows:
            record={}
            for key,value in zip(available[:30],row):
                if isinstance(value,(datetime.date,datetime.datetime,datetime.time,decimal.Decimal)):
                    v=str(value)
                elif isinstance(value,bytes):v=f'<binary data: {len(value)} bytes>'
                elif value is None or isinstance(value,(str,int,float,bool)):v=value
                else:v=str(value)
                if isinstance(v,str):v=v[:600]
                record[key]=v
            formatted.append(record)
        return (f'SQL Server SELECT only — {table} — rows returned: {len(formatted)} (max {limit})\n'+json.dumps(formatted,ensure_ascii=False,default=str,indent=2))[:16000]
    finally:
        try:conn.rollback()
        finally:conn.close()


LIVE_SPECS=[
 {'id':'live:web_search','name':'Live Web Search','description':'For recognised retailer requests, open official catalogue pages first; otherwise search the web, follow relevant same-site links and extract identifiable product offers. No API key needed by default; respects robots.txt.','source':'live','kind':'live','category':'Live information','readOnly':True,
  'inputSchema':{'type':'object','properties':{'query':{'type':'string','description':'Web search query'}},'required':['query']}},
 {'id':'live:sql_readonly','name':'Read-Only SQL Server','description':'Read up to 20 rows from an authorised SQL Server table. Choose a table; optional exact-match filter. Cannot run raw SQL.','source':'live','kind':'live','category':'Live information','readOnly':True,
  'inputSchema':{'type':'object','properties':{'table':{'type':'string','description':'Schema and table from database picker'},'limit':{'type':'integer'},'filter_column':{'type':'string'},'filter_value':{'type':'string'}},'required':['table']}}
]


def run_live(tool_id,arguments,progress=None):
    if not isinstance(arguments,dict):raise LiveToolError('Invalid live tool arguments.')
    if tool_id=='live:web_search':return web_search(arguments.get('query',''),progress=progress)
    if tool_id=='live:sql_readonly':return sql_readonly(arguments.get('table',''),arguments.get('limit',10),arguments.get('filter_column',''),arguments.get('filter_value',''))
    raise LiveToolError('Unknown live tool.')
