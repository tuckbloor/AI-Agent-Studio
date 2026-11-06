"""Agent Studio v1.8: real admin route and public homepage integration checks."""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.testclient import TestClient
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from studio_integration.routes import install_studio

class FakeStore:
    def __init__(self,folder):self.directory=folder
    def session(self,token):
        return {'username':'admin','csrf':'abc','must_change_password':False} if token=='valid' else None
    def permissions(self,user):return ['view_dashboard','manage_settings','manage_databases']
    def maintenance_on(self):return False


def get_app(tmp_path,mode='normal'):
    app=FastAPI()
    app.state.store=FakeStore(tmp_path)
    @app.get('/')
    def homepage():
        if mode=='maintenance':return HTMLResponse('<p>Maintenance</p>',status_code=503)
        if mode=='login':return RedirectResponse('/app-login',status_code=303)
        return HTMLResponse('<p>Original generic server page</p>')
    @app.get('/admin')
    def admin():return HTMLResponse('<h1>Original admin</h1>')
    install_studio(app)
    return app


def test_original_purple_design_at_root(tmp_path):
    with TestClient(get_app(tmp_path)) as c:
        r=c.get('/')
        assert r.status_code==200
        assert 'Describe your idea.' in r.text
        assert 'home-idea-form' in r.text
        assert '/studio/assets/styles.css' in r.text
        assert '/admin/studio' in r.text
        assert 'Original generic server page' not in r.text
        assert c.get('/studio/assets/styles.css').status_code==200
        assert c.get('/studio/assets/landing.js').status_code==200


def test_native_login_admin_editor(tmp_path):
    with TestClient(get_app(tmp_path)) as c:
        a=c.get('/admin/studio',follow_redirects=False)
        assert a.status_code==303 and a.headers['location']=='/admin'
        assert c.get('/studio/assets/studio.js').status_code==401
        c.cookies.set('aia_admin_session','valid')
        page=c.get('/admin/studio')
        assert page.status_code==200
        assert 'studio-csrf' in page.text
        assert 'AI BUILDER' in page.text
        assert 'src="/studio/assets/studio.js"' in page.text
        assert c.get('/studio/assets/studio.js').status_code==200
        assert c.get('/studio/').status_code==200  # legacy redirects to public home
        assert c.get('/studio/api/studio/status').status_code==200


def test_prod_login_and_maintenance_are_preserved(tmp_path):
    with TestClient(get_app(tmp_path/'a',mode='maintenance')) as c:
        r=c.get('/')
        assert r.status_code==503 and 'Maintenance' in r.text
        assert 'home-idea-form' not in r.text
    with TestClient(get_app(tmp_path/'b',mode='login')) as c:
        r=c.get('/',follow_redirects=False)
        assert r.status_code==303 and r.headers['location']=='/app-login'


def test_linked_editor_public_and_private_files(tmp_path):
    with TestClient(get_app(tmp_path)) as c:
        assert c.get('/studio/assets/admin-link.js').status_code==200
        assert c.get('/studio/assets/builder.css').status_code==401
        assert c.get('/studio/assets/secret.csv').status_code in (401,404)
        c.cookies.set('aia_admin_session','valid')
        assert c.get('/admin/studio/editor').status_code==200
        assert c.get('/studio/assets/secret.csv').status_code==404
