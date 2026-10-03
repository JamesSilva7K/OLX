'use strict';
let _currentPage='dashboard';
let _TK='',_ID=0,_ROLE='',_SUP=false,_SLUG=_JINJA_SLUG||'',_REF=null,_WA_T=null,_BADGES=[],_ALL_EV=[],_EV_F='all';
const SK='blade_admin_v2';
let _pmap = {};
// Alias para compatibilidade: bootWithSession é a mesma coisa que bootApp
function bootWithSession(session) { bootApp(session); }

// ── ENHANCED TOAST SYSTEM ──────────────────────────────────────
const TOAST_ICONS = {
  ok:  '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
  err: '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  inf: '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  wrn: '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  ld:  '<div class="spin"></div>',
};
const TOAST_TYPE_MAP = {ok:'ok',success:'ok',check:'ok',err:'err',error:'err',info:'inf',inf:'inf',warn:'wrn',warning:'wrn',load:'ld',loading:'ld'};
let _toastLoadingEl = null;

function toast(msg, t, d) {
  t = t || 'ok'; d = d || 3000;
  const h = document.getElementById('toast-host');
  const type = TOAST_TYPE_MAP[t] || 'inf';
  const el = document.createElement('div');
  el.className = 'toast';
  el.style.setProperty('--toast-dur', d + 'ms');
  el.innerHTML = '<div class="toast-ico ' + type + '">' + (TOAST_ICONS[type]||'') + '</div>' +
    '<div class="toast-msg">' + msg + '</div>' +
    '<button class="toast-close" onclick="this.closest(\'.toast\').remove()">&#10005;</button>';
  h.appendChild(el);
  if (t === 'load' || t === 'loading') { _toastLoadingEl = el; return el; }
  setTimeout(function(){ el.classList.add('out'); setTimeout(function(){ el.remove(); }, 260); }, d);
  return el;
}
function toastDismissLoading(msg, t='ok') {
  if (_toastLoadingEl) { _toastLoadingEl.remove(); _toastLoadingEl = null; }
  if (msg) toast(msg, t, 3000);
}

// ── PROGRESS BAR HELPERS ────────────────────────────────────────
function showConnBar() { document.getElementById('conn-bar').classList.add('show'); }
function hideConnBar() { document.getElementById('conn-bar').classList.remove('show'); }

// ── THEME TOGGLE ────────────────────────────────────────────────
function toggleTheme() {
  const html = document.documentElement;
  const curr = html.getAttribute('data-theme') || 'dark';
  const next = curr === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('blade_theme', next);
  document.getElementById('theme-ico-dark').style.display = next === 'dark' ? '' : 'none';
  document.getElementById('theme-ico-light').style.display = next === 'light' ? '' : 'none';
  document.querySelector('meta[name="theme-color"]').content = next === 'dark' ? '#0f0018' : '#F0EBF8';
}
function applyTheme() {
  const saved = localStorage.getItem('blade_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const di = document.getElementById('theme-ico-dark'), li = document.getElementById('theme-ico-light');
  if (di) di.style.display = saved === 'dark' ? '' : 'none';
  if (li) li.style.display = saved === 'light' ? '' : 'none';
}

// ── GLOBAL LOADER ────────────────────────────────────────────────
function setLoader(msg, pct) {
  const m = document.getElementById('gl-msg'), b = document.getElementById('gl-bar');
  if (m) m.textContent = msg || '';
  if (b && pct !== undefined) b.style.width = pct + '%';
}
function hideLoader() {
  const gl = document.getElementById('global-loader');
  if (gl) { gl.classList.add('hidden'); setTimeout(() => gl.style.display='none', 400); }
}

// ── SKELETON BUILDERS ────────────────────────────────────────────
function skelKpi() { return `<div class="page-loading"><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div class="skel skel-kpi"></div><div class="skel skel-kpi"></div><div class="skel skel-kpi"></div><div class="skel skel-kpi"></div></div></div>`; }
function skelCards(n=3) { return '<div class="page-loading">' + Array(n).fill('<div class="skel skel-card"></div>').join('') + '</div>'; }
function skelRows(n=5) { return '<div class="page-loading">' + Array(n).fill('<div class="skel skel-row"></div>').join('') + '</div>'; }

function goTo(n){
  if(typeof _currentPage !== 'undefined' && _currentPage === n) return;
  _currentPage = n;
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.ni').forEach(i=>i.classList.remove('active'));
  const p=document.getElementById('page-'+n),ni=document.getElementById('ni-'+n);
  if(p)p.classList.add('active');if(ni)ni.classList.add('active');
  showConnBar();
  const done = ()=>hideConnBar();
  if(n==='events'){Promise.all([loadEvents(),loadSessions()]).finally(done);}
  else if(n==='products'){loadProducts().finally(done);}
  else if(n==='config'){loadCfg().finally(done);}
  else if(n==='profile'){loadProf().finally(done);}
  else if(n==='dashboard'){loadStats().finally(done);}
  else if(n==='monitor'){Promise.all([loadLinkMonitor(),loadLeadMonitor()]).finally(done);}
  else done();
}

async function verifyTk(tk){
  try{const r=await fetch('/api/admin/verify-token',{headers:{'Authorization':'Bearer '+tk}});if(!r.ok&&r.status===429)return{ok:false,message:'Muitas tentativas. Aguarde 30min.'};return await r.json();}catch{return null;}
}

function syncTelegramProfile() {
  const tg = window.Telegram?.WebApp;
  const user = tg?.initDataUnsafe?.user;
  if(user) {
    const pfName = document.getElementById('auto-pf-name');
    const pfUser = document.getElementById('auto-pf-user');
    const pfAv = document.getElementById('auto-pf-avatar');
    if(pfName) pfName.textContent = (user.first_name||'') + ' ' + (user.last_name||'').trim();
    if(pfUser) pfUser.textContent = user.username ? '@' + user.username : user.id;
    if(pfAv && user.photo_url) {
      pfAv.innerHTML = `<img src="${user.photo_url}" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;" />`;
    } else if (pfAv && user.first_name) {
      pfAv.innerHTML = `<span style="font-size:24px">${user.first_name[0]}</span>`;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  syncTelegramProfile();
  initTWA();
  setupPinBoxes();
  // Auto-login from saved token
  const saved = localStorage.getItem(SK);
  if (saved) {
    verifyTk(saved).then(res => {
      if (res && res.ok) {
        _TK = saved;
        bootWithSession({token: saved, admin_id: res.admin_id, role: res.role, is_supreme: res.is_supreme, profile: res.profile, plan: res.plan});
      }
    });
  }
});

// Store profile globally
let _PROF = {};


function applyProfileUI(prof, id, sup, role, slug) {
  const name = (prof && prof.display_name && !prof.display_name.startsWith('Admin #')) 
    ? prof.display_name 
    : (id ? 'Admin #' + id : 'Administrador');
  const avatar = prof && prof.avatar_url ? prof.avatar_url : '';
  const letter = name.charAt(0).toUpperCase() || 'A';
  const roleLabel = sup ? 'Supreme Admin' : 'Administrador';
  const slugLabel = slug ? '@' + slug : '@admin';

  // Header avatar + name
  setAvEl('av-letter', letter, avatar);
  const admNameEl = document.getElementById('adm-name');
  if (admNameEl) admNameEl.textContent = name;
  const admRoleEl = document.getElementById('adm-role');
  if (admRoleEl) { admRoleEl.textContent = roleLabel; admRoleEl.className = 'role-tag ' + (sup ? 'role-sup' : 'role-adm'); }

  // Profile page hero
  setAvEl('prof-av-lg', letter, avatar);
  const hn = document.getElementById('prof-hero-name'); if (hn) hn.textContent = name;
  const hr = document.getElementById('prof-hero-role'); if (hr) { hr.textContent = roleLabel; hr.className = 'role-tag ' + (sup ? 'role-sup' : 'role-adm'); }
  const hs = document.getElementById('prof-hero-slug'); if (hs) hs.textContent = slugLabel;

  // Profile edit form
  const pfName = document.getElementById('pf-name'); if (pfName && !pfName.value) pfName.value = prof && prof.display_name ? prof.display_name : '';
  const pfBio = document.getElementById('pf-bio'); if (pfBio && !pfBio.value) pfBio.value = prof && prof.bio ? prof.bio : '';
  const pfContact = document.getElementById('pf-contact'); if (pfContact && !pfContact.value) pfContact.value = prof && prof.contact ? prof.contact : '';
  const pfAv = document.getElementById('pf-avatar'); if (pfAv && !pfAv.value) pfAv.value = avatar;
  prevAvatar(avatar);

  // Session info in profile
  const ti = document.getElementById('prof-tok-id'); if (ti) ti.textContent = id || '—';
  const tr = document.getElementById('prof-tok-role'); if (tr) tr.textContent = role || '—';
  const ts = document.getElementById('prof-tok-slug'); if (ts) ts.textContent = slug ? slug : (role==='supreme_admin' ? 'Master (S/ Slug)' : 'N/A');

  // Token security tab
  const tokPrev = document.getElementById('tok-prev'); if (tokPrev && _TK) tokPrev.textContent = _TK.slice(0,12)+'...'+_TK.slice(-4);
  const tokId = document.getElementById('tok-id'); if (tokId) tokId.textContent = id || '—';
  const tokRole = document.getElementById('tok-role'); if (tokRole) tokRole.textContent = role || '—';
}

function setAvEl(id, letter, avatarUrl) {
  const el = document.getElementById(id);
  if (!el) return;
  if (avatarUrl) {
    el.innerHTML = '<img src="' + avatarUrl + '" onerror="this.remove()" />' + letter;
  } else {
    el.textContent = letter;
  }
}

function prevAvatar(url) {
  const wrap = document.getElementById('av-prev');
  const letter = document.getElementById('av-prev-letter');
  if (!wrap) return;
  if (url) {
    wrap.innerHTML = '<img src="' + url + '" onerror="this.remove()" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>';
  } else {
    wrap.innerHTML = '<span id="av-prev-letter">' + (letter ? letter.textContent : 'A') + '</span>';
  }
}

function bootApp(a){
  document.getElementById('auth-gate').style.display='none';
  const sh=document.getElementById('app-shell');sh.style.display='flex';
  const rp=_SUP?'SUPREME':'ADMIN';
  const hdrBadge=document.getElementById('hdr-badge');if(hdrBadge)hdrBadge.textContent=rp;

  // Apply profile from verify-token response immediately (no extra request needed)
  const slug = (a.plan && a.plan.slug) ? a.plan.slug : _SLUG;
  _PROF = (a.profile && a.profile.display_name) ? a.profile : {};
  
  // Magically pull Telegram data if missing!
  if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
     const tgUser = window.Telegram.WebApp.initDataUnsafe.user;
     if(!_PROF.display_name || _PROF.display_name.startsWith('Admin #')) {
         _PROF.display_name = tgUser.first_name + (tgUser.last_name ? ' ' + tgUser.last_name : '');
     }
     if(!_PROF.avatar_url && tgUser.photo_url) {
         _PROF.avatar_url = tgUser.photo_url;
     }
  }
  
  applyProfileUI(_PROF, _ID, _SUP, _ROLE, slug);

  if(_SUP){
    document.querySelectorAll('[data-sup]').forEach(e=>e.style.display='block');
    const fc=document.getElementById('fin-card');if(fc)fc.style.display='block';
    const sow=document.getElementById('sup-overview-wrap');if(sow)sow.style.display='block';
    loadC7();setInterval(loadC7,120000);
  } else {
    document.querySelectorAll('[data-sup]').forEach(e=>e.style.display='none');
    const sow=document.getElementById('sup-overview-wrap');if(sow)sow.style.display='none';
  }
  if(a.plan&&a.plan.slug)_SLUG=a.plan.slug;
  updLink();
  // Load initial page data then hide loader
  loadStats().then(()=>{ hideLoader(); }).catch(()=>hideLoader());
  _REF=setInterval(fullRefresh,30000);
}

function doLogout(){
  localStorage.removeItem(SK);_TK='';_ID=0;_ROLE='';_SUP=false;
  if(_REF){clearInterval(_REF);_REF=null;}
  closeLivePreview();
  toast('Sessão encerrada. Redirecionando...','info',1500);
  setTimeout(()=>{ window.location.href=window.location.pathname; }, 1200);
}


async function initTWA() {
  applyTheme();
  setLoader('Iniciando painel...', 10);
  
  // Wait briefly to ensure Telegram SDK is fully attached
  await new Promise(r => setTimeout(r, 200));

  let initData = '';
  let initUnsafe = {};
  let tgUserId = 0;

  if (window.Telegram && window.Telegram.WebApp) {
    const twa = window.Telegram.WebApp;
    twa.ready();
    twa.expand();
    initData = twa.initData || '';
    initUnsafe = twa.initDataUnsafe || {};
    tgUserId = (initUnsafe.user && initUnsafe.user.id) ? initUnsafe.user.id : 0;
  }

  // Fallback: extract hash
  if (!initData && window.location.hash.includes('tgWebAppData=')) {
    try {
      const qs = new URLSearchParams(window.location.hash.substring(1));
      initData = qs.get('tgWebAppData') || '';
    } catch(e){}
  }

  if (initData || tgUserId > 0) {
    const nameStr = (initUnsafe.user && initUnsafe.user.first_name) ? initUnsafe.user.first_name : 'Admin';
    document.getElementById('twa-name').textContent = nameStr;
    document.getElementById('twa-status-text').textContent = 'Autenticando...';
    document.querySelector('.twa-pulse').style.background = '#3B82F6';
    document.querySelector('.twa-pulse').style.boxShadow = '0 0 10px #3B82F6';

    if(initUnsafe.user && initUnsafe.user.photo_url){
      const av = document.getElementById('twa-av');
      if (av) av.innerHTML = '<img src="' + initUnsafe.user.photo_url + '" onerror="this.style.display=\'none\'"/>';
    }

    try {
      setLoader('Verificando chaves de segurança...', 50);
      const res = await fetch('/api/admin/twa-login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ initData: initData, initDataUnsafe: initUnsafe })
      });
      const twaData = await res.json();
      if (twaData.ok) {
        document.querySelector('.twa-pulse').style.background = '#10B981';
        document.querySelector('.twa-pulse').style.boxShadow = '0 0 15px #10B981';
        document.getElementById('twa-status-text').textContent = 'Acesso Liberado!';
        setTimeout(() => {
          _TK = twaData.token;
          localStorage.setItem(SK, _TK);
          _ID = twaData.admin_id;
          _ROLE = twaData.role;
          _SUP = twaData.is_supreme;
          bootApp(twaData);
        }, 800);
      } else {
        document.getElementById('twa-name').textContent = 'Acesso Restrito';
        document.getElementById('twa-status-text').textContent = twaData.message || 'Acesso Negado';
        document.querySelector('.twa-pulse').style.background = '#EF4444';
        document.querySelector('.twa-pulse').style.boxShadow = '0 0 10px #EF4444';
      }
    } catch(e) {
      document.getElementById('twa-status-text').textContent = 'Erro de conexão';
      document.querySelector('.twa-pulse').style.background = '#EF4444';
      document.querySelector('.twa-pulse').style.boxShadow = '0 0 10px #EF4444';
    }
    hideLoader();
  } else {
    // Absolutely no WebApp context
    hideLoader();
    document.getElementById('twa-name').textContent = 'Acesso Restrito';
    document.getElementById('twa-status-text').textContent = 'Abra via botão de WebApp no bot!';
    document.querySelector('.twa-pulse').style.background = '#F59E0B'; // Changed to Orange!
    document.querySelector('.twa-pulse').style.boxShadow = '0 0 10px #F59E0B';
  }
}


