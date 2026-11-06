"""Complete Agent Studio installer on top of the user's AI App Server.

This is NOT a patch. All Agent Studio source is shipped within this package.
If AI App Server is absent, the installer downloads its public GitHub source
into a previously NONEXISTENT target directory. Existing user data is never
removed, replaced, or relocated.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

PACKAGE=Path(__file__).resolve().parent
REPO_ZIP='https://github.com/tuckbloor/AI-App-Server/archive/refs/heads/main.zip'

class SetupError(RuntimeError):
    pass

def log(msg):
    print(f'\n[AGENT STUDIO] {msg}',flush=True)

def run(*args,cwd=None):
    cmd=[str(v) for v in args]
    result=subprocess.run(cmd,cwd=cwd,check=False)
    if result.returncode:
        raise SetupError('Command failed: '+ ' '.join(cmd) + f' (exit {result.returncode})')

def valid_server(folder):
    return ((folder/'engine'/'ai_app_server'/'__init__.py').is_file()
            and (folder/'tools'/'bootstrap.py').is_file()
            and (folder/'starter'/'app.py').is_file())

def download_fresh_server(target:Path):
    """Only for a path that does not exist. Never replace existing installation."""
    if target.exists():
        raise SetupError(f'Refusing to replace existing directory: {target}')
    log('AI App Server folder is missing. Downloading your public AI-App-Server GitHub source.')
    print('This requires an internet connection for the initial installation.',flush=True)
    request=urllib.request.Request(REPO_ZIP,headers={'User-Agent':'Agent-Studio-Fresh-Installer/2.2'})
    try:
        with urllib.request.urlopen(request,timeout=45) as res:
            content=res.read(35*1024*1024+1)
    except Exception as exc:
        raise SetupError('Could not download AI App Server. Check the internet/GitHub and retry. '
                         'If you have an existing server installation, restore it to E:\\ai-app-server. '
                         f'Detail: {type(exc).__name__}: {exc}') from exc
    if len(content)>35*1024*1024:
        raise SetupError('The GitHub download was unexpectedly large.')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names=zf.namelist()
            if not names or not names[0].startswith('AI-App-Server-'):
                raise SetupError('Unexpected AI App Server archive structure.')
            prefix=names[0].split('/')[0]+'/'
            stage=Path(tempfile.mkdtemp(prefix='.studio-fresh-server-',dir=target.parent))
            try:
                for item in zf.infolist():
                    path=Path(item.filename)
                    if item.is_dir() or not item.filename.startswith(prefix): continue
                    rel=Path(*path.parts[1:])
                    if not rel.parts or rel.is_absolute() or '..' in rel.parts: continue
                    dest=stage/rel
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with zf.open(item) as src, dest.open('wb') as dst: shutil.copyfileobj(src,dst)
                if not valid_server(stage):
                    raise SetupError('GitHub package does not contain the expected AI App Server source files.')
                stage.replace(target)
            finally:
                if stage.exists(): shutil.rmtree(stage,ignore_errors=True)
    except (OSError,zipfile.BadZipFile) as exc:
        raise SetupError(f'Could not extract a complete AI App Server package: {exc}') from exc
    log(f'Fresh AI App Server source installed: {target}')
    print('Source: '+REPO_ZIP)

def select_venv_python(target:Path, *, allow_create=True)->Path:
    for name in ('.venv','venv'):
        py=target/name/'Scripts'/'python.exe' if os.name=='nt' else target/name/'bin'/'python'
        if py.is_file():return py
    if not allow_create:raise SetupError('No Python virtual environment exists.')
    log('Creating the private AI App Server Python environment')
    run(sys.executable,'-m','venv',target/'.venv')
    py=target/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else target/'.venv'/'bin'/'python'
    if not py.is_file():raise SetupError('Python virtual environment creation failed.')
    return py

def install_dependencies(target:Path, python_exe:Path):
    log('Checking AI App Server dependencies (only installs missing packages)')
    chk=subprocess.run([str(python_exe),'-c','import uvicorn, fastapi, ai_app_server.server'],
                       cwd=target,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if chk.returncode == 0:
        log('Python environment already works; no dependency reinstall needed')
        return
    log('Installing AI App Server into its PRIVATE Python environment')
    # Full fresh install: install using the server's own engine metadata.
    run(python_exe,'-m','pip','install','--disable-pip-version-check','-e',str(target/'engine'),cwd=target)
    run(python_exe,'-c','import uvicorn, fastapi, ai_app_server.server',cwd=target)

def install_studio(target:Path,source:Path=PACKAGE,python_exe:Path|None=None):
    """Complete additive install; preserve current server and user-owned files."""
    if not valid_server(target):
        raise SetupError(f'AI App Server is incomplete at {target}. No files overwritten. '
                         'Expected engine/, tools/ and starter/.')
    addon_src=source/'app'/'studio_integration'
    if not (addon_src/'routes.py').is_file() or not (addon_src/'studio.html').is_file():
        raise SetupError('Agent Studio ZIP is incomplete; extract the whole archive again.')
    app=target/'app'
    app.mkdir(exist_ok=True)
    dest=app/'studio_integration'
    backups=target/'backups'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    backup=backups/f'agent-studio-full-backup-{stamp}'
    staging=app/f'.studio-installing-{stamp}'
    staging.mkdir()
    previous_mcp=(app/'mcp_tools.py').exists()
    try:
        shutil.copytree(addon_src,staging,dirs_exist_ok=True)
        # Backup every file this installer is going to replace.
        candidates=['RUN_AGENT_STUDIO_ON_SERVER.py','START AGENT STUDIO ON AI SERVER.bat']
        if dest.exists():
            backup.mkdir(parents=True)
            shutil.copytree(dest,backup/'studio_integration')
        for name in candidates:
            if (target/name).exists():
                backup.mkdir(parents=True,exist_ok=True)
                shutil.copy2(target/name,backup/name)
        # Atomic directory rename where possible.
        if dest.exists():shutil.rmtree(dest)
        staging.replace(dest)
        for name in candidates:
            shutil.copy2(source/name,target/name)
        # Never overwrite anyone's MCP tools. Only fill empty new install.
        mcp_target=app/'mcp_tools.py'
        if not mcp_target.exists():shutil.copy2(source/'app'/'mcp_tools.py',mcp_target)
        # The old installer printed SUCCESS without exercising the actual server.
        # This step loads the REAL installed ai_app_server package and checks
        # that the registered endpoints exist. Failures roll back the add-on.
        if python_exe is not None:
            log('Verifying real installed AI App Server + Studio routes before declaring success')
            check=subprocess.run([str(python_exe),str(target/'RUN_AGENT_STUDIO_ON_SERVER.py'),'--check-only'],
                                 cwd=target,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 timeout=90,check=False)
            print(check.stdout,flush=True)
            if check.returncode:
                raise SetupError('Installed server route preflight FAILED. The Studio upgrade has been rolled back. '
                                 'Read the exact route details above. No database/settings were reset.')
    except Exception:
        if not previous_mcp and (app/'mcp_tools.py').exists():
            (app/'mcp_tools.py').unlink()
        if staging.exists():shutil.rmtree(staging,ignore_errors=True)
        if (backup/'studio_integration').exists():
            if dest.exists():shutil.rmtree(dest,ignore_errors=True)
            shutil.copytree(backup/'studio_integration',dest)
        elif dest.exists():
            shutil.rmtree(dest,ignore_errors=True)
        for name in ['RUN_AGENT_STUDIO_ON_SERVER.py','START AGENT STUDIO ON AI SERVER.bat']:
            if (backup/name).is_file():shutil.copy2(backup/name,target/name)
        raise
    log('Complete Agent Studio installed into AI App Server. NOT a patch.')
    if backup.exists():print('Previous Studio source backed up under: '+str(backup))
    return dest

def prepare(target:Path, *, download=True, deps=True):
    if not (sys.version_info >= (3,11)):
        raise SetupError('Python 3.11 or newer is required. Your Python is '+sys.version.split()[0])
    target=target.expanduser().resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        if not download:raise SetupError('Missing server folder: '+str(target))
        download_fresh_server(target)
    if not valid_server(target):
        raise SetupError('Existing folder is NOT a complete AI App Server: '+str(target)+
                         '. Refusing to replace it or erase data. Restore your original installation or choose another target.')
    # The server-provided bootstrap only creates missing app files; it never replaces existing DB.
    if not (target/'app'/'app.py').is_file():
        log('Creating default app/app.py using the official AI App Server bootstrap')
        run(sys.executable,target/'tools'/'bootstrap.py',cwd=target)
    (target/'data').mkdir(exist_ok=True)
    (target/'config').mkdir(exist_ok=True)
    py=select_venv_python(target)
    if deps:install_dependencies(target,py)
    install_studio(target,python_exe=py)
    return py

def main():
    parser=argparse.ArgumentParser(description='ONE complete Agent Studio installer and launcher')
    parser.add_argument('--server',default='E:/ai-app-server' if os.name=='nt' else str(Path.home()/'ai-app-server'))
    parser.add_argument('--install-only',action='store_true')
    args=parser.parse_args()
    target=Path(args.server)
    print('='*62)
    print('  AGENT STUDIO - COMPLETE INSTALL AND START')
    print('  Original purple interface  |  AI App Server backend')
    print('='*62)
    print('Server location:',target)
    print('Your existing DB, config, login and engine are preserved.')
    try:
        py=prepare(target)
        print('\nSUCCESS: INSTALLED AND VERIFIED. Studio routes are registered.')
        print('Open the NEW homepage at / or sign into /admin and choose Agent Studio.')
        if args.install_only:return 0
        log('Starting the integrated AI App Server on its configured port')
        try:
            run(py,target/'RUN_AGENT_STUDIO_ON_SERVER.py',cwd=target)
        except SetupError as startup_error:
            print('\nAGENT STUDIO INSTALLATION REMAINS VERIFIED; SERVER DID NOT START.',file=sys.stderr)
            print('The existing server may already be running on port 8501, or a runtime dependency may have failed.',file=sys.stderr)
            print(str(startup_error),file=sys.stderr)
            print('Close any previous AI App Server window, then launch START AGENT STUDIO ON AI SERVER.bat.',file=sys.stderr)
            return 2
        return 0
    except SetupError as exc:
        print('\nINSTALL/START ERROR: '+str(exc),file=sys.stderr)
        print('No existing AI App Server database or settings have been deleted.',file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nServer stopped by user.')
        return 0
    except Exception as exc:
        print('\nUnexpected setup failure:',type(exc).__name__,str(exc),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
