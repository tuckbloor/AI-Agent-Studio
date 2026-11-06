"""Bounded, key-free public web-page research for Agent Studio.

Search discovery remains in live_tools. This module verifies relevance, reads public
HTML (not JS-rendered pages), and follows closely related SAME-SITE anchor links.
No login, cookies, CAPTCHA bypass, arbitrary schemes, private IPs or open redirects.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from urllib import parse, robotparser

USER_AGENT = 'AgentStudioResearchBot/2.2 (+local self-hosted research; respects robots.txt)'
MAX_HTML = 450_000
MAX_ROBOTS = 70_000
MAX_PAGES = 12
MAX_DEPTH = 2
HOST_LIMIT = 12
MAX_ANCHORS = 6
STOPWORDS = {
    'the','a','an','and','or','for','to','is','are','what','how','can','i','me',
    'find','check','search','give','show','get','please','from','at','with','on',
    'this','that','best','lowest','cheapest','price','prices','buy','shop','shops',
    'online','today','current','latest','all','of','in','uk','gb','site','website',
    'compare','deal','deals','£','retailer','retailers','store','product','products'
}
NOISE_PATH = re.compile(r'/(?:login|sign-?in|account|cart|checkout|basket|privacy|terms|cookie|contact|wishlist|search)(?:/|$)', re.I)
PRICE = re.compile(r'£\s*(\d{1,5}(?:,\d{3})*(?:\.\d{1,2})?)')
ROBOT_CACHE = {}
ROBOT_LOCK = threading.RLock()

class ResearchError(ValueError):
    pass


# Grounded entry points for retailers whose public category URLs are verified.
# These are navigation suggestions, NOT claims that products or prices were read.
_BENSONS = 'https://www.bensonsforbeds.co.uk'
_BENSONS_NAME = re.compile(r'\bbenso(?:n|ns)?(?:\s+for)?\s+beds?\b', re.I)

def direct_retailer_entries(query):
    """Seed discovery from the *official* retailer when the prompt identifies it.

    Explicit https domains also work, but are checked by validate_url and the
    same robots.txt / pinned public DNS policy as ordinary search results.
    The function intentionally does NOT guess arbitrary retailer domains.
    """
    if not isinstance(query, str):
        return []
    if _BENSONS_NAME.search(query) or 'bensonsforbeds.co.uk' in query.lower():
        urls=[]
        if re.search(r'\bsuper[\s-]+king\b',query,re.I):
            urls.append((_BENSONS+'/beds/super-king-beds/',
                         'Super King Beds | Bensons for Beds',
                         'Official Bensons for Beds super king beds category'))
        urls.extend([(_BENSONS+'/sitemap/','Bensons for Beds Site Map',
                      'Official shop navigation with bed sizes and categories'),
                     (_BENSONS+'/beds/','Beds | Bensons for Beds',
                      'Official Bensons bed catalogue')])
        return [{'url':url,'title':title,'description':desc} for url,title,desc in urls]
    # An explicitly provided public retailer domain can be followed without
    # making up its structure; do not manufacture /beds/ category URLs.
    match=re.search(r'https://[a-z0-9.-]+(?:/[a-z0-9_./%-]*)?',query,re.I)
    if match:
        candidate=match.group(0).rstrip('.,)')
        try:
            parsed=validate_url(candidate)
        except (ResearchError,ValueError):
            return []
        root=f'https://{parsed.hostname}/'
        return [{'url':candidate,'title':parsed.hostname+' official page',
                 'description':'The public website address supplied in the agent task'},
                {'url':root,'title':parsed.hostname+' home',
                 'description':'Official website navigation'}] if candidate != root else [
                 {'url':root,'title':parsed.hostname+' home',
                  'description':'Official website navigation'}]
    return []


def _normalise_retailer_words(text):
    # Preserve product descriptors, and make common retailer spelling variants
    # refer to the same site. Do not rewrite model numbers or price figures.
    return _BENSONS_NAME.sub('Bensons for Beds',str(text))


def _words(text):
    return [w.rstrip('s') if len(w)>3 and w.endswith('s') else w
            for w in re.findall(r'[a-z0-9]{2,}', str(text).lower())
            if w not in STOPWORDS and not w.isdigit()]


def _terms(query):
    words=_words(re.sub(r'site:[^\s]+', ' ', _normalise_retailer_words(query), flags=re.I))
    return list(dict.fromkeys(words))[:14]


def rank(query, title='', url='', text='', anchor=False):
    """Lexical relevance; never turn zero-match search results into page evidence."""
    terms=_terms(query)
    if not terms:return 0
    title_words=set(_words(title))
    host=parse.urlsplit(url).hostname or ''
    host_words=host.replace('bensonsforbeds','bensons for beds')
    url_words=set(_words(host_words) + _words(parse.unquote(parse.urlsplit(url).path).replace('-', ' ')))
    url_words.update(t for t in terms if len(t)>3 and t in host.lower())
    body_words=set(_words(text[:700]))
    weights=sum(4 for t in terms if t in title_words) + sum(3 for t in terms if t in url_words) + sum(1 for t in terms if t in body_words)
    distinct=sum(t in (title_words|url_words|body_words) for t in terms)
    if distinct == 0:return 0
    # For a multi-topic request require more than one overlapping term, unless
    # the retailer/domain itself matches the unique named brand.
    if len(terms)>=2 and distinct==1:return 0
    if NOISE_PATH.search(parse.urlsplit(url).path):return 0
    if anchor and ('/products/' in url or '/product/' in url or '/beds/' in url):weights+=3
    if 'super king' in query.lower() and ('super king' in (title+' '+text).lower() or 'super-king' in url.lower()):weights+=12
    return weights


def validate_url(url):
    """Reject internal targets BEFORE DNS and again after DNS resolution."""
    if not isinstance(url,str) or len(url)>1200 or any(ord(c)<32 for c in url):
        raise ResearchError('Unsafe or oversized website address.')
    u=parse.urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):
        raise ResearchError('Only ordinary public HTTPS website pages can be researched.')
    host=u.hostname.rstrip('.').lower()
    if host=='localhost' or host.endswith(('.local','.internal','.localhost','.test','.invalid')) or '.' not in host:
        raise ResearchError('Internal/local website addresses cannot be opened by Web Research.')
    try:
        ip=ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        pass
    else:
        if not ip.is_global:raise ResearchError('Private or special-use IP addresses cannot be opened.')
    return u


def _resolve_public(host):
    try:answers=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError as exc:raise ResearchError('Cannot resolve this public website.') from exc
    addresses=list(dict.fromkeys(item[4][0] for item in answers))
    if not addresses:raise ResearchError('Website does not resolve.')
    # Refuse mixed public/private results to avoid DNS-rebinding tricks.
    if any(not ipaddress.ip_address(addr).is_global for addr in addresses):
        raise ResearchError('Website resolves to a private or reserved address; access refused.')
    return addresses[0]


def _fetch_public_bytes(url, *, size=MAX_HTML, timeout=5):
    """HTTPS GET with DNS-pinned public IP, validated TLS hostname, no redirects."""
    u=validate_url(url)
    host=u.hostname
    ip=_resolve_public(host)
    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            self.sock=socket.create_connection((ip,443),timeout=self.timeout)
            self.sock=self._context.wrap_socket(self.sock,server_hostname=host)
    conn=PinnedHTTPS(host,443,timeout=timeout,context=ssl.create_default_context())
    path=parse.urlunsplit(('', '', u.path or '/',u.query,''))
    try:
        conn.request('GET',path,headers={'User-Agent':USER_AGENT,'Accept':'text/html,application/xhtml+xml,text/plain;q=0.4',
                                         'Accept-Encoding':'identity','Host':host})
        resp=conn.getresponse()
        if 300 <= resp.status < 400:
            raise ResearchError('Website redirects this page; automatic redirects are disabled for safety.')
        if resp.status!=200:
            return resp.status, resp.getheader('Content-Type',''),b''
        length=resp.getheader('Content-Length')
        if length and length.isdecimal() and int(length)>size:
            raise ResearchError('Website page is too large to analyse safely.')
        raw=resp.read(size+1)
        if len(raw)>size:raise ResearchError('Website page exceeded its safe download limit.')
        return resp.status,resp.getheader('Content-Type',''),raw
    except (OSError,TimeoutError,ssl.SSLError) as exc:
        raise ResearchError('Public website could not be opened (blocked, network error or timeout).') from exc
    finally:conn.close()


def _robots_allowed(url):
    u=validate_url(url)
    host=u.hostname
    with ROBOT_LOCK:
        cached=ROBOT_CACHE.get(host)
        if cached and time.monotonic()-cached[0]<(60 if cached[1] is False else 600):
            rp=cached[1]
            return rp is not False and rp.can_fetch(USER_AGENT,url)
    robots=f'https://{host}/robots.txt'
    try:
        code,_,blob=_fetch_public_bytes(robots,size=MAX_ROBOTS,timeout=3)
        if code in (401,403) or code>=500:
            allowed=False
        elif code==404 or 400<=code<500:
            rp=robotparser.RobotFileParser();rp.parse([]);allowed=rp
        elif code==200:
            rp=robotparser.RobotFileParser()
            rp.parse(blob.decode('utf-8','replace').splitlines())
            allowed=rp
        else:allowed=False
    except ResearchError:
        # Conservative: do not crawl a site whose crawling policy is unknown.
        allowed=False
    with ROBOT_LOCK:ROBOT_CACHE[host]=(time.monotonic(),allowed)
    return allowed is not False and allowed.can_fetch(USER_AGENT,url)


def _safe_price(value):
    if value is None:return None
    try:amount=Decimal(str(value).replace(',','').replace('£','').strip())
    except (InvalidOperation,ValueError):return None
    if not amount.is_finite() or not Decimal('0.01')<=amount<=Decimal('50000'):return None
    return f'£{amount:,.2f}'


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title='';self.heading='';self.description='';self.meta_prices={};self.anchors=[];self.text=[];self.ldjson=[]
        self._capture=None;self._buf=[];self._anchor=None;self._script=False;self._ignore=0
        self.price_tags=[];self._price_active=[]

    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag in ('style','script','noscript','svg'):
            if tag=='script' and d.get('type','').lower()=='application/ld+json':self._script=True;self._buf=[]
            else:self._ignore+=1
            return
        if self._ignore:return
        classes=' '.join((d.get('class') or '',d.get('id') or '',d.get('itemprop') or '')).lower()
        # Only explicit product-price DOM elements, not random page numbers.
        if tag in ('span','div','strong','p') and re.search(r'(?:^|[-_\s])(?:price|amount)(?:$|[-_\s])',classes):
            if not any(word in classes for word in ('was','old','regular','delivery','shipping','monthly','installment','save','discount','filter','range','per-')):
                self._price_active.append({'tag':tag,'parts':[]})
        if tag=='title':self._capture='title';self._buf=[]
        elif tag=='h1' and not self.heading:self._capture='h1';self._buf=[]
        elif tag=='a' and d.get('href'):
            self._anchor=d.get('href');self._capture='a';self._buf=[]
        elif tag=='meta':
            key=(d.get('property') or d.get('name') or d.get('itemprop') or '').lower()
            value=d.get('content') or ''
            if key in ('description','og:description'):self.description=value[:500]
            if key in ('product:price:amount','price','og:price:amount'):
                self.meta_prices['price']=value
            if key in ('product:price:currency','pricecurrency','og:price:currency'):
                self.meta_prices['currency']=value

    def handle_data(self,data):
        if self._script:self._buf.append(data);return
        if self._ignore:return
        if self._capture:self._buf.append(data)
        if data.strip():self.text.append(data.strip())
        for item in self._price_active:item['parts'].append(data)

    def handle_endtag(self,tag):
        if self._price_active and self._price_active[-1]['tag']==tag:
            entry=self._price_active.pop()
            match=PRICE.search(' '.join(entry['parts']))
            if match:
                value=_safe_price(match.group(1))
                if value:self.price_tags.append(value)
        if tag=='script' and self._script:
            self.ldjson.append(''.join(self._buf)[:60000]);self._script=False;self._buf=[];return
        if tag in ('style','script','noscript','svg'):
            if self._ignore:self._ignore-=1
            return
        if self._capture and tag in ('title','h1','a'):
            value=' '.join(''.join(self._buf).split())[:220]
            if tag=='title' and self._capture=='title':self.title=value
            if tag=='h1' and self._capture=='h1':self.heading=value
            if tag=='a' and self._capture=='a' and value:self.anchors.append((self._anchor,value))
            self._capture=None;self._buf=[];self._anchor=None


def _products_from_jsonld(raw,url):
    products=[]
    def walk(value,depth=0):
        if depth>9:return
        if isinstance(value,list):
            for x in value[:100]:walk(x,depth+1)
        elif isinstance(value,dict):
            kind=value.get('@type','')
            kinds=kind if isinstance(kind,list) else [kind]
            if any(isinstance(k,str) and k.lower().endswith('product') for k in kinds):
                name=str(value.get('name') or '')[:200]
                offers=value.get('offers') or []
                offers=offers if isinstance(offers,list) else [offers]
                for offer in offers[:20]:
                    if not isinstance(offer,dict):continue
                    currency=offer.get('priceCurrency','')
                    if not currency and isinstance(offer.get('priceSpecification'),dict):
                        currency=offer['priceSpecification'].get('priceCurrency','')
                    if str(currency).upper()!='GBP':continue
                    candidate=offer.get('price')
                    if candidate is None and isinstance(offer.get('priceSpecification'),dict):candidate=offer['priceSpecification'].get('price')
                    amount=_safe_price(candidate)
                    if not amount:continue
                    products.append({'name':name or '(unnamed product)','price':amount,
                                     'size':str(value.get('size') or '')[:90],
                                     'url':url,'basis':'Structured Product/Offer on the retailer page',
                                     'availability':str(offer.get('availability','')).split('/')[-1][:45]})
            if '@graph' in value:walk(value['@graph'],depth+1)
            if 'mainEntity' in value:walk(value['mainEntity'],depth+1)
    try:walk(json.loads(raw))
    except (ValueError,TypeError):return []
    return products[:12]


def parse_page(html_data,url):
    parser=PageParser()
    parser.feed(html_data.decode('utf-8','replace'))
    title=(parser.heading or parser.title or url)[:180]
    products=[]
    for raw in parser.ldjson[:12]:products.extend(_products_from_jsonld(raw,url))
    if not products and parser.meta_prices.get('price') and parser.meta_prices.get('currency','GBP').upper()=='GBP':
        amount=_safe_price(parser.meta_prices['price'])
        if amount:products=[{'name':title,'price':amount,'url':url,'basis':'Product price metadata on retailer page','availability':''}]
    # A product detail page may render a clearly labelled price without JSON-LD.
    # Do not attach prices from category pages or infer from arbitrary body text.
    if not products and re.search(r'/products?/',parse.urlsplit(url).path,re.I):
        possible=list(dict.fromkeys(parser.price_tags))
        if len(possible)==1:
            products=[{'name':title,'price':possible[0],'url':url,
                       'basis':'Single labelled product-price element on retailer page',
                       'availability':''}]
    # Don't present a random number in page text as a definitive product price.
    body=' '.join(parser.text)[:12000]
    return {'title':title,'url':url,'description':parser.description[:300],
            'anchors':parser.anchors[:300],'products':products,'text':body}


def _same_site(a,b):
    host_a=(parse.urlsplit(a).hostname or '').lower().removeprefix('www.')
    host_b=(parse.urlsplit(b).hostname or '').lower().removeprefix('www.')
    return host_a==host_b


def _relevant_anchors(page,query):
    found=[];seen=set()
    for href,label in page['anchors']:
        dest=parse.urljoin(page['url'],href)
        dest=parse.urldefrag(dest)[0]
        if dest in seen or not _same_site(page['url'],dest):continue
        try:validate_url(dest)
        except (ResearchError,ValueError):continue
        score=rank(query,label,dest,anchor=True)
        if score<=0:continue
        seen.add(dest);found.append((score,dest,label))
    return sorted(found,key=lambda x:x[0],reverse=True)[:MAX_ANCHORS]


def research(query,results,progress=None,fetch_page=None,robots=None, *, discovery="search"):

    """Return ranked sources and on-page offers, or an honest no-evidence error.

    fetch_page/robots are injectable for offline acceptance tests.
    """
    if not isinstance(results,list):raise ResearchError('Search provider returned an invalid results list.')
    emit=progress or (lambda kind, **data:None)
    ranked=[]
    for item in results[:16]:
        if not isinstance(item,dict):continue
        url=str(item.get('url',''))
        try:validate_url(url)
        except (ResearchError,ValueError):continue
        title=str(item.get('title') or '')[:220]
        summary=str(item.get('description') or item.get('content') or '')[:600]
        score=rank(query,title,url,summary)
        if score>0:ranked.append({'title':title,'url':url,'description':summary,'score':score})
    ranked.sort(key=lambda item:item['score'],reverse=True)
    if not ranked:
        raise ResearchError('Search results were unrelated to your request. No pages or prices were accepted. Try a specific retailer or product name; the public search feed may be returning poor results.')
    sources=ranked[:8]
    mode='official retailer pages' if discovery=='retailer' else 'relevant search listings'
    emit('web_results',count=len(sources),message=f'Found {len(sources)} {mode}; opening matching pages.')
    pages=[];visited=set();per_host=defaultdict(int);queue=[(item['url'],0,item['title']) for item in sources[:4]]
    fetch=fetch_page or _fetch_public_bytes
    robots_check=robots or _robots_allowed
    failures=[]
    while queue and len(visited)<MAX_PAGES:
        url,depth,anchor=queue.pop(0)
        if url in visited:continue
        visited.add(url)
        hostname=parse.urlsplit(url).hostname
        if per_host[hostname]>=HOST_LIMIT:continue
        per_host[hostname]+=1
        if not robots_check(url):
            failures.append(f'Crawler access not permitted for {hostname} (robots.txt unavailable or disallowed).')
            emit('web_skipped',message=f'Skipped {hostname}: site disallows crawling or robots.txt could not be checked.')
            continue
        emit('web_page_opening',url=url,message=f'Opening relevant page: {anchor[:90]}')
        try:
            code,ctype,content=fetch(url)
            if code!=200:raise ResearchError(f'Website returned HTTP {code}.')
            if 'text/html' not in ctype.lower() and 'application/xhtml+xml' not in ctype.lower():
                raise ResearchError('This link does not return readable HTML.')
            page=parse_page(content,url)
        except (ResearchError,ValueError,UnicodeError) as exc:
            failures.append(f'{hostname}: {str(exc)[:130]}')
            emit('web_skipped',message=f'Could not read {hostname}: {str(exc)[:150]}')
            continue
        page_score=rank(query,page['title'],url,page['description']+' '+page['text'][:500])
        if page_score==0:
            emit('web_skipped',message=f'Skipped unrelated page: {page["title"][:80]}')
            continue
        page['score']=page_score;pages.append(page)
        emit('web_page_read',url=url,prices=len(page['products']),message=f'Read {page["title"][:70]}; found {len(page["products"])} structured product price(s).')
        if depth<MAX_DEPTH:
            for score,dest,label in _relevant_anchors(page,query):
                if dest not in visited and all(x[0]!=dest for x in queue):
                    queue.append((dest,depth+1,label))
                    emit('web_link_selected',url=dest,message=f'Following matching link text: {label[:100]}')
    offers=[];seen=set();unverified_size=0
    requested_super_king=bool(re.search(r'\bsuper[\s-]+king\b',query,re.I))
    for page in pages:
        for product in page['products']:
            name_matches=set(_terms(query)) & set(_words(product['name']))
            domain=(parse.urlsplit(product['url']).hostname or '').lower()
            # Don't attach a Miele price to a Shark request merely because the
            # category URL mentions Shark; the PRODUCT name or retailer must match.
            if not name_matches:continue
            if requested_super_king and not re.search(r'\bsuper[\s-]+king\b',product['name']+' '+str(product.get('size') or ''),re.I):
                # A product on a super-king category page may show the default
                # single/double price. Never call it a super-king price.
                unverified_size+=1
                continue
            if len(_terms(query))>1 and len(name_matches)<2:
                if not any(t in domain for t in _terms(query) if len(t)>3 and t not in name_matches):continue
            key=(product['name'].lower(),product['price'],product['url'])
            if key not in seen:offers.append(product);seen.add(key)
    offers=offers[:16]
    emit('web_research_complete',pages=len(pages),offers=len(offers),message=f'Checked {len(pages)} relevant pages and found {len(offers)} on-page GBP offer(s).')
    origin=('official retailer category and navigation pages (live access checked)' if discovery=='retailer'
            else 'ranked public search listings + readable retailer pages')
    lines=[f'Live web research: {query}', 'Source: '+origin,
           f'Matches: {len(sources)}',f'Pages examined: {len(pages)}',f'On-page GBP offers: {len(offers)}']
    if offers:
        lines.append('ON-PAGE PRODUCT PRICE EVIDENCE:')
        for i,product in enumerate(offers,1):
            lines.extend([f'PRODUCT {i}: {product["name"]}',f'PRICE: {product["price"]}',
                          f'PRODUCT URL: {product["url"]}',f'PRICE EVIDENCE: {product["basis"]}',
                          f'AVAILABILITY: {product["availability"] or "Not confirmed"}'])
    else:
        lines.append('NO VERIFIED PRODUCT PAGE PRICES: Relevant links may exist, but pages were unreadable, disallowed, JS-only or had no GBP Product/Offer metadata. DO NOT invent a price or cheapest retailer.')
    if requested_super_king:
        lines.append('SIZE CHECK: Only offers explicitly identifying SUPER KING in the product name or structured size are counted as verified-size prices.')
        if unverified_size:
            lines.append(f'EXCLUDED {unverified_size} product price(s) where the super-king size was not confirmed; these may refer to a smaller default option.')
    lines.append(('RELEVANT OFFICIAL RETAILER LINKS (not verified prices):' if discovery=='retailer'
                  else 'RELEVANT SEARCH LINKS (not verified prices):'))
    for i,item in enumerate(sources[:8],1):
        lines.extend([f'{i}. {item["title"]}',f'URL: {item["url"]}',f'Snippet: {item["description"]}'])
    lines.append('Price evidence is from publicly readable page metadata, not an independently verified checkout price. Check size, model, stock, delivery and date before comparing. Different models must not be ranked as identical products.')
    if failures:
        lines.append('Pages skipped: '+'; '.join(dict.fromkeys(failures))[:900])
    return '\n'.join(lines)[:22_000]
