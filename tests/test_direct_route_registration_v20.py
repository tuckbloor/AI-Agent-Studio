"""Regression for the user's real v1.9 Windows output.

The installed app had /admin/studio but not the routes mounted through the
Studio APIRouter. Prove direct registration works even if FastAPI.include_router
is intercepted or becomes a no-op in an installed integration.
"""
from pathlib import Path
import sys
from fastapi import FastAPI
from fastapi.testclient import TestClient

APP_DIR=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP_DIR))
from studio_integration.routes import install_studio


class Store:
    def __init__(self, directory):
        self.directory=directory
    def session(self, token):
        return {'username':'admin','csrf':'csrf','must_change_password':False} if token=='valid' else None
    def permissions(self,user):
        return ['view_dashboard','manage_settings','manage_databases']
    def audit(self,*args):pass


def test_registered_directly_even_if_include_router_is_broken(tmp_path):
    app=FastAPI()
    app.state.store=Store(tmp_path)
    app.include_router=lambda *args,**kwargs: None
    installed=install_studio(app)
    assert installed is app
    paths={r.path:getattr(r,'methods',set()) for r in app.routes}
    assert '/admin/studio' in paths
    assert 'GET' in paths['/studio/api/studio/status']
    assert 'POST' in paths['/studio/api/studio/run/events']
    assert '/studio/assets/{file_name:path}' in paths
    assert '/studio/' in paths
    with TestClient(app, base_url='http://127.0.0.1:8501') as client:
        assert client.get('/admin/studio',follow_redirects=False).status_code==303
        assert client.get('/studio/api/studio/status').status_code==401
        assert client.get('/studio/assets/studio.js').status_code==401
        assert client.post('/studio/api/studio/run/events', json={}).status_code==401
        assert client.get('/studio/assets/styles.css').status_code==200
        client.cookies.set('aia_admin_session','valid')
        assert client.get('/admin/studio').status_code==200
        assert client.get('/studio/api/studio/status').status_code==200


def test_new_studio_engine_extension_is_loaded(tmp_path):
    import sys
    sys.path.insert(0,str(APP_DIR.parent/'tools'))
    from studio_install import clean_copy, install_extension, ROOT, BUNDLE
    target=tmp_path/'agent studio'
    clean_copy(BUNDLE,target,dirs=('engine','starter','tools'))
    install_extension(target/'engine')
    contents=(target/'engine/ai_app_server/server.py').read_text(encoding='utf-8')
    assert 'studio_dir = script.parent' in contents
    assert 'install_studio(app)' in contents
    assert (BUNDLE/'engine/ai_app_server/server.py').read_text(encoding='utf-8') != contents
