"""Small loopback-only MCP Streamable HTTP client for Studio preview.

Handles JSON and request-scoped SSE replies; no redirects or remote-network access.
Not a general-purpose MCP SDK (no elicitation/sampling/stdio transports).
"""
import json
import re
from urllib import parse, request, error

MAX_RESPONSE=1_048_576

class MCPError(Exception):
    pass

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MCPError('MCP redirects are not allowed. Use the direct local /mcp URL.')

_OPENER=request.build_opener(NoRedirect())


def validate_url(url):
    if not isinstance(url,str) or len(url)>220:
        raise MCPError('Enter a local MCP URL, such as http://127.0.0.1:8501/mcp.')
    u=parse.urlsplit(url)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or u.username or u.password or u.query or u.fragment or u.path.rstrip('/')!='/mcp':
        raise MCPError('For this preview, MCP connections must use http://127.0.0.1:PORT/mcp (localhost only).')
    try:port=u.port
    except ValueError:raise MCPError('Invalid MCP port.') from None
    if port is None or port<1 or port>65535:
        raise MCPError('Specify the MCP server port in its URL.')
    return f'http://127.0.0.1:{port}/mcp'


def _parse_result(body, content_type):
    if len(body)>MAX_RESPONSE: raise MCPError('MCP response exceeds 1 MB.')
    try:
        if 'text/event-stream' in content_type:
            items=[]; parts=[]
            for line in body.decode('utf-8').splitlines():
                if line.startswith('data:'):
                    parts.append(line[5:].strip())
                elif not line.strip() and parts:
                    items.append(json.loads('\n'.join(parts)));parts=[]
            if parts:items.append(json.loads('\n'.join(parts)))
            for item in reversed(items):
                if isinstance(item,dict) and ('result' in item or 'error' in item):return item
            raise MCPError('MCP did not return a JSON-RPC result in its stream.')
        return json.loads(body)
    except (ValueError,UnicodeDecodeError) as exc: raise MCPError('MCP returned invalid JSON or SSE.') from exc


class LocalMCPClient:
    def __init__(self,url,token=''):
        self.url=validate_url(url)
        if not isinstance(token,str) or len(token)>4096 or '\n' in token or '\r' in token:
            raise MCPError('Invalid bearer token.')
        self.token=token
        self.session=None
        self.version='2025-06-18'
        self.number=0
        self.connected=False

    def _post(self,method,params=None,notification=False):
        self.number+=1
        message={'jsonrpc':'2.0','method':method}
        if not notification:
            message['id']=self.number
        if params is not None:
            message['params']=params
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream',
                 'MCP-Protocol-Version':self.version}
        if self.session:headers['Mcp-Session-Id']=self.session
        if self.token:headers['Authorization']='Bearer '+self.token
        req=request.Request(self.url, data=json.dumps(message).encode('utf-8'),headers=headers, method='POST')
        try:
            with _OPENER.open(req,timeout=12) as response:
                content=response.read(MAX_RESPONSE+1)
                session=response.headers.get('Mcp-Session-Id')
                if session and len(session)<512 and all('!'<=c<='~' for c in session):self.session=session
                if notification and response.status in (200,202,204):return {}
                result=_parse_result(content,response.headers.get('Content-Type',''))
        except error.HTTPError as exc:
            detail=exc.read(1024).decode('utf-8','replace')
            raise MCPError(f'MCP server returned HTTP {exc.code}: {detail[:180]}') from exc
        except error.URLError as exc:
            raise MCPError('Cannot contact the local MCP endpoint. Start AI App Server and check /mcp is enabled.') from exc
        except TimeoutError as exc:
            raise MCPError('The MCP server took too long to respond.') from exc
        if not isinstance(result,dict) or result.get('jsonrpc')!='2.0':
            raise MCPError('The endpoint did not return a valid MCP JSON-RPC message.')
        if result.get('error'):
            issue=result['error'];raise MCPError(str(issue.get('message','MCP error') if isinstance(issue,dict) else issue)[:300])
        return result.get('result',{})

    def connect(self):
        result=self._post('initialize',{'protocolVersion':self.version,'capabilities':{},'clientInfo':{'name':'agent-studio-preview','version':'0.5.0'}})
        if not isinstance(result,dict) or not isinstance(result.get('capabilities'),dict):
            raise MCPError('The endpoint did not complete the MCP initialization handshake.')
        remote_version=result.get('protocolVersion')
        if isinstance(remote_version,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',remote_version):self.version=remote_version
        self._post('notifications/initialized',notification=True)
        self.connected=True
        return result

    def list_tools(self):
        if not self.connected:self.connect()
        tools=[];cursor=None
        for _ in range(5):
            params={'cursor':cursor} if cursor else {}
            result=self._post('tools/list',params)
            if not isinstance(result,dict) or not isinstance(result.get('tools'),list):
                raise MCPError('MCP returned an invalid tools list.')
            for tool in result['tools']:
                if isinstance(tool,dict) and isinstance(tool.get('name'),str) and 0<len(tool['name'])<150:
                    schema=tool.get('inputSchema')
                    tools.append({'id':'remote:'+tool['name'],'name':tool['name'],'description':str(tool.get('description',''))[:300],
                     'category':'MCP server','kind':'remote','source':'remote',
                     'readOnly':tool.get('annotations',{}).get('readOnlyHint') is True if isinstance(tool.get('annotations'),dict) else False,
                     'inputSchema':schema if isinstance(schema,dict) else {'type':'object','properties':{}}})
            cursor=result.get('nextCursor')
            if not cursor or len(tools)>=100:break
        return tools[:100]

    def call_tool(self,name,arguments):
        if not self.connected:self.connect()
        result=self._post('tools/call',{'name':name,'arguments':arguments})
        if not isinstance(result,dict):raise MCPError('MCP tool returned invalid result.')
        if result.get('isError'):
            raise MCPError('MCP tool failed: '+_content_text(result.get('content',[]))[:260])
        return _content_text(result.get('content',[]))[:30000]


def _content_text(content):
    if not isinstance(content,list):return str(content)[:30000]
    return '\n'.join(x.get('text','') for x in content if isinstance(x,dict) and x.get('type')=='text' and isinstance(x.get('text'),str))[:30000] or '(MCP tool returned no text.)'


def build_arguments(schema, text, overrides=None):
    """Fill simple free-text tool inputs, reject unknown required non-text fields."""
    if overrides is not None and not isinstance(overrides,dict):raise MCPError('Tool arguments must be a JSON object.')
    result={}
    properties=schema.get('properties',{}) if isinstance(schema,dict) else {}
    required=schema.get('required',[]) if isinstance(schema,dict) else []
    if not isinstance(properties,dict):properties={}
    if not isinstance(required,list):required=[]
    for k,val in (overrides or {}).items():
        if k not in properties:raise MCPError(f'Unknown field {k!r} for the MCP tool.')
        if isinstance(val,str):val=val.replace('{{input}}',text[:8000])
        result[k]=val
    for key in required:
        if key in result:continue
        spec=properties.get(key,{})
        if key in ('text','input','query','prompt','message','content') and isinstance(spec,dict) and spec.get('type')=='string':
            result[key]=text[:8000]
        else:
            raise MCPError(f'MCP tool requires {key!r}. Open the Tool hub and enter its JSON arguments.')
    return result
