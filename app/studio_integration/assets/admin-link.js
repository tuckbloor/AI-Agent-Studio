/* Add Agent Studio to the native AI App Server admin menu without editing engine files. */
'use strict';
(()=>{
  const add=()=>{
    const nav=document.querySelector('#shell .sidebar nav');
    if(!nav||document.getElementById('native-agent-studio-link'))return;
    const link=document.createElement('a');
    link.id='native-agent-studio-link';
    link.className='nav-item';
    link.href='/admin/studio';
    link.title='Design and manage AI agents';
    const ico=document.createElement('span');ico.textContent='✦';
    const name=document.createElement('span');name.textContent='Agent Studio';
    link.append(ico,name);
    nav.append(link);
  };
  const ready=()=>{add();const shell=document.getElementById('shell');
    if(shell)new MutationObserver(add).observe(shell,{childList:true,subtree:true});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);
  else ready();
})();