function hdrs(){return{'Authorization':'Bearer '+_TK,'Content-Type':'application/json'};}
async function apiFetch(url,opts={}){return fetch(url,{...opts,headers:{...hdrs(),...(opts.headers||{})}});}

// ── GLOBAL 401 / AUTH EXPIRY HANDLER ───────────────────────────
function handleUnauth(){
  if(_REF){clearInterval(_REF);_REF=null;}
  closeLivePreview();
  localStorage.removeItem(SK);
  toast('Sessão expirada. Redirecionando para login...','err',4000);
  setTimeout(()=>{ window.location.href=window.location.pathname; },2000);
}

// ── GLOBAL API FETCH with auth + 401 handling ───────────────────
async function apiFetchSafe(url, opts={}) {
  showConnBar();
  try {
    const r = await fetch(url, {...opts, headers:{...hdrs(),...(opts.headers||{})}});
    if(r.status === 401) { handleUnauth(); return null; }
    if(r.status === 429) { toast('Muitas requisições. Aguarde.','wrn',4000); return null; }
    return r;
  } catch(e) {
    toast('Sem conexão com o servidor.','err',4000);
    return null;
  } finally {
    hideConnBar();
  }
}


async function loadStats(){
  const kgrid = document.getElementById('kpi-skel');
  if(kgrid) kgrid.innerHTML = skelKpi();
  try{
    const url=_SLUG?'/api/admin/stats?slug='+_SLUG:'/api/admin/stats';
    const r=await apiFetch(url);
    if(r.status===401){handleUnauth();return;}
    const d=await r.json();
    if(!d.ok)return;
    const s=d.stats||d;
    const sv=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v??'—';};
    sv('st-entries',s.entries??s.page_entries??'—');
    sv('st-buy',s.click_buy??'—');
    sv('st-leads',s.leads??s.lead_captured??'—');
    sv('st-paid',s.paid??s.payment_confirmed??'—');
    sv('st-conv','Taxa: '+(s.conv_rate??0)+'%');
    const ent=parseInt(s.entries||s.page_entries||0)||1;
    const buy=parseInt(s.click_buy||0)||0;
    const lds=parseInt(s.leads||s.lead_captured||0)||0;
    const pd=parseInt(s.paid||s.payment_confirmed||0)||0;
    sv('fn-entries',ent);sv('fn-buy',buy);sv('fn-leads',lds);sv('fn-paid',pd);
    const pct=v=>Math.min(100,Math.round((v/ent)*100))+'%';
    ['buy','leads','paid'].forEach(k=>{const el=document.getElementById('fnb-'+k);if(el)el.style.width=pct(k==='buy'?buy:k==='leads'?lds:pd);});
    if(kgrid) kgrid.innerHTML = '';
  }catch(e){
    console.warn('loadStats:',e);
    if(kgrid) kgrid.innerHTML = '<div class="empty"><p>Erro ao carregar estatísticas.</p></div>';
  }
}


async function loadEvents(){
  const tb=document.getElementById('ev-tbody');
  if(tb) tb.innerHTML='<tr><td colspan="4">'+skelRows(5)+'</td></tr>';
  try{
    const url=_SLUG?'/api/admin/events?slug='+_SLUG+'&limit=50':'/api/admin/events?limit=50';
    const r=await apiFetch(url);
    if(!r||r.status===401){handleUnauth();return;}
    const d=await r.json();
  _allEv=d.events||d.logs||[];
    _ALL_EV = _allEv;
    renderEv(_EV_F);
    const c=document.getElementById('ev-cnt');if(c)c.textContent=_allEv.length+' evento(s)';
  }catch(e){
    console.warn('loadEvents:',e);
    if(tb) tb.innerHTML='<tr><td colspan="4"><div class="empty"><p>Erro ao carregar eventos.</p></div></td></tr>';
  }
}

function filterEv(t,btn){_EV_F=t;document.querySelectorAll('#ev-tabs .tp').forEach(b=>b.classList.remove('active'));if(btn)btn.classList.add('active');const titles={all:'Todos os Eventos',LEAD_CAPTURED:'Leads',CLICK_BUY:'Compras',PIX_GENERATED:'Pix Gerado',PAYMENT_CONFIRMED:'Pagamentos'};const el=document.getElementById('ev-title');if(el)el.textContent=titles[t]||'Eventos';renderEv(t);}
function renderEv(f){
  const tb=document.getElementById('ev-tbody');if(!tb)return;
  const src = (typeof _ALL_EV !== 'undefined' && _ALL_EV.length) ? _ALL_EV : (typeof _allEv !== 'undefined' ? _allEv : []);
  const list=f==='all'?src:src.filter(e=>e.type===f);
  if(!list.length){tb.innerHTML='<tr><td colspan="4"><div class="empty"><div class="empty-ico"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div><h3>Sem eventos</h3><p>Nenhum evento nessa categoria.</p></div></td></tr>';return;}
  const bc={PAGE_ENTRY:'ev-entry',CLICK_BUY:'ev-buy',LEAD_CAPTURED:'ev-lead',PIX_GENERATED:'ev-pix',PAYMENT_CONFIRMED:'ev-paid',CLICK_CHAT:'ev-chat'};
  const lb={PAGE_ENTRY:'Visita',CLICK_BUY:'Compra',LEAD_CAPTURED:'Lead',PIX_GENERATED:'Pix',PAYMENT_CONFIRMED:'Pago',CLICK_CHAT:'Chat',WHATSAPP_REDIRECT:'WhatsApp',CEP_LOOKUP:'CEP'};
  tb.innerHTML=list.slice(0,40).map(ev=>{
    const dt=new Date((ev.ts||0)*1000),tm=dt.getHours().toString().padStart(2,'0')+':'+dt.getMinutes().toString().padStart(2,'0');
    const info=ev.data?(ev.data.name||ev.data.amount||ev.data.cep||''):'';
    return '<tr><td><span class="evb '+(bc[ev.type]||'ev-def')+'">'+(lb[ev.type]||ev.type)+'</span></td><td style="font-size:11px;font-family:monospace;color:var(--c-t3)">'+(ev.ip||'—')+'</td><td style="font-size:11.5px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+info+'</td><td style="font-size:11px;color:var(--c-t3);white-space:nowrap">'+tm+'</td></tr>';
  }).join('');
}

