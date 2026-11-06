"""Persistent Windows installation wizard for AI Agent Studio.

This is deliberately separate from the noninteractive installation engine.
All destructive decisions are made on the Tk main thread; the engine runs in
its own subprocess with captured output. The wizard NEVER closes on errors.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import traceback

from studio_install import (
    InstallError, VERSION, base_path, ensure_empty, find_existing_server,
    installed_server, is_studio_folder, safe_existing_studio,
)

ROOT = Path(__file__).resolve().parent.parent


def cli_python() -> Path:
    """Use the console interpreter for the engine, even when launched by pythonw."""
    current = Path(sys.executable)
    if current.name.lower() == 'pythonw.exe':
        sibling = current.with_name('python.exe')
        if sibling.is_file():
            return sibling
    return current


def installation_arguments(mode: str, server: Path, studio: Path, overwrite: bool) -> list[str]:
    if mode not in ('existing', 'new'):
        raise ValueError('Unrecognised AI App Server installation mode')
    argv = [str(cli_python()), str(ROOT / 'tools' / 'studio_install.py')]
    argv.extend(['--server' if mode == 'existing' else '--install-server', str(server)])
    argv.extend(['--studio', str(studio)])
    if overwrite:
        argv.append('--overwrite-existing')
    return argv


def logfile() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    base = Path(local) if local else Path.home() / '.local' / 'state'
    name = datetime.now(timezone.utc).strftime('installer-%Y%m%dT%H%M%SZ')
    return base / 'AI-Agent-Studio' / 'logs' / f'{name}-{os.getpid()}.log'


class InstallerWizard:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.root = root
        self.root.title(f'AI Agent Studio v{VERSION} | Installer')
        self.root.geometry('820x700')
        self.root.minsize(700, 600)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.report_callback_exception = self.callback_error
        self.in_progress = False
        self.events = queue.Queue()
        self.log_path = logfile()
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Installation must still work when local log folder cannot be created.
            self.log_path = None

        known_server = find_existing_server()
        self.mode = tk.StringVar(value='existing' if known_server else 'new')
        self.server = tk.StringVar(value=str(known_server or (base_path() / 'AI-App-Server')))
        self.studio = tk.StringVar(value=str(base_path() / 'AI-Agent-Studio'))
        self.status = tk.StringVar(value='Choose both folders, then click Install / Update.')
        self.completed_path = None

        outer = ttk.Frame(root, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='AI Agent Studio', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(outer, text=f'Complete installer  ·  v{VERSION}  ·  No fixed drive letters',
                  font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 16))

        group = ttk.LabelFrame(outer, text='1. AI App Server framework', padding=12)
        group.pack(fill='x', pady=(0, 12))
        ttk.Radiobutton(group, text='Use an existing AI App Server (read-only)',
                        variable=self.mode, value='existing').pack(anchor='w')
        ttk.Radiobutton(group, text='Install a new AI App Server first',
                        variable=self.mode, value='new').pack(anchor='w')
        self.path_line(group, self.server, 'AI App Server location', is_server=True)
        ttk.Label(group, text='Studio gets its own framework, database, accounts and port.').pack(anchor='w')

        group2 = ttk.LabelFrame(outer, text='2. AI Agent Studio destination', padding=12)
        group2.pack(fill='x', pady=(0, 12))
        self.path_line(group2, self.studio, 'Studio installation folder', is_server=False)
        ttk.Label(group2, text='Existing Studio? You will be asked before updating; a backup is created.').pack(anchor='w')

        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(0, 12))
        self.install_button = ttk.Button(controls, text='Install / Update', command=self.install)
        self.install_button.pack(side='left')
        self.start_button = ttk.Button(controls, text='Open installed folder', command=self.open_folder,
                                       state='disabled')
        self.start_button.pack(side='left', padx=(10, 0))
        ttk.Button(controls, text='Close', command=self.close).pack(side='right')
        ttk.Label(outer, textvariable=self.status, wraplength=750).pack(anchor='w', pady=(0, 8))

        log_frame = ttk.LabelFrame(outer, text='Installer progress and errors (this window remains open)', padding=7)
        log_frame.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(log_frame, orient='vertical')
        scroll.pack(side='right', fill='y')
        self.output = tk.Text(log_frame, height=13, wrap='word', yscrollcommand=scroll.set,
                              font=('Consolas', 9), state='disabled')
        self.output.pack(fill='both', expand=True)
        scroll.config(command=self.output.yview)
        self.append('Installer ready. No existing files will be changed without confirmation.')
        if known_server:
            self.append(f'Found a compatible AI App Server: {known_server}')
        if self.log_path:
            self.append(f'Installer log: {self.log_path}')
        self.root.after(100, self.drain_events)

    def path_line(self, parent, value, label, is_server):
        self.ttk.Label(parent, text=label).pack(anchor='w', pady=(10, 3))
        holder = self.ttk.Frame(parent)
        holder.pack(fill='x')
        self.ttk.Entry(holder, textvariable=value).pack(side='left', fill='x', expand=True)
        self.ttk.Button(holder, text='Browse…', command=lambda: self.browse(value)).pack(side='left', padx=(8, 0))

    def browse(self, value):
        chosen = Path(value.get()).expanduser()
        while not chosen.is_dir() and chosen != chosen.parent:
            chosen = chosen.parent
        try:
            directory = self.filedialog.askdirectory(parent=self.root, title='Choose installation location',
                                                       initialdir=str(chosen), mustexist=True)
        except Exception as exc:
            self.show_error(f'Cannot open folder browser: {exc}')
            return
        if directory:
            value.set(directory)

    def append(self, message):
        line = str(message).rstrip('\n')
        self.output.configure(state='normal')
        self.output.insert('end', line + '\n')
        self.output.see('end')
        self.output.configure(state='disabled')
        if self.log_path:
            try:
                with self.log_path.open('a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except OSError:
                pass

    def show_error(self, message):
        self.append('ERROR: ' + message)
        self.status.set('Installation stopped. See the error below; you can correct the paths and retry.')
        self.messagebox.showerror('AI Agent Studio installation problem', message, parent=self.root)

    def validated(self):
        mode = self.mode.get()
        server_input = self.server.get().strip().strip('"')
        studio_input = self.studio.get().strip().strip('"')
        if not server_input or not studio_input:
            raise InstallError('Choose both the AI App Server folder and the Studio folder.')
        server = Path(server_input).expanduser().resolve()
        studio = Path(studio_input).expanduser().resolve()
        existing = safe_existing_studio(studio, server)
        if mode == 'existing':
            if not installed_server(server):
                raise InstallError('That folder is not a complete, compatible AI App Server installation. '
                                   'Select the correct installed folder or choose Install a new AI App Server first.')
        elif mode == 'new':
            if existing:
                raise InstallError('To update an existing Studio, choose an existing AI App Server above. '
                                   'This avoids creating an unnecessary second server.')
            ensure_empty(server, studio)
        else:
            raise InstallError('Please select a server installation option.')
        if not existing:
            ensure_empty(studio, server)
        return mode, server, studio, existing

    def install(self):
        if self.in_progress:
            return
        try:
            mode, server, studio, existing = self.validated()
        except (OSError, InstallError, ValueError) as exc:
            self.show_error(str(exc))
            return
        overwrite = False
        if existing:
            overwrite = self.messagebox.askyesno(
                'Existing AI Agent Studio found',
                f'An existing AI Agent Studio project is installed at:\n\n{studio}\n\n'
                'Do you want to overwrite its application files with this version?\n\n'
                'YES: back up the previous code and user data; update application files.\n'
                'The database, agents, users and settings remain in their original location.\n\n'
                'NO: leave everything unchanged.', default=self.messagebox.NO, parent=self.root)
            if not overwrite:
                self.append('Cancelled by user. Existing project unchanged.')
                self.status.set('No changes made.')
                return
        elif mode == 'new':
            if not self.messagebox.askyesno('Install AI App Server first?',
                f'Install a separate AI App Server v1.0.5 into:\n{server}\n\n'
                f'Then install AI Agent Studio into:\n{studio}\n\nContinue?',
                default=self.messagebox.NO, parent=self.root):
                self.status.set('No changes made.')
                return

        argv = installation_arguments(mode, server, studio, overwrite)
        self.in_progress = True
        self.completed_path = None
        self.install_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.status.set('Installing. Keep this window open; progress appears below.')
        self.append('-----------------------------------------------------------')
        self.append('Starting install/update: ' + str(studio))
        self.append('Framework: ' + str(server) + ' (' + mode + ')')
        thread = threading.Thread(target=self.install_worker, args=(argv, studio), daemon=True)
        thread.start()

    def install_worker(self, argv, studio):
        try:
            opts = dict(cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                        bufsize=1)
            if sys.platform == 'win32':
                opts['creationflags'] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(argv, **opts)
            with proc.stdout:
                for line in proc.stdout:
                    self.events.put(('line', line.rstrip('\n')))
            code = proc.wait()
            self.events.put(('done', code, str(studio)))
        except Exception as exc:
            self.events.put(('crash', str(exc) + '\n' + traceback.format_exc()))

    def drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'line':
                    self.append(event[1])
                elif event[0] == 'done':
                    self.in_progress = False
                    self.install_button.configure(state='normal')
                    if event[1] == 0:
                        self.completed_path = Path(event[2])
                        self.start_button.configure(state='normal')
                        self.status.set('Installation completed successfully. Studio is ready.')
                        self.append('SUCCESS — AI Agent Studio installation completed.')
                        self.messagebox.showinfo('AI Agent Studio installed',
                            f'Installation completed.\n\nStudio folder:\n{event[2]}\n\n'
                            'The server startup is handled by the installer. This window will stay open.',
                            parent=self.root)
                    else:
                        self.status.set(f'Installation FAILED (exit code {event[1]}). See log below; retry is available.')
                        self.append(f'FAILED — exit code {event[1]}. The window will stay open for diagnosis.')
                        self.messagebox.showerror('AI Agent Studio installation failed',
                            f'The installer returned error {event[1]}.\n\n'
                            'Read the progress log in this window. Correct the problem and try again.\n\n'
                            f'Log: {self.log_path or "shown in this window"}', parent=self.root)
                elif event[0] == 'crash':
                    self.in_progress = False
                    self.install_button.configure(state='normal')
                    self.show_error(event[1])
        except queue.Empty:
            pass
        self.root.after(100, self.drain_events)

    def open_folder(self):
        if not self.completed_path:
            return
        try:
            if sys.platform == 'win32':
                os.startfile(str(self.completed_path))
            else:
                self.append('Installed folder: ' + str(self.completed_path))
        except OSError as exc:
            self.show_error(str(exc))

    def callback_error(self, cls, value, tb):
        self.show_error('Unexpected installer error:\n' + ''.join(traceback.format_exception(cls, value, tb)))

    def close(self):
        if self.in_progress:
            self.messagebox.showwarning('Installation in progress',
                'Installation is still running. Keep this window open until it finishes.', parent=self.root)
            return
        self.root.destroy()


def main(argv=None):
    p = argparse.ArgumentParser(description='AI Agent Studio persistent Windows installer')
    p.add_argument('--self-test', action='store_true', help='Verify the GUI module loads without opening a window')
    p.add_argument('--ui-smoke', action='store_true', help='Open and close the actual Tk wizard for Windows CI')
    opts = p.parse_args(argv)
    if opts.self_test:
        assert (ROOT / 'tools/studio_install.py').is_file()
        print('GUI launcher self-test PASS')
        return 0
    import tkinter as tk
    root = tk.Tk()
    InstallerWizard(root)
    if opts.ui_smoke:
        root.after(350, root.destroy)
    root.mainloop()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        details = traceback.format_exc()
        try:
            dest = logfile()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(details, encoding='utf-8')
        except Exception:
            pass
        try:
            from tkinter import messagebox, Tk
            r = Tk(); r.withdraw()
            messagebox.showerror('AI Agent Studio installer error',
                                 details[-3000:] + '\n\nSee installer log under LocalAppData.', parent=r)
            r.destroy()
        except Exception:
            pass
        raise
