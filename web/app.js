// Pantalla única del comparador: buscador, pedido del cliente, precios anotados a mano y estado de los datos.
// La pantalla de precios (botones, banda de lo más barato y tarjetas por proveedor) está en tarjetas.js.
const $ = id => document.getElementById(id);
let providers = [], visible = [];
const euro = value => new Intl.NumberFormat('es-ES', {style:'currency',currency:'EUR'}).format(Number(value));
const esc = text => String(text ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
async function api(path, body){const res=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await res.json();if(!res.ok){const detail=typeof data.detail==='string'?data.detail: Array.isArray(data.detail)?data.detail.map(x=>`${x.loc.at(-1)}: ${x.msg}`).join(' · '):'No se pudo completar la operación';throw Error(detail);}return data;}
const IVA=1.21;
const withIva=(amount,tax)=>tax==='net'?Number(amount)*IVA:Number(amount);
const isCardText=t=>{const n=t.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();return /tarjeta/.test(n)&&/visita/.test(n);};
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3500);}

// ---------- Buscador ----------
// Lo escrito decide la pantalla: nada o «tarjetas de visita» = la tarjeta estándar; otro producto = ese producto (tarjetas.js).
function search(){
  const text=$('cat-q').value.trim();
  try{const share=new URLSearchParams();if(text)share.set('q',text);history.replaceState(null,'',share.toString()?'?'+share:location.pathname);}catch{}
  cardsTool.onQuery(text);
}
function initFinder(){
  $('cat-go').addEventListener('click',search);
  $('cat-q').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();search();}});
  let typing;$('cat-q').addEventListener('input',()=>{clearTimeout(typing);typing=setTimeout(search,300);});
  const fromUrl=new URLSearchParams(location.search);if(fromUrl.get('q'))$('cat-q').value=fromUrl.get('q').slice(0,100);
  api('/api/suggestions').then(d=>{
    $('cat-suggest').innerHTML=d.terms.map(t=>`<option value="${esc(t.term)}"></option>`).join('');
    $('cat-chips').innerHTML='<button type="button" class="chip-main" data-term="tarjetas de visita">▭ Tarjetas de visita · pantalla guiada</button>'+d.terms.filter(t=>!isCardText(t.term)).slice(0,10).map(t=>`<button type="button" data-term="${esc(t.term)}">${esc(t.term)} <span class="auto-note">${t.count}</span></button>`).join('');
    $('cat-chips').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{$('cat-q').value=b.dataset.term;search();}));
  }).catch(()=>{});
  search();
}

// ---------- Precios anotados a mano ----------
let manualEditId=null,manualRows=[];
// "100 = 16,63" per line -> [{quantity, price}]; 10.000 is ten thousand
function parseMany(text){return text.split(/\n/).map(l=>l.trim()).filter(Boolean).map(line=>{const m=line.match(/^([\d.]+)\s*(?:=|:|;|\t|\s)\s*([\d.,]+)\s*€?$/);if(!m)throw Error(`No entiendo la línea «${line}». Escríbela así: 100 = 16,63`);const price=m[2].includes(',')?m[2].replace(/[.]/g,'').replace(',','.'):m[2];return {quantity:Number(m[1].replace(/[.](?=\d{3}\b)/g,'')),price};});}
function openManual(item,fill){manualEditId=null;$('manual-heading').textContent='Anotar el precio que ves en la web';$('manual-save').textContent='Guardar precio';$('manual-form').reset();
 $('m-provider').innerHTML=providers.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
 const provider=item?.provider||(visible[0]||providers[0]).id;$('m-provider').value=provider;
 $('m-url').value=item?.url||providers.find(p=>p.id===provider).url;$('m-title').value=item?.title?String(item.title).split(' · ')[0].slice(0,120):'Tarjetas de visita';
 const f=fill||{format:'85 x 55 mm',grams:'',paper_type:'',surface:'',sides:'1',finishing:'Sin',quantity:100};
 $('m-format').value=f.format||'85 x 55 mm';$('m-grams').value=f.grams||'';$('m-paper_type').value=f.paper_type||'';$('m-surface').value=f.surface||'';
 $('m-sides').value=f.sides||'1';$('m-finishing').value=f.finishing||'Sin';$('m-quantity').value=f.quantity||100;$('manual-error').textContent='';$('m-quantity').required=$('m-price').required=true;
 $('manual-dialog').showModal();}