async function loadSessions(){
  try{const url=_SLUG?'/api/admin/sessions?slug='+_SLUG+'&limit=15':'/api/admin/sessions?limit=15';const r=await apiFetch(url);const d=await r.json();const list=d.sessions||[];const el=document.getElementById('sess-list');if(!list.length){el.innerHTML='<div class="empty"><p>Nenhuma sessão.</p></div>';return;}const _sessIco='<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';el.innerHTML=list.slice(0,12).map((s,i)=>{const dt=new Date((s.entered_at||s.ts||0)*1000);const tm=dt.toLocaleDateString('pt-BR')+' '+dt.getHours().toString().padStart(2,'0')+':'+dt.getMinutes().toString().padStart(2,'0');const cv=s.converted?'<span class="chip chip-g" style="font-size:10px">Convertido</span>':'';const initials=((s.ip||'?').split('.').slice(-2).join(''));return '<div class="sess"><div class="sess-av" style="color:var(--c-purple3)">'+_sessIco+'</div><div class="sess-info"><div class="sess-ip">'+(s.ip||'—')+'</div><div class="sess-meta">'+((s.ua||'').slice(0,50)||'Desconhecido')+' '+cv+'</div></div><span class="sess-time">'+tm+'</span></div>';}).join('');}catch(e){}
}

function uploadProdFile(idx, inp){
  const file = inp.files && inp.files[0];
  if(!file) return;
  const dz = document.getElementById('p_dz'+idx);
  if(dz) dz.classList.add('loading');
  const fd = new FormData();
  fd.append('file', file);
  fetch('/api/admin/upload', {
    method: 'POST',
    headers: {'Authorization': 'Bearer '+_TK},
    body: fd
  }).then(r=>r.json()).then(d=>{
    if(dz) dz.classList.remove('loading');
    if(d.ok && d.url){
      document.getElementById('edit-img'+idx).value = d.url;
      prevProdPhoto(idx, d.url);
      toast('Foto '+idx+' enviada com sucesso!','ok');
    } else {
      toast(d.error || 'Erro no upload.','err');
    }
  }).catch(()=>{
    if(dz) dz.classList.remove('loading');
    toast('Erro de conexão no upload.','err');
  });
}

function prevProdPhoto(idx, url){
  const dz = document.getElementById('p_dz'+idx);
  if(!dz) return;
  if(url && url.trim()){
    dz.innerHTML = '<input type="file" accept="image/*" onchange="uploadProdFile('+idx+', this)"/><img src="'+url+'" onerror="this.remove()" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>';
    dz.classList.add('dz-done');
  } else {
    dz.innerHTML = '<input type="file" accept="image/*" onchange="uploadProdFile('+idx+', this)"/><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><span>Foto '+idx+(idx===1?' (Principal)':'')+'</span>';
    dz.classList.remove('dz-done');
  }
}

async function loadProducts(){
  const g=document.getElementById('prods-grid');
  if(g) g.innerHTML = skelCards(3);
  try{
    const r=await apiFetch('/api/admin/my-products');
    if(r.status===401){handleUnauth();return;}
    const d=await r.json();
    let list = d.products || [];
    if(!list.length){
      g.innerHTML='<div class="empty"><div class="empty-ico"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/></svg></div><h3>Nenhum produto</h3><p>Clique em "+ Novo" para cadastrar seu primeiro produto.</p></div>';
      return;
    }
    _pmap={};
    list.forEach(function(px){_pmap[px.product_code||px.code||'']=px;});
    g.innerHTML=list.map(p=>{
      const img=p.image1||p.image_url||p.image||'';
      const code=p.product_code||p.code||'';
      const title=p.title||p.name||'Produto Sem Nome';
      const oldp=p.old_price?'<span class="prod-oldp">R$ '+p.old_price+'</span>':'';
      const isActive=p.is_active||p.active;
      const activeBadge=isActive?'<span class="chip chip-g" style="font-size:10px;position:absolute;top:8px;right:8px">Principal</span>':'';
      const shipMode = p.shipping_mode === 'sedex' ? 'Sedex' : p.shipping_mode === 'local' ? 'Local' : 'Garantia Full';
      const prodLink = window.location.origin + '/p/' + (_SLUG || 'item') + '/' + code;
      
      const isCouponActive = p.coupon_active !== undefined ? (p.coupon_active == 1 || p.coupon_active === true) : true;
      let couponBadge = '';
      if(p.shipping_coupon && p.shipping_coupon.trim()){
        if(isCouponActive){
          couponBadge = '<span class="chip chip-g" style="font-size:10px;cursor:pointer" onclick="toggleProdCoupon(\''+code+'\', 0)" title="Clique para Desativar">🎟 ' + p.shipping_coupon.toUpperCase() + ' (Apenas Frete: Ativo ✅)</span>';
        } else {
          couponBadge = '<span class="chip chip-o" style="font-size:10px;cursor:pointer" onclick="toggleProdCoupon(\''+code+'\', 1)" title="Clique para Ativar">🎟 ' + p.shipping_coupon.toUpperCase() + ' (Cupom Pausado ⏸)</span>';
        }
      }
      
      return '<div class="prod-card" style="position:relative">'+
        '<div class="prod-img-wrap">'+(img?'<img class="prod-img" src="'+img+'" alt="'+title+'" onerror="this.style.display=\'none\'"/>':'')+
        '<div class="prod-img-ph" style="'+(img?'display:none':'')+'"><svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div>'+
        activeBadge+
        '</div>'+
        '<div class="prod-info"><div class="prod-name">'+title+'</div>'+
        '<div class="flex" style="align-items:baseline;gap:8px;margin-top:4px"><span class="prod-price">R$ '+p.price+'</span>'+oldp+'</div>'+
        '<div style="display:flex;align-items:center;gap:6px;margin-top:6px;flex-wrap:wrap">'+
          '<span class="chip chip-p" style="font-size:10px">'+shipMode+'</span>'+
          couponBadge+
          '<span class="prod-code" style="margin:0">Cod: '+code+'</span>'+
        '</div>'+
        '<div style="margin-top:8px;display:flex;gap:4px">'+
          '<input type="text" readonly value="'+prodLink+'" style="flex:1;font-size:10px;background:rgba(255,255,255,0.05);border:1px solid var(--c-border);border-radius:6px;padding:3px 6px;color:var(--c-t2);font-family:monospace" />'+
          '<button class="btn btn-g btn-xs" onclick="navigator.clipboard?.writeText(\''+prodLink+'\');toast(\'Link direto copiado!\',\'ok\')" title="Copiar Link"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>'+
          '<a href="'+prodLink+'" target="_blank" class="btn btn-g btn-xs" title="Abrir Link"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>'+
        '</div>'+
        '</div>'+
        '<div class="prod-acts" style="flex-wrap:wrap">'+
        '<button class="btn btn-s btn-xs" data-code="'+code.replace(/"/g,'&quot;')+'" data-title="'+title.replace(/"/g,'&quot;')+'" onclick="applyProd(this.dataset.code, this.dataset.title)"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>Ativar</button>'+
        '<button class="btn btn-g btn-xs" data-code="'+code.replace(/"/g,'&quot;')+'" onclick="openEditProd(_pmap[this.dataset.code])">Editar</button>'+
        '<button class="btn btn-g btn-xs" data-code="'+code.replace(/"/g,'&quot;')+'" onclick="openLivePreview(this.dataset.code)" title="Preview da página do cliente" style="color:var(--c-purple3);border-color:rgba(139,92,246,0.3)"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button>'+
        '<button class="btn btn-d btn-xs" data-code="'+code.replace(/"/g,'&quot;')+'" data-title="'+title.replace(/"/g,'&quot;')+'" onclick="delProd(this.dataset.code, this.dataset.title)" title="Excluir"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>'+
        '</div></div>';
    }).join('');
  }catch(e){
    console.warn('loadProducts:',e);
    if(g) g.innerHTML='<div class="empty"><p>Erro ao carregar produtos.</p></div>';
  }
}

async function toggleProdCoupon(code, newActive){
  if(!code) return;
  const p = _pmap ? _pmap[code] : null;
  const curFee = p ? p.shipping_fee || '19.90' : '19.90';
  const curCoupon = p ? p.shipping_coupon || '' : '';
  const curMode = p ? p.shipping_mode || 'full' : 'full';

  try {
    const r = await apiFetch('/api/admin/my-products/' + code + '/shipping', {
      method: 'POST',
      body: JSON.stringify({
        shipping_mode: curMode,
        shipping_fee: curFee,
        shipping_coupon: curCoupon,
        coupon_active: newActive ? 1 : 0,
        coupon_only_shipping: 1
      })
    });
    const d = await r.json();
    if(d.ok){
      toast(newActive ? 'Cupom ativado com sucesso!' : 'Cupom desativado com sucesso!', 'ok');
      loadProducts();
    } else {
      toast(d.error || 'Erro ao alterar status do cupom.', 'err');
    }
  } catch(e) {
    toast('Erro de conexão ao alterar cupom.', 'err');
  }
}

function openAddProd(){
  document.getElementById('prod-modal-ttl').textContent='Novo Produto no Catálogo';
  ['edit-code','edit-name','edit-price','edit-oldp','edit-desc','edit-slug','edit-img1','edit-img2','edit-img3','edit-shipping-coupon','edit-coupon-discount-value'].forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.value = '';
  });
  const sm = document.getElementById('edit-shipping-mode');
  if(sm) sm.value = 'full';
  const sf = document.getElementById('edit-shipping-fee');
  if(sf) sf.value = '19.90';
  const ca = document.getElementById('edit-coupon-active');
  if(ca) ca.checked = true;
  const cos = document.getElementById('edit-coupon-only-shipping');
  if(cos) cos.checked = true;

  document.getElementById('edit-slug').disabled=false;
  document.getElementById('edit-lnk-box').style.display='none';
  prevProdPhoto(1, '');
  prevProdPhoto(2, '');
  prevProdPhoto(3, '');
  document.getElementById('prod-modal').classList.add('open');
}

