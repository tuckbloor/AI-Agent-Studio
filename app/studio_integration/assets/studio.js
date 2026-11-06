'use strict';
(() => {
  const KEY = 'ai-app-server-agent-studio-v0.1'; // Preserve v0.1 saved drafts on upgrade
  const FORMAT = 'agent-studio/workflow';
  const TOOL_FORMAT='agent-studio/tool', TOOL_PACK='agent-studio/tool-pack', TOOL_KEY='ai-app-server-agent-studio-tools-v0.4', RESULTS_KEY='ai-app-server-agent-studio-results-v0.6'; // retain previous custom tools
  const TYPES = Object.freeze({
    trigger: {label:'Trigger', icon:'↗', css:'node-type-trigger', subtitle:'Start the workflow'},
    ai: {label:'AI Agent', icon:'✦', css:'node-type-ai', subtitle:'Think with Ollama'},
    mcp: {label:'Tool hub', icon:'⌘', css:'node-type-mcp', subtitle:'Choose several built-in, custom or connected MCP tools'},
    output: {label:'Output', icon:'✓', css:'node-type-output', subtitle:'Return the result'},
  });
  const byId = id => document.getElementById(id);
  const studioCsrf = () => document.querySelector('meta[name="studio-csrf"]')?.content || '';
  const studioFetch = (url, options={}) => {
    const op = {...options};
    if ((op.method||'GET').toUpperCase() !== 'GET') {
      op.headers = {...(op.headers||{}), 'X-CSRF-Token': studioCsrf()};
    }
    op.credentials='same-origin';
    return fetch(url,op);
  };
  const persistWorkflow = (workflow) => {
    if (!workflow) return;
    studioFetch('/studio/api/studio/workflows/latest', {
      method:'POST',headers:{'Content-Type':'application/json'}, body:JSON.stringify({workflow})
    }).then(r=>{if(!r.ok)throw Error('Server save rejected');})
      .catch(()=>{const el=byId('draft-indicator');if(el)el.textContent='Saved only in browser · server unavailable';});
  };
  let serverSaveTimer;
  let restoringServer=true;
  const scheduleServerSave = (workflow) => {
    window.clearTimeout(serverSaveTimer);
    serverSaveTimer=window.setTimeout(()=>persistWorkflow(workflow),600);
  };
  const restoreServerDraft = async () => {
    try {
      // Keep previously saved browser drafts; the user can import older exports manually.
      if (state.hadSavedDraft || new URLSearchParams(location.search).has('template')) return;
      const r=await studioFetch('/studio/api/studio/workflows/latest');
      if(!r.ok)return;
      const data=await r.json();if(!data.workflow)return;
      state.workflow=validateImported(data.workflow);
      state.selected=state.workflow.steps.find(s=>s.type==='ai')?.id||state.workflow.steps[0]?.id||null;
      state.hadSavedDraft=true;
      localStorage.setItem(KEY,JSON.stringify(state.workflow));render();
      toast('Your saved agent was restored from AI App Server.','success');
    }catch{ /* Initial setup can start with a fresh workflow. */ }
  };
  const makeId = () => (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `step-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const preset = (type, title, description, config = {}) => ({id:makeId(),type,title,description,config});
  // Seven runnable examples. The Tools hub comes BEFORE Ollama so the model
  // receives outputs from every selected tool as labelled evidence.
  const example=(name,steps,instructions,task)=>({name,description:instructions,task:task||instructions,steps:[
    preset('trigger','Start here','Run your saved job',{event:'manual'}),
    preset('mcp','Collect useful information',`${steps.length} tools selected`,{tools:steps,toolArgs:{}}),
    preset('ai','Think with Ollama','Use your chosen AI model',{model:'',instructions}),
    preset('output','Show the answer','Your finished result',{format:'text'})
  ]});
  const TEMPLATES={
    blank:()=>({name:'My first AI agent',description:'Answer questions clearly using my selected Ollama model.',task:'Explain what you can help me do and suggest three useful questions I could ask.',steps:[preset('trigger','Start here','Run your saved job',{event:'manual'}),preset('ai','Think with Ollama','Use a local AI model',{model:'',instructions:'You are a helpful, accurate assistant. Explain clearly in plain English.'}),preset('output','Show the answer','See the result',{format:'text'})]}),
    support:()=>example('Customer support assistant',['builtin:extract_emails','builtin:extract_actions','builtin:word_count'],'Draft a friendly, professional support reply. Use only facts supplied. Do not invent policies or promises.','Write a friendly reply to this example customer: My parcel arrived two days late and the packaging was damaged. Do not promise a refund.'),
    monitor:()=>example('System incident review',['builtin:extract_errors','builtin:extract_urls','builtin:extract_dates'],'Analyse incident logs and errors carefully. Explain observations separately from possible causes, recommend read-only checks first, and never claim you checked a server.','Analyse this EXAMPLE incident: HTTP 500 on /health, SQLSTATE[HYT00] login timeout, database server unreachable. Suggest safe next checks. This is sample text, not a live server check.'),
    knowledge:()=>example('Notes and knowledge assistant',['builtin:extract_headings','builtin:extract_actions','builtin:word_count'],'Use the supplied text and tool outputs to answer questions or organise notes. Acknowledge missing information.','Organise these SAMPLE notes into action items: Monday meeting: fix website errors, update documentation, assign a person to review deployment logs.'),
    research:()=>example('Research digest',['builtin:extract_urls','builtin:extract_dates','builtin:unique_lines'],'Create a clear digest from the provided notes and identified links/dates. You have not visited the links; do not invent article contents.','Create a short digest of these SAMPLE notes: Laravel 13 documentation: https://laravel.com/docs/13.x; next action: test application compatibility. Do not claim you visited the website.'),
    web:()=>example('Live web research',['live:web_search'],'Search the live internet for my topic. Summarise the search results with source URLs, dates when available and clear uncertainty. Do not invent pages not present in search results.','Search the live web for official Laravel 13 security advisories, then summarise the results with source URLs and publication dates when available.'),
    database:()=>example('SQL Server data assistant',['live:sql_readonly'],'Review the selected SQL Server table rows, explain important patterns, and clearly describe the data limitations. Never claim to have changed any data.','Read the selected SQL Server table and summarise up to 20 returned rows in plain English. This is read-only; mention the row limit.'),
    privacy:()=>example('Privacy text review helper',['builtin:redact_emails','builtin:redact_phones','builtin:word_count'],'Explain what sensitive patterns were identified and offer safe handling guidance. Do not claim the provided text was permanently erased.','Review this SAMPLE contact text for private information: Email pat@example.com or call 07700 900123. Show what should be masked.')
  };
  const LIVE_TOOLS=[
    {id:'live:web_search',name:'Live Web Search',description:'Search the web, open relevant public pages, follow matching same-site links and extract identifiable product prices. No API key required by default.',category:'Live information',source:'live',kind:'live',readOnly:true},
    {id:'live:sql_readonly',name:'Read-Only SQL Server',description:'Read a selected table safely. No SQL typing; maximum 20 rows; requires a read-only SQL login.',category:'Live information',source:'live',kind:'live',readOnly:true}
  ];
  const state = {hadSavedDraft:false,builderPlan:null,builderRevision:false,builderBusy:false,builderAbort:null,builderModelChoice:'',liveStatus:{webReady:true,sqlReady:false,webProvider:'bing'},sqlTables:[],sqlColumns:{},workflow:null,tools:[],builtins:[],remoteTools:[],mcpUrl:window.location.origin+'/mcp',mcpToken:'',mcpConnected:false,mcpServerName:'',selected:null,capabilities:{ready:false,canRun:false,models:[],tools:[],ollamaConnected:false,error:''},dragging:null,modalOpen:false,changed:false,run:null,runController:null,lastPrompt:'',savedResults:[]};
  const toast = (message, kind = '') => {
    const element = document.createElement('div'); element.className=`toast ${kind}`; element.textContent=message;
    byId('toast-layer').append(element); window.setTimeout(() => element.remove(), 4600);
  };
  const toolDefinition = raw => {
    if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('Invalid tool object.');
    const {id,name,description='',kind,body}=raw;
    if(typeof id!=='string'||!id||id.length>120)throw Error('Tool ID missing or invalid.');
    if(typeof name!=='string'||!name.trim()||name.length>100)throw Error('Tool name is required (up to 100 characters).');
    if(typeof description!=='string'||description.length>300)throw Error('Tool description is too long.');
    if(!['text','template'].includes(kind))throw Error('Choose Text or Template tool.');
    if(typeof body!=='string'||!body.trim()||body.length>12000)throw Error('Tool content must be 1–12,000 characters.');
    return {id,name:name.trim(),description,kind,body};
  };
  const loadTools=()=>{
    try{const input=JSON.parse(localStorage.getItem(TOOL_KEY)||'[]');if(Array.isArray(input))state.tools=input.slice(0,80).map(toolDefinition);}
    catch{state.tools=[];toast('Could not load your local tools. Import a backup JSON if you have one.','error');}
  };
  const saveTools=()=>{
    try{localStorage.setItem(TOOL_KEY,JSON.stringify(state.tools));
      // The saved custom tools are also exposed through Studio's local MCP
      // endpoint. Do not write into any existing AI App Server installation.
      studioFetch('/studio/api/studio/tools/sync',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({tools:state.tools})})
        .then(r=>{if(!r.ok)throw Error('Local MCP sync failed');})
        .catch(()=>toast('Tool saved in the browser but could not sync to local MCP. Restart Studio and save again.','error'));
      return true;
    }catch{toast('Browser storage failed. Export your tool JSON as a backup.','error');return false;}
  };
  const allAvailable=()=>[...LIVE_TOOLS,...state.builtins,...state.tools.map(t=>({...t,source:'custom',category:'My tools'})),...state.remoteTools];
  const itemById=id=>allAvailable().find(t=>t.id===id);
  const toolName=id=>itemById(id)?.name||id||'Unknown tool';
  const idsFor=step=>Array.isArray(step?.config?.tools)?step.config.tools:(step?.config?.tool?[step.config.tool]:[]);
  const selectFor=(step,id)=>{
    const ids=[...idsFor(step)],at=ids.indexOf(id);
    if(at>=0)ids.splice(at,1);else if(ids.length>=20){toast('Maximum 20 tools in one hub.','error');return;}else ids.push(id);
    step.config.tools=ids;delete step.config.tool;state.selected=step.id;markDirty();render();
  };
  const downloadable=(filename,data)=>{
    const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'});
    const url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=filename;
    document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const slug=value=>value.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'agent-studio';
  const exportTool=t=>{downloadable(`${slug(t.name)}-tool.json`,{format:TOOL_FORMAT,version:1,tool:t});toast('Tool exported. This JSON can be imported into another Studio.','success');};
  const exportAllTools=()=>{downloadable('agent-studio-tools.json',{format:TOOL_PACK,version:1,tools:state.tools});toast('Tool library exported.','success');};
  const mergeTools=(incoming,replaceSelection=false)=>{
    if(!Array.isArray(incoming)||incoming.length>80)throw Error('A tool file may contain up to 80 tools.');
    const ids={};const staged=[...state.tools];
    for(const obj of incoming){const t=toolDefinition(obj);if(staged.length>=80)throw Error('The tool library limit is 80.');
      const old=staged.find(x=>x.id===t.id);if(old){if(JSON.stringify(old)===JSON.stringify(t)){ids[t.id]=t.id;continue;}const oldId=t.id;t.id=makeId();ids[oldId]=t.id;}else ids[t.id]=t.id;
      staged.push(t);
    }
    state.tools=staged;saveTools();render();return ids;
  };
  const importToolFile=async file=>{
    if(!file)return;if(file.size>1024*1024){toast('Tool JSON exceeds 1 MB.','error');return;}
    try{const obj=JSON.parse(await file.text());const incoming=obj?.format===TOOL_FORMAT&&obj.version===1?[obj.tool]:obj?.format===TOOL_PACK&&obj.version===1?obj.tools:null;
      if(!incoming)throw Error('This is not an Agent Studio tool or tool pack.');mergeTools(incoming);toast(`${incoming.length} tool(s) imported. Select one under your Tool hub.`,'success');}
    catch(err){toast('Tool import rejected: '+err.message,'error');}
  };
  const loadResults=()=>{try{const items=JSON.parse(localStorage.getItem(RESULTS_KEY)||'[]');state.savedResults=Array.isArray(items)?items.filter(r=>r&&typeof r.id==='string'&&typeof r.output==='string').slice(0,20):[];}catch{state.savedResults=[];}updateResultsCount();};
  const restoreServerResults = async () => {
    try {
      const response=await studioFetch('/studio/api/studio/results');
      if(!response.ok)return;
      const records=await response.json();if(!Array.isArray(records))return;
      const all=[...state.savedResults,...records];
      const seen=new Set();
      state.savedResults=all.filter(r=>{
        if(!r||typeof r.id!=='string'||typeof r.output!=='string'||seen.has(r.id))return false;
        seen.add(r.id);return true;
      }).sort((a,b)=>String(b.when||'').localeCompare(String(a.when||''))).slice(0,20);
      localStorage.setItem(RESULTS_KEY,JSON.stringify(state.savedResults));
      updateResultsCount();
    }catch{ /* Offline browser results remain available. */ }
  };
  const updateResultsCount=()=>{if(byId('results-count'))byId('results-count').textContent=String(state.savedResults.length);};
  const downloadText=(filename,contents,type='text/plain;charset=utf-8')=>{const blob=new Blob([contents],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const copyText=async contents=>{try{await navigator.clipboard.writeText(contents);toast('Copied to clipboard.','success');}catch{toast('Copy was blocked. Select the text and press Ctrl+C.','error');}};
  const saveResult=(run)=>{
    if(!run||!run.finished||!run.success||!run.output.trim()){toast('There is no completed answer to save.','error');return;}
    if(state.savedResults.some(r=>r.runId===run.id)){toast('This answer is already saved.','success');return;}
    const record={id:makeId(),runId:run.id,agentName:run.agentName,when:new Date().toISOString(),prompt:run.prompt.slice(0,8000),output:run.output.slice(0,30000),elapsedMs:Date.now()-run.started};
    const next=[record,...state.savedResults].slice(0,20);
    try{localStorage.setItem(RESULTS_KEY,JSON.stringify(next));state.savedResults=next;updateResultsCount();studioFetch('/studio/api/studio/results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({result:record})}).catch(()=>{});toast('Result saved. Open Saved results to view it.','success');}
    catch{toast('Could not save locally. Download the answer as a text file.','error');}
  };
  const focusDetails=()=>{closeModal();byId('agent-details').scrollIntoView({behavior:'smooth',block:'center'});byId('workflow-description').focus();};
  const focusAIInstructions=()=>{const step=firstAiStep();if(!step){toast('Add an AI step first.','error');return;}if(state.modalOpen)closeModal();state.selected=step.id;render();byId('inspector-panel').scrollIntoView({behavior:'smooth',block:'start'});byId('setting-instructions')?.focus();};
  const openResultItem=record=>{byId('modal').classList.remove('run-mode');modal('SAVED RESULT',record.agentName,`<div class="result-info">Saved ${html(new Date(record.when).toLocaleString())} · Stored only in this browser</div><div class="field"><label>Original question</label><pre class="saved-result-text">${html(record.prompt)}</pre></div><div class="field"><label>Answer</label><pre class="saved-result-text">${html(record.output)}</pre></div>`,[
    {label:'← All results',action:openResults},
    {label:'Download .txt',action:()=>downloadText(`${slug(record.agentName)}-answer.txt`,record.output)},
    {label:'Copy answer',action:()=>copyText(record.output)},
    {label:'Use as next input',primary:true,action:()=>{closeModal();runAgent(record.output.slice(0,8000));}}
  ]);};
  const openResults=()=>{byId('modal').classList.remove('run-mode');const items=state.savedResults;modal('YOUR WORK','Saved answers',`<p>These answers are stored <strong>in this browser on this PC</strong>. Export important answers as text files. No answer is saved automatically.</p><div class="results-list">${items.length?items.map((r,i)=>`<div class="result-list-item"><div><strong>${html(r.agentName)}</strong><small>${html(new Date(r.when).toLocaleString())}</small><p>${html(r.output.slice(0,160))}${r.output.length>160?'…':''}</p></div><div class="result-list-buttons"><button type="button" class="small-button" data-open-result="${html(r.id)}">View</button><button type="button" class="small-button danger-button" data-delete-result="${html(r.id)}" aria-label="Delete result ${i+1}">Delete</button></div></div>`).join(''):'<div class="inspector-note">No saved answers yet. Run your agent, then click <strong>Save result</strong> after it finishes.</div>'}</div>`,[{label:'Back to editor',primary:true,action:closeModal}]);
    byId('modal-content').querySelectorAll('[data-open-result]').forEach(b=>b.addEventListener('click',()=>{const r=items.find(x=>x.id===b.dataset.openResult);if(r)openResultItem(r);}));
    byId('modal-content').querySelectorAll('[data-delete-result]').forEach(b=>b.addEventListener('click',()=>{const id=b.dataset.deleteResult;state.savedResults=state.savedResults.filter(x=>x.id!==id);try{localStorage.setItem(RESULTS_KEY,JSON.stringify(state.savedResults));updateResultsCount();openResults();toast('Saved answer deleted.');}catch{toast('Could not update saved results.','error');}}));
  };
  const openExamples=()=>{document.querySelector('.templates-side')?.scrollIntoView({behavior:'smooth',block:'center'});toast('Choose one of the seven examples in the left menu.');};
  const openToolGuide=()=>{const step=state.workflow.steps.find(s=>s.type==='mcp');if(step)openToolPicker(step.id);else modal('ADD YOUR FIRST TOOL','Choose a tool hub', '<p>Your current agent has no Tool hub. Add one, then choose from 20 local and two live tools.</p>',[{label:'Cancel',action:closeModal},{label:'Add a tool hub',primary:true,action:()=>{closeModal();addToolHub();}}]);};
  const addToolHub=()=>{const step=preset('mcp','Choose my tools','Run selected tools',{tools:[],toolArgs:{}}),position=state.workflow.steps.findIndex(s=>s.type==='ai');state.workflow.steps.splice(position<0?1:position,0,step);state.selected=step.id;markDirty();render();openToolPicker(step.id);};
  const save = () => {
    try {localStorage.setItem(KEY, JSON.stringify(state.workflow));state.changed=false;byId('draft-indicator').textContent='Saved locally';persistWorkflow(state.workflow);toast('Workflow saved to AI App Server.','success');return true;}
    catch {toast('Browser storage is unavailable. Export the JSON file instead.','error');return false;}
  };
  // Every editor change is stored immediately, so selecting a model cannot be lost
  // when the user changes cards or reloads the page. Preserve v0.1/v0.2 drafts.
  let storageWarningShown=false;
  const markDirty = () => {
    state.changed=true;
    try {
      localStorage.setItem(KEY, JSON.stringify(state.workflow));
      state.changed=false;
      byId('draft-indicator').textContent='Auto-saved';if(!restoringServer)scheduleServerSave(state.workflow);
    } catch {
      byId('draft-indicator').textContent='Not saved · Export JSON';
      if (!storageWarningShown) { toast('Could not auto-save. Please export your JSON file.', 'error'); storageWarningShown=true; }
    }
  };
  const createWorkflow = templateName => {
    const previousModel=state.workflow?.steps.find(s=>s.type==='ai')?.config?.model;
    const data = TEMPLATES[templateName] ? TEMPLATES[templateName]() : TEMPLATES.blank();
    const bestModel=(previousModel&&state.capabilities.models.includes(previousModel))?previousModel:state.capabilities.models[0]||'';
    data.steps.filter(s=>s.type==='ai').forEach(s=>{if(!s.config.model)s.config.model=bestModel;});
    state.workflow={format:FORMAT,version:1,id:makeId(),name:data.name,description:data.description||'',task:data.task||data.description||'',steps:data.steps};state.selected=data.steps.find(s=>s.type==='ai')?.id || data.steps[0]?.id || null;
    markDirty();render();if(!document.querySelector('.studio-main')?.classList.contains('builder-visible'))toast(`Opened: ${data.name}`,'success');
  };
  const validateImported = obj => {
    if(!obj || typeof obj!=='object' || Array.isArray(obj)) throw Error('This file is not a workflow object.');
    if(obj.format!==FORMAT || obj.version!==1) throw Error('Unsupported workflow format or version.');
    if(typeof obj.name!=='string'||!obj.name.trim()||obj.name.length>100) throw Error('Invalid workflow name.');
    if(obj.description!==undefined&&(typeof obj.description!=='string'||obj.description.length>500))throw Error('Agent description must be 500 characters or less.');
    if(obj.task!==undefined&&(typeof obj.task!=='string'||obj.task.length>2000))throw Error('Saved task must be 2,000 characters or less.');
    if(!Array.isArray(obj.steps) || obj.steps.length<1 || obj.steps.length>30) throw Error('Workflows must contain 1 to 30 steps.');
    const ids = new Set();
    const steps=obj.steps.map((s,index)=>{
      if(!s || typeof s!=='object' || !Object.hasOwn(TYPES,s.type)) throw Error(`Unsupported step at position ${index+1}.`);
      if(typeof s.title!=='string'||s.title.length>100||typeof s.description!=='string'||s.description.length>250) throw Error(`Invalid text in step ${index+1}.`);
      if(!s.config || typeof s.config!=='object' || Array.isArray(s.config)) throw Error(`Invalid settings in step ${index+1}.`);
      const cfg={};for(const [k,v] of Object.entries(s.config)){if(k==='tools'){
            if(!Array.isArray(v)||v.length>20||v.some(id=>typeof id!=='string'||id.length>180))throw Error(`Invalid selected tools in step ${index+1}.`);
            cfg.tools=[...new Set(v)];
          }else if(k==='toolArgs'){
            if(!v||typeof v!=='object'||Array.isArray(v)||JSON.stringify(v).length>12000)throw Error(`Invalid MCP tool inputs in step ${index+1}.`);
            cfg.toolArgs=v;
          }else{
            if(!['event','model','instructions','tool','arguments','format'].includes(k)||typeof v!=='string'||v.length>6000) throw Error(`Invalid configuration in step ${index+1}.`);
            cfg[k]=v;
          }}
      if(typeof s.id!=='string'||!s.id.trim()||ids.has(s.id)) throw Error(`Invalid or repeated ID in step ${index+1}.`);
      ids.add(s.id);
      return {id:s.id,type:s.type,title:s.title,description:s.description,config:cfg};
    });
    return {format:FORMAT,version:1,id:typeof obj.id==='string'&&obj.id.length<150?obj.id:makeId(),name:obj.name,description:obj.description||'',task:obj.task||obj.description||'',steps,tools:Array.isArray(obj.tools)?obj.tools:[]};
  };
  const loadDraft = () => {
    const query = new URLSearchParams(location.search).get('template');
    if(query && Object.hasOwn(TEMPLATES,query)) return createWorkflow(query);
    try{const draft=localStorage.getItem(KEY);if(draft){state.hadSavedDraft=true;state.workflow=validateImported(JSON.parse(draft));state.selected=state.workflow.steps.find(s=>s.type==='ai')?.id||state.workflow.steps[0]?.id||null;state.changed=false;byId('draft-indicator').textContent='Saved locally';render();return;}}catch{toast('A saved draft could not be loaded. A new design was opened.','error');}
    createWorkflow('blank');
  };
  const nodeLabel = step => step.type==='ai' ? (step.config.model || 'Choose an Ollama model') : step.type==='mcp' ? (idsFor(step).length+' tool(s) ready') : step.description;
  const renderCanvas = () => {
    const canvas=byId('workflow-canvas');canvas.replaceChildren();
    state.workflow.steps.forEach((step,index)=>{
      if(index>0){const connector=document.createElement('span');connector.className='node-connector';connector.setAttribute('aria-hidden','true');canvas.append(connector);}
      const node=document.createElement('button');node.type='button';node.className=`workflow-node${step.id===state.selected?' selected':''}`;node.dataset.id=step.id;node.draggable=true;
      node.setAttribute('aria-label',`Step ${index+1}: ${step.title}. Click to edit; drag to reorder.`);
      node.innerHTML=`<div class="workflow-node-top"><span class="workflow-node-icon ${TYPES[step.type].css}">${TYPES[step.type].icon}</span><span class="node-serial">STEP ${String(index+1).padStart(2,'0')}</span></div><h3>${html(step.title)}</h3><p>${html(nodeLabel(step))}</p><span class="node-port node-port-left" aria-hidden="true"></span><span class="node-port node-port-right" aria-hidden="true"></span>`;
      node.addEventListener('click',()=>{state.selected=step.id;render();byId('inspector-panel').classList.add('is-open');});
      node.addEventListener('dragstart',event=>{state.dragging=step.id;node.classList.add('dragging');event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',step.id);});
      node.addEventListener('dragend',()=>{state.dragging=null;canvas.querySelectorAll('.workflow-node').forEach(n=>n.classList.remove('dragging','drop-target'));});
      node.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='move';node.classList.add('drop-target');});
      node.addEventListener('dragleave',()=>node.classList.remove('drop-target'));
      node.addEventListener('drop',event=>{event.preventDefault();node.classList.remove('drop-target');moveStep(state.dragging,step.id);});
      const stack=document.createElement('div');stack.className='node-stack';stack.append(node);
      if(step.type==='mcp'){
        const branch=document.createElement('section');branch.className='tool-branch';branch.setAttribute('aria-label','Selected tools for '+step.title);
        const ids=idsFor(step);
        branch.innerHTML=`<div class="tool-branch-head"><span>↓ TOOLS RUN IN THIS ORDER</span><small>${ids.length} selected</small></div>
          <div class="tool-branch-list">${ids.length?ids.map((id,i)=>`<div class="branch-tool active"><span class="branch-index">${i+1}</span><span><strong>${html(toolName(id))}</strong><small>${html(itemById(id)?.source==='remote'?'Connected MCP server':itemById(id)?.source==='live'?'Live connection · configurable':itemById(id)?.source==='custom'?'My tool':'Built-in text tool')}</small></span><button class="branch-remove" type="button" data-remove-tool="${html(id)}" title="Remove ${html(toolName(id))}">×</button></div>`).join(''):'<p class="branch-empty">No tools selected. Add one below.</p>'}</div>
          <button type="button" class="branch-create">+ Choose tools (${state.builtins.length} built in)</button>
          <div class="tool-branch-note">Tool results feed into the next step. Click a selected tool to remove it.</div>`;
        branch.querySelectorAll('[data-remove-tool]').forEach(b=>b.addEventListener('click',()=>selectFor(step,b.dataset.removeTool)));
        branch.querySelector('.branch-create').addEventListener('click',()=>openToolPicker(step.id));
        stack.append(branch);
      }
      canvas.append(stack);
    });
    const add=document.createElement('button');add.className='add-end';add.type='button';add.title='Add a step';add.setAttribute('aria-label','Add a step');add.textContent='+';add.addEventListener('click',openAdd);canvas.append(add);
    byId('step-count').textContent=String(state.workflow.steps.length);
  };
  const moveStep = (from,to) => {
    if(!from||from===to)return;
    const steps=state.workflow.steps;const fromIndex=steps.findIndex(s=>s.id===from);const toIndex=steps.findIndex(s=>s.id===to);
    if(fromIndex<0||toIndex<0)return;
    const [item]=steps.splice(fromIndex,1);steps.splice(toIndex,0,item);markDirty();render();
  };
  const field = (key,label,value,kind='text',placeholder='',help='')=>{
    const id=`setting-${key}`;const control=kind==='textarea'?`<textarea id="${id}" data-setting="${key}" maxlength="6000" placeholder="${html(placeholder)}">${html(value)}</textarea>`:
      `<input id="${id}" data-setting="${key}" maxlength="${key==='instructions'||key==='arguments'?6000:180}" type="text" value="${html(value)}" placeholder="${html(placeholder)}"/>`;
    return `<div class="field"><label for="${id}">${label}</label>${control}${help?`<span class="field-help">${help}</span>`:''}</div>`;
  };
  const selectField = (key,label,value,options,help='')=>`<div class="field"><label for="setting-${key}">${label}</label><select data-setting="${key}" id="setting-${key}">${options.map(opt=>`<option value="${html(opt[0])}"${opt[0]===value?' selected':''}>${html(opt[1])}</option>`).join('')}</select>${help?`<span class="field-help">${help}</span>`:''}</div>`;
  // An always-visible model picker. It controls the first AI step, even if a
  // Trigger/Output card is selected and the detailed model settings disappear.
  const firstAiStep = () => state.workflow?.steps.find(step=>step.type==='ai');
  const refreshMainModel = () => {
    const picker=byId('main-ollama-model');
    if (!picker) return;
    const step=firstAiStep();
    const selected=step?.config.model||'';
    const models=state.capabilities.models;
    const options=[['', models.length?'Choose your model…':'Checking for Ollama models…'],...models.map(name=>[name,name])];
    if(selected && !models.includes(selected))options.push([selected,selected+' (currently unavailable)']);
    picker.innerHTML=options.map(([name,label])=>`<option value="${html(name)}"${selected===name?' selected':''}>${html(label)}</option>`).join('');
    picker.disabled=!step||models.length===0;
    const indicator=byId('main-model-status');
    if(indicator)indicator.textContent=models.length?`${models.length} installed · Auto-saved`:state.capabilities.error||'Start Ollama, then refresh';
  };
  const renderInspector = () => {
    const step=state.workflow.steps.find(s=>s.id===state.selected);
    if(!step){byId('inspector-title').textContent='Select a step';byId('inspector-description').textContent='Choose a card on the canvas to configure it.';byId('inspector-body').textContent='Your agent settings will appear here.';return;}
    byId('inspector-title').textContent=step.title;
    byId('inspector-description').textContent=TYPES[step.type].subtitle;
    let details=field('title','Step name',step.title,'text','Give this step a name');
    details+=field('description','What this step does (edit here)',step.description,'text','Explain this step in plain English');
    if(step.type==='trigger')details+=selectField('event','When should it start?',step.config.event||'manual',[['manual','Manual start'],['webhook','Webhook (requires server setup)']], 'The server must register and authorise any webhook before it can run.');
    if(step.type==='ai'){
      const detected=state.capabilities.models;
      const selectedModel=step.config.model||'';
      const options=[['','Select an installed Ollama model…'],...detected.map(name=>[name,name])];
      if(selectedModel&&!detected.includes(selectedModel))options.push([selectedModel,selectedModel+' (not detected)']);
      details+=selectField('model','Ollama model',selectedModel,options,'Choose a model installed on this PC. No typing model names.');
      details+=`<button type="button" class="small-button" id="refresh-models">↻ Refresh Ollama models</button>`;
      details+=`<div class="inspector-note" style="margin-top:10px">${state.capabilities.ollamaConnected ? (detected.length?`✓ Ollama connected · ${detected.length} model(s) detected.`:'Ollama connected but no models installed. Run <code>ollama pull llama3.2</code> in PowerShell.') : 'Ollama is offline or unavailable. Start Ollama, then click Refresh models.'}</div>`;
      details+=field('instructions','Agent instructions',step.config.instructions||'','textarea','Describe exactly what the agent should do');
    }
    if(step.type==='mcp'){
      details+=`<div class="inspector-note"><strong>What happens here?</strong> Agent Studio runs your selected tools from top to bottom, gathers their answers, then gives the results to the next Ollama step. These are real MCP-exposed local tools; connected server tools appear after you connect.</div>`;
      details+=`<div class="selected-tools">${idsFor(step).length?idsFor(step).map((id,i)=>`<div class="selected-tool-row"><span>${i+1}. ${html(toolName(id))}</span><button type="button" data-up-tool="${html(id)}" title="Move up">↑</button><button type="button" data-down-tool="${html(id)}" title="Move down">↓</button><button type="button" data-clear-tool="${html(id)}" title="Remove">×</button></div>`).join(''):'<p>No tools selected.</p>'}</div>`;
      details+=`<button type="button" class="small-button strong-button" id="browse-tools">+ Choose one or more tools</button> <button type="button" class="small-button" id="create-local-tool">+ Create your own tool</button>`;
      details+=`<button type="button" class="small-button" id="manage-local-tools">Manage / import / export your tools</button>`;
      if(idsFor(step).includes('live:web_search')){
        const q=step.config.toolArgs?.['live:web_search']?.query||'{{input}}';
        details+=`<div class="live-setup"><h3>🌐 Live Web Search</h3><p>Search the web for the text you enter when running, or type a fixed topic below.</p><div class="field"><label for="live-web-query">Search topic</label><input id="live-web-query" value="${html(q)}" placeholder="{{input}}"/></div><div class="inspector-note">${state.liveStatus.webReady?'✓ Web search configured':'Built-in search is ready by default; no API key is required.'}</div><button class="small-button" type="button" id="live-web-configure">Configure Web Search</button></div>`;
      }
      if(idsFor(step).includes('live:sql_readonly')){
        const args=step.config.toolArgs?.['live:sql_readonly']||{},table=args.table||'',columns=state.sqlColumns[table]||[];
        const tableNames=[...new Set([...state.sqlTables,...(table?[table]:[])])];
        const columnNames=[...new Set([...columns,...(args.filter_column?[args.filter_column]:[])])];
        details+=`<div class="live-setup"><h3>▦ Read-Only SQL Server</h3><p>Choose a database table. Studio generates a SELECT query; it cannot run SQL you type.</p>
          <div class="field"><label for="live-sql-table">Database table (required)</label><select id="live-sql-table"><option value="">${state.sqlTables.length?'Choose a table…':'Connect SQL Server and load tables…'}</option>${tableNames.map(x=>`<option value="${html(x)}" ${x===table?'selected':''}>${html(x)}</option>`).join('')}</select></div>
          <div class="field"><label for="live-sql-limit">Maximum rows to read</label><select id="live-sql-limit">${[5,10,20].map(n=>`<option value="${n}" ${Number(args.limit||10)===n?'selected':''}>${n} rows</option>`).join('')}</select></div>
          <div class="field"><label for="live-sql-filter">Optional exact-match column filter</label><select id="live-sql-filter"><option value="">No filter</option>${columnNames.map(x=>`<option value="${html(x)}" ${x===args.filter_column?'selected':''}>${html(x)}</option>`).join('')}</select></div>
          <div class="field"><label for="live-sql-value">Value to match (optional)</label><input id="live-sql-value" value="${html(args.filter_value||'')}" placeholder="Example: Active"/></div>
          <div class="inspector-note">${state.liveStatus.sqlReady?'✓ SQL connection configured':'Connect a read-only SQL Server account before running.'} No INSERT, UPDATE, DELETE or raw SQL.</div>
          <button type="button" class="small-button" id="live-sql-reload">↻ Load tables</button> <button type="button" class="small-button" id="live-sql-configure">Configure SQL Server</button></div>`;
      }
      details+=`<div class="field"><label for="tool-args-edit">Optional inputs for connected MCP tools (JSON)</label><textarea id="tool-args-edit" rows="3" spellcheck="false" placeholder='{"remote:tool_name":{"query":"{{input}}"}}'>${html(JSON.stringify(step.config.toolArgs||{},null,2))}</textarea><span class="field-help">Most read-only tools accepting text work automatically. For tools with other required inputs, enter a map of selected tool IDs to parameter objects. Use {{input}} to insert the current input.</span></div>`;
    }
    if(step.type==='output')details+=selectField('format','Output format',step.config.format||'text',[['text','Plain text'],['markdown','Markdown'],['json','JSON']]);
    details+=`<div class="inspector-divider"></div><div class="inspector-actions"><button type="button" class="small-button" id="move-left">← Move back</button><button type="button" class="small-button" id="move-right">Move forward →</button><button type="button" class="small-button danger-button" id="remove-step">Remove</button></div>`;
    details+=`<div class="inspector-note">Local tools run now. Connected MCP tools may have side effects; approval is requested for tools not marked read-only. Run trusted tools with your AI App Server administrator session.</div>`;
    byId('inspector-body').className='inspector-form';byId('inspector-body').innerHTML=details;
    byId('inspector-body').querySelectorAll('[data-setting]').forEach(control=>control.addEventListener('input',()=>{
      const key=control.dataset.setting;const value=control.value;
      if(key==='title'||key==='description')step[key]=value;else step.config[key]=value;
      markDirty();
      if(key==='title'||key==='description'){const node=byId('workflow-canvas').querySelector(`[data-id="${CSS.escape(step.id)}"]`);if(node){const el=node.querySelector(key==='title'?'h3':'p');if(el&&step.type!=='ai'&&step.type!=='mcp')el.textContent=value;else if(el&&key==='title')el.textContent=value;}byId('inspector-title').textContent=step.title;}
      if(key==='model'){refreshMainModel();refreshSourceDetail();}
    }));
    byId('inspector-body').querySelectorAll('[data-setting]').forEach(control=>control.addEventListener('change',()=>render()));
    const refreshModels=byId('refresh-models');if(refreshModels)refreshModels.addEventListener('click',async()=>{refreshModels.disabled=true;refreshModels.textContent='Checking Ollama…';await serverStatus();toast(state.capabilities.models.length?`${state.capabilities.models.length} installed Ollama model(s) found.`:'No Ollama models found. See Connections.',state.capabilities.models.length?'success':'error');});
    byId('browse-tools')?.addEventListener('click',()=>openToolPicker(step.id));
    byId('create-local-tool')?.addEventListener('click',()=>openToolEditor(null,step.id));
    byId('inspector-body').querySelectorAll('[data-clear-tool]').forEach(b=>b.addEventListener('click',()=>selectFor(step,b.dataset.clearTool)));
    const shift=(id,delta)=>{const arr=[...idsFor(step)];const i=arr.indexOf(id),j=i+delta;if(i<0||j<0||j>=arr.length)return;[arr[i],arr[j]]=[arr[j],arr[i]];step.config.tools=arr;markDirty();render();};
    byId('inspector-body').querySelectorAll('[data-up-tool]').forEach(b=>b.addEventListener('click',()=>shift(b.dataset.upTool,-1)));
    byId('inspector-body').querySelectorAll('[data-down-tool]').forEach(b=>b.addEventListener('click',()=>shift(b.dataset.downTool,1)));
    byId('tool-args-edit')?.addEventListener('change',event=>{try{const obj=JSON.parse(event.target.value||'{}');if(!obj||typeof obj!=='object'||Array.isArray(obj))throw Error();step.config.toolArgs=obj;markDirty();toast('MCP tool inputs saved.','success');}catch{toast('MCP tool inputs must be a JSON object.','error');}});
    byId('live-web-configure')?.addEventListener('click',openLiveSettings);
    byId('live-sql-configure')?.addEventListener('click',openLiveSettings);
    byId('live-web-query')?.addEventListener('input',e=>{setLiveArgs(step,'live:web_search','query',e.target.value||'{{input}}');});
    const updateSqlField=(inputId,key,transform=x=>x)=>byId(inputId)?.addEventListener('change',e=>{setLiveArgs(step,'live:sql_readonly',key,transform(e.target.value));});
    updateSqlField('live-sql-limit','limit',v=>Number(v));
    updateSqlField('live-sql-value','filter_value');
    updateSqlField('live-sql-filter','filter_column');
    byId('live-sql-table')?.addEventListener('change',async e=>{
      const table=e.target.value;setLiveArgs(step,'live:sql_readonly','table',table);
      setLiveArgs(step,'live:sql_readonly','filter_column','');setLiveArgs(step,'live:sql_readonly','filter_value','');
      if(table)await loadSqlColumns(table);renderInspector();
    });
    byId('live-sql-reload')?.addEventListener('click',loadSqlTables);
    byId('manage-local-tools')?.addEventListener('click',openToolLibrary);
    const currentIndex=state.workflow.steps.indexOf(step);
    const left=byId('move-left'),right=byId('move-right');left.disabled=currentIndex===0;right.disabled=currentIndex===state.workflow.steps.length-1;
    left.addEventListener('click',()=>moveStep(step.id,state.workflow.steps[currentIndex-1].id));right.addEventListener('click',()=>moveStep(step.id,state.workflow.steps[currentIndex+1].id));
    byId('remove-step').addEventListener('click',()=>{if(state.workflow.steps.length===1){toast('Keep at least one step in the workflow.','error');return;}state.workflow.steps.splice(currentIndex,1);state.selected=state.workflow.steps[Math.min(currentIndex,state.workflow.steps.length-1)].id;markDirty();render();toast('Step removed.');});
  };
  const render = () => {
    byId('workflow-name').value=state.workflow.name;
    byId('workflow-description').value=state.workflow.description||'';
    byId('workflow-task').value=state.workflow.task||'';
    renderCanvas();renderInspector();refreshMainModel();refreshSourceDetail();
    if(state.run?.nodeStates)updateNodeStates();
  };
  let priorFocus=null;
  const closeModal=()=>{if(byId('modal'))byId('modal').classList.remove('run-mode');byId('modal').hidden=true;state.modalOpen=false;byId('modal-content').replaceChildren();byId('modal-actions').replaceChildren();priorFocus?.focus?.();};
  const modal=(eyebrow,title,content,actions=[])=>{
    priorFocus=document.activeElement;byId('modal-eyebrow').textContent=eyebrow;byId('modal-title').textContent=title;
    byId('modal-content').innerHTML=content;byId('modal-actions').replaceChildren();
    actions.forEach(a=>{const b=document.createElement('button');b.type='button';b.className=`small-button ${a.primary?'strong-button':''}`;b.textContent=a.label;b.addEventListener('click',a.action);byId('modal-actions').append(b);});
    byId('modal').hidden=false;state.modalOpen=true;byId('modal-close').focus();
  };
  function openAdd(){modal('BUILD YOUR WORKFLOW','Add your next step','<p>Choose what your agent should do next. The step will be inserted after the currently selected step.</p><div class="add-step-grid"><button class="add-option" data-type="trigger"><span>↗</span><strong>Trigger</strong><small>Start from a request or webhook.</small></button><button class="add-option" data-type="ai"><span>✦</span><strong>AI Agent</strong><small>Give a local model instructions.</small></button><button class="add-option" data-type="mcp"><span>⌘</span><strong>Tool hub</strong><small>Choose one or more of 20 built-in, two live or connected MCP tools.</small></button><button class="add-option" data-type="output"><span>✓</span><strong>Output</strong><small>Return the result to the user.</small></button></div>',[{label:'Cancel',action:closeModal}]);
    byId('modal-content').querySelectorAll('[data-type]').forEach(btn=>btn.addEventListener('click',()=>{
      if(state.workflow.steps.length>=30){toast('Maximum 30 steps per workflow.','error');return;}
      const type=btn.dataset.type,meta=TYPES[type],item=preset(type,meta.label,meta.subtitle,type==='ai'?{model:'',instructions:''}:type==='mcp'?{tools:[],toolArgs:{}}:type==='trigger'?{event:'manual'}:{format:'text'});
      const current=state.workflow.steps.findIndex(s=>s.id===state.selected);
      state.workflow.steps.splice(current<0?state.workflow.steps.length:current+1,0,item);
      state.selected=item.id;markDirty();closeModal();render();byId('inspector-panel').classList.add('is-open');toast('Step added.','success');
    }));
  }
  const validate = () => {
    const errors=[];
    const steps=state.workflow.steps;
    if(!state.workflow.name.trim()) errors.push('Give your workflow a name.');
    if(steps[0]?.type!=='trigger')errors.push('The first step should be a trigger.');
    if(steps.at(-1)?.type!=='output')errors.push('The final step should be an output.');
    steps.forEach((s,i)=>{
      if(!s.title.trim())errors.push(`Step ${i+1}: a step name is required.`);
      if(s.type==='ai'&&!s.config.model?.trim())errors.push(`Step ${i+1}: choose an installed Ollama model.`);
      if(s.type==='ai'&&!s.config.instructions?.trim())errors.push(`Step ${i+1}: add agent instructions.`);
      if(s.type==='mcp'){
        const ids=idsFor(s);if(!ids.length)errors.push(`Step ${i+1}: choose at least one tool.`);
        ids.forEach(id=>{if(!itemById(id))errors.push(`Step ${i+1}: unavailable tool ${id}. Import it or reconnect your MCP server.`);});
      }

    });
    return errors;
  };
  const showValidation=()=>{const errors=validate();
    if(errors.length){modal('WORKFLOW CHECK',`${errors.length} thing${errors.length===1?'':'s'} to finish`,`<p>Before a server can run this design, check the following:</p><div class="inspector-note">${errors.map(e=>`<div style="padding:5px 0">• ${html(e)}</div>`).join('')}</div>`,[{label:'Back to editor',action:closeModal}]);}
    else{modal('WORKFLOW CHECK','Your design looks ready','<p>The workflow structure passes the front-end checks. Server-side permissions, tool schemas, authentication, and model availability must still be verified before a real execution.</p>',[{label:'Done',primary:true,action:closeModal}]);}
  };
  const exportFile=()=>{
    const selectedIds=new Set(state.workflow.steps.filter(s=>s.type==='mcp').flatMap(s=>idsFor(s)));
    downloadable(`${slug(state.workflow.name)}-workflow.json`,{...state.workflow,tools:state.tools.filter(t=>selectedIds.has(t.id))});
    toast('Workflow exported with its selected tool definitions.','success');
  };
  const importFile=async file=>{
    if(!file)return;
    if(file.size>1024*1024){toast('JSON file is too large (1 MB maximum).','error');return;}
    try{const data=validateImported(JSON.parse(await file.text()));const remap=mergeTools(data.tools||[]);data.steps.forEach(s=>{if(s.type==='mcp'){s.config.tools=idsFor(s).map(id=>remap[id]||id);delete s.config.tool;}});delete data.tools;state.workflow=data;state.selected=data.steps[0].id;markDirty();render();toast('Workflow and attached local tools imported.','success');}
    catch(err){toast(`Import rejected: ${err.message}`,'error');}
  };
  const serverStatus = async () => {
    const stateElement=byId('sidebar-connection-state');
    stateElement.className='connection-state';stateElement.lastElementChild.textContent='Checking local Ollama…';
    try {
      const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),6000);
      let response;try{response=await studioFetch('/studio/api/studio/status',{credentials:'same-origin',signal:controller.signal,cache:'no-store',headers:{'Accept':'application/json'}});}finally{clearTimeout(timer);}
      if(!response.ok||!response.headers.get('content-type')?.includes('json'))throw Error('The local Studio bridge is unavailable. Start Agent Studio using START AGENT STUDIO ON AI SERVER.bat.');
      const data=await response.json();if(data?.ready!==true)throw Error('Studio bridge not ready.');
      const readList=async path=>{const r=await studioFetch(path,{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});if(!r.ok)return[];const values=await r.json();return Array.isArray(values)?values.filter(x=>typeof x==='string').slice(0,150):[];};
      const models=await readList('/studio/api/studio/models');
      state.capabilities={ready:true,canRun:true,ollamaConnected:data.ollamaConnected===true,models,tools:[],error:data.error||''};
      const tr=await studioFetch('/studio/api/studio/tools',{cache:'no-store'});
      if(tr.ok){const all=await tr.json();state.builtins=all.filter(t=>t.source==='builtin');}
      if(!state.tools.length){try{const customR=await studioFetch('/studio/api/studio/tools/custom',{cache:'no-store'});if(customR.ok){const saved=await customR.json();if(Array.isArray(saved)&&saved.length){state.tools=saved.map(toolDefinition);localStorage.setItem(TOOL_KEY,JSON.stringify(state.tools));}}}catch{}}
      const first=firstAiStep();if(first&&!first.config.model&&models.length){first.config.model=models[0];markDirty();}
      renderCanvas();
      stateElement.className='connection-state '+(models.length?'connected':'');
      stateElement.lastElementChild.textContent=models.length?`Ollama ready · ${models.length} model(s)`:(data.ollamaConnected?'Ollama connected · no models':'Ollama not running');
      renderInspector();refreshMainModel();refreshSourceDetail();refreshBuilderModels();return models.length>0;
    }catch(err){state.capabilities={ready:false,canRun:false,models:[],tools:[],ollamaConnected:false,error:err.message};stateElement.className='connection-state';stateElement.lastElementChild.textContent='Studio bridge unavailable';renderInspector();refreshMainModel();refreshSourceDetail();refreshBuilderModels();return false;}
  };
  function openToolLibrary(){
    modal('YOUR TOOL LIBRARY','Create and manage reusable tools',`<p>Each saved tool can be selected under a <strong>Tool hub</strong> on the canvas. Click a tool to edit it, or use Export to move it to another PC.</p><div class="tool-library-list">${state.tools.length?state.tools.map(t=>`<div class="tool-library-row"><div><strong>${html(t.name)}</strong><small>${html(t.description|| (t.kind==='text'?'Reference text':'Text template'))}</small></div><button class="small-button" type="button" data-edit-tool="${html(t.id)}">Edit</button><button class="small-button" type="button" data-export-tool="${html(t.id)}">Export</button></div>`).join(''):'<div class="inspector-note">No tools yet. Click Create tool to make your first one.</div>'}</div><div class="inspector-note">Saved in this browser and synced to Studio's local MCP endpoint. <strong>Export a JSON backup</strong> before clearing browser data. This does not publish a tool to your external MCP server.</div>`,[
      {label:'Close',action:closeModal},{label:'Import tools',action:()=>byId('file-import-tool').click()},
      {label:'Export all',action:exportAllTools},{label:'+ Create tool',primary:true,action:()=>openToolEditor()}
    ]);
    byId('modal-content').querySelectorAll('[data-edit-tool]').forEach(b=>b.addEventListener('click',()=>openToolEditor(state.tools.find(t=>t.id===b.dataset.editTool))));
    byId('modal-content').querySelectorAll('[data-export-tool]').forEach(b=>b.addEventListener('click',()=>{const t=state.tools.find(t=>t.id===b.dataset.exportTool);if(t)exportTool(t);}));
  }
  function openToolEditor(existing=null,selectForStep=null){
    const tool=existing?{...existing}:{id:makeId(),name:'',description:'',kind:'text',body:''};
    modal('TOOL DESIGNER',existing?'Edit saved tool':'Create a tool',`<div class="tool-form-help"><strong>What will this tool do?</strong><p><b>Reference text:</b> return knowledge you enter below. <b>Text template:</b> produce a message using <code>{{input}}</code> (previous step output) or <code>{{prompt}}</code> (original question). Neither type can run scripts or call external APIs.</p></div><div class="field"><label for="tool-name">Tool name *</label><input id="tool-name" maxlength="100" value="${html(tool.name)}" placeholder="e.g. Product information"/></div><div class="field"><label for="tool-description">What does it do?</label><input id="tool-description" maxlength="300" value="${html(tool.description)}" placeholder="Briefly describe this tool"/></div><div class="field"><label for="tool-kind">Tool type</label><select id="tool-kind"><option value="text" ${tool.kind==='text'?'selected':''}>Reference text — return saved information</option><option value="template" ${tool.kind==='template'?'selected':''}>Text template — use input from earlier steps</option></select></div><div class="field"><label for="tool-body">Tool content *</label><textarea id="tool-body" maxlength="12000" rows="8" placeholder="${tool.kind==='text'?'Add text the agent can use':'e.g. Summarise this: {{input}}'}">${html(tool.body)}</textarea><span class="field-help">Maximum 12,000 characters. Don't put passwords, API keys or private customer information here: exported files will contain this text.</span></div>`,[
      {label:'Cancel',action:openToolLibrary},...(existing?[{label:'Delete',action:()=>confirmDeleteTool(tool.id)}]:[]),
      {label:'Save tool',primary:true,action:()=>{
        try{const updated=toolDefinition({id:tool.id,name:byId('tool-name').value,description:byId('tool-description').value,kind:byId('tool-kind').value,body:byId('tool-body').value});
          const index=state.tools.findIndex(t=>t.id===updated.id);
          if(index<0){if(state.tools.length>=80)throw Error('You can save up to 80 tools.');state.tools.push(updated);}else state.tools[index]=updated;
          saveTools();if(selectForStep){const target=state.workflow.steps.find(s=>s.id===selectForStep);if(target?.type==='mcp'){target.config.tools=[...new Set([...idsFor(target),updated.id])];delete target.config.tool;}}
          markDirty();render();openToolLibrary();toast(`Saved tool: ${updated.name}`,'success');
        }catch(err){toast(err.message,'error');}
      }}
    ]);
    byId('tool-name')?.focus();
  }
  function confirmDeleteTool(id){
    const tool=state.tools.find(t=>t.id===id);if(!tool)return;
    modal('DELETE TOOL',`Delete ${html(tool.name)}?`,'<p>This removes it from the local tool library. Existing workflows using it will need another tool selected.</p>',[
      {label:'Cancel',action:openToolLibrary},{label:'Delete tool',primary:true,action:()=>{state.tools=state.tools.filter(t=>t.id!==id);saveTools();render();openToolLibrary();}}
    ]);
  }
  function openToolPicker(stepId){
    const step=state.workflow.steps.find(s=>s.id===stepId);if(!step)return;
    const content=`<p><strong>Tick the tools you want.</strong> You can select several. They run from top to bottom and pass the information to Ollama.</p>
      <div class="field"><label for="tool-search">Find a tool by name or what it does</label><input id="tool-search" placeholder="Search 20 built-in tools, your tools, MCP server…" autocomplete="off"/></div>
      <div class="tool-picker-list" id="tool-picker-list"></div>
      <div class="inspector-note" id="tool-picker-total">${idsFor(step).length} selected · Saved automatically when selected</div>`;
    modal('TOOLS FOR YOUR AGENT','Choose your tools',content,[{label:'Create my own',action:()=>openToolEditor(null,step.id)},{label:'Set up Live Web / SQL',action:openLiveSettings},{label:'Connect an MCP server',action:openConnection},{label:'Done',primary:true,action:closeModal}]);
    const list=byId('tool-picker-list');
    const update=()=>{
      const q=(byId('tool-search')?.value||'').trim().toLowerCase();const selected=new Set(idsFor(step));
      const items=allAvailable().filter(t=>(`${t.name} ${t.description} ${t.category}`).toLowerCase().includes(q));
      list.innerHTML=items.length?items.map(t=>`<label class="tool-choice"><input type="checkbox" data-pick="${html(t.id)}" ${selected.has(t.id)?'checked':''}/><span class="tool-choice-info"><strong>${html(t.name)}</strong><small>${html(t.description||'Reusable tool')}</small><em>${html(t.source==='live'?'LIVE DATA · NEEDS CONNECTION':t.source==='builtin'?'BUILT-IN · LOCAL MCP':t.source==='remote'?'CONNECTED MCP SERVER':'YOUR TOOL')}</em></span></label>`).join(''):'<p class="inspector-note">No tools match. Try another search.</p>';
      list.querySelectorAll('[data-pick]').forEach(el=>el.addEventListener('change',()=>{
        selectFor(step,el.dataset.pick);
        byId('tool-picker-total').textContent=idsFor(step).length+' selected · Saved automatically';
        update();
      }));
    };
    byId('tool-search').addEventListener('input',update);update();byId('tool-search').focus();
  }
  const setLiveArgs=(step,id,key,value)=>{
    step.config.toolArgs=step.config.toolArgs||{};
    step.config.toolArgs[id]=step.config.toolArgs[id]||{};
    step.config.toolArgs[id][key]=value;
    markDirty();
  };
  const refreshLiveStatus=async()=>{
    try{const r=await studioFetch('/studio/api/studio/live/status');if(!r.ok)throw Error('Not available');state.liveStatus=await r.json();refreshSourceDetail();return true;}
    catch{toast('Could not read live connection settings. Check the terminal.','error');return false;}
  };
  const loadSqlTables=async()=>{
    const button=byId('live-sql-reload');if(button){button.disabled=true;button.textContent='Loading tables…';}
    try{
      const r=await studioFetch('/studio/api/studio/sql/tables');const data=await r.json();if(!r.ok)throw Error(data.error||'Could not connect to SQL Server');
      state.sqlTables=data.tables||[];toast(`${state.sqlTables.length} visible database tables found.`,'success');renderInspector();
    }catch(err){toast('SQL Server: '+err.message,'error');if(button){button.disabled=false;button.textContent='↻ Load tables';}}
  };
  const loadSqlColumns=async(table)=>{
    if(!table)return;
    try{const r=await studioFetch('/studio/api/studio/sql/columns?table='+encodeURIComponent(table));const data=await r.json();if(!r.ok)throw Error(data.error||'Could not list table columns');state.sqlColumns[table]=data.columns||[];}
    catch(err){toast('SQL columns: '+err.message,'error');}
  };
  const openLiveSettings=async()=>{
    await refreshLiveStatus();const c=state.liveStatus;
    modal('REAL INFORMATION SOURCES','Web Search works without an account',`<p><strong>Web Search is built in.</strong> No API key, Docker or separate search server required. It uses a public web search RSS feed. Your search queries leave this computer; the public feed may occasionally restrict automated requests.</p>
      <div class="live-setup"><h3>🌐 Built-in Web Search</h3><p><strong>Ready to use with no setup.</strong> Click Test to search the web, open matching public pages, follow relevant links and look for prices. This is a real network test, not a simulated success. Some sites block automated access.</p>
        <div class="field"><label for="live-test-query">Try searching for</label><input id="live-test-query" value="Shark vacuum cleaner UK price" maxlength="180" placeholder="What would you like to find?"/></div>
        <button class="small-button strong-button" id="live-test-web" type="button">🔎 Test web search now</button>
        <details style="margin-top:14px"><summary style="cursor:pointer">Advanced: choose another search provider (optional)</summary>
        <div class="field"><label for="live-provider">Search provider</label><select id="live-provider"><option value="bing" ${c.webProvider==='bing'?'selected':''}>Built-in public search — no account, no API key</option><option value="brave" ${c.webProvider==='brave'?'selected':''}>Brave Search API (optional)</option><option value="searxng" ${c.webProvider==='searxng'?'selected':''}>My own local SearXNG (optional)</option></select></div>
        <div class="field"><label for="live-brave-key">Brave API key — only if you choose Brave</label><input id="live-brave-key" type="password" autocomplete="off" placeholder="Optional · never exported"/></div>
        <div class="field"><label for="live-searx-url">Local SearXNG address — only if you choose SearXNG</label><input id="live-searx-url" value="${html(c.searxUrl||'http://127.0.0.1:8888')}"/></div></details></div>
      <div id="live-test-result" class="inspector-note" style="white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0">Web Search is enabled automatically. Click Test web search now to check access.</div>
      <div id="live-save-feedback" class="inspector-note">Web ${c.webReady?'ready for testing':'needs attention'} · SQL ${c.sqlReady?'configured':'not configured (optional)'}. No search account needed.</div>
      <details style="margin-top:16px"><summary style="cursor:pointer">Advanced: Connect a SQL Server database (optional)</summary>
      <div class="live-setup"><h3>▦ Read-Only SQL Server</h3><p>The table picker uses safe, parameterised SELECT queries. Use a SQL login with <strong>SELECT permission only</strong>; the application-intent hint alone does not prevent writes.</p>
        <div class="field"><label for="live-sql-server">SQL Server name or instance</label><input id="live-sql-server" value="${html(c.sqlServer||'')}" placeholder="SERVER\\INSTANCE or localhost,1433"/></div>
        <div class="field"><label for="live-sql-database">Database name</label><input id="live-sql-database" value="${html(c.sqlDatabase||'')}" placeholder="MyDatabase"/></div>
        <div class="field"><label for="live-sql-auth">Sign in using</label><select id="live-sql-auth"><option value="windows" ${c.sqlAuth==='windows'?'selected':''}>Windows authentication</option><option value="sql" ${c.sqlAuth==='sql'?'selected':''}>SQL Server read-only login</option></select></div>
        <div class="field"><label for="live-sql-user">SQL login (only for SQL authentication)</label><input id="live-sql-user" autocomplete="off" value="${html(c.sqlUser||'')}" placeholder="studio_reader"/></div>
        <div class="field"><label for="live-sql-password">SQL password</label><input id="live-sql-password" type="password" autocomplete="off" placeholder="Not saved to disk or exported"/></div>
        <div class="field"><label for="live-sql-driver">Microsoft ODBC driver</label><select id="live-sql-driver"><option ${c.sqlDriver==='ODBC Driver 18 for SQL Server'?'selected':''}>ODBC Driver 18 for SQL Server</option><option ${c.sqlDriver==='ODBC Driver 17 for SQL Server'?'selected':''}>ODBC Driver 17 for SQL Server</option></select></div>
        <label class="live-check"><input type="checkbox" id="live-sql-trust" ${c.sqlTrustCert?'checked':''}/> Trust SQL Server's TLS certificate (only for an approved development server)</label>
        <button class="small-button" id="live-test-sql" type="button">Test SQL connection · list tables</button><p class="field-help">First time: run <strong>INSTALL SQL SUPPORT.bat</strong> and install Microsoft's ODBC Driver 18. Then restart Studio.</p></div>
      </details>`,[
      {label:'Done',primary:true,action:closeModal},{label:'Save connections',action:async()=>{
        const payload={provider:byId('live-provider').value,brave_key:byId('live-brave-key').value,searx_url:byId('live-searx-url').value.trim(),
          sql_server:byId('live-sql-server').value.trim(),sql_database:byId('live-sql-database').value.trim(),sql_auth:byId('live-sql-auth').value,
          sql_user:byId('live-sql-user').value.trim(),sql_password:byId('live-sql-password').value,sql_driver:byId('live-sql-driver').value,sql_trust_cert:byId('live-sql-trust').checked};
        const feedback=byId('live-save-feedback');feedback.textContent='Saving connections locally…';
        try{const r=await studioFetch('/studio/api/studio/live/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||'Could not save connection');
          state.liveStatus=data;byId('live-brave-key').value='';byId('live-sql-password').value='';feedback.textContent=`✓ Saved advanced settings. Web: ${data.webReady?'ready':'needs attention'}. SQL: ${data.sqlReady?'configured':'not configured (optional)'}.`;refreshSourceDetail();toast('Connection settings updated.','success');
        }catch(err){feedback.textContent='✕ '+err.message;toast(err.message,'error');}
      }}]);
    const test=(kind)=>async()=>{
      const label=byId('live-test-result');
      const button=byId(kind==='web'?'live-test-web':'live-test-sql');
      const old=button.textContent;button.disabled=true;button.textContent=kind==='web'?'Searching real websites…':'Connecting to SQL…';
      label.textContent='Checking '+(kind==='web'?'public search results':'SQL Server')+' — this needs an actual connection…';
      try{
        const settings={provider:byId('live-provider').value,brave_key:byId('live-brave-key').value,searx_url:byId('live-searx-url').value.trim(),
          sql_server:byId('live-sql-server').value.trim(),sql_database:byId('live-sql-database').value.trim(),sql_auth:byId('live-sql-auth').value,
          sql_user:byId('live-sql-user').value.trim(),sql_password:byId('live-sql-password').value,sql_driver:byId('live-sql-driver').value,sql_trust_cert:byId('live-sql-trust').checked};
        const saved=await studioFetch('/studio/api/studio/live/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
        const saveData=await saved.json();if(!saved.ok)throw Error(saveData.error||'Unable to apply settings');
        state.liveStatus=saveData;refreshSourceDetail();
        const query=kind==='web'?byId('live-test-query').value.trim():'';
        if(kind==='web'&&!query)throw Error('Enter something to search for.');
        const r=await studioFetch('/studio/api/studio/live/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,query})});
        const obj=await r.json();if(!r.ok)throw Error(obj.error||'The live service did not respond');
        label.textContent=kind==='web'?`✓ Actual web search worked. These are real public search and page research results, not simulated:\n${obj.preview}`:`✓ SQL Server connected. ${obj.count} table(s) visible: ${obj.tables.join(', ')}`;
        toast('Live connection test passed.','success');
      }catch(err){label.textContent='✕ Search not completed: '+err.message+'\nNo prices were invented. Some sites block automated page reading.';toast('Could not complete live test: '+err.message,'error');}
      finally{button.disabled=false;button.textContent=old;}
    };
    byId('live-test-web')?.addEventListener('click',test('web'));
    byId('live-test-sql')?.addEventListener('click',test('sql'));
  };
  const openConnection=async()=>{
    await serverStatus();const c=state.capabilities;
    modal('YOUR CONNECTIONS','Ollama and MCP tools',`<div class="inspector-note"><strong>Ollama:</strong> ${c.models.length?`Ready · ${c.models.length} installed model(s)`:'Offline or no installed models'}<br/>
      <strong>Studio MCP server:</strong> Ready · 20 built-in tools at <code>the AI App Server /mcp endpoint</code><br/>
      <strong>External MCP:</strong> ${state.mcpConnected?`Connected · ${html(state.mcpServerName)} · ${state.remoteTools.length} tools`:'Not connected'}</div>
      <button type="button" class="small-button strong-button" id="mcp-open-live">Configure Live Web Search / SQL Server</button>
      <p>Connect to this installation’s native AI App Server MCP endpoint, enabled in /admin. Tools registered by your server become available alongside built-in tools.</p>
      <div class="field"><label for="mcp-url">AI App Server MCP URL (this computer)</label><input id="mcp-url" type="text" value="${html(state.mcpUrl)}" placeholder="http://127.0.0.1:8501/mcp"/></div>
      <div class="field"><label for="mcp-token">Bearer token (only if your server requires one)</label><input id="mcp-token" type="password" autocomplete="off" placeholder="Optional · not saved or exported" value="${html(state.mcpToken)}"/></div>
      <div class="inspector-note" id="mcp-connection-result">For safety, MCP client connections are limited to localhost. Remote tools may read or change data depending on their server permissions.</div>`,[
      {label:'Close',action:closeModal},{label:'Refresh Ollama',action:async()=>{await serverStatus();toast('Ollama models checked.','success');}},
      {label:'Connect MCP',primary:true,action:async()=>{
        const url=byId('mcp-url').value.trim(),token=byId('mcp-token').value;
        const result=byId('mcp-connection-result');result.textContent='Connecting and discovering MCP tools…';
        try{
          const r=await studioFetch('/studio/api/studio/mcp/connect',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,token})});
          const data=await r.json();if(!r.ok)throw Error(data.error||'Connection failed');
          state.mcpConnected=true;state.mcpUrl=data.url;state.mcpToken=token;state.mcpServerName=data.name;
          state.remoteTools=data.tools;result.textContent=`Connected to ${data.name}. Found ${data.tools.length} MCP tools. Click Done and open a Tool hub → Choose tools.`;
          render();toast(`${data.tools.length} external MCP tools discovered.`,'success');
        }catch(err){state.mcpConnected=false;state.remoteTools=[];result.textContent='Connection failed: '+err.message;toast(err.message,'error');}
      }}
    ]);
    byId('mcp-open-live')?.addEventListener('click',openLiveSettings);
  };
  const openGuide=()=>modal('YOUR FIRST AGENT','Follow these five easy steps',`<div class="guide-details">
    <p><strong>1. Choose an example:</strong> Click a starter on the left. Each includes several useful pre-selected tools.</p>
    <p><strong>Live sources:</strong> Choose the Live web research or SQL Server reader example, then click Live Web / SQL to configure the source. For SQL, select a table from the Tool hub. No SQL code needed.</p><p><strong>2. Choose Ollama:</strong> Use the permanent model selector above the workflow. Your choice is saved.</p>
    <p><strong>3. Choose your tools:</strong> Click Tool hub → <strong>+ Choose tools</strong>. Tick any of the 20 built-ins, use Create your own, or connect another MCP server.</p>
    <p><strong>4. Run:</strong> Write the job once in <strong>What to do each time</strong>, then click <strong>Run saved job</strong>. No second text box. Click <strong>Different input</strong> only when you want to ask something new.</p>
    <p><strong>5. After running:</strong> Save your answer, download it, copy it, run again or click Edit agent to change the description. Saved results are in the left menu.</p>
    <p><strong>6. Share:</strong> Click Export to save a workflow JSON (including your custom tool definitions). On another PC install Studio, Import the JSON, and install an Ollama model.</p>
    <p><strong>Extra:</strong> Your AI App Server exposes the 20 registered text tools through its native <code>/mcp</code> when enabled by an administrator. Use Connections to discover them.</p>
    </div><div class="inspector-note">Live MCP connections can perform real operations. Studio requires confirmation before executing external tools that are not marked read-only by their server. Background scheduling is not implemented. Production deployment requires additional review.</div>`,[
    {label:'Close',action:closeModal},{label:'Choose tools',primary:true,action:()=>{closeModal();const s=state.workflow.steps.find(x=>x.type==='mcp');if(s)openToolPicker(s.id);else openAdd();}}]);
  const updateNodeStates=()=>{
    document.querySelectorAll('.workflow-node').forEach(node=>{
      node.classList.remove('run-active','run-done','run-error');
      const num=state.workflow.steps.findIndex(s=>s.id===node.dataset.id)+1;
      const flag=state.run?.nodeStates?.[num];
      if(flag==='running')node.classList.add('run-active');
      if(flag==='done')node.classList.add('run-done');
      if(flag==='error')node.classList.add('run-error');
    });
  };
  const cancelRun=()=>{state.runController?.abort();if(state.run){state.run.aborted=true;} };
  const executeRun=async (prompt,approveRemote=false)=>{
    const button=byId('btn-run');button.disabled=true;button.textContent='Running…';
    state.run={id:makeId(),agentName:state.workflow.name,prompt,success:false,nodeStates:{},started:Date.now(),output:'',aborted:false,finished:false,approveRemote};state.lastPrompt=prompt;
    state.runController=new AbortController();
    modal('LIVE EXECUTION','Your agent is running',`<div class="run-context"><strong>What this agent is doing</strong><p id="run-mode-description">${html(state.workflow.description||'No agent purpose entered.')}</p><p class="saved-job-display"><strong>Job being run:</strong> ${html(prompt)}</p>${runSources()}</div><div class="run-topline"><span id="run-status" class="run-pill">● Starting</span><strong id="run-clock">0s elapsed</strong></div><p id="run-explanation">Checking your workflow and preparing your model…</p><div class="run-evidence" id="run-evidence"><strong>What tools actually checked</strong><div id="run-evidence-items">Waiting for tools…</div><div class="run-phase-metrics" id="run-phase-metrics">No model output received yet.</div></div><div class="run-layout"><div><h3>STEP-BY-STEP FEEDBACK</h3><ol id="run-events" class="run-events" aria-live="polite"></ol></div><div><h3><span id="run-output-title">LIVE DRAFT · SOURCES NOT YET CHECKED</span> <span id="run-chars">0 characters</span></h3><pre id="run-output" class="run-output" aria-live="off">Waiting for your model to generate text…</pre></div></div>`,[
      {label:'Cancel run',action:cancelRun}
    ]);
    byId('modal').classList.add('run-mode');
    const clock=setInterval(()=>{if(byId('run-clock')&&state.run?.started&&!state.run.finished)byId('run-clock').textContent=`${Math.floor((Date.now()-state.run.started)/1000)}s elapsed`;},1000);
    const log=(message,kind='')=>{const item=document.createElement('li');item.className=`run-event ${kind}`;item.textContent=message;byId('run-events')?.append(item);item.scrollIntoView({block:'nearest'});};
    const setStatus=(status,message)=>{if(byId('run-status'))byId('run-status').textContent=status;if(byId('run-explanation'))byId('run-explanation').textContent=message;};
    let completed=false;
    let activeOperation={step:0,name:'Preparing the workflow',kind:'workflow'};
    let failure=null;
    const diagnose=(message,op=activeOperation)=>{
      const reason=String(message||'The run did not finish.').slice(0,1000);
      const tool=op.name||'Workflow';
      const lower=(reason+' '+tool).toLowerCase();
      let kind='Workflow failed',fix='Check the failed step and its exact error, then run again.';
      if(/web search|search provider|bing|rss|internet/.test(lower)||op.kind==='web'){
        kind='Web Search failed';
        if(/http 403|http 429|rate.limit|restricting|blocked/.test(lower))fix='The public search service restricted this request. No API key is missing. Its availability cannot be guaranteed; retry later or choose another source.';
        else if(/connect|internet|dns|firewall|timeout|timed out|resolve/.test(lower))fix='Agent Studio could not reach the search service. Check your PC internet/DNS/firewall, then try Test web search now.';
        else fix='The public search feed returned no usable results. Try a more specific search phrase or test the service again; the agent will not invent prices.';
      }else if(op.kind==='ai'||/ollama|model /.test(lower)){
        kind='Ollama failed';fix='Check that Ollama is running and the selected model is installed. Refresh models and retry.';
      }else if(op.kind==='sql'||/sql server|odbc/.test(lower)){
        kind='SQL Server failed';fix='Check your read-only database connection and the chosen table under Live Web / SQL.';
      }
      return {kind,reason,fix,tool,step:op.step};
    };
    const evidenceRoot=byId('run-evidence-items');
    evidenceRoot.replaceChildren();
    const evidenceItems=new Map();
    const addEvidence=(name,text,klass='')=>{
      let details=evidenceItems.get(name);
      if(!details){details=document.createElement('details');details.open=true;const summary=document.createElement('summary');summary.textContent=name;details.append(summary);const pre=document.createElement('pre');details.append(pre);evidenceRoot.append(details);evidenceItems.set(name,details);}
      details.lastElementChild.textContent=text;details.className=klass;
    };
    const eventHandler=evt=>{
      const number=evt.step||0;
      if(evt.type==='workflow_started'){setStatus('● Working','Workflow checked. Running '+evt.total+' steps in order.');log('Workflow started · '+evt.total+' steps','start');}
      if(evt.type==='step_started'){activeOperation={step:number,name:evt.title||evt.kind||'Step',kind:evt.kind};if(evt.kind==='ai'){state.run.output='';if(byId('run-output'))byId('run-output').textContent='Waiting for Ollama to generate…';}state.run.nodeStates[number]='running';updateNodeStates();setStatus(`● Step ${number} running`,evt.message||'Working…');log(`Step ${number}: ${evt.title||evt.kind||'Step'} · ${evt.message||''}`,'start');}
      if(evt.type==='tool_started'){activeOperation={step:number,name:evt.name,kind:evt.name==='Live Web Search'?'web':evt.name==='Read-Only SQL Server'?'sql':'tool'};setStatus(`● Tool ${evt.tool_number}/${evt.tool_total} · step ${number}`,evt.message);log('↳ '+evt.message,'start');addEvidence(evt.name,'Running now…');}
      if(evt.type==='tool_detail'){log('↳ '+evt.message,'info');addEvidence(evt.name,evt.message);}
      if(evt.type==='evidence_warning'){log('⚠ '+evt.message,'error');addEvidence('Price evidence',evt.message,'warning');}
      if(evt.type==='tool_completed'){const metrics=evt.evidence?.search_hits!==undefined?` · ${evt.evidence.search_hits} matching links · ${evt.evidence.pages_read||0} pages read · ${evt.evidence.price_mentions} on-page prices`:'';log(`✓ ${evt.name} finished · ${evt.message}${metrics} · ${((evt.elapsed_ms||0)/1000).toFixed(1)}s`,'done');addEvidence(evt.name,(evt.preview||evt.message)+(metrics?'\n'+metrics:''));}
      if(evt.type==='tool_failed'){failure=diagnose(evt.message,{step:number,name:evt.name,kind:activeOperation.kind});log(`✕ ${evt.name}: ${evt.message}`,'error');addEvidence(evt.name,'FAILED: '+evt.message,'warning');}
      if(evt.type==='model_waiting'){setStatus(`● Waiting for Ollama · step ${number}`,evt.message);log(`Ollama: ${evt.message}`,'info');byId('run-phase-metrics').textContent=`Model: ${evt.model||'Ollama'} · waiting for its first response. Elapsed time is shown above.`;}
      if(evt.type==='model_generating'){setStatus(`● Generating · step ${number}`,evt.message);log(`Ollama: ${evt.message}`,'info');byId('run-phase-metrics').textContent='Ollama is generating the answer. Text appears live on the right.';}
      if(evt.type==='token'){
        if(!state.run.output){byId('run-output').textContent='';}
        byId('run-phase-metrics').textContent='Ollama is generating a draft · final price claims will be checked against live search evidence.';
        state.run.output+=evt.delta||'';byId('run-output').textContent=state.run.output;
        byId('run-chars').textContent=`${state.run.output.length.toLocaleString()} characters`;
        const box=byId('run-output');if(box)box.scrollTop=box.scrollHeight;
      }
      if(evt.type==='step_completed'){
        state.run.nodeStates[number]='done';updateNodeStates();
        const metrics=evt.tokens===undefined?'':` · ${evt.tokens} tokens${evt.tokens_per_sec?` · ${evt.tokens_per_sec} tokens/s`:''}`;
        log(`✓ Step ${number} finished · ${evt.message||'Complete'} · ${((evt.elapsed_ms||0)/1000).toFixed(1)}s${metrics}`,'done');
        if(evt.kind==='ai')byId('run-phase-metrics').textContent=`Ollama finished · ${evt.load_ms===undefined?'model load time unavailable':(evt.load_ms/1000).toFixed(1)+'s model load'}${metrics}`;
      }
      if(evt.type==='workflow_completed'){
        byId('modal-title').textContent='Run complete — your answer is ready';
        completed=true;state.run.success=true;state.run.output=evt.output||'';
        byId('run-output').textContent=state.run.output||'(No output)';
        byId('run-phase-metrics').textContent='Final answer received · review retailer links and verify the checkout price.';
        byId('run-output-title').textContent='FINAL ANSWER · VERIFY RETAILER PRICES';
        byId('run-chars').textContent=`${state.run.output.length.toLocaleString()} characters`;
        setStatus('✓ Completed',`All steps finished in ${(evt.elapsed_ms/1000).toFixed(1)} seconds.`);
        log('✓ Your agent finished successfully.','done');
      }
      if(evt.type==='workflow_failed'){if(!failure)failure=diagnose(evt.error);throw Error(evt.error||'The workflow could not complete.');}
    };
    try{
      const response=await studioFetch('/studio/api/studio/run/events',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/x-ndjson'},signal:state.runController.signal,
        body:JSON.stringify({workflow:state.workflow,prompt,tools:state.tools.filter(t=>state.workflow.steps.some(s=>s.type==='mcp'&&idsFor(s).includes(t.id))),mcp:state.mcpConnected?{url:state.mcpUrl,token:state.mcpToken}:null,approveRemote:state.run.approveRemote})});
      if(!response.ok){let obj={};try{obj=await response.json();}catch{}throw Error(obj.error||`Request rejected: HTTP ${response.status}`);}
      if(!response.body)throw Error('Streaming responses are not supported by this browser.');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
        let i;while((i=buffer.indexOf('\n'))!==-1){const line=buffer.slice(0,i);buffer=buffer.slice(i+1);if(line.trim())eventHandler(JSON.parse(line));}
      }
      if(buffer.trim())eventHandler(JSON.parse(buffer));
      if(!completed)throw Error('Connection closed before the workflow finished.');
    }catch(err){
      const aborted=state.run.aborted||err.name==='AbortError';
      const message=aborted?'You cancelled the run.':err.message;failure=aborted?{kind:'Run cancelled',reason:message,fix:'You may run the job again.',tool:activeOperation.name,step:activeOperation.step}:(failure||diagnose(message));state.run.failure=failure;
      byId('modal-title').textContent=aborted?'Run cancelled':'Run failed — '+failure.kind;setStatus(aborted?'■ Stopped':'✕ Failed',message);log((aborted?'■ ':'✕ ')+message,'error');
      const active=Object.keys(state.run.nodeStates).find(k=>state.run.nodeStates[k]==='running');
      if(active)state.run.nodeStates[active]='error';updateNodeStates();
    }finally{
      clearInterval(clock);state.run.finished=true;state.runController=null;
      button.disabled=false;button.innerHTML='<svg class="icon"><use href="#icon-play"/></svg> Run saved job';
      byId('modal-actions').replaceChildren();
      const actions=byId('modal-actions');
      const makeAction=(label,handler,primary=false,disabled=false)=>{const b=document.createElement('button');b.type='button';b.className=`small-button ${primary?'strong-button':''}`;b.textContent=label;b.disabled=disabled;b.addEventListener('click',handler);actions.append(b);return b;};
      const success=state.run.success&&!!state.run.output.trim();
      const advice=document.createElement('div');advice.className='after-run-panel';
      if(success){advice.innerHTML='<strong>✓ Your agent finished.</strong><p>Save, download, or reuse the answer.</p>';}
      else{
        const f=failure||diagnose('The run ended without a final answer.');
        advice.classList.add('run-failure-panel');
        const heading=document.createElement('strong');heading.textContent='✕ '+f.kind;
        const step=document.createElement('p');step.textContent='Failed at step '+(f.step||'?')+': '+f.tool;
        const reason=document.createElement('p');reason.className='failure-reason';reason.textContent='Exact error: '+f.reason;
        const fix=document.createElement('p');fix.textContent='What to do: '+f.fix;
        advice.append(heading,step,reason,fix);
      }
      byId('modal-content').append(advice);
      if(success){
        makeAction('💾 Save result',()=>saveResult(state.run),true);
        makeAction('↓ Download .txt',()=>downloadText(`${slug(state.run.agentName)}-answer.txt`,state.run.output));
        makeAction('Copy answer',()=>copyText(state.run.output));
        makeAction('↗ Use answer as next input',()=>{const output=state.run.output.slice(0,8000);closeModal();runAgent(output);});
      }
      if(!success&&failure){
        makeAction('Copy error details',()=>copyText('Agent Studio v1.3\nAgent: '+state.run.agentName+'\nStep: '+(failure.step||'?')+' '+failure.tool+'\nProblem: '+failure.kind+'\nError: '+failure.reason+'\nSuggestion: '+failure.fix),true);
      }
      makeAction('↻ Run again (same job)', ()=>{const input=state.run.prompt;const riskyRun=state.run.approveRemote;closeModal();if(riskyRun){runAgent(input);}else{executeRun(input,false);}});
      makeAction('✎ Edit agent',focusDetails);
      if(state.workflow.steps.some(s=>s.type==='mcp'&&idsFor(s).includes('live:web_search')))makeAction('🌐 Test Web Search',()=>{closeModal();openLiveSettings();});
      makeAction('View saved results',openResults);
      makeAction('Close',closeModal);

    }
  };
  // Show information sources explicitly. Built-ins analyse provided text; they do not
  // silently visit websites or connect to databases. External MCP tools only operate
  // when the user has connected a server and deliberately selected the tool.
  const runSources=()=>{
    const ids=state.workflow.steps.filter(s=>s.type==='mcp').flatMap(s=>idsFor(s));
    const builtin=ids.filter(x=>x.startsWith('builtin:'));
    const live=ids.filter(x=>x.startsWith('live:'));
    const custom=ids.filter(x=>!x.startsWith('builtin:')&&!x.startsWith('remote:')&&!x.startsWith('live:'));
    const remote=ids.filter(x=>x.startsWith('remote:'));
    const ai=firstAiStep();
    const parts=[`<span class="source-chip">✎ Your saved job (or optional one-time input)</span>`];
    if(builtin.length)parts.push(`<span class="source-chip">✓ ${builtin.length} local text tool${builtin.length===1?'':'s'} (no web/DB access)</span>`);
    if(custom.length)parts.push(`<span class="source-chip">✓ ${custom.length} custom text tool${custom.length===1?'':'s'}</span>`);
    if(live.includes('live:web_search'))parts.push(`<span class="source-chip source-chip-remote">🌐 Live Web Search ${state.liveStatus.webProvider==='bing'?'(key-free; availability not tested)':state.liveStatus.webReady?'(configured; availability not tested)':'(setup needed)'}</span>`);
    if(live.includes('live:sql_readonly'))parts.push(`<span class="source-chip source-chip-remote">▦ SQL Server ${state.liveStatus.sqlReady?'(ready)':'(setup needed)'}</span>`);
    if(remote.length)parts.push(`<span class="source-chip source-chip-remote">↔ ${remote.length} selected external MCP tool${remote.length===1?'':'s'}${state.mcpConnected?' (connected)':' (not connected)'}</span>`);
    if(ai)parts.push(`<span class="source-chip">✦ Ollama: ${html(ai.config.model||'model not selected')}</span>`);
    const summary=live.length?`<strong>Live sources:</strong> ${live.map(x=>html(toolName(x))).join(', ')}. Web searches contact your configured provider. SQL reads use only your selected table and cannot change rows. Check the connections and tool settings before running.`:remote.length?`<strong>External MCP:</strong> ${remote.map(x=>html(toolName(x))).join(', ')}. These tools may access real services if the connected server supports them. Review permissions before running.`:'<strong>No live web search or database connection is active.</strong> This workflow does not open websites or query SQL Server by itself.';
    return `<div class="source-chips">${parts.join('')}</div><p class="source-footnote">${summary}</p>`;
  };
  const refreshSourceDetail=()=>{const el=byId('editor-source-detail');if(el)el.innerHTML=runSources();};
  const bindRunDescription=()=>{
    const el=byId('run-description');if(!el)return;
    el.addEventListener('input',()=>{
      state.workflow.description=el.value;
      byId('workflow-description').value=el.value;
      markDirty();
      if(byId('run-mode-description'))byId('run-mode-description').textContent=el.value||'No agent purpose entered.';
    });
  };
  // Run the prepared job from the editor. No second prompt: the task and
  // selected tools already define what happens. One-time input is a separate action.
  const runSavedAgent=async()=>{
    if(state.run&&!state.run.finished){toast('This agent is already running.','error');return;}
    const task=(state.workflow.task||state.workflow.description||'').trim();
    if(!task){byId('workflow-task').scrollIntoView({behavior:'smooth',block:'center'});byId('workflow-task').focus();toast('Enter the job to run once in the saved job box.','error');return;}
    if(!state.capabilities.ready||(!state.capabilities.models.length&&state.workflow.steps.some(s=>s.type==='ai'))){openConnection();return;}
    const errors=validate();if(errors.length){showValidation();return;}
    if(state.workflow.steps[0]?.config.event!=='manual'){toast('Choose Manual start for your trigger.','error');return;}
    const toolIds=state.workflow.steps.filter(s=>s.type==='mcp').flatMap(s=>idsFor(s));
    const retailTask=/(best|cheapest|lowest|find|compare).{0,65}(price|prices|deal|deals)/i.test(task)&&!/(pasted|paste|provided text|my invoice)/i.test(task);
    if(retailTask&&!toolIds.includes('live:web_search')&&!toolIds.some(x=>x.startsWith('remote:'))){
      modal('FIX THIS AGENT','This job needs a live price search',`<p>Your job asks for <strong>current shop prices</strong>, but the selected tools can only inspect the text you type. That caused the earlier misleading “No numbers found” response.</p><p>Studio can replace those text tools with <strong>Live Web Search</strong>. It will then search the web when you press Run. Web Search is built in; it only needs an internet connection.</p>`,[
        {label:'Back to editor',action:closeModal},
        {label:'Fix tools for this agent',primary:true,action:()=>{
          let hub=state.workflow.steps.find(s=>s.type==='mcp');
          if(!hub){hub=preset('mcp','Search current retailer prices','Use Web Search, not local text extraction',{tools:[],toolArgs:{}});state.workflow.steps.splice(1,0,hub);}
          hub.config.tools=['live:web_search'];hub.config.toolArgs=hub.config.toolArgs||{};
          hub.config.toolArgs['live:web_search']={query:task.slice(0,300)};
          state.selected=hub.id;markDirty();render();closeModal();
          toast('Fixed: your agent will now use Web Search. Check the query in the Tool hub.','success');
          if(!state.liveStatus.webReady)openLiveSettings();
        }}
      ]);return;
    }
    if(toolIds.includes('live:web_search')&&!state.liveStatus.webReady){toast('Web Search is unavailable. Open Live Web / SQL to check its connection.','error');openLiveSettings();return;}
    if(toolIds.includes('live:sql_readonly')&&!state.liveStatus.sqlReady){toast('Connect your authorised read-only SQL Server first.','error');openLiveSettings();return;}
    const risky=toolIds.filter(id=>id.startsWith('remote:')&&itemById(id)?.readOnly!==true);
    if(risky.length){
      modal('CONFIRM EXTERNAL TOOLS','Approve this agent run',`<p>This agent is about to run the saved job:</p><p class="job-preview">${html(task)}</p><p><strong>${risky.length} connected MCP tool(s) are not marked read-only.</strong> Check their permissions before you approve. They may change information on your connected server.</p>`,[
        {label:'Cancel',action:closeModal},
        {label:'Approve and run',primary:true,action:()=>{closeModal();executeRun(task,true);}}
      ]);return;
    }
    executeRun(task,false);
  };
  const runAgent=async(initialPrompt='')=>{
    const preparedPrompt=(typeof initialPrompt==='string'&&initialPrompt)?initialPrompt:state.lastPrompt;
    if(!state.capabilities.ready||(!state.capabilities.models.length&&state.workflow.steps.some(s=>s.type==='ai'))){openConnection();return;}
    const errors=validate();if(errors.length){showValidation();return;}
    if(state.workflow.steps[0]?.config.event!=='manual'){toast('Choose Manual start for the trigger to run locally.','error');return;}
    const remoteIds=state.workflow.steps.filter(s=>s.type==='mcp').flatMap(s=>idsFor(s)).filter(id=>id.startsWith('remote:'));
    const risky=remoteIds.filter(id=>itemById(id)?.readOnly!==true);
    modal('RUN YOUR AGENT','Review the task before running',`<div class="run-task"><div class="run-task-header"><strong>1. What should the agent do?</strong><small>You can edit this here. It stays visible during the run and is sent to Ollama.</small></div>
      <textarea id="run-description" rows="3" maxlength="500" placeholder="Describe the agent's purpose">${html(state.workflow.description||'')}</textarea></div>
      <div class="run-input-area"><strong>2. What information should it work with?</strong>
        <label class="input-mode"><input type="radio" name="run-input-mode" value="text" checked/> <span><b>I'll paste a question, log or some text</b><small>Best for examples using text-processing tools</small></span></label>
        <div id="run-prompt-section" class="field"><label for="run-prompt">Input text</label><textarea id="run-prompt" rows="4" maxlength="8000" placeholder="Example: ERROR HTTP 500 on /health — explain likely causes">${html(preparedPrompt.slice(0,8000))}</textarea></div>
        <label class="input-mode"><input type="radio" name="run-input-mode" value="description"/> <span><b>Run the saved task without extra text</b><small>Uses the agent description as its input — it does not automatically fetch data</small></span></label>
      </div>
      <div class="run-sources"><strong>3. What will it actually access?</strong>${runSources()}<p class="source-help">A website or database is accessed only if its live tool is selected and configured. A pasted URL alone is not fetched.</p></div>
      ${risky.length?`<label class="run-approval"><input id="approve-remote" type="checkbox"/> <span>I approve calling ${risky.length} connected MCP tool(s) that are <strong>not marked read-only</strong>. They may change data on the connected server.</span></label>`:''}`, [
      {label:'Back to editor',action:closeModal},{label:'Run this agent',primary:true,action:()=>{
        const useDescription=byId('modal-content').querySelector('input[name="run-input-mode"]:checked')?.value==='description';
        const prompt=useDescription?(state.workflow.description||'').trim():byId('run-prompt')?.value?.trim()||'';
        if(!prompt){toast(useDescription?'Write an agent description first.':'Paste a question or choose Run the saved task.','error');return;}
        const approved=byId('approve-remote')?.checked===true;
        if(risky.length&&!approved){toast('Approve the connected MCP tools to run them.','error');return;}
        executeRun(prompt,approved);
      }}
    ]);
    bindRunDescription();
    const promptSection=byId('run-prompt-section');
    byId('modal-content').querySelectorAll('input[name="run-input-mode"]').forEach(radio=>radio.addEventListener('change',()=>{
      promptSection.hidden=radio.value==='description'&&radio.checked;
      byId('run-description').focus();
    }));
    byId('run-prompt')?.focus();
  };
  const createNew=()=>modal('NEW WORKFLOW','Start with a blank canvas','<p>Create a new workflow? You can export your current work first. The existing locally saved workflow remains available until you save the new one.</p>',[{label:'Cancel',action:closeModal},{label:'Start new',primary:true,action:()=>{closeModal();createWorkflow('blank');}}]);

  // Existing '/studio/api/studio/design' endpoint remains supported for older clients.
  // -------- AI-FIRST BUILDER v1.1 --------
  // The browser sends only the user's description, installed-model choice, and
  // optional connected MCP credentials to the localhost design endpoint.
  // The server is responsible for rejecting unknown or invented tool IDs.
  const refreshBuilderModels=()=>{
    const picker=byId('builder-model');if(!picker)return;
    const models=state.capabilities.models||[];
    const current=picker.value||state.builderModelChoice||firstAiStep()?.config.model||'';
    picker.replaceChildren();
    if(!models.length){const opt=document.createElement('option');opt.value='';opt.textContent='No Ollama models detected';picker.append(opt);}
    for(const name of models){const opt=document.createElement('option');opt.value=name;opt.textContent=name;picker.append(opt);}
    if(models.includes(current))picker.value=current;
    else if(models.length)picker.value=models[0];
    state.builderModelChoice=picker.value;
  };
  const builderStatus=(message,kind='')=>{const el=byId('builder-status');if(!el)return;el.textContent=message;el.className='builder-status'+(kind?' '+kind:'');};
  const showBuilder=(revision=false)=>{
    if(state.run&&!state.run.finished){toast('Finish or cancel the current run before designing another agent.','error');return;}
    if(state.modalOpen)closeModal();
    state.builderRevision=revision;
    byId('builder-review').hidden=true;byId('builder-form-layout').hidden=false;
    if(revision&&state.workflow){byId('builder-description').value=state.workflow.task||state.workflow.description||'';}
    if(!revision){byId('builder-description').value='';state.builderPlan=null;}
    byId('builder-char-count').textContent=byId('builder-description').value.length+' / 2400';
    builderStatus('Describe the job once. Ollama will suggest tools and draw the workflow before it can run.');
    byId('builder-open-saved').textContent=state.hadSavedDraft?'↗ Open my saved agent':'↗ Open visual editor';
    byId('builder-create').disabled=false;
    byId('builder-create').innerHTML='<span>✦</span> Design my agent <span class="builder-button-arrow">→</span>';
    byId('builder-model').value=state.builderModelChoice||firstAiStep()?.config.model||'';
    byId('nav-workflows').classList.remove('active');byId('nav-ai-create').classList.add('active');
    document.querySelector('.studio-main').classList.add('builder-visible');
    window.scrollTo({top:0,behavior:'instant'});
  };
  const showEditor=()=>{
    document.querySelector('.studio-main').classList.remove('builder-visible');
    byId('nav-ai-create').classList.remove('active');byId('nav-workflows').classList.add('active');
    window.scrollTo({top:0,behavior:'instant'});
  };
  const renderBuilderReview=plan=>{
    byId('builder-form-layout').hidden=true;byId('builder-review').hidden=false;
    byId('builder-plan-title').textContent=plan.workflow.name;
    byId('builder-plan-summary').textContent=plan.summary||'';
    const list=plan.tools||[];
    const ordered=plan.workflow.steps.map((step,index)=>{
      const icon={trigger:'↗',mcp:'⌘',ai:'✦',output:'✓'}[step.type]||'○';
      const info=step.type==='mcp'?`<div class="builder-tools-vertical">${list.map(t=>`<div>● ${html(t.name)}</div>`).join('')}</div>`:'';
      return `<div class="builder-path-node"><b>${icon}</b><span><strong>${html(step.title)}</strong><small>${html(step.type==='mcp'?`${list.length} real tools selected`:step.description)}</small></span></div>${info}${index!==plan.workflow.steps.length-1?'<div class="builder-path-arrow">↓</div>':''}`;
    }).join('');
    byId('builder-path').innerHTML=ordered;
    byId('builder-tool-list').innerHTML=list.length?list.map(t=>`<div class="builder-tool-choice"><strong>${html(t.name)}</strong><small>${html(t.why)}</small><small>${html(t.category)}${t.readOnly?' · Read-only':' · Permission required'}</small></div>`).join(''):'<p class="builder-good">No external tools needed. Ollama can handle this saved task directly.</p>';
    const warnings=plan.warnings||[];
    byId('builder-warnings').innerHTML=warnings.length?warnings.map(w=>`<p class="builder-warning">⚠ ${html(w)}</p>`).join(''):'<p class="builder-good">✓ No known missing connections for the selected tools. Check the agent before running.</p>';
    const para=document.createElement('p');para.className='builder-warning';para.textContent=plan.limitations||'The runtime follows your selected tool order; it does not choose new tools by itself.';byId('builder-warnings').append(para);
    window.scrollTo({top:0,behavior:'instant'});
  };
  const createWithAI=async()=>{
    if(state.builderBusy){state.builderAbort?.abort();return;}
    const description=byId('builder-description').value.trim(),model=byId('builder-model').value;
    if(description.length<12){builderStatus('Please describe the job in at least 12 characters.','error');byId('builder-description').focus();return;}
    if(!model){builderStatus('Ollama has no installed model. Start Ollama, then click the refresh button.','error');return;}
    state.builderModelChoice=model;state.builderBusy=true;
    const controller=new AbortController();state.builderAbort=controller;
    const button=byId('builder-create');button.innerHTML='■ Stop designing';button.disabled=false;
    const start=Date.now();
    builderStatus(`Asking ${model} to design your agent. It is examining the available tools… 0s`,'working');
    const activity=byId('builder-live-progress'),timeline=byId('builder-live-events');
    activity.hidden=false;timeline.replaceChildren();
    let lastType='',lastRow=null;
    const showStage=(type,message,klass='')=>{
      if(type===lastType&&lastRow){lastRow.textContent=message;return;}
      const li=document.createElement('li');li.textContent=message;li.className=klass;timeline.append(li);timeline.scrollTop=timeline.scrollHeight;
      lastType=type;lastRow=li;
    };
    showStage('connecting','● Contacting Agent Studio and checking Ollama…');
    let lastMessage='Checking your installed model and tools…';
    const timer=setInterval(()=>{if(state.builderBusy)builderStatus(`${lastMessage} · ${Math.floor((Date.now()-start)/1000)}s elapsed`,'working');},1000);
    try{
      const body={description,model,mcp:state.mcpConnected?{url:state.mcpUrl,token:state.mcpToken}:null};
      if(state.builderRevision)body.current=state.workflow;
      const response=await studioFetch('/studio/api/studio/design/events',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/x-ndjson'},signal:controller.signal,body:JSON.stringify(body)});
      if(!response.ok){let error={};try{error=await response.json();}catch{}throw Error(error.error||`AI design request rejected (HTTP ${response.status})`);}
      if(!response.body)throw Error('This browser does not support live design updates.');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',done=false;
      const process=(evt)=>{
        if(evt.type==='heartbeat')return;
        const events={design_started:'Checking your model and connections',tools_checked:'Available tools verified',research_required:'Shopping requires real Web Search',model_waiting:'Waiting for Ollama',model_generating:'Ollama is preparing a design',design_checked:'Checking suggested tools',design_completed:'Design completed',design_failed:'Design failed'};
        const title=events[evt.type]||evt.type;
        if(evt.type==='design_failed')throw Error(evt.error||'AI could not prepare this design.');
        showStage(evt.type,`${evt.type==='design_completed'?'✓':'•'} ${title}: ${evt.message||''}`,evt.type==='design_completed'?'done':'');
        lastMessage=evt.message||title;builderStatus(lastMessage,'working');
        if(evt.type==='design_completed'){
          const data=evt.result,validated=validateImported(data.workflow);
          state.builderPlan={...data,workflow:validated};
          renderBuilderReview(state.builderPlan);
          builderStatus('Design ready. Review the chosen tools and any missing connections.','success');done=true;
        }
      };
      while(true){const {done:finished,value}=await reader.read();if(finished)break;buffer+=decoder.decode(value,{stream:true});let i;
        while((i=buffer.indexOf('\n'))!==-1){const line=buffer.slice(0,i);buffer=buffer.slice(i+1);if(line.trim())process(JSON.parse(line));}
      }
      if(buffer.trim())process(JSON.parse(buffer));
      if(!done)throw Error('Ollama stopped responding before the agent design was complete.');
    }catch(err){
      const msg=err.name==='AbortError'?'Design stopped. Your description is still here.':`Could not design the agent: ${err.message}`;
      builderStatus(msg,'error');showStage('error','✕ '+msg,'error');
    }finally{
      clearInterval(timer);state.builderBusy=false;state.builderAbort=null;
      button.innerHTML='<span>✦</span> Design my agent <span class="builder-button-arrow">→</span>';
    }
  };
  const acceptAIPlan=()=>{
    if(!state.builderPlan?.workflow){toast('Generate and review an agent design first.','error');return;}
    state.workflow=state.builderPlan.workflow;
    state.hadSavedDraft=true;
    state.selected=state.workflow.steps.find(s=>s.type==='mcp')?.id||state.workflow.steps.find(s=>s.type==='ai')?.id||state.workflow.steps[0].id;
    markDirty();render();showEditor();toast('Your AI-designed agent is saved. You can now edit tools or run it.','success');
  };
  const initializeBuilder=()=>{
    byId('nav-ai-create').addEventListener('click',()=>showBuilder(false));
    byId('builder-open-saved').addEventListener('click',showEditor);
    byId('btn-builder-change').addEventListener('click',()=>showBuilder(true));
    byId('builder-description').addEventListener('input',e=>{byId('builder-char-count').textContent=e.target.value.length+' / 2400';});
    byId('builder-model').addEventListener('change',e=>{state.builderModelChoice=e.target.value;});
    byId('builder-refresh').addEventListener('click',async()=>{builderStatus('Checking installed Ollama models…','working');const ready=await serverStatus();builderStatus(ready?`${state.capabilities.models.length} installed model(s) available. Describe your idea above.`:'Ollama not available. Start Ollama and click refresh.',ready?'success':'error');});
    byId('builder-create').addEventListener('click',createWithAI);
    byId('builder-back').addEventListener('click',()=>{byId('builder-review').hidden=true;byId('builder-form-layout').hidden=false;});
    byId('builder-redesign').addEventListener('click',()=>{byId('builder-review').hidden=true;byId('builder-form-layout').hidden=false;createWithAI();});
    byId('builder-accept').addEventListener('click',acceptAIPlan);
    document.querySelectorAll('[data-builder-idea]').forEach(b=>b.addEventListener('click',()=>{const field=byId('builder-description');field.value=b.dataset.builderIdea;field.dispatchEvent(new Event('input'));field.focus();}));
    // Carry the homepage's plain-English idea into the private admin builder.
    try{
      const pending=sessionStorage.getItem('agent-studio.pending-description');
      if(pending){
        const field=byId('builder-description');field.value=pending.slice(0,2400);
        field.dispatchEvent(new Event('input'));
        sessionStorage.removeItem('agent-studio.pending-description');
      }
    }catch{}
    refreshBuilderModels();
    const params=new URLSearchParams(location.search);
    if(params.has('template')||params.has('editor'))showEditor();else showBuilder(false);
  };

  document.addEventListener('DOMContentLoaded',()=>{
    loadTools();loadResults();loadDraft();restoreServerDraft().finally(()=>{restoringServer=false;scheduleServerSave(state.workflow);});restoreServerResults();initializeBuilder();serverStatus();refreshLiveStatus();
    byId('workflow-name').addEventListener('input',event=>{state.workflow.name=event.target.value;markDirty();});
    byId('workflow-description').addEventListener('input',event=>{state.workflow.description=event.target.value;markDirty();});
    byId('workflow-task').addEventListener('input',event=>{state.workflow.task=event.target.value;markDirty();});
    byId('btn-edit-agent').addEventListener('click',()=>{byId('agent-details').scrollIntoView({behavior:'smooth',block:'center'});byId('workflow-description').focus();});
    byId('edit-ollama-instructions').addEventListener('click',focusAIInstructions);
    byId('configure-live-sources')?.addEventListener('click',openLiveSettings);
    byId('configure-data-source').addEventListener('click',()=>{const s=state.workflow.steps.find(x=>x.type==='mcp');if(s)openToolPicker(s.id);else openAdd();});
    byId('nav-results').addEventListener('click',openResults);
    byId('btn-view-results').addEventListener('click',openResults);
    byId('guide-example').addEventListener('click',openExamples);
    byId('guide-tools').addEventListener('click',openToolGuide);
    byId('guide-model').addEventListener('click',()=>{byId('main-ollama-model').scrollIntoView({behavior:'smooth',block:'center'});byId('main-ollama-model').focus();});
    byId('main-ollama-model').addEventListener('change',event=>{
      const step=firstAiStep();if(!step)return;
      step.config.model=event.target.value;
      markDirty();render();
      toast(`Model selected: ${step.config.model}. Saved automatically.`, 'success');
    });
    byId('main-model-refresh').addEventListener('click',async()=>{
      const button=byId('main-model-refresh');button.disabled=true;button.textContent='Checking…';
      const found=await serverStatus();button.disabled=false;button.textContent='↻ Refresh';
      toast(found?`${state.capabilities.models.length} installed models available.`:'Could not load installed models.',found?'success':'error');
    });
    byId('quick-test-agent').addEventListener('click',runSavedAgent);
    byId('quick-guide').addEventListener('click',openGuide);
    byId('nav-tools').addEventListener('click',openToolLibrary);
    byId('file-import-tool').addEventListener('change',async event=>{await importToolFile(event.target.files?.[0]);event.target.value='';openToolLibrary();});
    byId('pan-left').addEventListener('click',()=>byId('canvas-surface').scrollBy({left:-340,behavior:'smooth'}));
    byId('pan-right').addEventListener('click',()=>byId('canvas-surface').scrollBy({left:340,behavior:'smooth'}));
    byId('btn-save').addEventListener('click',()=>{save();saveTools();});byId('btn-export').addEventListener('click',exportFile);byId('btn-add').addEventListener('click',openAdd);
    byId('btn-validate').addEventListener('click',showValidation);byId('btn-run').addEventListener('click',runSavedAgent);byId('btn-run-once').addEventListener('click',()=>runAgent());
    byId('btn-import').addEventListener('click',()=>byId('file-import').click());
    byId('file-import').addEventListener('change',async e=>{await importFile(e.target.files?.[0]);e.target.value='';});
    byId('nav-new').addEventListener('click',()=>showBuilder(false));byId('nav-workflows').addEventListener('click',()=>{showEditor();byId('canvas-surface').scrollTo({left:0,behavior:'smooth'});});
    byId('nav-live')?.addEventListener('click',openLiveSettings);
    byId('nav-connect').addEventListener('click',openConnection);byId('nav-guide').addEventListener('click',openGuide);
    byId('btn-mobile-settings').addEventListener('click',()=>byId('inspector-panel').classList.toggle('is-open'));
    byId('modal-close').addEventListener('click',()=>{if(!state.run||state.run.finished){byId('modal').classList.remove('run-mode');closeModal();}else toast('The agent is still running. Use Cancel run to stop it.','error');});byId('modal').addEventListener('click',event=>{if(event.target===byId('modal')&&(!state.run||state.run.finished)){byId('modal').classList.remove('run-mode');closeModal();}});
    byId('modal').addEventListener('keydown',event=>{if(event.key==='Tab'){
      const focusables=[...byId('modal').querySelectorAll('button:not([disabled]),input,textarea,select,a[href]')].filter(x=>x.getClientRects().length);
      if(!focusables.length)return;const first=focusables[0],last=focusables.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&state.modalOpen&&(!state.run||state.run.finished)){byId('modal').classList.remove('run-mode');closeModal();}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save();}});
    document.querySelectorAll('[data-template]').forEach(button=>button.addEventListener('click',()=>modal('STARTER TEMPLATE','Open this workflow?','<p>The selected starter template will replace the current editor view. Export any unsaved changes you want to keep first.</p>',[{label:'Cancel',action:closeModal},{label:'Open template',primary:true,action:()=>{const key=button.dataset.template;closeModal();createWorkflow(key);showEditor();}}])));
  });
})();
