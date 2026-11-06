"""Portable installer with opt-in, backed-up updates of an existing Studio.

Existing AI App Server installations are read-only. Studio user data is preserved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / 'framework'
VERSION = '2.3.4'
REQUIRED = ('engine/pyproject.toml','engine/ai_app_server/server.py',
            'engine/ai_app_server/version.py','engine/ai_app_server/desktop_launcher.py',
            'starter/app.py','tools/bootstrap.py')

class InstallError(RuntimeError):
    pass


def version_of(folder: Path):
    p=folder/'engine/ai_app_server/version.py'
    if not p.is_file():return None
    m=re.search(r'__version__\s*=\s*[\'\"](\d+)\.(\d+)\.(\d+)[\'\"]',p.read_text(encoding='utf-8'))
    return tuple(map(int,m.groups())) if m else None


def valid_source(folder: Path) -> bool:
    return all((folder/p).is_file() for p in REQUIRED) and version_of(folder) in {(1,0,4),(1,0,5)}


def installed_server(folder: Path) -> bool:
    exe=folder/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else folder/'.venv'/'bin'/'python'
    other=folder/'venv'/'Scripts'/'python.exe' if os.name=='nt' else folder/'venv'/'bin'/'python'
    return valid_source(folder) and (exe.is_file() or other.is_file()) and (folder/'app/app.py').is_file()


def state_file() -> Path:
    """User-local pointer to Studio's selected directory, never in the Git repo."""
    override = os.environ.get('AI_AGENT_STUDIO_STATE_FILE')
    if override:
        return Path(override).expanduser().resolve()
    home = Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home() / '.local' / 'state'
    return home / 'AI-Agent-Studio' / 'installations.json'


def is_studio_folder(folder: Path) -> bool:
    """True for a Studio copy including one stopped partway through setup."""
    return (valid_source(folder) and
            (folder/'app/studio_integration/routes.py').is_file() and
            'studio_dir = script.parent' in (folder/'engine/ai_app_server/server.py').read_text(encoding='utf-8'))


def remember_studio(destination: Path) -> None:
    """Best-effort pointer; failure must not prevent an otherwise valid install."""
    if not is_studio_folder(destination):
        return
    p = state_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        temporary = p.with_name(p.name + '.tmp')
        temporary.write_text(__import__('json').dumps({'schema': 1, 'studio': str(destination.resolve())}), encoding='utf-8')
        temporary.replace(p)
    except OSError as ex:
        print('[NOTICE] Could not save the Studio shortcut location:', ex, flush=True)


def remembered_studio() -> Path | None:
    p = state_file()
    try:
        obj = __import__('json').loads(p.read_text(encoding='utf-8'))
        if obj.get('schema') != 1 or not isinstance(obj.get('studio'), str):
            return None
        destination = Path(obj['studio']).expanduser().resolve()
        return destination if is_studio_folder(destination) else None
    except (ValueError, TypeError, OSError):
        return None


def select_installed_studio() -> Path:
    """Use the last known install or ask explicitly for the installed folder."""
    found = remembered_studio()
    if found:
        print('[INFO] Using your previous AI Agent Studio installation:', found, flush=True)
        return found
    suggestion = base_path() / 'AI-Agent-Studio'
    if is_studio_folder(suggestion):
        return suggestion
    selected = pick_path('Select INSTALLED Studio folder (NOT the extracted ZIP)', suggestion)
    if not is_studio_folder(selected):
        raise InstallError('That folder does not contain an installed AI Agent Studio. '
                           'Choose the destination selected during INSTALL.bat, NOT the extracted ZIP: ' + str(selected))
    return selected


def base_path() -> Path:
    return Path(os.environ.get('LOCALAPPDATA') or str(Path.home())) / 'Programs'


def find_existing_server() -> Path | None:
    candidates=[]
    if os.environ.get('AI_APP_SERVER_HOME'):
        candidates.append(Path(os.environ['AI_APP_SERVER_HOME']))
    candidates += [base_path()/'AI-App-Server',Path.home()/'AI-App-Server']
    if os.name=='nt':
        try:
            from ctypes import windll
            mask=windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if mask & (1<<i):
                    drive=Path(f'{chr(65+i)}:/')
                    candidates += [drive/'AI-App-Server',drive/'ai-app-server']
        except Exception:
            pass
    for folder in candidates:
        try:
            if installed_server(folder.expanduser().resolve()):return folder.expanduser().resolve()
        except OSError:
            pass
    return None