function openEditProd(p){
  if(!p) return;
  document.getElementById('prod-modal-ttl').textContent='Editar Produto';
  const code=p.product_code||p.code||'';
  document.getElementById('edit-code').value=code;
  document.getElementById('edit-name').value=p.title||p.name||'';
  document.getElementById('edit-price').value=p.price||'';
  document.getElementById('edit-oldp').value=p.old_price||'';
  document.getElementById('edit-desc').value=p.description||'';
  document.getElementById('edit-slug').value=code;
  document.getElementById('edit-slug').disabled=true;
  
  const img1 = p.image1 || p.image_url || p.image || '';
  const img2 = p.image2 || '';
  const img3 = p.image3 || '';
  document.getElementById('edit-img1').value = img1;
  document.getElementById('edit-img2').value = img2;
  document.getElementById('edit-img3').value = img3;
  prevProdPhoto(1, img1);
  prevProdPhoto(2, img2);
  prevProdPhoto(3, img3);
  
  const sm = document.getElementById('edit-shipping-mode');
  if(sm) sm.value = p.shipping_mode || 'full';
  const sf = document.getElementById('edit-shipping-fee');
  if(sf) sf.value = p.shipping_fee || '19.90';
  const sc = document.getElementById('edit-shipping-coupon');
  if(sc) sc.value = p.shipping_coupon || '';
  
  const ca = document.getElementById('edit-coupon-active');
  if(ca) ca.checked = p.coupon_active !== undefined ? (p.coupon_active == 1 || p.coupon_active === true) : true;
  const cos = document.getElementById('edit-coupon-only-shipping');
  if(cos) cos.checked = p.coupon_only_shipping !== undefined ? (p.coupon_only_shipping == 1 || p.coupon_only_shipping === true) : true;

  if(code){
    document.getElementById('edit-lnk').value=window.location.origin+'/p/'+(_SLUG||'item')+'/'+code;
    document.getElementById('edit-lnk-box').style.display='flex';
  }
  document.getElementById('prod-modal').classList.add('open');
}

function closeProdModal(){document.getElementById('prod-modal').classList.remove('open');}
function cpEditLnk(){navigator.clipboard?.writeText(document.getElementById('edit-lnk').value);toast('Link copiado!','ok');}

async function saveProd(){
  const code=document.getElementById('edit-code').value;
  const slugInp=document.getElementById('edit-slug').value.trim().replace(/[^a-z0-9_]/gi,'_').toLowerCase();
  const name=document.getElementById('edit-name').value.trim();
  const price=document.getElementById('edit-price').value.trim();
  const oldp=document.getElementById('edit-oldp').value.trim();
  const desc=document.getElementById('edit-desc').value.trim();
  const img1=document.getElementById('edit-img1').value.trim();
  const img2=document.getElementById('edit-img2').value.trim();
  const img3=document.getElementById('edit-img3').value.trim();
  const shipping_mode=document.getElementById('edit-shipping-mode').value;
  const shipping_fee=document.getElementById('edit-shipping-fee').value.trim();
  const shipping_coupon=document.getElementById('edit-shipping-coupon').value.trim();
  const coupon_discount_value=document.getElementById('edit-coupon-discount-value').value.trim();
  const coupon_active=document.getElementById('edit-coupon-active') ? (document.getElementById('edit-coupon-active').checked ? 1 : 0) : 1;
  const coupon_only_shipping=document.getElementById('edit-coupon-only-shipping') ? (document.getElementById('edit-coupon-only-shipping').checked ? 1 : 0) : 1;

  if(!name||!price){toast('Nome e Preço são obrigatórios.','err');return;}
  
  const btn=document.getElementById('save-prod-btn'),sp=document.getElementById('save-prod-txt');
  btn.disabled=true;sp.textContent='Salvando...';
  
  const payload = {
    title: name,
    name: name,
    price: price,
    old_price: oldp,
    description: desc,
    image1: img1,
    image2: img2,
    image3: img3,
    image_url: img1,
    shipping_mode: shipping_mode,
    shipping_fee: shipping_fee,
    shipping_coupon: shipping_coupon,
    coupon_active: coupon_active,
    coupon_only_shipping: coupon_only_shipping,
    product_code: slugInp || code
  };

  try{
    let r;
    if(code){
      r=await apiFetch('/api/admin/my-products/'+code, {method:'PUT', body:JSON.stringify(payload)});
    }else{
      r=await apiFetch('/api/admin/my-products', {method:'POST', body:JSON.stringify(payload)});
    }
    const d=await r.json();
    if(d.ok){
      toast(code?'Produto atualizado com sucesso!':'Produto criado com sucesso!','ok');
      closeProdModal();
      loadProducts();
      if(typeof _onProdSaved==='function') _onProdSaved();
    }else{
      toast(d.error||'Erro ao salvar produto.','err');
    }
  }catch{
    toast('Erro de conexão.','err');
  }finally{
    btn.disabled=false;sp.textContent='Salvar Produto';
  }
}

async function applyProd(code,name){
  if(!confirm('Definir "'+name+'" como produto principal?'))return;
  try{
    const r=await apiFetch('/api/products/'+code+'/apply',{method:'POST'});
    const d=await r.json();
    if(d.ok)toast('"'+name+'" ativado como produto principal!','ok',4000);
    else toast(d.error||'Erro.','err');
  }catch{toast('Erro.','err');}
}

async function delProd(code,name){
  if(!confirm('Excluir produto "'+name+'"?'))return;
  try{
    const r=await apiFetch('/api/admin/my-products/'+code,{method:'DELETE'});
    const d=await r.json();
    if(d.ok){toast('Produto excluído com sucesso!','info');loadProducts();}
    else toast(d.error||'Erro ao excluir.','err');
  }catch{toast('Erro.','err');}
}

async function loadCfg(){
  try{const url=_SLUG?'/api/config/'+_SLUG:'/api/config';const r=await fetch(url);const d=await r.json();const sv=(id,v)=>{const el=document.getElementById(id);if(el&&v!==undefined)el.value=v;};sv('cfg-pname',d.product_name);sv('cfg-price',d.product_price);sv('cfg-oldp',d.product_old_price);sv('cfg-desc',d.product_description);sv('cfg-img',d.product_image);sv('cfg-sname',d.seller_name);sv('cfg-ssince',d.seller_since);sv('cfg-sstatus',d.seller_status);sv('cfg-logo',d.logo_url);sv('cfg-wa',d.whatsapp_number);sv('cfg-wa-msg',d.whatsapp_message);sv('pu1',d.product_image1);sv('pu2',d.product_image2);sv('pu3',d.product_image3);if(d.logo_url)prevLogo(d.logo_url);const defBadges = Object.values(PB).map(b => ({url:b.url, label:b.label, active:true}));if(d.payment_badges){try{_BADGES=JSON.parse(d.payment_badges);if(!Array.isArray(_BADGES))_BADGES=defBadges;}catch(e){_BADGES=defBadges;}}else{_BADGES=defBadges;}renderBadges();loadTgls();}catch(e){}
}
async function loadTgls(){try{const r=await apiFetch('/api/admin/config');const d=await r.json();if(!d.ok)return;const c=d.config||{};const sc=(id,v)=>{const el=document.getElementById(id);if(el)el.checked=v==='1'||v===true||v===1;};sc('tgl-active',c.active);sc('tgl-pixel',c.pixel_active);sc('tgl-notif',c.notifications);}catch{}}

async function saveCfg(u){try{const r=await apiFetch('/api/admin/config',{method:'POST',body:JSON.stringify(u)});const d=await r.json();if(d.ok)toast('Configurações salvas!','ok');else toast(d.error||d.message||'Erro.','err');}catch{toast('Erro.','err');}}
function saveProdCfg(){saveCfg({product_name:document.getElementById('cfg-pname').value,product_price:document.getElementById('cfg-price').value,product_old_price:document.getElementById('cfg-oldp').value,product_description:document.getElementById('cfg-desc').value,product_image:document.getElementById('cfg-img').value});}
function saveSellerCfg(){saveCfg({seller_name:document.getElementById('cfg-sname').value,seller_since:document.getElementById('cfg-ssince').value,seller_status:document.getElementById('cfg-sstatus').value});}
function saveWaCfg(){saveCfg({whatsapp_number:document.getElementById('cfg-wa').value,whatsapp_message:document.getElementById('cfg-wa-msg').value});}
function saveTgl(k,v){saveCfg({[k]:v?'1':'0'});}
function saveVisualCfg(){saveCfg({logo_url:document.getElementById('cfg-logo').value, payment_badges:JSON.stringify(_BADGES)});}
function savePhotos(){saveCfg({product_image1:document.getElementById('pu1').value,product_image2:document.getElementById('pu2').value,product_image3:document.getElementById('pu3').value});}

function cfgTab(n,btn){
  ['produto','vendedor','whatsapp','visual','sistema','financeiro'].forEach(t=>{
    const e=document.getElementById('ct-'+t);
    if(e)e.classList.add('hidden');
  });
  document.querySelectorAll('#cfg-tabs .tp').forEach(b=>b.classList.remove('active'));
  
  if(n==='visual'){
    ['produto','vendedor','whatsapp','visual'].forEach(t=>{
      const e=document.getElementById('ct-'+t);
      if(e)e.classList.remove('hidden');
    });
  }else{
    const e=document.getElementById('ct-'+n);
    if(e)e.classList.remove('hidden');
  }
  if(btn)btn.classList.add('active');
  if(n==='sistema')loadStatus();
}

async function loadProf(){
  try {
    // Fetch rich profile with personal stats
    const r = await apiFetch('/api/admin/me');
    const d = await r.json();
    if (d.ok) {
      _PROF = d.profile || {};
      applyProfileUI(_PROF, d.admin_id || _ID, d.is_supreme || _SUP, d.role || _ROLE, d.slug || _SLUG);
      // Fill personal stats 24h
      const s = d.stats_24h || {};
      const sv = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ?? '—'; };
      sv('ps-entries', s.page_entries ?? s.entries ?? '—');
      sv('ps-buy',     s.click_buy ?? '—');
      sv('ps-leads',   s.leads ?? s.lead_captured ?? '—');
      sv('ps-paid',    s.paid ?? s.payment_confirmed ?? '—');
    }
  } catch(e) { console.warn('loadProf:', e); }
  // Load other admins
  try {
    const r2 = await apiFetch('/api/admin/profiles/all');
    const d2 = await r2.json();
    const c = document.getElementById('other-admins');
    const oth = (d2.profiles || []).filter(p => p.tg_id !== _ID);
    if (!oth.length) {
      c.innerHTML = '<div class="empty"><p>Nenhum outro admin cadastrado.</p></div>';
    } else {
      c.innerHTML = oth.map(p => {
        const name = p.display_name || 'Admin #' + p.tg_id;
        const letter = name.charAt(0).toUpperCase();
        const av = p.avatar_url ? '<img src="' + p.avatar_url + '" onerror="this.remove()" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>' + letter : letter;
        return '<div class="sess"><div class="sess-av" style="overflow:hidden;position:relative">' + av + '</div><div class="sess-info"><div class="sess-ip">' + name + '</div><div class="sess-meta">\' + (p.bio || p.contact || \'@\' + (p.username || \'—\')) + \'</div><div class="sess-meta" style="margin-top:4px;color:var(--c-purple3);display:flex;gap:12px"><span>Vendas: \' + (p.sales_count||0) + \'</span><span>Produtos: \' + (p.products_count||0) + \'</span></div></div>\' + (p.slug ? \'<span class="sess-time">/\' + p.slug + \'</span>\' : \'\') + \'</div>\';
      }).join('');
    }
  } catch(e) {}
  // Supreme overview
  if (_SUP) loadSupremeOverview();
}

