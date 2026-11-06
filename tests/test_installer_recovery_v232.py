"""Regression coverage for misdirected START.bat and interrupted installs.

Do not touch real Windows state or need network access.
"""
from pathlib import Path
import hashlib
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import studio_install as si


def test_source_and_installed_launcher_have_safe_recovery_branches():
    content = (ROOT / 'START.bat').read_text(encoding='utf-8')
    assert 'goto :source' in content
    # Source also contains app/studio_integration; source detection must win.
    assert content.index('if exist "%~dp0framework\\engine\\pyproject.toml" goto :source') < content.index('if exist "%~dp0engine\\pyproject.toml"')
    assert '--launch-installed' in content
    assert 'goto :recover' in content
    assert '--resume' in content
    assert 'tools\\studio_install.py' in content
    assert '.venv\\Scripts\\python.exe' in content
    assert 'E:\\' not in content
    assert '--project "%CD%"' in content
    assert '--resume "%CD%"' in content
    assert len(list(ROOT.rglob('*.bat'))) == 2


def test_installed_copy_contains_recovery_python(tmp_path):
    framework = tmp_path / 'framework'
    studio = tmp_path / 'studio'
    si.new_server(framework, copy_only=True)
    si.fresh_studio(framework, studio, copy_only=True)
    assert (studio / 'tools/studio_install.py').is_file()
    assert (studio / 'START.bat').is_file()
    assert not (studio / '.venv').exists()


def test_remember_and_find_studio_does_not_read_or_modify_database(tmp_path, monkeypatch):
    framework = tmp_path / 'framework'
    studio = tmp_path / 'Studio Directory With Spaces'
    si.new_server(framework, copy_only=True)
    si.fresh_studio(framework, studio, copy_only=True)
    (studio / 'data').mkdir()
    db = studio / 'data' / 'server.sqlite3'
    db.write_bytes(b'never change my database')
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    state = tmp_path / 'state' / 'installations.json'
    monkeypatch.setenv('AI_AGENT_STUDIO_STATE_FILE', str(state))
    si.remember_studio(studio)
    assert si.remembered_studio() == studio
    assert json.loads(state.read_text())['studio'] == str(studio)
    assert si.select_installed_studio() == studio
    assert hashlib.sha256(db.read_bytes()).hexdigest() == digest


def test_bad_or_stale_state_does_not_start_wrong_directory(tmp_path, monkeypatch):
    state = tmp_path / 'installations.json'
    monkeypatch.setenv('AI_AGENT_STUDIO_STATE_FILE', str(state))
    state.write_text('{not-json', encoding='utf-8')
    assert si.remembered_studio() is None
    state.write_text(json.dumps({'schema': 1, 'studio': str(ROOT)}), encoding='utf-8')
    assert si.remembered_studio() is None  # extracted ZIP is not an installation


def test_interrupted_install_recovers_missing_environment_without_replacing_data(tmp_path, monkeypatch):
    framework = tmp_path / 'framework'
    studio = tmp_path / 'Studio Partial'
    si.new_server(framework, copy_only=True)
    si.fresh_studio(framework, studio, copy_only=True)
    (studio / 'data').mkdir()
    db = studio / 'data' / 'server.sqlite3'
    db.write_bytes(b'keep user data unchanged')
    app = studio / 'app' / 'app.py'
    assert not app.exists()
    exe = studio / ('.venv/Scripts/python.exe' if si.os.name == 'nt' else '.venv/bin/python')
    events = []

    def fake_setup(destination):
        assert destination == studio
        assert db.read_bytes() == b'keep user data unchanged'
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b'fake interpreter')
        app.write_text('original app entry', encoding='utf-8')
        events.append('setup')
        return exe

    monkeypatch.setattr(si, 'python_setup', fake_setup)
    monkeypatch.setattr(si, 'verify_studio', lambda d, x, no_start=False: events.append(('verify', d, x, no_start)))
    monkeypatch.setenv('AI_AGENT_STUDIO_STATE_FILE', str(tmp_path / 'user-state.json'))
    si.resume_studio(studio, no_start=True)
    assert events == ['setup', ('verify', studio, exe, True)]
    assert db.read_bytes() == b'keep user data unchanged'
    assert si.remembered_studio() == studio


def test_launch_from_extracted_source_targets_install_not_source(tmp_path, monkeypatch):
    framework = tmp_path / 'framework'
    studio = tmp_path / 'Studio'
    si.new_server(framework, copy_only=True)
    si.fresh_studio(framework, studio, copy_only=True)
    (studio / 'app/app.py').write_text('test', encoding='utf-8')
    exe = studio / ('.venv/Scripts/python.exe' if si.os.name == 'nt' else '.venv/bin/python')
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'fake interpreter')
    monkeypatch.setenv('AI_AGENT_STUDIO_STATE_FILE', str(tmp_path / 'location.json'))
    si.remember_studio(studio)
    calls = []
    monkeypatch.setattr(si, 'verify_studio', lambda *args, **kwargs: calls.append('preflight'))
    monkeypatch.setattr(si, 'command', lambda args, cwd, desc: calls.append((args, cwd, desc)))
    si.launch_installed('start', no_browser=True)
    assert calls[0] == 'preflight'
    args, cwd, _ = calls[1]
    assert cwd == studio
    assert str(studio) in [str(x) for x in args]
    assert '--no-browser' in args
    assert str(ROOT) not in [str(x) for x in args]
    assert calls[1][0][3] == 'start'


def test_resume_never_accepts_extracted_source_folder(tmp_path):
    with pytest.raises(si.InstallError, match='Not a valid AI Agent Studio'):
        si.resume_studio(ROOT)


def test_server_copy_includes_recovery_without_extra_batch(tmp_path):
    framework = tmp_path / 'Framework'
    si.new_server(framework, copy_only=True)
    assert (framework/'tools/studio_install.py').is_file()
    content = (framework/'START.bat').read_text(encoding='utf-8')
    assert '--resume-server' in content
    assert '--resume-server "%CD%"' in content
    assert len(list(framework.rglob('*.bat'))) == 1


def test_interrupted_separate_server_recovers_without_changing_database(tmp_path, monkeypatch):
    framework = tmp_path / 'Server setup interrupted'
    si.new_server(framework, copy_only=True)
    (framework/'data').mkdir()
    db = framework/'data'/'server.sqlite3'
    db.write_bytes(b'preserve all server accounts')
    exe = framework/('.venv/Scripts/python.exe' if si.os.name=='nt' else '.venv/bin/python')
    calls=[]
    def fake_python_setup(d):
        assert d == framework
        assert db.read_bytes() == b'preserve all server accounts'
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b'fake python')
        calls.append('setup')
        return exe
    monkeypatch.setattr(si,'python_setup',fake_python_setup)
    monkeypatch.setattr(si,'command',lambda args,cwd,desc:calls.append((args,cwd,desc)))
    si.resume_server(framework,no_start=False,no_browser=True)
    assert db.read_bytes() == b'preserve all server accounts'
    assert calls[0] == 'setup'
    assert '--no-browser' in calls[1][0]
    assert calls[1][1] == framework


def test_server_recovery_does_not_accept_studio(tmp_path):
    framework = tmp_path/'server'
    studio=tmp_path/'studio'
    si.new_server(framework,copy_only=True)
    si.fresh_studio(framework,studio,copy_only=True)
    with pytest.raises(si.InstallError,match='Not an AI App Server installation'):
        si.resume_server(studio)