def pick_path(title:str, suggested:Path)->Path:
    """Editable directory chooser; does not require the destination already exist."""
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog
        win=tk.Tk()
    except Exception as ex:
        if not sys.stdin.isatty():raise InstallError('No GUI; pass --studio and --server/--install-server paths.') from ex
        result=input(f'{title} [{suggested}]: ').strip().strip('"')
        return Path(result or suggested).expanduser().resolve()
    win.title(title);win.geometry('630x190');win.resizable(False,False)
    frame=ttk.Frame(win,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=title,font=('Segoe UI',13,'bold')).pack(anchor='w',pady=(0,10))
    ttk.Label(frame,text='Enter or browse to a destination folder. Existing files are protected.').pack(anchor='w')
    value=tk.StringVar(value=str(suggested));holder=ttk.Frame(frame);holder.pack(fill='x',pady=8)
    entry=ttk.Entry(holder,textvariable=value);entry.pack(side='left',expand=True,fill='x')
    def browse():
        here=Path(value.get()).expanduser()
        while not here.is_dir() and here!=here.parent:here=here.parent
        found=filedialog.askdirectory(parent=win,initialdir=str(here),title=title)
        if found:value.set(found)
    ttk.Button(holder,text='Browse...',command=browse).pack(side='left',padx=(10,0))
    selection=[]
    def accept():
        if value.get().strip():selection.append(Path(value.get().strip().strip('"')).expanduser().resolve());win.destroy()
    actions=ttk.Frame(frame);actions.pack(anchor='e')
    ttk.Button(actions,text='Cancel',command=win.destroy).pack(side='right')
    ttk.Button(actions,text='Continue',command=accept).pack(side='right',padx=10)
    win.protocol('WM_DELETE_WINDOW',win.destroy);entry.focus_set();win.mainloop()
    if not selection:raise InstallError('Installation cancelled.')
    return selection[0]


def prompt_interactive():
    """Offer detected server, browse for another existing server, or install new."""
    try:
        from tkinter import messagebox
    except ImportError:
        raise InstallError('No Tkinter available. Use --server or --install-server with --studio.')
    found=find_existing_server()
    if found:
        answer=messagebox.askyesnocancel('AI App Server detected',
            f'Compatible AI App Server found at:\n{found}\n\n'
            'YES: use this installation without modifying it.\n'
            'NO: choose a different server or install a new one.\n'
            'CANCEL: cancel setup.')
        if answer is None:raise InstallError('Installation cancelled.')
        if answer:
            mode='existing';server=found
        else:
            use_other=messagebox.askyesnocancel('Choose AI App Server',
                'YES: browse to a different existing AI App Server.\n'
                'NO: install a fresh AI App Server v1.0.5 first.\n'
                'CANCEL: stop installation.')
            if use_other is None:raise InstallError('Installation cancelled.')
            mode='existing' if use_other else 'new'
            server=pick_path('Locate an existing AI App Server',found) if use_other else pick_path('Install AI App Server',base_path()/'AI-App-Server')
    else:
        choice=messagebox.askyesnocancel('AI App Server required',
            'No compatible AI App Server was detected.\n\n'
            'YES: browse for an existing server at another location.\n'
            'NO: install bundled AI App Server v1.0.5 first.\n'
            'CANCEL: stop installation.')
        if choice is None:raise InstallError('Installation cancelled.')
        mode='existing' if choice else 'new'
        server=pick_path('Locate an existing AI App Server',base_path()/'AI-App-Server') if choice else pick_path('Install AI App Server',base_path()/'AI-App-Server')
        if mode=='new' and not messagebox.askyesno('Install AI App Server?',
            f'Install AI App Server v1.0.5 into this NEW, empty folder?\n{server}\n\n'
            'Then install Agent Studio into another folder?'):
            raise InstallError('Installation cancelled.')
    studio=pick_path('Install AI Agent Studio v'+VERSION,base_path()/'AI-Agent-Studio')
    return mode,server,studio