async function loadSupremeOverview() {
  const el = document.getElementById('sup-admins-list');
  if (!el) return;
  try {
    const r = await apiFetch('/api/admin/supreme/full-overview');
    const d = await r.json();
    if (!d.ok) { el.innerHTML = '<div class="empty"><p>' + (d.error || 'Indisponivel.') + '</p></div>'; return; }
    const admins = d.admins || [];
    if (!admins.length) { el.innerHTML = '<div class="empty"><p>Nenhum admin registrado.</p></div>'; return; }
    el.innerHTML = admins.map(a => {
      const prof = a.profile || {};
      const name = prof.display_name || 'Admin #' + a.tg_id;
      const letter = name.charAt(0).toUpperCase();
      const av = prof.avatar_url ? '<img src="' + prof.avatar_url + '" onerror="this.remove()" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>' + letter : letter;
      const s24 = a.stats_24h || {};
      const planChip = a.plan && a.plan.plan_name ? '<span class="chip chip-p" style="font-size:10px;margin-left:auto">' + a.plan.plan_name + '</span>' : '';
      return '<div class="sup-admin-card" style="border:1px solid rgba(139,92,246,0.2);box-shadow:0 8px 24px rgba(0,0,0,0.2)">' +
        '<div class="sup-admin-head">' +
          '<div class="adm-av" style="overflow:hidden;position:relative">' + av + '</div>' +
          '<div style="flex:1;min-width:0"><div class="sup-admin-name">' + name + '</div><div class="sup-admin-slug" style="color:var(--c-purple3)"><svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Blindagem de Dados: Ativa</div></div>' +
          planChip +
        '</div>' +
        '<div class="sup-stat-row">' +
          '<div class="sup-stat-chip"><div class="sup-stat-chip-val">' + (s24.page_entries ?? s24.entries ?? 0) + '</div><div class="sup-stat-chip-lbl">Visitas</div></div>' +
          '<div class="sup-stat-chip"><div class="sup-stat-chip-val">' + (s24.leads ?? s24.lead_captured ?? 0) + '</div><div class="sup-stat-chip-lbl">Leads</div></div>' +
          '<div class="sup-stat-chip"><div class="sup-stat-chip-val">' + (s24.paid ?? s24.payment_confirmed ?? 0) + '</div><div class="sup-stat-chip-lbl">Pagos</div></div>' +
          '<div class="sup-stat-chip"><div class="sup-stat-chip-val">' + (a.products ? a.products.length : 0) + '</div><div class="sup-stat-chip-lbl">Prods</div></div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.05)">' +
           '<button class="btn sup-action-btn btn-promote" onclick="changeRole(' + a.tg_id + ')">Mudar Cargo</button>' +
           '<button class="btn sup-action-btn btn-block" onclick="blockAdmin(' + a.tg_id + ')">Bloquear (Blindagem)</button>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {
    el.innerHTML = '<div class="empty"><p>Erro ao carregar overview.</p></div>';
  }
}

window.changeRole = async function(tg_id) {
    const p = prompt('Digite o novo plano (free, starter, pro, unlimited):');
    if(!p) return;
    try {
        const r = await apiFetch('/api/admin/supreme/set-plan', {
            method: 'POST',
            body: JSON.stringify({tg_id: tg_id, plan: p.toLowerCase().trim()})
        });
        const d = await r.json();
        if(d.ok) {
            toast('Cargo atualizado com sucesso! (Blindagem verificada)', 'ok');
            loadSupremeOverview();
        } else {
            toast(d.error || 'Erro ao alterar plano', 'err');
        }
    } catch(e) {
        toast('Erro de conexão', 'err');
    }
}

window.blockAdmin = async function(tg_id) {
    if(!confirm('Tem certeza que deseja bloquear este administrador e revogar acesso financeiro? (Ação protegida pela blindagem de dados)')) return;
    try {
        const r = await apiFetch('/api/admin/supreme/set-plan', {
            method: 'POST',
            body: JSON.stringify({tg_id: tg_id, plan: 'blocked'})
        });
        const d = await r.json();
        toast('Admin Bloqueado! Dados Financeiros Ocultados.', 'ok');
        loadSupremeOverview();
    } catch(e) {
        toast('Erro ao bloquear administrador.', 'err');
    }
}
async function saveProf(){
  const btn=document.getElementById('save-prof-txt');if(btn)btn.textContent='Salvando...';
  try{
    const name=document.getElementById('pf-name')?.value||'';
    const bio=document.getElementById('pf-bio')?.value||'';
    const contact=document.getElementById('pf-contact')?.value||'';
    const avatar_url=document.getElementById('pf-avatar')?.value||'';
    const r=await apiFetch('/api/admin/profile',{method:'POST',body:JSON.stringify({display_name:name,bio,contact,avatar_url})});
    const d=await r.json();
    if(d.ok){
      toast('Perfil salvo!','ok');
      _PROF={..._PROF,display_name:name,bio,contact,avatar_url};
      applyProfileUI(_PROF,_ID,_SUP,_ROLE,_SLUG);
    }else toast(d.error||'Erro.','err');
  }catch{toast('Erro de conexão.','err');}
  if(btn)btn.textContent='Salvar Perfil';
}

async function loadC7(){if(!_SUP)return;try{const r=await apiFetch('/api/c7/balance',{method:'POST'});const d=await r.json();const fmt=v=>'R$ '+parseFloat(v||0).toLocaleString('pt-BR',{minimumFractionDigits:2});if(d.ok||d.balance!==undefined){document.getElementById('c7-bal').textContent=fmt(d.balance);document.getElementById('c7-lim').textContent=fmt(d.limit_generate);const fp=parseFloat(d.fee_pct||0),ff=parseFloat(d.fee_fixed||0);document.getElementById('c7-fee').textContent=ff>0?fp+'% + '+fmt(ff):fp+'%';}else{document.getElementById('c7-bal').textContent=d.message || (d.error && d.error.includes('api_key') ? 'Sem API Key' : d.error) || 'Erro API';document.getElementById('c7-lim').textContent='--';}}catch{document.getElementById('c7-bal').textContent='Offline';document.getElementById('c7-lim').textContent='--';}}

async function loadStatus(){try{const r=await apiFetch('/api/admin/c7-status');const d=await r.json();const el=document.getElementById('st-c7');if(el){const ok=d.c7_status==='connected'||d.c7_status==='connected_sandbox_active';el.className='chip '+(ok?'chip-g':'chip-o');el.textContent=ok?'Conectado':'Verificando';}}catch{}}

function updLink(){const l=_SLUG?window.location.origin+'/p/'+_SLUG:window.location.origin;const inp=document.getElementById('my-link'),a=document.getElementById('my-link-open');if(inp)inp.value=l;if(a)a.href=l;}
function copyMyLink(){const v=document.getElementById('my-link').value;navigator.clipboard?.writeText(v);toast('Link copiado!','ok');}
function shareLink(){const l=document.getElementById('my-link').value;if(navigator.share)navigator.share({title:'Meu Anúncio',url:l}).catch(()=>{});else{navigator.clipboard?.writeText(l);toast('Link copiado para compartilhar!','ok');}}

function renewTok(){toast('Envie /admin_link ao bot no Telegram.','inf',5000);}

function prevLogo(url){const b=document.getElementById('logo-prev'),i=document.getElementById('logo-img');if(url&&b&&i){i.src=url;b.style.display='block';}else if(b)b.style.display='none';}
async function uploadLogoFile(inp) {
  const file = inp.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/api/admin/upload', { method: 'POST', headers: { 'Authorization': 'Bearer ' + _TK }, body: fd });
    const d = await r.json();
    if (d.url) {
      document.getElementById('cfg-logo').value = d.url;
      prevLogo(d.url);
      toast('Logo enviado com sucesso!', 'ok');
    } else {
      toast(d.error || 'Erro no upload.', 'err');
    }
  } catch (e) {
    toast('Erro de conexão no upload.', 'err');
  }
  inp.value = '';
}
let _wa_t=null;
function debWa(){clearTimeout(_wa_t);_wa_t=setTimeout(validateWa,700);}
async function validateWa(){const inp=document.getElementById('cfg-wa'),dot=document.getElementById('wa-dot'),msg=document.getElementById('wa-msg');if(!inp||!inp.value.trim()){if(dot)dot.style.background='rgba(255,255,255,0.12)';return;}if(dot)dot.style.background='#F59E0B';try{const r=await apiFetch('/api/admin/validate-whatsapp',{method:'POST',body:JSON.stringify({number:inp.value.trim()})});const d=await r.json();if(d.valid){dot.style.background='#10B981';inp.value=d.clean_number||inp.value;if(msg){msg.textContent=(d.formatted_national||'')+' — '+(d.ddd_info?.region||'Brasil');msg.style.color='#34D399';}}else{dot.style.background='#EF4444';if(msg){msg.textContent=d.error||'Número inválido.';msg.style.color='#F87171';}}}catch{if(dot)dot.style.background='#EF4444';}}

async function upPhoto(n,inp){const file=inp.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);try{const r=await fetch('/api/admin/upload',{method:'POST',headers:{'Authorization':'Bearer '+_TK},body:fd});const d=await r.json();if(d.url){document.getElementById('pu'+n).value=d.url;const dz=document.getElementById('dz'+n);if(dz){dz.innerHTML='<img src="'+d.url+'" />';dz.classList.add('dz-done');}toast('Foto '+n+' enviada!','ok');}else toast(d.error||'Erro.','err');}catch{toast('Erro upload.','err');}}
function prevPhoto(n){const url=document.getElementById('pu'+n)?.value.trim();const dz=document.getElementById('dz'+n);if(!dz)return;if(url){dz.innerHTML='<input type="file" id="fi'+n+'" accept="image/*" onchange="upPhoto('+n+',this)"/><img src="'+url+'" onerror="this.style.display=&quot;none&quot;" />';dz.classList.add('dz-done');}}

