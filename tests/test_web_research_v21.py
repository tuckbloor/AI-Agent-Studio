"""Offline acceptance tests for actual Bensons-style navigation and anti-hallucination safeguards."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from studio_integration.web_research import (rank,research,parse_page,validate_url,
                                              _safe_price,ResearchError)
from studio_integration.agent_designer import shopping_search_query
from studio_integration import core,live_tools

CAT='https://www.bensonsforbeds.co.uk/beds/'
P1='https://www.bensonsforbeds.co.uk/products/silvia-bed-frame/'
P2='https://www.bensonsforbeds.co.uk/products/bergamo-usb-bed/'

CATEGORY=b'''<html><head><title>Beds and Bed Frames | Bensons for Beds</title></head>
<body><h1>Bensons for Beds: Beds and Frames</h1><a href="/products/silvia-bed-frame/">Silvia bed frame - double</a>
<a href="/products/bergamo-usb-bed/">Bergamo USB bed frame - single</a><a href="/login">Account</a></body></html>'''

def product(name,amount):
    data={'@context':'https://schema.org','@type':'Product','name':name,
          'offers':{'@type':'Offer','price':amount,'priceCurrency':'GBP','availability':'https://schema.org/InStock'}}
    return ('<html><head><title>'+name+'</title><script type="application/ld+json">'+json.dumps(data)+'</script></head>'
           '<body><h1>'+name+'</h1><p>Available in different sizes</p></body></html>').encode()

FIXTURES={CAT:CATEGORY,P1:product('Silvia Bed Frame Double','199.99'),P2:product('Bergamo Bed Frame Single','149.99')}


def fetched(url):
    return 200,'text/html; charset=utf-8',FIXTURES[url]


def test_shopping_query_preserves_retailer_and_item():
    query=shopping_search_query('Find me the best price of all beds at Benson for Beds Online Shop')
    assert 'Bensons for Beds' in query and 'beds' in query and 'UK prices' in query
    assert 'Shark vacuum cleaner' in shopping_search_query('Find the best price for a Shark vacuum cleaner in the UK')


def test_irrelevant_results_rejected_without_crawling():
    query='Benson for Beds beds UK prices buy'
    results=[{'title':'Getting - meaning and definition','url':'https://dictionary.example.org/getting/',
              'description':'Getting means acquiring something.'}]
    with pytest.raises(ResearchError, match='unrelated'):
        research(query,results,fetch_page=lambda _:pytest.fail('must not crawl irrelevant result'),robots=lambda _:True)


def test_crawls_relevant_anchor_text_and_distinct_product_prices():
    q='Benson for Beds beds UK prices buy'
    events=[]
    result=research(q,[{'title':'Bensons for Beds | Beds','url':CAT,
                         'description':'Browse beds at Bensons for Beds'}],
                    fetch_page=fetched,robots=lambda _:True,
                    progress=lambda typ,**kw:events.append((typ,kw)))
    assert 'On-page GBP offers: 2' in result
    assert 'Silvia Bed Frame Double' in result and 'PRICE: £199.99' in result
    assert 'Bergamo Bed Frame Single' in result and 'PRICE: £149.99' in result
    assert f'PRODUCT URL: {P1}' in result and f'PRODUCT URL: {P2}' in result
    assert len([e for e in events if e[0]=='web_link_selected'])==2
    assert len([e for e in events if e[0]=='web_page_read'])==3


def test_visible_unrelated_page_numbers_are_not_verified_prices():
    page=parse_page('<html><h1>Great Shark vacuums</h1><p>Someone paid £999 somewhere. £49 delivery.</p></html>'.encode('utf-8'),
                    'https://example.co.uk/vacuums')
    assert not page['products']


def test_structured_offer_requires_gbp_not_usd():
    page=parse_page(product('Shark Vacuum', '199.99').replace(b'GBP',b'USD'),'https://example.co.uk/item')
    assert page['products']==[]


@pytest.mark.parametrize('url',[
    'http://example.com/','https://127.0.0.1/','https://192.168.0.1/',
    'https://localhost/admin','file:///etc/passwd', 'https://example.com:8443/',
    'https://user:pass@example.com/','https://internal.local/', 'https://10.0.0.12/'
])
def test_rejects_nonpublic_addresses(url):
    with pytest.raises((ResearchError,ValueError)):validate_url(url)


def test_public_domain_is_allowed():
    assert validate_url('https://www.bensonsforbeds.co.uk/products/bed/').hostname=='www.bensonsforbeds.co.uk'


def test_robots_block_is_respected():
    result=research('Shark vacuum cleaner UK prices buy',[
        {'title':'Shark vacuum cleaner','url':'https://example.org/shark/','description':'Shark vacuum cleaner'}],
        fetch_page=lambda _:pytest.fail('robots disallow this'),robots=lambda _:False)
    assert 'Pages examined: 0' in result and 'NO VERIFIED PRODUCT PAGE PRICES' in result


def test_live_tool_plumbs_research_evidence_and_no_key(monkeypatch):
    sample=b'<rss><channel><item><title>Bensons for Beds | Beds</title><link>'+CAT.encode()+b'</link><description>Browse beds</description></item></channel></rss>'
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return sample
    monkeypatch.setattr(live_tools._OPENER,'open',lambda req,timeout:Reply())
    from studio_integration import web_research
    monkeypatch.setattr(web_research,'_fetch_public_bytes',lambda url,**kwargs:fetched(url))
    monkeypatch.setattr(web_research,'_robots_allowed',lambda url:True)
    monkeypatch.setitem(live_tools.SETTINGS,'provider','bing')
    monkeypatch.setattr(live_tools,'direct_retailer_entries',lambda q: [])
    result=live_tools.web_search('Benson for Beds beds UK prices buy')
    assert 'On-page GBP offers: 2' in result
    assert 'PRICE: £199.99' in result


def test_workflow_emits_research_progress_before_tool_completed(monkeypatch):
    events=[]
    def fake_live(tool_id,args,progress=None):
        assert tool_id=='live:web_search'
        progress('web_results',message='Two relevant links found')
        progress('web_page_read',message='Read product page',prices=1)
        return 'Live web research: shark vacuums\nMatches: 1\nPages examined: 1\nOn-page GBP offers: 1\nPRODUCT 1: Shark Model ABC\nPRICE: £199.99\nPRODUCT URL: https://example.co.uk/shark\n'
    monkeypatch.setattr(core,'run_live',fake_live)
    workflow={'description':'','steps':[
      {'type':'trigger','config':{'event':'manual'}},
      {'type':'mcp','config':{'tools':['live:web_search'],'toolArgs':{'live:web_search':{'query':'Shark vacuum UK price'}}}},
      {'type':'output','config':{'format':'text'}}]}
    events=list(core.run_events(workflow,'Find best price of Shark vacuum cleaner',models=[]))
    kinds=[item['type'] for item in events]
    assert kinds.count('tool_detail')>=3
    assert kinds.index('tool_detail')<kinds.index('tool_completed')
    completed=next(item for item in events if item['type']=='tool_completed')
    assert completed['evidence']['pages_read']==1
    assert completed['evidence']['price_mentions']==1


def test_bad_public_search_retries_one_simpler_query(monkeypatch):
    bad=b'<rss><channel><item><title>Getting definition</title><link>https://example.org/getting/</link><description>Getting is a verb</description></item></channel></rss>'
    good=b'<rss><channel><item><title>Bensons for Beds | Beds</title><link>'+CAT.encode()+b'</link><description>Browse beds</description></item></channel></rss>'
    calls=[]
    class Reply:
        def __init__(self,body):self.body=body
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return self.body
    def open_fake(req,timeout):
        calls.append(req.full_url)
        return Reply(bad if len(calls)==1 else good)
    monkeypatch.setattr(live_tools._OPENER,'open',open_fake)
    from studio_integration import web_research
    monkeypatch.setattr(web_research,'_fetch_public_bytes',lambda url,**kw:fetched(url))
    monkeypatch.setattr(web_research,'_robots_allowed',lambda url:True)
    monkeypatch.setitem(live_tools.SETTINGS,'provider','bing')
    monkeypatch.setattr(live_tools,'direct_retailer_entries',lambda q: [])
    stages=[]
    output=live_tools.web_search('Benson for Beds beds UK prices buy',progress=lambda typ,**kw:stages.append(typ))
    assert len(calls)==2
    assert 'web_retry' in stages
    assert 'PRICE: £199.99' in output


def test_single_labelled_price_on_product_detail_page():
    markup='<h1>Shark Stratos Vacuum</h1><span class="product-price">£249.99</span><p>Delivery £49</p>'
    parsed=parse_page(markup.encode('utf-8'),'https://retailer.co.uk/products/shark-stratos')
    assert len(parsed['products'])==1 and parsed['products'][0]['price']=='£249.99'


def test_multiple_price_markups_are_not_assigned_to_single_product():
    markup='<h1>Shop Shark Vacuums</h1><div class="price">£199</div><div class="price">£299</div>'
    parsed=parse_page(markup.encode(),'https://retailer.co.uk/products/shark-vacuum')
    assert not parsed['products']


def test_unrelated_structured_product_does_not_count_as_offer():
    unrelated=product('Miele Cat and Dog Vacuum', '149.99')
    result=research('Shark vacuum cleaner UK prices buy',[
        {'title':'Shark vacuum cleaners online','url':'https://example.co.uk/shark-vacuums',
         'description':'Shark vacuum cleaner shopping options'}],
        fetch_page=lambda url:(200,'text/html',unrelated),robots=lambda url:True)
    assert 'On-page GBP offers: 0' in result