def ensure_empty(destination:Path,other:Path) -> None:
    dest=destination.resolve(); other=other.resolve(); source=ROOT.resolve()
    if dest in source.parents or source in dest.parents or dest==source:
        raise InstallError('Do not install over/inside the extracted source ZIP.')
    if dest==other or dest in other.parents or other in dest.parents:
        raise InstallError('AI App Server and Studio must use separate, non-nested directories.')
    if dest.exists() and (dest.is_symlink() or not dest.is_dir() or any(dest.iterdir())):
        raise InstallError('Refusing to overwrite non-empty or special destination: '+str(dest))



# A non-empty directory is NEVER a valid overwrite target unless it has the
# exact isolated Studio extension and supported AI App Server framework.
def safe_existing_studio(destination: Path, other: Path) -> bool:
    dest = destination.expanduser().resolve()
    ensure_distinct_locations(dest, other)
    if not destination.exists():
        return False
    if destination.is_symlink() or not destination.is_dir():
        raise InstallError('Refusing to overwrite a special destination: ' + str(destination))
    if not any(destination.iterdir()):
        return False
    if not is_studio_folder(dest):
        raise InstallError('This folder contains files but is NOT a recognised AI Agent Studio '
                           'installation. Nothing was overwritten: ' + str(dest))
    return True


def ensure_distinct_locations(destination: Path, other: Path) -> None:
    dest = destination.expanduser().resolve()
    reference = other.expanduser().resolve()
    source = ROOT.resolve()
    if dest == source or dest in source.parents or source in dest.parents:
        raise InstallError('Do not install over/inside the extracted source ZIP.')
    if dest == reference or dest in reference.parents or reference in dest.parents:
        raise InstallError('AI App Server and Studio must use separate, non-nested directories.')


def confirm_overwrite_studio(destination: Path) -> bool:
    """Default is NO; user must explicitly consent to replacement."""
    prompt = (f'An existing AI Agent Studio project was found at:\n\n{destination}\n\n'
              'Do you want to OVERWRITE its application files with this release?\n\n'
              'YES: back up existing project code and data, then update Studio.\n'
              'Your database, agents, users, app settings and personal files stay in place.\n'
              'NO: cancel without changing anything.\n\n'
              'Stop any running Studio instance before updating.')
    try:
        from tkinter import messagebox
        return bool(messagebox.askyesno('Existing AI Agent Studio project', prompt,
                                        default=messagebox.NO))
    except Exception as ex:
        raise InstallError('Existing AI Agent Studio project found at ' + str(destination)
                           + '. No changes made. To explicitly confirm from a terminal, '
                           'use --overwrite-existing.') from ex


# Never touch .venv, data, config, app/app.py, custom user modules or old backups.
# Replace only known release-managed code and documentation. The standalone
# AI App Server (if installed separately) is NEVER modified.
MANAGED_PATHS = (
    'engine', 'starter', 'tools/bootstrap.py', 'tools/studio_install.py',
    'app/studio_integration', 'app/mcp_tools.py', 'START.bat', 'README.md', 'LICENSE',
)
USER_PATHS_TO_BACK_UP = ('data', 'config', 'app/app.py')


def make_studio_update_payload(staging: Path) -> None:
    """Construct a complete replacement from bundled, vetted release files."""
    if not valid_source(BUNDLE) or version_of(BUNDLE) != (1, 0, 5):
        raise InstallError('Bundled AI App Server v1.0.5 is incomplete.')
    shutil.copytree(BUNDLE / 'engine', staging / 'engine',
                    ignore=shutil.ignore_patterns('*.pyc', '__pycache__', '.pytest_cache', '*.egg-info'))
    shutil.copytree(BUNDLE / 'starter', staging / 'starter')
    shutil.copytree(ROOT / 'app/studio_integration', staging / 'app/studio_integration',
                    ignore=shutil.ignore_patterns('*.pyc', '__pycache__', '.pytest_cache'))
    for relative, src in (
        ('tools/bootstrap.py', BUNDLE / 'tools/bootstrap.py'),
        ('tools/studio_install.py', ROOT / 'tools/studio_install.py'),
        ('app/mcp_tools.py', ROOT / 'app/mcp_tools.py'),
        ('START.bat', ROOT / 'START.bat'),
        ('README.md', ROOT / 'README.md'),
        ('LICENSE', ROOT / 'LICENSE'),
    ):
        p = staging / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)
    install_extension(staging / 'engine')
    p = staging / 'engine/ai_app_server/desktop_launcher.py'
    p.write_text(p.read_text(encoding='utf-8').replace(
        'f"AI App Server {service_name(paths(project)[1])[-10:]}.vbs"',
        'f"AI Agent Studio {service_name(paths(project)[1])[-10:]}.vbs"'), encoding='utf-8')


