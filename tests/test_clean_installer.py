"""Regression checks for portable distribution, no drive assumption, non-destructive installs."""
from pathlib import Path
import hashlib
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import studio_install as si


def test_exactly_two_bats_in_complete_source():
    assert {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*.bat')} == {'INSTALL.bat','START.bat'}


def test_version_and_bundled_framework_match_readme():
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    assert si.VERSION=='2.3.4'
    assert si.version_of(si.BUNDLE)==(1,0,5)
    assert 'v2.3.4' in readme and 'v1.0.5' in readme


def test_new_server_then_studio_copy_without_other_files(tmp_path):
    server=tmp_path/'Framework path with spaces'
    studio=tmp_path/'Studio application with spaces'
    si.ensure_empty(server,studio)
    si.ensure_empty(studio,server)
    si.new_server(server,copy_only=True)
    si.fresh_studio(server,studio,copy_only=True)
    assert (server/'START.bat').is_file()
    assert (studio/'START.bat').is_file()
    assert (studio/'app/studio_integration/routes.py').is_file()
    assert not (studio/'app/app.py').exists() # bootstrap creates only on real install
    assert not (server/'data').exists()
    assert 'studio_dir = script.parent' in (studio/'engine/ai_app_server/server.py').read_text()
    assert 'studio_dir = script.parent' not in (server/'engine/ai_app_server/server.py').read_text()


def test_existing_server_never_changed(tmp_path):
    existing=tmp_path/'Existing AI App Server'
    si.new_server(existing,copy_only=True)
    (existing/'data').mkdir()
    (existing/'data'/'server.sqlite3').write_bytes(b'critical original database')
    digest=hashlib.sha256((existing/'engine/ai_app_server/server.py').read_bytes()).hexdigest()
    studio=tmp_path/'Studio copy'
    si.fresh_studio(existing,studio,copy_only=True)
    assert hashlib.sha256((existing/'engine/ai_app_server/server.py').read_bytes()).hexdigest()==digest
    assert (existing/'data'/'server.sqlite3').read_bytes()==b'critical original database'
    assert not (studio/'data').exists()


def test_refuse_overwrite_and_nested_paths(tmp_path):
    existing=tmp_path/'Existing'
    existing.mkdir()
    (existing/'do-not-delete.sqlite3').write_bytes(b'keep')
    with pytest.raises(si.InstallError):si.ensure_empty(existing,tmp_path/'Other')
    with pytest.raises(si.InstallError):si.ensure_empty(tmp_path/'A'/'B',tmp_path/'A')
    assert (existing/'do-not-delete.sqlite3').read_bytes()==b'keep'


def test_no_fixed_drive_destination():
    source=(ROOT/'tools/studio_install.py').read_text(encoding='utf-8')
    assert 'E:/ai-app-server' not in source and 'E:\\ai-app-server' not in source
    assert 'GetLogicalDrives()' in source
    assert 'LOCALAPPDATA' in source


def test_installer_copy_only_command(tmp_path):
    server=tmp_path/'server';studio=tmp_path/'studio'
    assert si.main(['--install-server',str(server),'--studio',str(studio),'--copy-only']) == 0
    assert (server/'engine/pyproject.toml').exists()
    assert (studio/'app/studio_integration/routes.py').exists()
    assert si.main(['--install-server',str(server),'--studio',str(studio),'--copy-only']) == 1