function openManualEdit(r){if(!r)return;openManual();manualEditId=r.id;$('manual-heading').textContent='Editar el precio anotado';$('manual-save').textContent='Guardar cambios';
 $('m-provider').value=r.provider;$('m-url').value=r.url;$('m-title').value=r.title;$('m-format').value=r.format;$('m-grams').value=r.grams||'';$('m-paper_type').value=r.paper_type;$('m-surface').value=r.surface;
 $('m-sides').value=String(r.sides);$('m-finishing').value=r.finishing;$('m-quantity').value=r.quantity;$('m-price').value=String(r.price).replace('.',',');$('m-tax').value=r.tax;$('m-shipping').value=r.shipping;
 $('m-days').value=r.delivery_days||'';$('m-note').value=r.note||'';}
async function loadManual(){try{const d=await api('/api/manual-prices'),by=Object.fromEntries(providers.map(p=>[p.id,p.name]));$('manual-count').textContent=d.items.length;manualRows=d.items;
 $('manual-body').innerHTML='<p><button type="button" class="primary" id="manual-add">＋ Anotar un precio</button></p>'+(d.items.length?`<div class="comparison-box"><table><thead><tr><th>Proveedor</th><th>Ficha</th><th>Características</th><th>Cantidad</th><th>Precio</th><th>Anotado</th><th></th></tr></thead><tbody>${d.items.map(r=>`<tr><td>${esc(by[r.provider]||r.provider)}</td><td><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)} ↗</a></td><td>${esc([r.format,r.grams?r.grams+' g/m²':'',r.paper_type,r.surface,r.sides+(r.sides===1?' cara':' caras'),r.finishing].filter(Boolean).join(' · '))}</td><td>${r.quantity}</td><td>${euro(r.price)} ${r.tax==='gross'?'con IVA':'sin IVA'}${r.shipping==='included'?' · envío incluido':r.shipping==='excluded'?' · envío aparte':''}</td><td>${esc(r.created_at.slice(0,10))}${r.note?'<div class="auto-note">'+esc(r.note)+'</div>':''}</td><td><button type="button" class="outline manual-edit" data-id="${r.id}">Editar</button> <button type="button" class="outline manual-del" data-id="${r.id}">Borrar</button></td></tr>`).join('')}</tbody></table></div>`:'<p class="auto-note">Todavía no has anotado ningún precio. En cualquier tarjeta de proveedor pulsa «Anotar precio» y escribe el que ves en su web.</p>');}catch{$('manual-body').textContent='No se pudieron cargar los precios anotados.';}}
function initManual(){loadManual();
 $('manual-body').addEventListener('click',e=>{if(e.target.closest('#manual-add'))openManual(null,window.manualFillFor?manualFillFor():undefined);});
 $('manual-body').addEventListener('click',e=>{const b=e.target.closest('.manual-edit');if(b)openManualEdit(manualRows.find(r=>r.id===Number(b.dataset.id)));});
 $('manual-body').addEventListener('click',async e=>{const b=e.target.closest('.manual-del');if(!b||!confirm('¿Borrar este precio anotado?'))return;try{await api('/api/manual-prices/delete',{id:Number(b.dataset.id)});toast('Precio borrado');await loadManual();cardsTool.search();}catch(err){toast(err.message);}});
 $('close-manual').addEventListener('click',()=>$('manual-dialog').close());
 $('m-many').addEventListener('input',()=>{$('m-quantity').required=$('m-price').required=!$('m-many').value.trim();});  // with a list, the single quantity and price are not needed
 $('manual-form').addEventListener('submit',async e=>{e.preventDefault();$('manual-save').disabled=true;$('manual-error').textContent='';
  try{const v=id=>$(id).value.trim(),many=!manualEditId&&v('m-many')?parseMany(v('m-many')):null;const common={provider:v('m-provider'),url:v('m-url'),title:v('m-title'),format:v('m-format'),grams:v('m-grams')?Number(v('m-grams')):null,paper_type:v('m-paper_type'),surface:v('m-surface'),sides:Number(v('m-sides')),finishing:v('m-finishing')||'Sin',tax:v('m-tax'),shipping:v('m-shipping'),delivery_days:v('m-days')?Number(v('m-days')):null,note:v('m-note')};
   if(many)await api('/api/manual-prices/bulk',{...common,items:many});else await api(manualEditId?'/api/manual-prices/update':'/api/manual-prices',{...(manualEditId?{id:manualEditId}:{}),...common,quantity:Number(v('m-quantity')),price:v('m-price').replace(',','.')});
   $('manual-dialog').close();toast(manualEditId?'Cambios guardados':many?`${many.length} precios anotados`:'Precio anotado');if(!visible.some(p=>p.id===v('m-provider'))){location.reload();return;}await loadManual();cardsTool.search();}
  catch(err){$('manual-error').textContent=err.message;}finally{$('manual-save').disabled=false;}});}

