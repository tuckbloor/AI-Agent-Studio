import importlib.util
import sys
import tempfile
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('full_installer',ROOT/'INSTALL_AND_RUN.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def fake_ai_server(folder):
    (folder/'engine'/'ai_app_server').mkdir(parents=True)
    (folder/'engine'/'ai_app_server'/'__init__.py').write_text('')
    (folder/'tools').mkdir()
    (folder/'tools'/'bootstrap.py').write_text('')
    (folder/'starter').mkdir()
    (folder/'starter'/'app.py').write_text('')
    (folder/'app').mkdir()
    (folder/'app'/'app.py').write_text('# existing')
    (folder/'data').mkdir()
    (folder/'data'/'server.sqlite3').write_text('PRESERVE THIS DATABASE')
    (folder/'config').mkdir()
    (folder/'config'/'host.json').write_text('{"port":8501}')
    (folder/'app'/'mcp_tools.py').write_text('# keep custom mcp')

def test_full_package_is_self_contained_for_studio():
    assert (ROOT/'INSTALL AND RUN.bat').is_file()
    assert (ROOT/'app'/'studio_integration'/'studio.html').is_file()
    assert (ROOT/'app'/'studio_integration'/'routes.py').is_file()
    assert (ROOT/'RUN_AGENT_STUDIO_ON_SERVER.py').is_file()
    assert 'ThreadingHTTPServer(' not in (ROOT/'app'/'studio_integration'/'routes.py').read_text()

def test_fresh_studio_install_keeps_ai_app_server(tmp_path):
    target=tmp_path/'ai-app-server'
    fake_ai_server(target)
    module.install_studio(target)
    assert (target/'app'/'studio_integration'/'routes.py').is_file()
    assert (target/'app'/'studio_integration'/'studio.html').is_file()
    assert (target/'data'/'server.sqlite3').read_text()=='PRESERVE THIS DATABASE'
    assert (target/'config'/'host.json').read_text()=='{"port":8501}'
    assert (target/'app'/'mcp_tools.py').read_text()=='# keep custom mcp'
    assert (target/'app'/'app.py').read_text()=='# existing'
    assert (target/'RUN_AGENT_STUDIO_ON_SERVER.py').is_file()

def test_rerun_full_package_backups_old_studio(tmp_path):
    target=tmp_path/'ai-app-server'
    fake_ai_server(target)
    old=target/'app'/'studio_integration'
    old.mkdir()
    (old/'old.txt').write_text('original contents')
    module.install_studio(target)
    backups=list((target/'backups').glob('agent-studio-full-backup-*'))
    assert len(backups)==1
    assert (backups[0]/'studio_integration'/'old.txt').read_text()=='original contents'

def test_missing_partial_server_is_not_replaced(tmp_path):
    target=tmp_path/'ai-app-server'
    target.mkdir()
    (target/'server.sqlite3').write_text('DO NOT TOUCH')
    with pytest.raises(module.SetupError):module.prepare(target,download=False,deps=False)
    assert (target/'server.sqlite3').read_text()=='DO NOT TOUCH'

def test_missing_server_no_download_flag_preserves_empty_path(tmp_path):
    target=tmp_path/'ai-app-server'
    with pytest.raises(module.SetupError):module.prepare(target,download=False,deps=False)
    assert not target.exists()