const PB={pix:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Logo%E2%80%94pix_powered_by_Banco_Central_%28Brazil%2C_2020%29.svg/512px-Logo%E2%80%94pix_powered_by_Banco_Central_%28Brazil%2C_2020%29.svg.png',label:'Pix'},visa:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Visa_Inc._logo.svg/512px-Visa_Inc._logo.svg.png',label:'Visa'},master:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Mastercard-logo.svg/512px-Mastercard-logo.svg.png',label:'Mastercard'},elo:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/Elo_logo.svg/512px-Elo_logo.svg.png',label:'Elo'},amex:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/American_Express_logo.svg/512px-American_Express_logo.svg.png',label:'Amex'},boleto:{url:'https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/Boleto_logo.svg/512px-Boleto_logo.svg.png',label:'Boleto'}};
function addPBadge(k){const b=PB[k];if(!b)return;if(_BADGES.some(x=>x.url===b.url)){toast('Badge já adicionada.','info');return;}_BADGES.push({url:b.url,label:b.label,active:true});renderBadges();}
function addBadgeURL(){const i=document.getElementById('badge-url');const url=i.value.trim();if(!url)return;if(_BADGES.some(x=>x.url===url)){toast('Já adicionada.','info');return;}_BADGES.push({url,label:'URL',active:true});renderBadges();i.value='';}
async function uploadBadgeFile(inp) {
  const file = inp.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/api/admin/upload', {method:'POST', headers:{'Authorization':'Bearer '+_TK}, body:fd});
    const d = await r.json();
    if (d.url) {
      if (_BADGES.some(x => x.url === d.url)) { toast('Badge já adicionada.', 'info'); return; }
      _BADGES.push({url: d.url, label: 'Upload', active: true});
      renderBadges();
      toast('Badge adicionada via upload!', 'ok');
    } else {
      toast(d.error || 'Erro no upload.', 'err');
    }
  } catch (e) {
    toast('Erro de upload.', 'err');
  }
  inp.value = '';
}
function toggleBadgeStatus(i) {
  _BADGES[i].active = !(_BADGES[i].active !== false);
  renderBadges();
}
function delBadge(i){_BADGES.splice(i,1);renderBadges();}
function clearBadges(){if(!confirm('Remover todas as badges?'))return;_BADGES=[];renderBadges();toast('Badges removidas.','info');}
function setAllBadges(active) {
  _BADGES.forEach(b => b.active = active);
  renderBadges();
}
function renderBadges() {
  const g = document.getElementById('badge-grid');
  if (!g) return;
  if (!_BADGES.length) {
    g.innerHTML = '<span style="font-size:12px;color:var(--c-t3)">Nenhum método adicionado.</span>';
    return;
  }
  g.innerHTML = _BADGES.map((b, i) => {
    const isActive = b.active !== false;
    const op = isActive ? '1' : '0.35';
    const filter = isActive ? 'grayscale(0%)' : 'grayscale(100%)';
    const scale = isActive ? '1.0' : '0.96';
    return `<div class="badge-chip" style="opacity:${op}; filter:${filter}; transform:scale(${scale}); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer;" onclick="document.getElementById('tgl-badge-${i}').click()">
      <img src="${b.url}" alt="${b.label||'badge'}" onerror="this.style.opacity='0.3'" style="transition: all 0.4s ease;"/>
      ${b.label ? `<span style="font-size:10px;font-weight:700;color:var(--c-t3);margin-right:6px">${b.label}</span>` : ''}
      <div style="display:flex;gap:4px;margin-left:auto;align-items:center" onclick="event.stopPropagation()">
        <label class="tgl" style="transform:scale(0.7);margin-bottom:0">
          <input type="checkbox" id="tgl-badge-${i}" ${isActive ? 'checked' : ''} onchange="toggleBadgeStatus(${i})" />
          <span class="tgl-sl"></span>
        </label>
        <button class="btn btn-d btn-xs" style="padding:0 6px;height:22px" onclick="delBadge(${i})">×</button>
      </div>
    </div>`;
  }).join('');
}


async function loadLinkMonitor(){
  const el=document.getElementById('mon-link-list');if(!el)return;
  try{
    const url=_SLUG?'/api/admin/stats?slug='+_SLUG:'/api/admin/stats';
    const r=await apiFetch(url);const d=await r.json();const s=d.stats||d;
    const sv=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v??'0';};
    sv('mon-total-visits',s.entries??s.page_entries??'0');
    sv('mon-unique-visits',s.unique_visitors??'0');
    sv('mon-leads-today',s.leads??s.lead_captured??'0');
    const conv=s.conv_rate??0;sv('mon-conv-rate',conv+'%');
    
    const rLinks = await apiFetch('/api/admin/monitor/links?limit=10');
    const dLinks = await rLinks.json();
    if(dLinks.ok && dLinks.links && dLinks.links.length){
      el.innerHTML = '<table class="dtbl" style="width:100%;margin-top:10px"><thead><tr><th>Link/Produto</th><th>Visitas</th><th>Leads</th><th>Conversão</th></tr></thead><tbody>' + 
      dLinks.links.map(lk => `<tr><td><span class="chip chip-p">${lk.code||'Principal'}</span></td><td style="font-weight:700">${lk.views||0}</td><td style="color:var(--c-green);font-weight:700">${lk.leads||0}</td><td>${lk.conv_rate||0}%</td></tr>`).join('') + 
      '</tbody></table>';
    } else {
      el.innerHTML='<div class="empty"><p>Nenhuma performance registrada.</p></div>';
    }
    loadVisitorsMonitor();
  }catch(e){console.error(e);if(el)el.innerHTML='<div class="empty"><p>Erro ao atualizar métricas.</p></div>';}
}

async function loadVisitorsMonitor() {
  const el=document.getElementById('mon-visitors-list');if(!el)return;
  try{
    const r=await apiFetch('/api/admin/monitor/visitors?limit=10');
    const d=await r.json();
    if(d.ok && d.visitors && d.visitors.length){
      el.innerHTML = '<div style="display:flex;flex-direction:column;">' + 
      d.visitors.map(v => {
        const dt = new Date((v.ts||0)*1000);
        return `<div class="sess"><div class="sess-av">${v.ip?v.ip[0]:'?'}</div><div class="sess-info"><div class="sess-ip">${v.ip||'—'}</div><div class="sess-meta">${v.ua||'—'} &bull; Produto: ${v.product_code||'Principal'}</div></div><div class="sess-time">${dt.getHours().toString().padStart(2,'0')}:${dt.getMinutes().toString().padStart(2,'0')}</div></div>`;
      }).join('') + '</div>';
    } else {
      el.innerHTML='<div class="empty"><p>Nenhum visitante recente.</p></div>';
    }
  }catch(e){if(el)el.innerHTML='<div class="empty"><p>Erro ao carregar visitantes.</p></div>';}
}
let _LEADS_CACHE = [];
async function loadLeadMonitor(){
  const el=document.getElementById('mon-leads-list');if(!el)return;
  try{
    const r=await apiFetch('/api/admin/monitor/leads?limit=50');
    const d=await r.json();
    if(!d.ok){el.innerHTML='<div class="empty"><p>Erro ao carregar leads.</p></div>';return;}
    _LEADS_CACHE = d.leads||[];
    const badge=document.getElementById('leads-badge');
    if(badge)badge.textContent=_LEADS_CACHE.length+' leads';
    // Update today counter
    const todayEl=document.getElementById('mon-leads-today');if(todayEl)todayEl.textContent=d.today_count??'—';
    renderLeadsUI(_LEADS_CACHE);
  }catch(e){if(el)el.innerHTML='<div class="empty"><p>Erro.</p></div>';}
}

function filterLeadsUI(){
  const q=(document.getElementById('lead-search')?.value||'').toLowerCase();
  if(!q){renderLeadsUI(_LEADS_CACHE);return;}
  const filtered=_LEADS_CACHE.filter(ld=>{
    return (ld.name||'').toLowerCase().includes(q)||(ld.cpf||'').toLowerCase().includes(q)||
           (ld.phone||'').toLowerCase().includes(q)||(ld.email||'').toLowerCase().includes(q)||
           (ld.city||'').toLowerCase().includes(q)||(ld.slug||'').toLowerCase().includes(q);
  });
  renderLeadsUI(filtered);
}

function renderLeadsUI(list){
  const el=document.getElementById('mon-leads-list');if(!el)return;
  if(!list.length){el.innerHTML='<div class="empty"><p>Nenhum lead encontrado.</p></div>';return;}
  el.innerHTML=list.map(ld=>{
    const dt=new Date((ld.ts||0)*1000);
    const tm=dt.toLocaleDateString('pt-BR')+' '+dt.getHours().toString().padStart(2,'0')+':'+dt.getMinutes().toString().padStart(2,'0');
    const name=ld.name||'—';
    const phone=ld.phone||'—';
    const cpf=ld.cpf||'—';
    const email=ld.email||'';
    const city=ld.city?(ld.city+(ld.state?'/'+ld.state:'')):'—';
    const product=ld.product||'—';
    const amount=ld.amount?'R$ '+parseFloat(ld.amount).toFixed(2).replace('.',','):'—';
    const verified=ld.cpf_verified;
    const addr=ld.street?(ld.street+(ld.number?', '+ld.number:'')+(ld.neighborhood?', '+ld.neighborhood:'')):'—';
    const initials=name.split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase()||'?';
    return `<div class="lead-card" style="border-bottom:1px solid var(--c-border);padding:12px 14px;display:flex;flex-direction:column;gap:8px;transition:background .15s" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background=''">` +
      `<div style="display:flex;align-items:center;gap:10px">` +
        `<div style="width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#7C3AED,#A855F7);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;flex-shrink:0">${initials}</div>` +
        `<div style="flex:1;min-width:0">` +
          `<div style="font-size:14px;font-weight:700;color:var(--c-text);display:flex;align-items:center;gap:6px">${name}` +
            (verified?'<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:20px;background:rgba(16,185,129,0.15);color:#34D399;border:1px solid rgba(16,185,129,0.3);display:inline-flex;align-items:center;gap:2px"><svg width="9" height="9" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>CPF OK</span>':'')+
          `</div>` +
          `<div style="font-size:12px;color:var(--c-t3);margin-top:2px">${tm} · <code style="font-size:11px">${ld.ip||'—'}</code></div>` +
        `</div>` +
        `<div style="text-align:right;flex-shrink:0">` +
          `<div style="font-size:13px;font-weight:800;color:var(--c-green)">${amount}</div>` +
          `<div style="font-size:10px;color:var(--c-t3);margin-top:2px">${ld.slug||'—'}</div>` +
        `</div>` +
      `</div>` +
      `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">` +
        `<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">TELEFONE</div>` +
          `<div style="font-size:13px;font-weight:600;color:var(--c-text)">${phone}</div>` +
        `</div>` +
        `<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">CPF</div>` +
          `<div style="font-size:13px;font-weight:600;font-family:monospace;color:var(--c-text)">${cpf}</div>` +
        `</div>` +
        (email?`<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px;grid-column:1/-1">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">EMAIL</div>` +
          `<div style="font-size:13px;font-weight:600;color:var(--c-text)">${email}</div>` +
        `</div>`:'')+
        `<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">CIDADE</div>` +
          `<div style="font-size:13px;font-weight:600;color:var(--c-text)">${city}</div>` +
        `</div>` +
        `<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">PRODUTO</div>` +
          `<div style="font-size:13px;font-weight:600;color:var(--c-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${product}</div>` +
        `</div>` +
        (addr&&addr!=='—'?`<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:7px 10px;grid-column:1/-1">` +
          `<div style="font-size:10px;color:var(--c-t3);font-weight:600;letter-spacing:.5px;margin-bottom:2px">ENDEREÇO</div>` +
          `<div style="font-size:12px;font-weight:600;color:var(--c-t2)">${addr}</div>` +
        `</div>`:'')+
      `</div>` +
    `</div>`;
  }).join('');
}