// ---------- Pedido de un cliente ----------
let customerItems=[];
async function applyRequest(i){const item=customerItems[i];
 document.querySelectorAll('#customer-items [data-item]').forEach(b=>b.classList.toggle('active',Number(b.dataset.item)===i));
 if(isCardText(item.query)){$('cat-q').value='';await cardsTool.apply(item);$('tool-summary').textContent='He entendido: '+item.understood+'. Puedes cambiar lo que no sea correcto con los botones.';$('tool-steps').scrollIntoView({block:'start'});return;}
 $('cat-q').value=item.query;cardsTool.preset={quantity:item.quantity,days:item.max_days};search();$('cards-tool').scrollIntoView({block:'start'});}
async function readCustomer(){const text=$('customer-text').value.trim(),box=$('customer-items');if(text.length<3){box.textContent='Pega primero el texto del cliente.';return;}
 box.textContent='Leyendo…';try{const d=await api('/api/parse-request',{text});customerItems=d.items;
  if(!customerItems.length){box.innerHTML='<p class="auto-note">No he reconocido ningún producto en ese texto. Escribe el producto en el buscador.</p>';return;}
  box.innerHTML=`<p class="auto-note">${customerItems.length>1?'He encontrado '+customerItems.length+' productos. Pulsa uno para ver sus precios:':'Esto es lo que he entendido (puedes cambiar lo que no sea correcto con los botones):'}</p>`+customerItems.map((it,i)=>`<button type="button" class="customer-item" data-item="${i}"><strong>${esc(it.understood)}</strong>${it.quantity?'':' <span class="auto-note">· no he visto la cantidad, uso la que hay puesta</span>'}</button>`).join('');
  box.querySelectorAll('[data-item]').forEach(b=>b.addEventListener('click',()=>applyRequest(Number(b.dataset.item))));await applyRequest(0);}catch(e){box.textContent='No se pudo leer el texto: '+e.message;}}

// ---------- Estado de los datos ----------
let statusLoaded=false;
async function loadStatus(){const box=$('data-status-body');try{const d=await api('/api/data-status');const ago=iso=>{if(!iso)return '—';const n=Math.floor((Date.now()-new Date(iso).getTime())/864e5);return n<=0?'hoy':`hace ${n} d${n>30?' ⚠':''}`;};
 box.innerHTML=`<div class="comparison-box"><table><thead><tr><th>Proveedor</th><th>Con precio</th><th>Sin leer el precio</th><th>Por descargar</th><th>Última lectura</th></tr></thead><tbody>${d.providers.map(r=>`<tr><td>${esc(r.name)}</td><td>${r.ok}</td><td>${r.failed}${Object.keys(r.reasons).length?`<div class="auto-note">${Object.entries(r.reasons).map(([k,v])=>`${v}: ${esc(k)}`).join(' · ')}</div>`:''}</td><td>${r.pending}</td><td>${ago(r.last)}</td></tr>`).join('')}</tbody></table></div><p class="auto-note">«Por descargar»: páginas de su catálogo que aún no se han recogido. «Sin leer el precio»: salen en el catálogo como enlace, salvo las que ya no existen.</p>`;}catch(e){box.textContent='No se pudo leer el estado: '+e.message;}}

async function init(){
  try{
    providers=(await api('/api/providers')).providers;
    visible=providers.filter(p=>p.products>0);if(!visible.length)visible=providers;
    if(window.loadSettings)await loadSettings();  // what the buttons start on, before the first search
    initFinder();initManual();if(window.initSettings)initSettings();
    if(window.initCardsTool)initCardsTool();
  }catch(e){$('tool-results').innerHTML=`<p class="auto-note warn">No se ha podido cargar el comparador: ${esc(e.message)}. Recarga la página con Ctrl+F5.</p>`;}
}
$('customer-go').addEventListener('click',readCustomer);
$('data-status-details').addEventListener('toggle',()=>{if($('data-status-details').open&&!statusLoaded){statusLoaded=true;loadStatus();}});
window.addEventListener('hashchange',()=>{if(location.hash==='#data-status')$('data-status-details').open=true;});
// tarjetas.js is loaded after this file: start when every script has run (a slow answer of the server must not win the race)
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
