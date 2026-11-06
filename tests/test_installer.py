"""Installer regressions for the complete v1.7 package (no patch files)."""
import importlib.util
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_complete',PACKAGE/'INSTALL_AND_RUN.py')
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

def prepare_example_server(server):
    for folder in ('engine/ai_app_server','app','data','config','tools','starter'):
        (server/folder).mkdir(parents=True,exist_ok=True)
    (server/'engine'/'ai_app_server'/'__init__.py').write_text('')
    (server/'tools'/'bootstrap.py').write_text('')
    (server/'starter'/'app.py').write_text('')
    (server/'app'/'app.py').write_text('original app unchanged')
    (server/'data'/'server.sqlite3').write_bytes(b'original sqlite data')
    (server/'data'/'.secret-key').write_bytes(b'original secret')
    (server/'config'/'settings.json').write_text('original config')
    (server/'app'/'mcp_tools.py').write_text('existing MCP tools')

def test_existing_install_files_preserved(tmp_path):
    server=tmp_path/'ai-app-server'
    prepare_example_server(server)
    installer.install_studio(server)
    assert (server/'app'/'app.py').read_text()=='original app unchanged'
    assert (server/'data'/'server.sqlite3').read_bytes()==b'original sqlite data'
    assert (server/'data'/'.secret-key').read_bytes()==b'original secret'
    assert (server/'config'/'settings.json').read_text()=='original config'
    assert (server/'app'/'mcp_tools.py').read_text()=='existing MCP tools'
    assert (server/'RUN_AGENT_STUDIO_ON_SERVER.py').exists()
    assert (server/'app'/'studio_integration'/'routes.py').exists()
    installer.install_studio(server)
    assert list((server/'backups').glob('agent-studio-full-backup-*'))

def test_incomplete_server_is_rejected_without_deletion(tmp_path):
    bad=tmp_path/'not-the-ai-server';bad.mkdir()
    (bad/'mydata.db').write_bytes(b'KEEP')
    try:
        installer.prepare(bad,download=False,deps=False)
    except installer.SetupError:
        pass
    else:
        assert False,'Expected to stop rather than overwrite a partial folder'
    assert (bad/'mydata.db').read_bytes()==b'KEEP'
    assert not (bad/'app').exists()
