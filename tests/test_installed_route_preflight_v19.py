"""Exercise the actual launcher as a subprocess against an installed server layout.

Unlike v1.8's all-FastAPI-fake unit tests, these load the extension through the
same E:/ai-app-server/app path and Python entry point used by the installer.
"""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys

SOURCE=Path(__file__).resolve().parents[1]

def fixture_server(tmp_path,monkeypatch):
    target=tmp_path/'ai-app-server'
    for sub in ['app','engine/ai_app_server','tools','starter','data']:(target/sub).mkdir(parents=True,exist_ok=True)
    (target/'engine/ai_app_server/__init__.py').write_text('')
    (target/'engine/ai_app_server/hosting.py').write_text(
        "def initialize_port(data): return {'port':8501,'mode':'development'}\n")
    (target/'engine/ai_app_server/server.py').write_text('''from fastapi import FastAPI
from pathlib import Path
class Store:
    def __init__(self,path):self.directory=Path(path)
def create_app(script,*,data_dir,mode,secure_cookies,local_only):
    app=FastAPI()
    app.state.store=Store(data_dir)
    @app.get('/')
    def home():return {'ok':True}
    return app
''')
    (target/'app/app.py').write_text('print("hi")\n')
    (target/'tools/bootstrap.py').write_text('')
    (target/'starter/app.py').write_text('')
    monkeypatch.setenv('PYTHONPATH',str(target/'engine'))
    return target

def test_real_installed_subprocess_registers_routes(tmp_path,monkeypatch):
    target=fixture_server(tmp_path,monkeypatch)
    shutil.copytree(SOURCE/'app/studio_integration',target/'app/studio_integration')
    shutil.copy2(SOURCE/'RUN_AGENT_STUDIO_ON_SERVER.py',target/'RUN_AGENT_STUDIO_ON_SERVER.py')
    result=subprocess.run([sys.executable,str(target/'RUN_AGENT_STUDIO_ON_SERVER.py'),'--check-only'],
         text=True,capture_output=True,cwd=target,timeout=25)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PREFLIGHT PASS' in result.stdout
    assert '/admin/studio' in result.stdout
    assert '/studio/api/studio/status' in result.stdout

def test_failed_real_preflight_rolls_back_complete_extension(tmp_path,monkeypatch):
    target=fixture_server(tmp_path,monkeypatch)
    existing=target/'app/studio_integration'
    existing.mkdir()
    (existing/'old-marker.txt').write_text('keep this')
    (target/'RUN_AGENT_STUDIO_ON_SERVER.py').write_text('original launcher')
    (target/'START AGENT STUDIO ON AI SERVER.bat').write_text('original batch')
    broken=tmp_path/'broken-package'
    shutil.copytree(SOURCE,broken,ignore=shutil.ignore_patterns('tests','__pycache__'))
    # Induce the same missing-route condition that the user's v1.8 install hit.
    (broken/'app/studio_integration/__init__.py').write_text('def install_studio(app): return app\n')
    spec=importlib.util.spec_from_file_location('package_installer_v19',str(SOURCE/'INSTALL_AND_RUN.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.install_studio(target,source=broken,python_exe=Path(sys.executable))
    except module.SetupError as error:
        assert 'preflight FAILED' in str(error)
    else:
        assert False,'Expected actual installed route check to reject missing routes'
    assert (existing/'old-marker.txt').read_text()=='keep this'
    assert (target/'RUN_AGENT_STUDIO_ON_SERVER.py').read_text()=='original launcher'
    assert (target/'START AGENT STUDIO ON AI SERVER.bat').read_text()=='original batch'
    assert not (target/'app/mcp_tools.py').exists()
