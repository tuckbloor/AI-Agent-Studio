"""Existing Studio overwrite consent, safe backup, and rollback regression tests."""
import hashlib
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import studio_install as si


def installed_studio(tmp_path):
    server=tmp_path/'Independent AI App Server'
    studio=tmp_path/'AI Agent Studio'
    si.new_server(server,copy_only=True)
    si.fresh_studio(server,studio,copy_only=True)
    (studio/'data').mkdir()
    (studio/'data/server.sqlite3').write_bytes(b'important database')
    (studio/'app/app.py').write_text('existing own app',encoding='utf-8')
    (studio/'config').mkdir()
    (studio/'config/settings.json').write_bytes(b'configuration')
    (studio/'app/studio_integration/agent_designer.py').write_bytes(b'# previous code')
    (studio/'.venv').mkdir()
    (studio/'.venv/.do-not-touch').write_bytes(b'environment marker')
    (studio/'extra-user-note.txt').write_text('user file',encoding='utf-8')
    return server,studio


def test_existing_detected_and_unknown_folder_rejected(tmp_path):
    server,studio=installed_studio(tmp_path)
    assert si.safe_existing_studio(studio,server)
    unrelated=tmp_path/'Other folder'
    unrelated.mkdir()
    (unrelated/'personal.txt').write_text('do not overwrite')
    with pytest.raises(si.InstallError,match='NOT a recognised'):
        si.safe_existing_studio(unrelated,server)
    assert (unrelated/'personal.txt').read_text()=='do not overwrite'


def test_user_no_cancels_without_creating_files(tmp_path,monkeypatch):
    server,studio=installed_studio(tmp_path)
    before={str(p.relative_to(studio)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in studio.rglob('*') if p.is_file()}
    monkeypatch.setattr(si,'confirm_overwrite_studio',lambda dst: False)
    assert si.main(['--server',str(server),'--studio',str(studio),'--copy-only'])==0
    after={str(p.relative_to(studio)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in studio.rglob('*') if p.is_file()}
    assert before==after
    assert not list(tmp_path.glob('AI Agent Studio-backup-*'))


def test_user_yes_updates_code_with_backup_and_preserves_data(tmp_path,monkeypatch):
    server,studio=installed_studio(tmp_path)
    monkeypatch.setattr(si,'confirm_overwrite_studio',lambda dst: True)
    monkeypatch.setenv('AI_AGENT_STUDIO_STATE_FILE',str(tmp_path/'state.json'))
    before_server=hashlib.sha256((server/'engine/ai_app_server/server.py').read_bytes()).hexdigest()
    assert si.main(['--server',str(server),'--studio',str(studio),'--copy-only'])==0
    backups=list(tmp_path.glob('AI Agent Studio-backup-*'))
    assert len(backups)==1
    backup=backups[0]
    assert (backup/'app/studio_integration/agent_designer.py').read_bytes()==b'# previous code'
    assert (backup/'data/server.sqlite3').read_bytes()==b'important database'
    assert (backup/'config/settings.json').read_bytes()==b'configuration'
    assert (studio/'data/server.sqlite3').read_bytes()==b'important database'
    assert (studio/'app/app.py').read_text()=='existing own app'
    assert (studio/'.venv/.do-not-touch').read_bytes()==b'environment marker'
    assert (studio/'extra-user-note.txt').read_text()=='user file'
    assert (studio/'app/studio_integration/agent_designer.py').read_bytes()!=b'# previous code'
    assert hashlib.sha256((server/'engine/ai_app_server/server.py').read_bytes()).hexdigest()==before_server


def test_cli_overwrite_requires_explicit_flag(tmp_path,monkeypatch):
    server,studio=installed_studio(tmp_path)
    monkeypatch.setattr(si,'confirm_overwrite_studio',lambda dst: (_ for _ in ()).throw(si.InstallError('Must confirm')))
    assert si.main(['--server',str(server),'--studio',str(studio),'--copy-only'])==1
    assert (studio/'data/server.sqlite3').read_bytes()==b'important database'
    assert si.main(['--server',str(server),'--studio',str(studio),'--overwrite-existing','--copy-only'])==0


def test_update_rollback_restores_previous_managed_code(tmp_path,monkeypatch):
    server,studio=installed_studio(tmp_path)
    before=(studio/'app/studio_integration/agent_designer.py').read_bytes()
    # Failure after files are replaced must restore original code.
    monkeypatch.setattr(si,'remember_studio',lambda folder: (_ for _ in ()).throw(RuntimeError('injected failure')))
    with pytest.raises(RuntimeError,match='injected failure'):
        si.update_studio(studio,copy_only=True)
    assert (studio/'app/studio_integration/agent_designer.py').read_bytes()==before
    assert (studio/'data/server.sqlite3').read_bytes()==b'important database'
    assert (studio/'config/settings.json').read_bytes()==b'configuration'
    assert si.is_studio_folder(studio)


def test_refuse_running_or_unrelated_with_overwrite_flag(tmp_path):
    server,studio=installed_studio(tmp_path)
    (studio/'data/runtime.json').write_text('{"pid": 123}')
    with pytest.raises(si.InstallError,match='may still be running'):
        si.update_studio(studio,copy_only=True)
    assert (studio/'data/server.sqlite3').read_bytes()==b'important database'
    unrelated=tmp_path/'Unrelated'
    unrelated.mkdir()
    (unrelated/'something.txt').write_text('existing')
    assert si.main(['--server',str(server),'--studio',str(unrelated),
                    '--overwrite-existing','--copy-only'])==1
    assert (unrelated/'something.txt').read_text()=='existing'