def update_studio(destination: Path, *, no_start: bool = False,
                  copy_only: bool = False) -> Path:
    """Back up then replace *only* managed application code; roll back on errors.

    Copies data/config/app entry to backup without moving them from installation.
    All managed paths are moved to a sibling backup before replacements. On
    failure the previous code is restored; persistent state is never deleted.
    """
    destination = destination.expanduser().resolve()
    if not is_studio_folder(destination):
        raise InstallError('Cannot update an unrecognised Studio project: ' + str(destination))
    runtime = destination / 'data/runtime.json'
    exe = destination / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    if runtime.is_file():
        if not copy_only and exe.is_file():
            # Launcher verifies the process belongs to THIS Studio instance.
            command([exe, '-m', 'ai_app_server.desktop_launcher', 'stop',
                     '--project', destination], destination,
                    'Stop existing Agent Studio before updating')
        if runtime.is_file():
            raise InstallError('Studio may still be running. Stop it using START.bat --stop '
                               'before overwriting; no code or data was changed.')
    parent = destination.parent
    staging = Path(tempfile.mkdtemp(prefix='.ai-studio-update-stage-', dir=parent))
    backup = parent / (destination.name + '-backup-' +
                       datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    transferred = []
    created = []
    try:
        make_studio_update_payload(staging)
        backup.mkdir()
        for rel in USER_PATHS_TO_BACK_UP:
            original = destination / rel
            if not original.exists():
                continue
            if original.is_symlink():
                raise InstallError('Refusing unsafe symlink in data backup: ' + str(original))
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            if original.is_dir():
                shutil.copytree(original, saved, symlinks=False)
            elif original.is_file():
                shutil.copy2(original, saved)
        # Replacement files are prepared before any installed code changes.
        for rel in MANAGED_PATHS:
            old = destination / rel
            new = staging / rel
            if not new.exists() or new.is_symlink():
                raise InstallError('Missing or unsafe release file: ' + str(new))
            if old.is_symlink():
                raise InstallError('Refusing unsafe installed symlink: ' + str(old))
            if old.exists():
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                old.rename(saved)
                transferred.append((old, saved))
            old.parent.mkdir(parents=True, exist_ok=True)
            new.rename(old)
            created.append(old)
        if not copy_only:
            exe = python_setup(destination)
            verify_studio(destination, exe, no_start=no_start)
        remember_studio(destination)
        print('[SUCCESS] Existing Studio project updated:', destination, flush=True)
        print('[BACKUP] Previous code and a copy of persistent data:', backup, flush=True)
        return backup
    except Exception:
        # Restore previous release-managed code even after a partially failed
        # update. Never remove data/, config/, app/app.py or user's other files.
        for target in reversed(created):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for target, saved in reversed(transferred):
            target.parent.mkdir(parents=True, exist_ok=True)
            saved.rename(target)
        print('[ROLLBACK] Existing Studio application files restored.', flush=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)

def clean_copy(source:Path,dest:Path,dirs=(),files=()) -> None:
    """Atomic source copy, with no links or user runtime files."""
    dest.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.ai-studio-stage-',dir=dest.parent))
    try:
        for item in dirs:
            src=source/item
            if not src.is_dir() or any(p.is_symlink() for p in src.rglob('*')):
                raise InstallError('Missing or unsafe source directory: '+str(src))
            shutil.copytree(src,staging/item,
                ignore=shutil.ignore_patterns('*.pyc','__pycache__','.pytest_cache','*.egg-info'))
        for item in files:
            src=source/item
            if not src.is_file() or src.is_symlink():raise InstallError('Missing source file: '+str(src))
            shutil.copy2(src,staging/item)
        if dest.exists():
            if any(dest.iterdir()):raise InstallError('Destination changed while installing; no overwrite performed.')
            dest.rmdir()
        staging.rename(dest)
    finally:
        if staging.exists():shutil.rmtree(staging)


def command(args,cwd:Path,description:str):
    print('\n[INSTALL] '+description,flush=True)
    result=subprocess.run([str(a) for a in args],cwd=cwd,check=False)
    if result.returncode:raise InstallError(f'{description} failed (exit code {result.returncode}).')


def python_setup(destination:Path)->Path:
    exe=destination/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else destination/'.venv'/'bin'/'python'
    if not exe.is_file():command([sys.executable,'-m','venv',destination/'.venv'],destination,'Create isolated Python environment')
    if not exe.is_file():raise InstallError('Virtual environment not created: '+str(exe))
    command([exe,destination/'tools/bootstrap.py'],destination,'Create starter app and storage')
    command([exe,'-m','pip','install','--disable-pip-version-check','-e',str(destination/'engine')],destination,'Install AI App Server dependencies')
    return exe


def new_server(destination:Path,copy_only:bool=False):
    if not valid_source(BUNDLE) or version_of(BUNDLE)!=(1,0,5):
        raise InstallError('Bundled AI App Server v1.0.5 is incomplete.')
    clean_copy(BUNDLE,destination,dirs=('engine','starter','tools'),files=('server-start.template',))
    (destination/'server-start.template').rename(destination/'START.bat')
    shutil.copy2(ROOT/'tools/studio_install.py',destination/'tools/studio_install.py')
    shutil.copy2(ROOT/'LICENSE',destination/'LICENSE')
    (destination/'README.md').write_text('AI App Server v1.0.5. Run START.bat to start this independent server.\n')
    if not copy_only:python_setup(destination)
    print('[OK] Installed separate AI App Server at',destination,flush=True)


EXTENSION_HOOK="""    # Studio extension is loaded from THIS isolated app, never from a shared server.
    studio_dir = script.parent / 'studio_integration'
    if (studio_dir / '__init__.py').is_file():
        import sys
        if str(script.parent) not in sys.path:
            sys.path.insert(0, str(script.parent))
        from studio_integration import install_studio
        app = install_studio(app) or app
    return app
"""


def install_extension(engine:Path):
    p=engine/'ai_app_server/server.py';code=p.read_text(encoding='utf-8')
    if 'studio_dir = script.parent' in code:return
    if code.count('    return app\n') != 1:
        raise InstallError('Incompatible server.py extension point. Existing server was not touched.')
    p.write_text(code.replace('    return app\n',EXTENSION_HOOK),encoding='utf-8')


def fresh_studio(server:Path,destination:Path,copy_only:bool=False,no_start:bool=False):
    if not valid_source(server):raise InstallError('AI App Server framework must be version 1.0.4 or 1.0.5.')
    clean_copy(server,destination,dirs=('engine','starter','tools'))
    (destination/'app').mkdir()
    shutil.copytree(ROOT/'app/studio_integration',destination/'app/studio_integration')
    shutil.copy2(ROOT/'app/mcp_tools.py',destination/'app/mcp_tools.py')
    for fn in ('START.bat','README.md','LICENSE'):shutil.copy2(ROOT/fn,destination/fn)
    # Include recovery code in the installed copy, not another BAT file.
    shutil.copy2(ROOT/'tools/studio_install.py', destination/'tools/studio_install.py')
    install_extension(destination/'engine')
    # Rename the startup shortcut label in the new Studio copy only.
    p=destination/'engine/ai_app_server/desktop_launcher.py'
    s=p.read_text(encoding='utf-8').replace('f"AI App Server {service_name(paths(project)[1])[-10:]}.vbs"',
                                             'f"AI Agent Studio {service_name(paths(project)[1])[-10:]}.vbs"')
    p.write_text(s,encoding='utf-8')
    if copy_only:return
    remember_studio(destination)
    exe=python_setup(destination)
    verify_studio(destination, exe, no_start=no_start)


# Router containers from some FastAPI versions do not expose .path. Inspect
# real endpoint routes safely, including endpoints nested in router containers.
# A missing endpoint MUST still cause installation to fail.
ROUTE_PREFLIGHT = """from pathlib import Path
from tempfile import TemporaryDirectory
from ai_app_server.server import create_app

# Initialise the application against a disposable database instead of altering
# installed users, settings, agents or any existing SQLite files.
with TemporaryDirectory(prefix='ai-studio-route-check-') as tmp:
    app = create_app(Path('app/app.py').resolve(), data_dir=Path(tmp))
    required = {'/admin/studio', '/studio/api/studio/status', '/studio/api/studio/run/events'}
    paths = set()
    seen = set()
    pending = [app]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        path = getattr(item, 'path', None)
        if isinstance(path, str):
            paths.add(path)
        pending.extend(getattr(item, 'routes', ()) or ())
        router = getattr(item, 'router', None)
        if router is not None:
            pending.append(router)
    missing = required - paths
    if missing:
        raise RuntimeError('Missing Studio routes: ' + ', '.join(sorted(missing)))
print('Agent Studio route preflight PASS')
"""


def verify_studio(destination:Path, exe:Path, *, no_start:bool=False):
    command([exe,'-c',ROUTE_PREFLIGHT],destination,'Verify Studio routes and server integration')
    if not no_start:
        command([exe,'-m','ai_app_server.desktop_launcher','install','--project',destination],destination,
                'Start Studio and register Windows sign-in startup')
    print('[SUCCESS] Agent Studio ready at',destination,flush=True)


def resume_server(destination: Path, *, no_start: bool = False, no_browser: bool = False):
    """Recover the separate bundled server without touching persistent data."""
    destination = destination.expanduser().resolve()
    if not valid_source(destination) or is_studio_folder(destination):
        raise InstallError('Not an AI App Server installation: ' + str(destination))
    print('[RECOVERY] Completing AI App Server environment in:', destination, flush=True)
    # Re-run the idempotent bootstrap and editable environment install. Neither
    # step replaces existing app.py, databases, user accounts or settings.
    exe = python_setup(destination)
    if not no_start:
        args=[exe,'-m','ai_app_server.desktop_launcher','install','--project',destination]
        if no_browser: args.append('--no-browser')
        command(args,destination,'Start AI App Server and register Windows sign-in startup')


def resume_studio(destination: Path, *, no_start: bool = False):
    """Finish a partial Studio install in-place; never replace database or app files."""
    destination = destination.expanduser().resolve()
    if not is_studio_folder(destination):
        raise InstallError('Not a valid AI Agent Studio installation (you may have selected the extracted ZIP): ' + str(destination))
    exe = destination/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else destination/'.venv'/'bin'/'python'
    if not exe.is_file() or not (destination/'app/app.py').is_file():
        print('[RECOVERY] Completing missing Python environment or starter app in:', destination, flush=True)
        # bootstrap only creates app.py when missing, and never replaces existing
        # app code, databases, agents, accounts, settings or storage.
        exe = python_setup(destination)
    remember_studio(destination)
    verify_studio(destination, exe, no_start=no_start)


def launch_installed(action: str = 'start', *, no_browser: bool = False):
    """START.bat in a source ZIP finds the real installed instance safely."""
    destination = select_installed_studio()
    if action == 'start':
        resume_studio(destination, no_start=True)
    elif not (destination/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')).is_file():
        raise InstallError('The selected installation has an incomplete Python environment. '
                           'Run START.bat to finish recovery before requesting ' + action + '.')
    exe=destination/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else destination/'.venv'/'bin'/'python'
    args=[exe,'-m','ai_app_server.desktop_launcher',action,'--project',destination]
    if no_browser and action=='start': args.append('--no-browser')
    command(args,destination,'Run '+action+' for installed AI Agent Studio')
    remember_studio(destination)



def main(argv=None):
    parser=argparse.ArgumentParser(description='AI Agent Studio v2.3.4 complete installer')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--server',type=Path,help='Existing AI App Server directory')
    group.add_argument('--install-server',type=Path,help='New, empty AI App Server directory')
    group.add_argument('--resume',type=Path,nargs='?',const=Path('__SELECT_PREVIOUS_STUDIO_INSTALL__'),
                       help='Finish a previous Studio installation; omit the path to choose the installed folder')
    group.add_argument('--launch-installed',action='store_true',help='Start a previously installed Studio from the source folder')
    group.add_argument('--resume-server',type=Path,help='Repair an interrupted separately installed AI App Server')
    parser.add_argument('--studio',type=Path,help='New, empty Studio directory')
    parser.add_argument('--overwrite-existing', action='store_true',
                        help='Explicitly approve a backed-up update to a recognised Studio installation')
    parser.add_argument('--no-start',action='store_true',help='Do not start Studio or enable sign-in startup')
    parser.add_argument('--copy-only',action='store_true',help='Test packaging without installing dependencies')
    parser.add_argument('--action',choices=('start','stop','status','remove-startup'),default='start')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(argv)
    try:
        if sys.version_info<(3,11):raise InstallError('Python 3.11 or newer is required.')
        if sys.platform!='win32' and not args.copy_only:
            raise InstallError('This interactive installer runs on Windows only.')
        if args.resume_server is not None:
            if args.studio is not None or args.copy_only or args.launch_installed:
                raise InstallError('--resume-server takes only a server destination (optional --no-start).')
            resume_server(args.resume_server,no_start=args.no_start,no_browser=args.no_browser)
            return 0
        if args.launch_installed:
            if args.studio is not None or args.copy_only or args.no_start:
                raise InstallError('--launch-installed cannot be combined with fresh-install options.')
            launch_installed(action=args.action,no_browser=args.no_browser)
            return 0
        if args.resume is not None:
            if args.studio is not None or args.copy_only:
                raise InstallError('--resume takes only the installed Studio directory (optional --no-start).')
            to_resume=(select_installed_studio()
                       if args.resume==Path('__SELECT_PREVIOUS_STUDIO_INSTALL__') else args.resume)
            resume_studio(to_resume,no_start=args.no_start)
            return 0
        if not valid_source(BUNDLE):raise InstallError('Full ZIP required: bundled AI App Server is missing.')
        if not (ROOT/'app/studio_integration/routes.py').is_file():raise InstallError('Studio source missing.')
        if args.studio is not None and not (args.server or args.install_server):
            raise InstallError('Specify --server or --install-server with --studio.')
        if (args.server or args.install_server) and args.studio is None:
            raise InstallError('Specify --studio DESTINATION.')
        if args.server or args.install_server:
            mode='existing' if args.server else 'new'
            server=(args.server or args.install_server).expanduser().resolve()
            studio=args.studio.expanduser().resolve()
        else:
            mode,server,studio=prompt_interactive()
        print(f'AI Agent Studio v{VERSION}\nServer: {server} ({mode})\nStudio: {studio}',flush=True)
        # Inspect the Studio destination BEFORE installing anything or creating
        # a second framework. Only a recognised Studio may be overwritten.
        existing = safe_existing_studio(studio, server)
        if existing:
            if not args.overwrite_existing and not confirm_overwrite_studio(studio):
                print('[CANCELLED] Existing AI Agent Studio project unchanged.', flush=True)
                return 0
            # Updated Studio receives only bundled v1.0.5 framework files;
            # a separate existing AI App Server is always read-only.
            update_studio(studio, copy_only=args.copy_only, no_start=args.no_start)
            return 0
        ensure_empty(studio,server)
        if mode=='new':
            ensure_empty(server,studio)
            new_server(server,copy_only=args.copy_only)
        elif not (valid_source(server) if args.copy_only else installed_server(server)):
            raise InstallError('Existing AI App Server must be installed and version 1.0.4–1.0.5: '+str(server))
        fresh_studio(server,studio,copy_only=args.copy_only,no_start=args.no_start)
        return 0
    except (OSError,InstallError,subprocess.SubprocessError, ValueError) as exc:
        print('\nINSTALL FAILED: '+str(exc),file=sys.stderr,flush=True)
        print('Existing installations and user data were not overwritten.',file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
