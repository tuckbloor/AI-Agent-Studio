"""Retailer-first regression tests for the customer's failing Bensons request."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from studio_integration import live_tools,web_research
from studio_integration.web_research import direct_retailer_entries, research, parse_page
from studio_integration.agent_designer import shopping_search_query

Q='search benso beds super king beds UK prices buy'
CAT='https://www.bensonsforbeds.co.uk/beds/super-king-beds/'
PROD1='https://www.bensonsforbeds.co.uk/products/staples-super-king-bed/'
PROD2='https://www.bensonsforbeds.co.uk/products/snooze-super-king-bed/'
SITEMAP='https://www.bensonsforbeds.co.uk/sitemap/'
BEDS='https://www.bensonsforbeds.co.uk/beds/'

CAT_HTML=b'''<html><head><title>Super King Beds | Bensons for Beds</title></head><body><h1>Super King Beds</h1>
<a href="/products/staples-super-king-bed/">Staples super king ottoman bed</a>
<a href="/products/snooze-super-king-bed/">Snooze super king bed frame</a>
<a href="/contact">Contact customer service</a></body></html>'''

def product(name,price):
    d={'@type':'Product','name':name,'offers':{'@type':'Offer','price':price,'priceCurrency':'GBP'}}
    return ('<html><head><title>'+name+'</title><script type="application/ld+json">'+json.dumps(d)+'</script></head><body><h1>'+name+'</h1></body></html>').encode()

HTML={CAT:CAT_HTML,PROD1:product('Staples Super King Ottoman Bed','699.99'),PROD2:product('Snooze Super King Bed Frame','799.99'),SITEMAP:b'<h1>Bensons for Beds Sitemap</h1><a href="/beds/super-king-beds/">Super King Beds</a>',BEDS:b'<h1>Bensons for Beds</h1><a href="/beds/super-king-beds/">Super King Beds</a>'}

def fake_fetch(url,**kw):return (200,'text/html',HTML[url])

def test_benso_typo_seeds_real_official_category_first():
    candidates=direct_retailer_entries(Q)
    assert candidates[0]['url']==CAT
    assert candidates[1]['url']==SITEMAP
    assert all('bensonsforbeds.co.uk' in c['url'] for c in candidates)


def test_retailer_first_runs_without_search_provider(monkeypatch):
    from studio_integration import web_research as wr
    monkeypatch.setattr(wr,'_fetch_public_bytes',fake_fetch)
    monkeypatch.setattr(wr,'_robots_allowed',lambda url:True)
    monkeypatch.setattr(live_tools._OPENER,'open',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('RSS must not run if direct retailer product pages worked')))
    monkeypatch.setitem(live_tools.SETTINGS,'provider','bing')
    event=[]
    result=live_tools.web_search(Q,progress=lambda kind,**kw:event.append((kind,kw)))
    assert 'On-page GBP offers: 2' in result
    assert 'Staples Super King Ottoman Bed' in result and 'PRICE: £699.99' in result
    assert 'Snooze Super King Bed Frame' in result and 'PRICE: £799.99' in result
    assert 'SIZE CHECK' in result
    assert 'web_direct_retailer' in [kind for kind,_ in event]
    assert any(kind=='web_link_selected' for kind,_ in event)


def test_bad_rss_cannot_replace_official_links(monkeypatch):
    from studio_integration import web_research as wr
    monkeypatch.setattr(wr,'_fetch_public_bytes',lambda url,**kw:(403,'text/html',b''))
    monkeypatch.setattr(wr,'_robots_allowed',lambda url:False)
    bad=b'<rss><channel><item><title>Getting word definition</title><link>https://dictionary.example.org/getting/</link><description>Getting means acquiring something.</description></item></channel></rss>'
    class R:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return bad
    monkeypatch.setattr(live_tools._OPENER,'open',lambda *a,**kw:R())
    monkeypatch.setitem(live_tools.SETTINGS,'provider','bing')
    result=live_tools.web_search(Q)
    assert 'Super King Beds | Bensons for Beds' in result
    assert CAT in result
    assert 'On-page GBP offers: 0' in result
    assert 'public search fallback was unrelated' in result.lower()
    assert 'Getting word definition' not in result


def test_super_king_category_precedes_generic_bed_page():
    entries=direct_retailer_entries('find super king beds at Bensons for Beds')
    assert entries[0]['url']==CAT


def test_no_guessed_domain_for_unknown_shop():
    assert direct_retailer_entries('Cheapest Shark vacuum from Mystery Shop')==[]


def test_explicit_public_domain_is_supported():
    entries=direct_retailer_entries('Find some prices at https://www.example.com/beds/')
    assert entries[0]['url']=='https://www.example.com/beds/'


def test_random_numbers_are_not_verified_prices():
    page=parse_page(b'<h1>Super King Bed</h1><p>10 reviews and 2 day delivery</p>',PROD1)
    assert page['products']==[]


def test_shopping_query_retains_real_retailer_spelling():
    assert 'Bensons for Beds' in shopping_search_query('find prices for super king beds at benso beds')

def test_default_size_offer_cannot_be_mislabelled_super_king():
    wrong_product='https://www.bensonsforbeds.co.uk/products/any-bed-frame/'
    page=b'<html><h1>Standard Ottoman Bed Frame</h1><script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Standard Ottoman Bed Frame','offers':{'price':'199.99','priceCurrency':'GBP'}}).encode()+b'</script></html>'
    seed=[{'title':'Bensons for Beds Super King Beds','url':CAT,'description':'Shop super king bed frames'}]
    def fetch(url,**kwargs):
        if url==CAT:
            return 200,'text/html',b'<h1>Super King Beds</h1><a href="/products/any-bed-frame/">Standard Ottoman Bed Frame Super King</a>'
        if url==wrong_product:return 200,'text/html',page
        raise AssertionError(url)
    output=research(Q,seed,fetch_page=fetch,robots=lambda u:True,discovery='retailer')
    assert 'On-page GBP offers: 0' in output
    assert 'EXCLUDED 1 product price' in output
    assert 'PRICE: £199.99' not in output
