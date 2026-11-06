'use strict';
const menuButton = document.getElementById('menu-toggle');
const menu = document.getElementById('site-nav');
menuButton?.addEventListener('click', () => {
  const open = menu.classList.toggle('open');
  menuButton.setAttribute('aria-expanded', String(open));
});
menu?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
  menu.classList.remove('open'); menuButton?.setAttribute('aria-expanded', 'false');
}));

const ideaForm=document.getElementById('home-idea-form');
ideaForm?.addEventListener('submit',event=>{
  event.preventDefault();
  const text=document.getElementById('home-idea')?.value.trim()||'';
  if(text.length<12){document.getElementById('home-idea').focus();return;}
  try{sessionStorage.setItem('agent-studio.pending-description',text);}catch{}
  window.location.assign('/admin/studio');
});
