"""Regression for the user's failed Windows v2.3.0 route verification.

A FastAPI router container is not necessarily an endpoint with a .path.
"""
from pathlib import Path
import hashlib
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import studio_install as si


class _IncludedRouter:
    def __init__(self, routes):
        self.routes = routes


class _Endpoint:
    def __init__(self, path):
        self.path = path


class _App:
    def __init__(self, routes):
        self.routes = routes


def test_route_preflight_skips_router_containers_without_path(monkeypatch):
    needed = [_Endpoint('/admin/studio'),
              _Endpoint('/studio/api/studio/status'),
              _Endpoint('/studio/api/studio/run/events')]
    server = types.ModuleType('ai_app_server.server')
    server.create_app = lambda *args, **kwargs: _App([
        _IncludedRouter([_Endpoint('/health')]),
        _IncludedRouter(needed[:2]), needed[2],
    ])
    monkeypatch.setitem(sys.modules, 'ai_app_server.server', server)
    exec(si.ROUTE_PREFLIGHT, {'__name__': '__main__'})


def test_route_preflight_still_fails_when_studio_route_is_missing(monkeypatch):
    server = types.ModuleType('ai_app_server.server')
    server.create_app = lambda *args, **kwargs: _App([
        _IncludedRouter([_Endpoint('/admin/studio')]),
        _Endpoint('/studio/api/studio/status'),
    ])
    monkeypatch.setitem(sys.modules, 'ai_app_server.server', server)
    with pytest.raises(RuntimeError, match='Missing Studio routes: .*run/events'):
        exec(si.ROUTE_PREFLIGHT, {'__name__': '__main__'})


def test_resume_installation_does_not_copy_or_overwrite_data(tmp_path, monkeypatch):
    server = tmp_path / 'Existing AI App Server'
    installed = tmp_path / 'Installed Studio with spaces'
    si.new_server(server, copy_only=True)
    si.fresh_studio(server, installed, copy_only=True)
    (installed / 'app/app.py').write_text('print("example")', encoding='utf-8')
    (installed / 'data').mkdir()
    db = installed / 'data/server.sqlite3'
    db.write_bytes(b'my existing data must not be modified')
    executable = installed / '.venv/bin/python' if sys.platform != 'win32' else installed / '.venv/Scripts/python.exe'
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'fake python executable')
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    called = []
    monkeypatch.setattr(si, 'command', lambda cmd, cwd, desc: called.append((cmd, cwd, desc)))
    si.resume_studio(installed, no_start=False)
    assert len(called) == 2
    assert called[0][0][2] == si.ROUTE_PREFLIGHT
    assert str(called[1][0][-1]) == str(installed)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_resume_rejects_non_studio_folder(tmp_path):
    other = tmp_path / 'random'
    other.mkdir()
    (other / 'data.sqlite3').write_bytes(b'unchanged')
    with pytest.raises(si.InstallError, match='Not a valid AI Agent Studio'):
        si.resume_studio(other)
    assert (other / 'data.sqlite3').read_bytes() == b'unchanged'
