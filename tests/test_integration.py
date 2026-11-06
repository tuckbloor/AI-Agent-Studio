import json
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

APP_DIR=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP_DIR))
from studio_integration.routes import install_studio
from studio_integration import core

class FakeStore:
    def __init__(self, path):
        self.directory=path
        self.actions=[]
    def session(self,token):
        if token!='valid':return None
        return {'username':'testadmin','csrf':'test-csrf','must_change_password':False}
    def permissions(self,user):return ['view_dashboard','manage_settings','manage_databases']
    def audit(self,*args):self.actions.append(args)

@pytest.fixture
def client(tmp_path,monkeypatch):
    app=FastAPI()
    app.state.store=FakeStore(tmp_path/'data')
    app.state.store.directory.mkdir()
    app.state.mode='development'
    app.state.production=False
    install_studio(app)
    monkeypatch.setattr(core,'installed_models', lambda:['testmodel:latest'])
    return TestClient(app,base_url='http://testserver')

HEADERS={'Origin':'http://testserver','X-CSRF-Token':'test-csrf'}
COOKIE={'aia_admin_session':'valid'}


def test_admin_login_required_for_pages_and_tools(client):
    assert client.get('/studio/',follow_redirects=False).status_code==303
    assert client.get('/studio/api/studio/tools').status_code==401
    assert client.get('/studio/assets/studio.js').status_code==401
    assert client.get('/admin/studio',follow_redirects=False).headers['location']=='/admin'
    assert client.get('/studio/assets/styles.css').status_code==200
    assert client.get('/studio/assets/landing.js').status_code==200
    client.cookies.set('aia_admin_session','valid')
    assert client.get('/studio/',follow_redirects=False).status_code==303
    assert client.get('/studio/studio.html').status_code==200
    assert client.get('/admin/studio').status_code==200
    assert 'studio-csrf' in client.get('/admin/studio').text
    assert '/studio/assets/studio.js' in client.get('/admin/studio').text
    assert len(client.get('/studio/api/studio/tools').json())>=20
    assert client.get('/studio/preview.py').status_code==404
    assert client.get('/studio/assets/../core.py').status_code==404


def test_csrf_and_origin_protect_writes(client):
    client.cookies.set('aia_admin_session','valid')
    r=client.post('/studio/api/studio/tools/sync',json={'tools':[]})
    assert r.status_code==403
    r=client.post('/studio/api/studio/tools/sync',json={'tools':[]},headers={'X-CSRF-Token':'test-csrf','Origin':'https://attacker.example'})
    assert r.status_code==403
    r=client.post('/studio/api/studio/tools/sync',json={'tools':[]},headers=HEADERS)
    assert r.status_code==200


def test_models_and_status(client):
    client.cookies.set('aia_admin_session','valid')
    assert client.get('/studio/api/studio/models').json()==['testmodel:latest']
    assert client.get('/studio/api/studio/status').json()['aiAppServerIntegrated'] is True


def test_workflow_saved_to_private_server_sqlite(client,tmp_path):
    client.cookies.set('aia_admin_session','valid')
    workflow={'format':'agent-studio/workflow','version':1,'id':'one','name':'Saved example','description':'hello',
              'steps':[{'type':'trigger','config':{'event':'manual'}},
                       {'type':'ai','config':{'model':'testmodel:latest','instructions':'Explain things'}},
                       {'type':'output','config':{'format':'text'}}]}
    assert client.post('/studio/api/studio/workflows/latest',json={'workflow':workflow},headers=HEADERS).status_code==200
    got=client.get('/studio/api/studio/workflows/latest').json()
    assert got['workflow']['name']=='Saved example'
    assert (tmp_path/'data'/'agent-studio'/'studio.sqlite3').is_file()


def test_save_run_result(client):
    client.cookies.set('aia_admin_session','valid')
    r={'id':'run1','output':'This is an answer','agentName':'Agent','when':'2026-11-05'}
    assert client.post('/studio/api/studio/results',json={'result':r},headers=HEADERS).status_code==200
    assert client.get('/studio/api/studio/results').json()[0]['output']=='This is an answer'


def test_live_events_are_on_same_server(client,monkeypatch):
    client.cookies.set('aia_admin_session','valid')
    wf={'name':'sample','steps':[{'type':'trigger','config':{}},{'type':'ai','config':{}},{'type':'output','config':{}}]}
    monkeypatch.setattr(core,'validate_run',lambda *a,**kw: (wf['steps'],{}))
    monkeypatch.setattr(core,'run_events',lambda *a,**kw: iter([
        {'type':'workflow_started','total':3}, {'type':'workflow_completed','output':'hello'}]))
    r=client.post('/studio/api/studio/run/events',json={'workflow':wf,'prompt':'hi'},headers=HEADERS)
    assert r.status_code==200
    events=[json.loads(x) for x in r.text.splitlines() if x]
    assert events[-1]['output']=='hello'


def test_no_duplicate_preview_server():
    root=APP_DIR/'studio_integration'
    assert 'ThreadingHTTPServer(' not in (root/'routes.py').read_text()
    script=(APP_DIR.parent/'RUN_AGENT_STUDIO_ON_SERVER.py').read_text()
    assert 'create_app(' in script and 'install_studio(' in script
