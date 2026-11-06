"""Run Agent Studio inside the installed AI App Server. Includes a real route preflight.

Never starts an unrelated server if the actual imported extension does not register.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import importlib
import inspect
import os
import socket
import sys

ROOT=Path(__file__).resolve().parent
APP=ROOT/'app'
DATA=ROOT/'data'

def make_app():
    # Always put THIS installation ahead of any stray old Studio installation.
    sys.path[:] = [p for p in sys.path if Path(p or '.').resolve() != APP.resolve()]
    sys.path.insert(0, str(APP))
    importlib.invalidate_caches()
    from ai_app_server.server import create_app
    from ai_app_server.hosting import initialize_port
    import studio_integration
    from studio_integration import install_studio
    expected=(APP/'studio_integration').resolve()
    real_package=Path(studio_integration.__file__).resolve().parent
    if real_package != expected:
        raise RuntimeError('Agent Studio was imported from '+str(real_package)+
                           ', expected '+str(expected)+'. Cannot safely start.')
    script=APP/'app.py'
    if not script.is_file():
        raise RuntimeError('AI App Server application is missing: '+str(script))
    configured=initialize_port(DATA)
    mode=configured['mode']
    if mode not in ('development','production'):
        raise RuntimeError('AI App Server returned an invalid mode.')
    application=create_app(script,data_dir=DATA,mode=mode,
                           secure_cookies=(mode=='production'),local_only=True)
    # Unlike v1.8, retain the returned app if a newer integration returns a wrapper.
    application=install_studio(application) or application
    return application

def verify_routes(application):
    expected={'/admin/studio','/studio/api/studio/status','/studio/api/studio/run/events'}
    expected_methods={
        '/admin/studio': {'GET'},
        '/studio/api/studio/status': {'GET'},
        '/studio/api/studio/run/events': {'POST'},
    }
    routes=list(getattr(getattr(application,'router',None),'routes',[]) or [])
    paths={str(getattr(item,'path','')) for item in routes}
    missing=sorted(expected-paths)
    wrong_methods=[]
    for item in routes:
        path=str(getattr(item,'path',''))
        if path in expected_methods and not expected_methods[path].issubset(getattr(item,'methods',set()) or set()):
            wrong_methods.append(path)
    if missing or wrong_methods:
        found=sorted(p for p in paths if p.startswith('/studio') or p.startswith('/admin'))
        raise RuntimeError('Studio route verification FAILED. Missing: '+(', '.join(missing) or '(none)')+'; Wrong HTTP methods: '+(', '.join(wrong_methods) or '(none)')+
                           '. Routes registered: '+(', '.join(found[:40]) or '(none)')+
                           '. The existing AI App Server / Studio extension may be incompatible. '+
                           'The installer will restore the previous Studio source if this is an install test.')
    print('[OK] AI App Server and Studio routes registered on the SAME application:')
    for path in sorted(expected):print('  '+path)
    return True

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true',help='Verify real installed routes without binding a port')
    args=parser.parse_args()
    import uvicorn
    from ai_app_server.hosting import initialize_port
    settings=initialize_port(DATA)
    port=int(settings['port']);mode=settings['mode']
    if not 1 <= port <= 65535:raise RuntimeError('Invalid configured port.')
    application=make_app()
    verify_routes(application)
    if args.check_only:
        print('PREFLIGHT PASS: routes are registered; no port was opened.')
        return
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(('127.0.0.1',port))==0:
            raise RuntimeError('Port '+str(port)+' already has a listener. Stop the existing server instance first.')
    print('AI APP SERVER + AGENT STUDIO | '+mode+' | one process, one port')
    print('Homepage: http://127.0.0.1:'+str(port)+'/')
    print('Studio editor: http://127.0.0.1:'+str(port)+'/admin/studio')
    print('Admin login: http://127.0.0.1:'+str(port)+'/admin')
    uvicorn.run(application,host='127.0.0.1',port=port,proxy_headers=False,ws_max_size=65536)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('\nSTARTUP FAILED: '+type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise SystemExit(1)
