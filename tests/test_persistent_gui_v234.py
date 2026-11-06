"""Headless tests for the persistent Windows installer entry point."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))
import studio_gui as gui


def test_installer_is_gui_and_has_only_two_batch_files():
    bat = (ROOT / 'INSTALL.bat').read_text()
    assert 'studio_gui.py' in bat
    assert 'start "" /D' in bat
    assert 'pyw -3' in bat
    assert 'goto :command_line' in bat
    assert {p.name for p in ROOT.rglob('*.bat')} == {'INSTALL.bat', 'START.bat'}


def test_command_constructed_for_preexisting_server(tmp_path):
    server, studio = tmp_path / 'existing server', tmp_path / 'studio new'
    cmd = gui.installation_arguments('existing', server, studio, False)
    assert cmd[1] == str(TOOLS / 'studio_install.py')
    assert cmd[2:] == ['--server', str(server), '--studio', str(studio)]
    assert '--overwrite-existing' not in cmd


def test_explicit_overwrite_is_passed_only_after_confirmation(tmp_path):
    server, studio = tmp_path / 'existing server', tmp_path / 'studio old'
    cmd = gui.installation_arguments('existing', server, studio, True)
    assert cmd[-1] == '--overwrite-existing'
    assert cmd.count('--overwrite-existing') == 1


def test_new_server_path_installs_then_studio(tmp_path):
    cmd = gui.installation_arguments('new', tmp_path / 'server with spaces', tmp_path / 'Studio Test', False)
    assert '--install-server' in cmd
    assert '--studio' in cmd
    assert '--server' not in cmd


def test_gui_entrypoint_self_test_does_not_open_any_windows():
    out = subprocess.run([sys.executable, str(TOOLS / 'studio_gui.py'), '--self-test'],
                         cwd=ROOT, check=True, capture_output=True, text=True)
    assert 'GUI launcher self-test PASS' in out.stdout


def test_ui_keeps_dialog_and_error_logs_visible():
    src = (TOOLS / 'studio_gui.py').read_text(encoding='utf-8')
    assert "self.root.after(100, self.drain_events)" in src
    assert "self.messagebox.showerror('AI Agent Studio installation failed'" in src
    assert "self.root.mainloop()" not in src  # GUI uses the real tkinter root
    assert "root.mainloop()" in src
    assert 'if self.in_progress:' in src