function exportLeadsCSV(){
  if(!_LEADS_CACHE.length){toast('Sem leads para exportar.','wrn');return;}
  const headers=['Nome','CPF','Telefone','Email','Cidade','Estado','CEP','Endereço','Número','Bairro','Produto','Valor','Verificado','Slug','IP','Data'];
  const rows=_LEADS_CACHE.map(ld=>[
    ld.name||'',ld.cpf||'',ld.phone||'',ld.email||'',ld.city||'',ld.state||'',ld.cep||'',
    ld.street||'',ld.number||'',ld.neighborhood||'',ld.product||'',ld.amount||'',
    ld.cpf_verified?'Sim':'Não',ld.slug||'',ld.ip||'',
    ld.ts?new Date(ld.ts*1000).toLocaleString('pt-BR'):''
  ].map(v=>'"'+String(v).replace(/"/g,'""')+'"'));
  const csv=[headers.join(','),...rows.map(r=>r.join(','))].join('\n');
  const a=document.createElement('a');a.href='data:text/csv;charset=utf-8,\uFEFF'+encodeURIComponent(csv);
  a.download='leads_'+new Date().toISOString().slice(0,10)+'.csv';a.click();
  toast('CSV exportado!','ok');
}

async function fullRefresh(){await loadStats();updLink();}


// ── VAULT / FINANCIAL PANEL ───────────────────────────────────────────────
let _AI_DET = null;
const GW_META = {
  c7:         {name:'Carteira do 7',  logo:'C7',  color:'#7C3AED'},
  mercadopago:{name:'Mercado Pago',   logo:'MP',  color:'#009EE3'},
  pagseguro:  {name:'PagSeguro',      logo:'PS',  color:'#00B272'},
  stripe:     {name:'Stripe',         logo:'ST',  color:'#635BFF'},
  efipay:     {name:'Efi Pay',        logo:'EFI', color:'#1A5EFF'},
  pix_manual: {name:'Pix Manual',     logo:'PIX', color:'#32BCAD'},
  custom:     {name:'Personalizada',  logo:'API', color:'#6B7280'},
};
const GW_FIELDS = {
  c7:         [{key:'api_key',label:'API Key',pw:true,hint:'c7_live_...'},{key:'api_secret',label:'API Secret',pw:true,hint:'0449fb...'},{key:'internal_token',label:'Token Interno',pw:true,hint:'39Qrhf...'},{key:'base_url',label:'Base URL',pw:false,hint:'https://api.carteirado7.com/v2'},{key:'acquirer_code',label:'Cod. Adquirente',pw:false,hint:'Opcional'}],
  mercadopago:[{key:'access_token',label:'Access Token',pw:true,hint:'APP_USR-...'},{key:'public_key',label:'Public Key',pw:false,hint:'APP_USR-...'}],
  pagseguro:  [{key:'token',label:'Token',pw:true,hint:'UUID token'},{key:'email',label:'E-mail',pw:false,hint:'seu@email.com'}],
  stripe:     [{key:'secret_key',label:'Secret Key',pw:true,hint:'sk_live_...'},{key:'publishable_key',label:'Publishable Key',pw:false,hint:'pk_live_...'},{key:'webhook_secret',label:'Webhook Secret',pw:true,hint:'whsec_...'}],
  efipay:     [{key:'client_id',label:'Client ID',pw:false,hint:'Client_Id_...'},{key:'client_secret',label:'Client Secret',pw:true,hint:'Client_Secret_...'},{key:'pix_key',label:'Chave Pix',pw:false,hint:'CPF/e-mail/tel'},{key:'sandbox',label:'Sandbox',pw:false,hint:'true/false'}],
  pix_manual: [{key:'pix_key',label:'Chave Pix',pw:false,hint:'CPF, CNPJ, e-mail...'},{key:'pix_name',label:'Nome Recebedor',pw:false,hint:'Nome completo'},{key:'pix_city',label:'Cidade',pw:false,hint:'Sao Paulo'}],
  custom:     [{key:'raw_credentials',label:'Credenciais JSON',pw:false,hint:'{"key":"..."}'},{key:'base_url',label:'URL Base',pw:false,hint:'https://...'}],
};
cfgTab = function(n, btn) {
  ['visual','sistema','financeiro'].forEach(t=>{const e=document.getElementById('ct-'+t);if(e)e.classList.add('hidden');});
  document.querySelectorAll('#cfg-tabs .tp').forEach(b=>b.classList.remove('active'));
  const t=document.getElementById('ct-'+n);if(t)t.classList.remove('hidden');if(btn)btn.classList.add('active');
  if(n==='sistema')loadStatus();
  if(n==='financeiro'){loadVaultGateways();loadVaultAudit();}
};
function onGwSelChange(){const gw=document.getElementById('vault-gw-sel').value;renderVaultFields(gw,{});}
function renderVaultFields(gw,prefill){
  const wrap=document.getElementById('vault-fields-wrap');if(!gw||!GW_FIELDS[gw]){wrap.innerHTML='';return;}
  const meta=GW_META[gw]||{};
  wrap.innerHTML='<div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:10px;background:rgba(255,255,255,0.04);margin-bottom:14px"><div style="width:28px;height:28px;border-radius:7px;background:'+(meta.color||'#888')+';display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:900;color:#fff">'+(meta.logo||'?')+'</div><span style="font-size:13px;font-weight:700;color:#fff">'+(meta.name||gw)+'</span><span class="chip chip-p" style="margin-left:auto;font-size:10px">Configurando</span></div>'+
  GW_FIELDS[gw].map(f=>'<div class="fg"><label class="flbl">'+f.label+'</label><input type="'+(f.pw?'password':'text')+'" class="fi vault-field" data-key="'+f.key+'" placeholder="'+(f.hint||'')+'" value="'+(prefill[f.key]||'')+'" autocomplete="off" spellcheck="false"/></div>').join('');
}
async function saveVaultCreds(){
  const gw=document.getElementById('vault-gw-sel').value;if(!gw){toast('Selecione um gateway.','err');return;}
  const fields={};document.querySelectorAll('.vault-field').forEach(el=>{if(el.value.trim())fields[el.dataset.key]=el.value.trim();});
  if(!Object.keys(fields).length){toast('Preencha ao menos um campo.','err');return;}
  const btn=document.getElementById('vault-save-btn');btn.disabled=true;
  try{const r=await apiFetch('/api/admin/vault/credentials',{method:'POST',body:JSON.stringify({gateway:gw,fields})});const d=await r.json();if(d.ok){toast('Credenciais salvas com AES-256!','ok');loadVaultGateways();loadVaultAudit();}else toast(d.error||'Erro.','err');}catch{toast('Erro.','err');}
  btn.disabled=false;
}
async function loadVaultGateways(){
  const grid=document.getElementById('vault-gw-grid');const banner=document.getElementById('vault-active-banner');
  try{const r=await apiFetch('/api/admin/vault/gateways');const d=await r.json();
  if(!d.ok){grid.innerHTML='<div class="empty"><p>Vault indisponivel.</p></div>';return;}
  const gws=d.gateways||[];const active=d.active_gateway;
  if(active&&banner){banner.style.display='block';const m=GW_META[active]||{};document.getElementById('vault-active-name').textContent=m.name||active;}else if(banner)banner.style.display='none';
  if(!gws.length){grid.innerHTML='<div class="empty"><div class="empty-ico"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" width="24" height="24"><rect x="2" y="5" width="20" height="14" rx="2"/></svg></div><h3>Nenhum gateway</h3><p>Configure um acima.</p></div>';return;}
  grid.innerHTML = gws.map(gw => {
    const meta = GW_META[gw.gateway] || {};
    const isA = gw.gateway === active;
    const dt = gw.updated_at ? new Date(gw.updated_at * 1000).toLocaleDateString('pt-BR') : '';
    const borderColor = isA ? 'rgba(16,185,129,0.35)' : 'var(--c-border)';
    const activateBtn = !isA
      ? `<button class="btn btn-s btn-xs" onclick="activateGw('${gw.gateway}')"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="20 6 9 17 4 12"/></svg>Ativar</button>`
      : '';
    const deactivateBtn = isA
      ? `<button class="btn btn-d btn-xs" onclick="deactivateAll()">Desativar</button>`
      : '';
    return `<div style="background:var(--c-card2);border:1.5px solid ${borderColor};border-radius:14px;padding:14px 16px"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px"><div style="width:36px;height:36px;border-radius:10px;background:${meta.color||'#888'};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;color:#fff;flex-shrink:0">${meta.logo||'?'}</div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:800;color:#fff">${meta.name||gw.gateway}</div><div style="font-size:11px;color:rgba(255,255,255,0.4)">${gw.field_count||0} campo(s) &bull; ${dt}</div></div><span class="chip ${isA?'chip-g':'chip-o'}" style="font-size:10px;flex-shrink:0">${isA?'Ativo':'Inativo'}</span></div><div style="display:flex;gap:6px;flex-wrap:wrap">${activateBtn} <button class="btn btn-g btn-xs" onclick="editGw('${gw.gateway}')">Editar</button> <button class="btn btn-d btn-xs" onclick="deleteGw('${gw.gateway}')">Excluir</button> ${deactivateBtn}</div></div>`;
  }).join('');
  }catch(e){grid.innerHTML='<div class="empty"><p>Erro.</p></div>';}
}
async function activateGw(gw){
  const r=await apiFetch('/api/admin/vault/activate',{method:'POST',body:JSON.stringify({gateway:gw,active:true})});const d=await r.json();
  if(d.ok){toast('Gateway ativado!','ok');loadVaultGateways();}else toast(d.error||'Erro.','err');
}
async function deactivateAll(){
  await apiFetch('/api/admin/vault/activate',{method:'POST',body:JSON.stringify({gateway:'deactivate',active:false})});
  toast('Gateway desativado.','info');loadVaultGateways();
}
async function editGw(gw){
  document.getElementById('vault-gw-sel').value=gw;
  const r=await apiFetch('/api/admin/vault/credentials?gateway='+gw);const d=await r.json();
  renderVaultFields(gw,d.masked||{});
  document.getElementById('vault-add-card').scrollIntoView({behavior:'smooth'});
}
async function deleteGw(gw){
  const meta=GW_META[gw]||{};if(!confirm('Excluir '+(meta.name||gw)+'?'))return;
  const r=await apiFetch('/api/admin/vault/delete',{method:'POST',body:JSON.stringify({gateway:gw})});const d=await r.json();
  if(d.ok){toast('Gateway removido.','info');loadVaultGateways();loadVaultAudit();}else toast(d.error||'Erro.','err');
}
async function loadVaultAudit(){
  const el=document.getElementById('vault-audit-list');if(!el)return;
  try{const r=await apiFetch('/api/admin/vault/audit?limit=15');const d=await r.json();
  const items=d.audit||[];
  if(!items.length){el.innerHTML='<div class="empty"><p>Sem registros.</p></div>';return;}
  const _icoSave='<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>';
  const _icoOk='<svg fill="none" viewBox="0 0 24 24" stroke="#34D399" stroke-width="2.5" width="16" height="16"><polyline points="20 6 9 17 4 12"/></svg>';
  const _icoStop='<svg fill="none" viewBox="0 0 24 24" stroke="#F87171" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>';
  const _icoDel='<svg fill="none" viewBox="0 0 24 24" stroke="#F87171" stroke-width="2" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>';
  const _icoKey='<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>';
  const icons={SAVE_CREDENTIALS:_icoSave,ACTIVATE:_icoOk,DEACTIVATE_ALL:_icoStop,DELETE_GATEWAY:_icoDel};
  el.innerHTML=items.map(a=>{const dt=new Date(a.ts*1000);const tm=dt.getDate().toString().padStart(2,'0')+'/'+(dt.getMonth()+1).toString().padStart(2,'0')+' '+dt.getHours().toString().padStart(2,'0')+':'+dt.getMinutes().toString().padStart(2,'0');const meta=GW_META[a.gateway]||{};
  return '<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.04)"><span style="flex-shrink:0;width:24px;height:24px;border-radius:6px;background:rgba(255,255,255,0.05);display:flex;align-items:center;justify-content:center">'+(icons[a.action]||_icoKey)+'</span><div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:700;color:var(--c-text)">'+a.action.replace(/_/g,' ')+'</div><div style="font-size:11px;color:var(--c-t3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+(meta.name||a.gateway||'—')+' &bull; '+(a.ip||'—')+'</div></div><span style="font-size:11px;color:var(--c-t3);flex-shrink:0">'+tm+'</span></div>';}).join('');
  }catch{el.innerHTML='<div class="empty"><p>Erro.</p></div>';}
}
async function aiDetectCreds(){
  const text=document.getElementById('ai-detect-input').value.trim();
  if(text.length<5){toast('Cole as credenciais ou documentacao da API.','err');return;}
  const btn=document.getElementById('ai-detect-btn');btn.disabled=true;btn.textContent='Analisando...';
  try{
    const r=await apiFetch('/api/admin/vault/detect',{method:'POST',body:JSON.stringify({text})});
    const d=await r.json();
    if(!d.ok){toast(d.error||'Erro.','err');return;}
    _AI_DET=d.detection;
    const det=d.detection;
    const meta=GW_META[det.gateway]||{};
    const res=document.getElementById('ai-result');
    res.style.display='block';
    // Logo + Name
    const logo=document.getElementById('ai-gw-logo');
    logo.textContent=meta.logo||'?';logo.style.background=meta.color||'#888';
    document.getElementById('ai-gw-name').textContent=meta.name||det.gateway;
    // Confidence bar
    const pct=Math.round((det.confidence||0)*100);
    document.getElementById('ai-gw-conf').textContent=pct+'%';
    document.getElementById('ai-conf-fill').style.width=pct+'%';
    document.getElementById('ai-conf-fill').style.background=pct>80?'linear-gradient(90deg,#10B981,#34D399)':pct>50?'linear-gradient(90deg,#F59E0B,#FBBF24)':'linear-gradient(90deg,#EF4444,#F87171)';
    // Engine chip
    const ec=document.getElementById('ai-engine-chip');
    ec.textContent=d.engine==='full'?'IA Avancada':'IA Basica';
    // Runner-up
    const ru=det.runner_up||[];const ruEl=document.getElementById('ai-runnerup');
    if(ru.length){document.getElementById('ai-runnerup-text').textContent=ru.map(x=>(GW_META[x.gateway]||{}).name||x.gateway).join(', ');ruEl.style.display='block';}else ruEl.style.display='none';
    // Issues / Warnings
    const issues=det.issues||det.warnings||[];const iEl=document.getElementById('ai-issues');const iList=document.getElementById('ai-issues-list');
    const issArr=Array.isArray(issues)?issues:Object.values(issues);
    if(issArr.length){iList.innerHTML=issArr.map(i=>'<div>'+i+'</div>').join('');iEl.style.display='block';}else iEl.style.display='none';
    // Extracted fields preview
    const flds=det.fields||{};const vld=det.validated_fields||{};const fpEl=document.getElementById('ai-fields-preview');const fList=document.getElementById('ai-fields-list');
    const fEntries=Object.entries(flds).filter(([k,v])=>v);
    if(fEntries.length){
      fList.innerHTML=fEntries.map(([k,v])=>{const ok=vld[k];const badge=ok===true?'<span style="color:#10B981;font-size:10px">VALIDO</span>':ok===false?'<span style="color:#EF4444;font-size:10px">INVALIDO</span>':'';
      return '<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)"><span style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.55);min-width:90px;flex-shrink:0">'+k+'</span><span style="font-size:11px;font-family:monospace;color:rgba(255,255,255,0.8);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+v.substring(0,40)+(v.length>40?'...':'')+'</span>'+badge+'</div>';}).join('');
      fpEl.style.display='block';
    }else fpEl.style.display='none';
    // Instructions
    const instr=det.instructions||[];const instrEl=document.getElementById('ai-instructions');const instrList=document.getElementById('ai-instructions-list');
    if(instr.length){instrList.innerHTML=instr.map(i=>'<li>'+i+'</li>').join('');instrEl.style.display='block';}else instrEl.style.display='none';
  }catch(e){toast('Erro na analise: '+e.message,'err');}
  btn.disabled=false;
  btn.innerHTML='<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Detectar Gateway';
}
function useAiDetection(){
  if(!_AI_DET)return;const gw=_AI_DET.gateway;
  document.getElementById('vault-gw-sel').value=gw;
  // Fill with extracted fields — api_intel returns 'fields', basic vault returns 'detected_fields'
  const prefill=_AI_DET.fields||_AI_DET.detected_fields||{};
  renderVaultFields(gw,prefill);
  document.getElementById('vault-add-card').scrollIntoView({behavior:'smooth'});
  const cnt=Object.keys(prefill).filter(k=>prefill[k]).length;
  toast(cnt?cnt+' campo(s) preenchido(s) automaticamente!':'Gateway selecionado. Preencha os campos.','ok');
}
document.addEventListener('contextmenu',e=>{if(document.getElementById('auth-gate').style.display!=='flex')e.preventDefault();});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){closeLivePreview();}
  if(e.key==='F12'||(e.ctrlKey&&e.shiftKey&&['I','i','J','j','C','c'].includes(e.key))||(e.ctrlKey&&['u','U','s','S'].includes(e.key))){e.preventDefault();toast('Painel protegido.','inf');}
});

// ── LIVE PREVIEW SYSTEM ─────────────────────────────────────────────────────
let _pvUrl = '';
let _pvProducts = [];
let _pvClock = null;

function _startPvClock(){
  if(_pvClock) clearInterval(_pvClock);
  const el = document.getElementById('pv-time-bar');
  function tick(){const n=new Date();el.textContent=n.getHours().toString().padStart(2,'0')+':'+n.getMinutes().toString().padStart(2,'0');}
  tick();
  _pvClock = setInterval(tick, 10000);
}

function _stopPvClock(){if(_pvClock){clearInterval(_pvClock);_pvClock=null;}}

async function openLivePreview(productCode){
  const overlay = document.getElementById('preview-overlay');
  if(!overlay) return;
  overlay.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  _startPvClock();
  await refreshPreview(productCode);
}

function closeLivePreview(){
  const overlay = document.getElementById('preview-overlay');
  if(!overlay || overlay.style.display==='none') return;
  overlay.style.display = 'none';
  document.body.style.overflow = '';
  _stopPvClock();
  const iframe = document.getElementById('pv-iframe');
  if(iframe) iframe.src = 'about:blank';
}

async function refreshPreview(productCode){
  const loadingEl = document.getElementById('pv-loading-overlay');
  if(loadingEl) loadingEl.style.display='flex';
  try {
    const code = productCode || document.getElementById('pv-product-sel')?.value || '';
    const qs = code ? '?code='+encodeURIComponent(code) : '';
    const r = await apiFetch('/api/admin/preview'+qs);
    if(!r) { toast('Erro: sem resposta do servidor','err'); return; }
    const d = await r.json();
    if(!d.ok){ toast('Erro no preview: '+(d.error||'?'),'err'); return; }

    _pvUrl = d.public_url || '';
    _pvProducts = d.products || [];

    // Update URL displays
    const urlBadge = document.getElementById('pv-url-badge');
    const urlBar = document.getElementById('pv-url-bar');
    const openBtn = document.getElementById('pv-open-btn');
    if(urlBadge) urlBadge.textContent = _pvUrl || '—';
    if(urlBar){
      try {const u=new URL(_pvUrl);urlBar.textContent=u.hostname+u.pathname;}
      catch{urlBar.textContent=_pvUrl||'—';}
    }
    if(openBtn) openBtn.href = _pvUrl || '#';

    // Populate product selector
    const sel = document.getElementById('pv-product-sel');
    if(sel && _pvProducts.length){
      const currentVal = sel.value;
      sel.innerHTML = '<option value="">Produto ativo</option>' +
        _pvProducts.map(p=>'<option value="'+(p.product_code||p.code||'')+'"'+(p.product_code===code?' selected':'')+'>'+((p.title||'Produto').substring(0,22))+'</option>').join('');
      if(currentVal && !code) sel.value = currentVal;
    }

    // Load page in iframe
    if(_pvUrl && _pvUrl !== window.location.origin){
      const iframe = document.getElementById('pv-iframe');
      if(iframe){
        iframe.src = _pvUrl;
      }
    } else {
      // No valid URL — show message
      if(loadingEl){
        loadingEl.innerHTML = '<div style="text-align:center;padding:20px"><div style="font-size:28px;margin-bottom:8px">🔗</div><div style="font-size:13px;font-weight:700;color:var(--c-text);margin-bottom:6px">Configure seu link primeiro</div><div style="font-size:12px;color:var(--c-t3)">Adicione um produto no catálogo para ver o preview.</div></div>';
        loadingEl.style.display='flex';
      }
    }
  } catch(err){
    console.error('[Preview]', err);
    toast('Erro ao carregar preview: '+err.message,'err');
    if(loadingEl) loadingEl.style.display='none';
  }
}

function previewSelectProduct(code){
  refreshPreview(code);
}

function onPreviewIframeLoad(iframe){
  const loadingEl = document.getElementById('pv-loading-overlay');
  if(iframe.src && iframe.src !== 'about:blank'){
    // Small delay for page to render
    setTimeout(()=>{if(loadingEl)loadingEl.style.display='none';}, 300);
  }
}

function copyPreviewUrl(){
  if(!_pvUrl){toast('Nenhum link para copiar','wrn');return;}
  navigator.clipboard.writeText(_pvUrl).then(()=>toast('Link copiado!','ok')).catch(()=>{
    const ta=document.createElement('textarea');ta.value=_pvUrl;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);toast('Link copiado!','ok');
  });
}

// Hook: refresh preview automatically after saving a product
const _origSaveProd = typeof saveProd === 'function' ? saveProd : null;
// We patch the global after prod save to auto-refresh the preview
function _onProdSaved(){
  const overlay = document.getElementById('preview-overlay');
  if(overlay && overlay.style.display !== 'none'){
    setTimeout(()=>refreshPreview(), 800);
  }
}