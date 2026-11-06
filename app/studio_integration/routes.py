"""Mount Agent Studio onto the SAME FastAPI app as AI App Server /admin and /mcp.

No ThreadingHTTPServer, no separate port, no second admin or database reset.
All Studio requests use an existing AI App Server administrator session.
"""
import hmac
import json
import logging
import os
from html import escape
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from . import core
from . import live_tools
from . import mcp_transport
from .persistence import StudioStorage

log = logging.getLogger('agent_studio')
STATIC = Path(__file__).resolve().parent
MAX_BODY=256 * 1024


def install_studio(app):
    """Register Studio routes on the existing AI App Server app instance."""
    db = StudioStorage(app.state.store.directory)
    core.TOOL_FILE = db.directory / 'tools.json'
    # Studio endpoints are registered DIRECTLY on the real AI App Server FastAPI
    # object. Earlier packages used an APIRouter; a Windows installation showed
    # its /admin/studio decorators present but its entire /studio router missing.
    # Direct decorators use the same registration path as /admin/studio and do
    # not depend on the final app.include_router() call.
    def studio_get(path: str):
        return app.get('/studio' + path, include_in_schema=False)

    def studio_post(path: str):
        return app.post('/studio' + path, include_in_schema=False)

    def actor(request: Request, *, write=False, permission=None):
        token=request.cookies.get('aia_admin_session','')
        user=app.state.store.session(token)
        if not user:
            raise HTTPException(401, 'Sign in to your AI App Server administrator account first.')
        if user['must_change_password']:
            raise HTTPException(403, 'Change the initial AI App Server administrator password first.')
        permissions=app.state.store.permissions(user)
        needed=permission or ('manage_settings' if write else 'view_dashboard')
        if needed not in permissions:
            raise HTTPException(403, 'Your AI App Server role does not allow this action.')
        if write:
            received=request.headers.get('x-csrf-token','')
            expected=str(user['csrf'])
            if not hmac.compare_digest(received,expected):
                raise HTTPException(403, 'Security token missing or outdated; reload Studio after login.')
            origin=request.headers.get('origin','')
            expected_origin=(os.environ.get('AI_APP_SERVER_PUBLIC_ORIGIN') or str(request.base_url).rstrip('/')).rstrip('/')
            if not origin or origin.rstrip('/') != expected_origin:
                raise HTTPException(403, 'Request must come from the signed-in AI App Server site.')
        return user

    async def read_json(request: Request):
        ctype=request.headers.get('content-type','').split(';',1)[0].lower()
        if ctype!='application/json':
            raise HTTPException(415, 'Send application/json.')
        size=0; chunks=[]
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_BODY:raise HTTPException(413,'Request exceeds 256 KB.')
            chunks.append(chunk)
        try:
            data=json.loads(b''.join(chunks))
        except (UnicodeDecodeError,ValueError) as exc:
            raise HTTPException(400, 'Invalid JSON.') from exc
        if not isinstance(data,dict):raise HTTPException(400,'Expected a JSON object.')
        return data

    def handle_error(exc):
        if isinstance(exc,(core.AgentDesignError,ValueError,live_tools.LiveToolError,TypeError,KeyError)):
            return JSONResponse({'error':str(exc)[:300]},status_code=400)
        if isinstance(exc,(core.OllamaUnavailable,mcp_transport.MCPError)):
            return JSONResponse({'error':str(exc)[:300]},status_code=503)
        log.exception('Unexpected Studio error')
        return JSONResponse({'error':'Unexpected Agent Studio error; check server logs.'},status_code=500)

    @studio_get('/studio.html')
    async def html_page(request:Request):
        try:user=actor(request)
        except HTTPException as exc:
            if exc.status_code==401:return RedirectResponse('/admin',status_code=303)
            raise
        page=(STATIC/'studio.html').read_text(encoding='utf-8')
        page=admin_editor_markup(page)
        page=page.replace('</head>', '<meta name="studio-csrf" content="'+escape(str(user['csrf']),quote=True)+'" /></head>',1)
        return HTMLResponse(page,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @studio_get('/assets/{file_name:path}')
    def assets(file_name:str,request:Request):
        if file_name not in ('styles.css','landing.js','admin-link.js'):
            actor(request)
        if file_name not in ('styles.css','studio.js','landing.js','builder.css','admin-link.js'):
            raise HTTPException(404,'Asset not found')
        return FileResponse(STATIC/'assets'/file_name,headers={'Cache-Control':'no-store'})

    def admin_editor_markup(page: str) -> str:
        # No <base> element: AI App Server CSP correctly prohibits base-uri.
        return (page.replace('href="assets/', 'href="/studio/assets/')
                    .replace('src="assets/', 'src="/studio/assets/')
                    .replace('href="index.html"', 'href="/"'))

    @app.get('/admin/studio', include_in_schema=False)
    @app.get('/admin/studio/', include_in_schema=False)
    @app.get('/admin/studio/editor', include_in_schema=False)
    async def admin_studio(request:Request):
        try:user=actor(request)
        except HTTPException as exc:
            if exc.status_code==401:
                return RedirectResponse('/admin',status_code=303)
            raise
        page=admin_editor_markup((STATIC/'studio.html').read_text(encoding='utf-8'))
        page=page.replace('</head>', '<meta name="studio-csrf" content="'+escape(str(user['csrf']),quote=True)+'" /></head>',1)
        return HTMLResponse(page,headers={'Cache-Control':'no-store, private',
                                          'X-Content-Type-Options':'nosniff'})

    @studio_get('')
    @studio_get('/')
    @studio_get('/index.html')
    async def old_studio_landing(request:Request):
        return RedirectResponse('/',status_code=303)

    # Respect the AI App Server homepage's production login, maintenance mode,
    # host checks and security headers by letting the original route run first.
    @app.middleware('http')
    async def studio_home_and_admin_link(request:Request,call_next):
        response=await call_next(request)
        if request.method != 'GET' or response.status_code != 200:
            return response
        path=request.url.path
        if path not in ('/','/admin','/admin/'):
            return response
        if 'text/html' not in response.headers.get('content-type',''):
            return response
        if path=='/':
            content=(STATIC/'index.html').read_text(encoding='utf-8')
            # Root path uses the original purple design; all static assets
            # have absolute URLs and do not expose private Studio APIs.
        else:
            try:
                import ai_app_server
                original=Path(ai_app_server.__file__).resolve().parent/'static'/'admin.html'
                content=original.read_text(encoding='utf-8')
            except (ImportError,OSError):
                return response
            content=content.replace('</body>',
                '<script defer src="/studio/assets/admin-link.js"></script></body>',1)
        safe={k:v for k,v in response.headers.items()
              if k.lower() not in ('content-length','content-type','content-encoding','etag','last-modified')}
        safe['Cache-Control']='no-store, private'
        return HTMLResponse(content,headers=safe)

    def mcp_is_enabled():
        try:
            from ai_app_server.mcp_module import read_config
            return read_config(app.state.store.directory).get('enabled') is True
        except ImportError:
            return False

    @studio_get('/api/studio/status')
    def status(request:Request):
        actor(request)
        try:
            models=core.installed_models()
            return {'ready':True,'canRun':bool(models),'ollamaConnected':True,'modelCount':len(models),
                    'mcpLocalReady':mcp_is_enabled(),'builtInTools':20,'customTools':len(core.load_custom_tools()),'aiAppServerIntegrated':True}
        except core.OllamaUnavailable as exc:
            return {'ready':True,'canRun':False,'ollamaConnected':False,'modelCount':0,
                    'mcpLocalReady':mcp_is_enabled(),'builtInTools':20,'customTools':len(core.load_custom_tools()),
                    'aiAppServerIntegrated':True,'error':str(exc)}

    @studio_get('/api/studio/models')
    def models(request:Request):
        actor(request)
        try:return core.installed_models()
        except Exception as exc:return handle_error(exc)

    @studio_get('/api/studio/tools')
    def tools(request:Request):
        actor(request)
        return core.public_tools()+[{'id':t['id'],'name':t['name'],'description':t['description'],
            'kind':t['kind'],'source':'custom','category':'My tools'} for t in core.load_custom_tools().values()]

    @studio_get('/api/studio/tools/custom')
    def tools_custom(request:Request):
        actor(request)
        return list(core.load_custom_tools().values())

    @studio_get('/api/studio/live/status')
    def live_status(request:Request):
        actor(request)
        return live_tools.status()

    @studio_get('/api/studio/sql/tables')
    def sql_tables(request:Request):
        actor(request,permission='manage_databases')
        try:return {'tables':live_tools.list_tables()}
        except Exception as exc:return handle_error(exc)

    @studio_get('/api/studio/sql/columns')
    def sql_columns(request:Request,table:str=''):
        actor(request,permission='manage_databases')
        try:return {'columns':live_tools.columns_for(table)}
        except Exception as exc:return handle_error(exc)

    @studio_get('/api/studio/workflows/latest')
    def latest(request:Request):
        user=actor(request)
        return db.load_workflow(user['username'])

    @studio_post('/api/studio/workflows/latest')
    async def save_latest(request:Request):
        user=actor(request,write=True)
        data=await read_json(request)
        try:
            stamp=db.save_workflow(user['username'],data.get('workflow'))
            return {'ok':True,'updated_at':stamp}
        except ValueError as exc:return handle_error(exc)

    @studio_get('/api/studio/results')
    def results(request:Request):
        user=actor(request)
        return db.results(user['username'])

    @studio_post('/api/studio/results')
    async def save_result(request:Request):
        user=actor(request,write=True)
        data=await read_json(request)
        try:db.save_result(user['username'],data.get('result'));return {'ok':True}
        except ValueError as exc:return handle_error(exc)

    @studio_post('/api/studio/tools/sync')
    async def sync(request:Request):
        user=actor(request,write=True)
        data=await read_json(request)
        try:
            saved=core.save_custom_tools(data.get('tools'))
            app.state.store.audit(user['username'],'studio_tool_save',str(saved))
            return {'ok':True,'saved':saved}
        except Exception as exc:return handle_error(exc)

    @studio_post('/api/studio/live/config')
    async def config(request:Request):
        user=actor(request,write=True,permission='manage_databases')
        data=await read_json(request)
        try:
            result=live_tools.configure(data)
            app.state.store.audit(user['username'],'studio_connection_config')
            return result
        except Exception as exc:return handle_error(exc)

    @studio_post('/api/studio/live/test')
    async def live_test(request:Request):
        user=actor(request,write=True,permission='manage_databases')
        data=await read_json(request)
        try:
            if data.get('kind')=='web':
                return {'ok':True,'preview':live_tools.run_live('live:web_search',{'query':str(data.get('query') or 'Shark vacuum cleaner UK price')[:180]})[:2500]}
            if data.get('kind')=='sql':
                rows=live_tools.list_tables()
                return {'ok':True,'tables':rows[:30],'count':len(rows)}
            raise ValueError('Choose web or sql test.')
        except Exception as exc:return handle_error(exc)

    @studio_post('/api/studio/mcp/connect')
    async def connect_mcp(request:Request):
        actor(request,write=True)
        data=await read_json(request)
        try:
            client=mcp_transport.LocalMCPClient(data.get('url'),data.get('token',''))
            server=client.connect(); listed=client.list_tools()
            return {'ok':True,'name':server.get('serverInfo',{}).get('name','MCP server'),'tools':listed,'url':client.url}
        except Exception as exc:return handle_error(exc)

    @studio_post('/api/studio/design')
    async def design(request:Request):
        actor(request,write=True)
        data=await read_json(request)
        try:return core.design_request(data)
        except Exception as exc:return handle_error(exc)

    def to_line(event):
        return json.dumps(event,ensure_ascii=False)+'\n'

    @studio_post('/api/studio/design/events')
    async def design_stream(request:Request):
        actor(request,write=True)
        data=await read_json(request)
        def events():
            try:
                for event in core.design_events(data):yield to_line(event)
            except Exception:
                log.exception('Design event stream failed')
                yield to_line({'type':'design_failed','error':'Unexpected design failure. Check server logs.'})
        return StreamingResponse(events(),media_type='application/x-ndjson',headers={'X-Accel-Buffering':'no','Cache-Control':'no-store'})

    async def run_payload(request):
        data=await read_json(request)
        workflow=data.get('workflow'); prompt=data.get('prompt'); tools=data.get('tools')
        mcp=data.get('mcp'); approve=data.get('approveRemote') is True
        models=core.installed_models() if isinstance(workflow,dict) and any(isinstance(s,dict) and s.get('type')=='ai' for s in workflow.get('steps',[])) else []
        core.validate_run(workflow,prompt,models,tools,mcp)
        return workflow,prompt,tools,mcp,approve,models

    @studio_post('/api/studio/run')
    async def run(request:Request):
        user=actor(request,write=True)
        try:
            workflow,prompt,tools,mcp,approve,models=await run_payload(request)
            result=core.run_workflow(workflow,prompt,tools,mcp,approve)
            app.state.store.audit(user['username'],'studio_run',str(workflow.get('name','agent'))[:80])
            return result
        except Exception as exc:return handle_error(exc)

    @studio_post('/api/studio/run/events')
    async def run_stream(request:Request):
        user=actor(request,write=True)
        try:workflow,prompt,tools,mcp,approve,models=await run_payload(request)
        except Exception as exc:return handle_error(exc)
        try:app.state.store.audit(user['username'],'studio_run',str(workflow.get('name','agent'))[:80])
        except Exception:log.exception('Studio run audit failed')
        def events():
            try:
                for evt in core.run_events(workflow,prompt,tools,models,mcp,approve):yield to_line(evt)
            except (core.OllamaUnavailable,ValueError,mcp_transport.MCPError,live_tools.LiveToolError) as exc:
                yield to_line({'type':'workflow_failed','error':str(exc)[:500]})
            except Exception:
                log.exception('Studio run failed')
                yield to_line({'type':'workflow_failed','error':'Unexpected workflow error. Check server logs.'})
        return StreamingResponse(events(),media_type='application/x-ndjson',headers={'X-Accel-Buffering':'no','Cache-Control':'no-store'})

    return app
