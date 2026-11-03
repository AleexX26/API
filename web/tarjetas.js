// The guided screen. The usual choices are buttons, the rest are dropdowns. Business cards start on the standard card
// (85 x 55 mm, 1 cara, 350 g estucado, sin acabado); any other product gets the options its collected pages state, all on
// "Cualquiera". Uses the helpers of app.js (loaded before this file).
const STANDARD = {quantity: 100, format: '85 x 55 mm', pages: '1 cara', grams: '350 g/m²', paper_type: 'Estucado / cuché', surface: '', finishing: 'Sin', inks: 'cmyk', days: 0, type: 'Estándar', orientation: '', processing: 'Cortar'};
const cardsTool = {mode: 'cards', state: {...STANDARD}, items: [], form: null, ticket: 0, preset: null, apply: null, search: null, onQuery: null};
const generic = {query: '', quantity: 100, days: 0, filters: {}, form: {groups: []}, ticket: 0};
const GENERIC_QUANTITIES = [1, 10, 50, 100, 250, 500, 1000, 5000];
const QUANTITIES = [100, 250, 500, 1000, 2500];
const INK_CHOICES = [['cmyk', 'Color (CMYK)'], ['special', 'Pantone, oro o plata'], ['', 'Cualquiera']];
const DAY_CHOICES = [[0, 'Cualquiera'], [3, 'Hasta 3 días'], [7, 'Hasta 7 días'], [10, 'Hasta 10 días']];
const FIELDS = [
  {key: 'format', label: 'Tamaño', popular: ['85 x 55 mm', '90 x 50 mm', '55 x 55 mm'], standard: STANDARD.format, any: true},
  {key: 'pages', label: 'Caras', popular: ['1 cara', '2 caras'], standard: STANDARD.pages},
  {key: 'grams', label: 'Gramaje', popular: ['300 g/m²', '350 g/m²', '400 g/m²'], standard: STANDARD.grams, any: true},
  {key: 'paper_type', label: 'Papel', popular: ['Estucado / cuché', 'Offset', 'Reciclado'], standard: STANDARD.paper_type, any: true},
  {key: 'surface', label: 'Mate o brillo', popular: ['Mate', 'Brillo'], any: true, fixed: true},
  {key: 'finishing', label: 'Acabado', popular: ['Sin', 'Plastificado', 'Barniz'], standard: STANDARD.finishing, any: true, prefix: true},
];
const MORE = [['type', 'Tipo de tarjeta', 'types'], ['orientation', 'Orientación', 'orientation'], ['processing', 'Esquinas y corte', 'processing']];

function shown(key, value) {
  if (value === '' || value == null) return 'Cualquiera';
  if (key === 'format') return value.replace(/ x /g, ' × ');
  if (key === 'grams') return value.replace(/ g[/]m²$/, ' g');
  if (key === 'finishing') return value === 'Sin' ? 'Sin acabado' : value.replace(/ [(].*$/, '');
  return value;
}
function optionsOf(field) {
  const form = cardsTool.form || {};
  return form[field.key] || [];
}
function pill(key, value, label, on, tag) {
  return `<button type="button" class="pill${on ? ' on' : ''}" data-key="${key}" data-value="${esc(value)}" aria-pressed="${on}">${esc(label)}${tag ? ` <small>${tag}</small>` : ''}</button>`;
}
function stepHtml(field) {
  const all = field.all || optionsOf(field), current = field.generic ? (generic.filters[field.name] || '') : cardsTool.state[field.key];
  const popular = field.popular.map(p => field.prefix ? all.find(o => o.startsWith(p)) : all.find(o => o === p)).filter(Boolean);
  const rest = all.filter(o => !popular.includes(o));
  let html = '';
  if (field.any) html += pill(field.key, '', 'Cualquiera', current === '');
  html += popular.map(v => pill(field.key, v, shown(field.key, v), current === v, v === field.standard ? 'estándar' : '')).join('');
  if (rest.length) {
    const onRest = rest.includes(current);
    html += `<select class="pill-select${onRest ? ' on' : ''}" data-key="${field.key}" aria-label="${esc(field.label)}: otras opciones"><option value="">Otro…</option>${rest.map(o => `<option value="${esc(o)}"${o === current ? ' selected' : ''}>${esc(shown(field.key, o))}</option>`).join('')}</select>`;
  }
  return `<div class="step"><div class="step-label">${field.label}</div><div class="pills" role="group" aria-label="${field.label}">${html}</div></div>`;
}
function quantityHtml() {
  const any = cardsTool.mode === 'generic', list = any ? GENERIC_QUANTITIES : QUANTITIES, q = any ? generic.quantity : cardsTool.state.quantity, custom = !list.includes(q);
  return `<div class="step"><div class="step-label">¿Cuántas?</div><div class="pills" role="group" aria-label="Cantidad">${list.map(n => pill('quantity', n, n.toLocaleString('es-ES'), q === n, !any && n === STANDARD.quantity ? 'estándar' : '')).join('')}<input class="pill-input${custom ? ' on' : ''}" type="number" min="1" max="1000000" data-key="quantity" aria-label="Otra cantidad" placeholder="Otra cantidad" value="${custom ? q : ''}"></div></div>`;
}
function inksHtml() {
  const current = cardsTool.state.inks;
  return `<div class="step"><div class="step-label">Colores</div><div class="pills" role="group" aria-label="Colores">${INK_CHOICES.map(([value, label]) => pill('inks', value, label, current === value, value === STANDARD.inks ? 'estándar' : '')).join('')}</div></div>`;
}
function daysHtml() {
  const d = cardsTool.mode === 'generic' ? generic.days : cardsTool.state.days;
  return `<div class="step"><div class="step-label">Entrega</div><div class="pills" role="group" aria-label="Entrega">${DAY_CHOICES.map(([n, label]) => pill('days', n, label, d === n)).join('')}</div></div>`;
}
function moreHtml() {
  const form = cardsTool.form || {}, state = cardsTool.state;
  return `<details class="tool-more"><summary>Más opciones</summary><div class="more-grid">${MORE.map(([key, label, source]) => `<label>${label}<select data-key="${key}"><option value="">Cualquiera</option>${(form[source] || []).map(o => `<option${o === state[key] ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select></label>`).join('')}</div></details>`;
}
function genericFields() {
  return (generic.form.groups || []).slice(0, 6).map(g => ({generic: true, key: 'g:' + g.name, name: g.name, label: g.name, popular: g.options.slice(0, 4), all: g.options, any: true}));
}
function renderSteps() {
  const box = $('tool-steps'), open = box.querySelector('.tool-more')?.open;
  if (cardsTool.mode === 'generic') {
    const fields = genericFields();
    box.innerHTML = quantityHtml() + fields.map(stepHtml).join('') + daysHtml()
      + `${fields.length ? '' : '<p class="auto-note">Todavía no hay características recogidas para este producto: se muestran todos sus precios.</p>'}<div class="step-actions"><button type="button" class="outline" id="tool-reset">↺ Quitar las opciones</button></div>`;
    return;
  }
  box.innerHTML = quantityHtml() + FIELDS.slice(0, 2).map(stepHtml).join('') + inksHtml() + FIELDS.slice(2).map(stepHtml).join('') + daysHtml() + moreHtml() + '<div class="step-actions"><button type="button" class="outline" id="tool-reset">↺ Volver a lo estándar</button></div>';
  if (open) box.querySelector('.tool-more').open = true;
}
function describeChoice() {
  if (cardsTool.mode === 'generic') {
    return [generic.query, `${generic.quantity.toLocaleString('es-ES')} uds`, ...Object.values(generic.filters), generic.days ? `entrega en ${generic.days} días como máximo` : ''].filter(Boolean).join(' · ');
  }
  const s = cardsTool.state, paper = [s.grams ? shown('grams', s.grams) : '', s.paper_type].filter(Boolean).join(' ') || 'cualquier papel';
  return [`${s.quantity.toLocaleString('es-ES')} tarjetas`, shown('format', s.format).replace('Cualquiera', 'cualquier tamaño'), s.pages, s.inks === 'cmyk' ? 'a todo color' : s.inks === 'special' ? 'colores especiales' : '', paper, s.surface, s.finishing ? shown('finishing', s.finishing).toLowerCase() : '', s.days ? `entrega en ${s.days} días como máximo` : ''].filter(Boolean).join(' · ');
}
function toolBrief() {
  const s = cardsTool.state, extras = {};
  for (const key of ['pages', 'type', 'surface', 'orientation', 'processing']) if (s[key]) extras[key] = s[key];
  const grams = s.grams.replace(/ g[/]m²$/, '');
  const material = grams && s.paper_type ? `${grams} g/m² ${s.paper_type}` : grams ? `${grams} g/m²` : s.paper_type || 'Sin especificar';
  const printing = s.inks === 'cmyk' ? (s.pages === '1 cara' ? '4+0 tintas (CMYK)' : s.pages === '2 caras' ? '4+4 tintas (CMYK)' : 'Sin especificar') : s.inks === 'special' ? 'Pantone' : 'Sin especificar';
  return {format: s.format || 'Sin especificar', material, printing, finishing: s.finishing || 'Sin especificar', extras};
}
function whatIs(item) {
  return item.spec.filter(x => ['Formato', 'Papel', 'Impresión', 'Acabados', 'Realización'].includes(x.group) || /formato|papel|impres|acabado|realiz/i.test(x.group)).slice(0, 5).map(x => x.label).join(' · ') || item.spec.slice(0, 3).map(x => x.label).join(' · ');
}
function offerTotal(item) {return item.at ? withIva(Number(item.at.total), item.tax_status) : null;}  // with VAT: what the offers are ranked by
const netOf = (value, tax) => tax === 'gross' ? Number(value) / IVA : Number(value);  // without VAT: what is shown first
function netTotal(item) {return netOf(item.at.total, item.tax_status);}
function offerRank(item) {
  const total = offerTotal(item);
  return [item.near ? 1 : 0, total === null ? 1 : 0, total ?? 0];
}
function byRank(a, b) {
  const x = offerRank(a), y = offerRank(b);
  return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
}
function chips(item, qty) {
  const tier = (item.prices || []).find(x => Number(x[0]) === qty) || (item.prices || [])[0], out = [];
  out.push(item.shipping === 'included' ? ['ok', 'Envío incluido'] : item.shipping === 'excluded' ? ['warn', 'Envío aparte'] : ['warn', 'Envío sin confirmar']);
  if (tier && tier[2] != null) out.push(['', `Entrega ~${tier[2]} días`]);
  if (item.tax_status === 'unknown') out.push(['warn', 'IVA sin confirmar']);
  if (item.at?.estimated) out.push(['warn', item.at.between ? `Estimado entre ${item.at.between[0]} y ${item.at.between[1]} uds` : 'Precio estimado']);
  const age = Math.floor((Date.now() - new Date(item.observed_at).getTime()) / 864e5);
  if (age > 30) out.push(['warn', `Dato de hace ${age} días`]);
  if (item.manual) out.push(['', '✎ Anotado a mano']);
  return out.map(([kind, text]) => `<span class="chip ${kind}">${esc(text)}</span>`).join('');
}
function priceBlock(item, qty) {
  const total = offerTotal(item);
  if (total === null) return `<div class="big muted">Sin precio a ${qty.toLocaleString('es-ES')} uds</div><div class="per">desde ${euro(netOf(item.from_price, item.tax_status))}${item.tax_status === 'unknown' ? '' : ' sin IVA'} a ${item.from_quantity} uds</div>`;
  const approx = item.at.estimated ? '≈ ' : '';
  if (item.tax_status === 'unknown') return `<div class="big">${approx}${euro(total)}</div><div class="per">IVA sin confirmar · ${euro(total / qty)}/ud</div>`;
  const net = netTotal(item);
  return `<div class="big">${approx}${euro(net)} <span class="tax">sin IVA</span></div><div class="with-iva">${euro(total)} con IVA (21 %)</div><div class="per">${euro(net / qty)}/ud sin IVA</div>`;
}
function otherRow(item, qty) {
  const total = offerTotal(item);
  const price = total === null ? 'sin precio' : item.tax_status === 'unknown' ? euro(total) : `${euro(netTotal(item))} sin IVA<div class="auto-note">${euro(total)} con IVA</div>`;
  return `<tr><td><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)} ↗</a>${item.near ? `<div class="auto-note warn">${esc(item.near)}</div>` : ''}</td><td>${price}</td><td>${esc(whatIs(item))}</td></tr>`;
}
function offerCard(group, best, qty, badges) {
  const p = group.provider, index = cardsTool.items.indexOf(best), others = group.items.filter(i => i !== best);
  const classes = ['offer', badges.includes('best') ? 'best' : '', p.own ? 'own' : '', best.near ? 'near' : ''].filter(Boolean).join(' ');
  return `<article class="${classes}"><div class="offer-head"><span class="monogram">${esc(p.initials)}</span><div><strong>${esc(p.name)}</strong>${p.own ? ' <span class="tag own">Nuestra web</span>' : ''}${badges.includes('best') ? ' <span class="tag best">Más barato</span>' : ''}</div></div>
 <div class="offer-price">${priceBlock(best, qty)}</div>
 <div class="offer-meta">${chips(best, qty)}</div>
 <p class="offer-what">${esc(whatIs(best))}</p>
 ${best.near ? `<p class="offer-near">Es el precio de la configuración por defecto de la ficha: ${esc(best.near)}. En la web quizá se pueda pedir lo que quieres con otro precio.</p>` : ''}
 <div class="offer-actions"><a class="go-button" href="${esc(best.url)}" target="_blank" rel="noopener noreferrer">Ver ficha ↗</a>${best.near ? `<button type="button" class="outline tool-manual" data-index="${index}">✎ Anotar el precio real</button>` : ''}${best.manual ? '<button type="button" class="outline tool-edit-manual">✎ Editar el precio anotado</button>' : ''}</div>
 ${others.length || group.links?.length ? `<details class="auto-more-products"><summary>Ver más de ${esc(p.name)} (${others.length + (group.links?.length || 0)})</summary>${others.length ? `<div class="comparison-box"><table><thead><tr><th>Ficha</th><th>Precio</th><th>Qué es</th></tr></thead><tbody>${others.map(i => otherRow(i, qty)).join('')}</tbody></table></div>` : ''}${group.links?.length ? `<div class="auto-note">Páginas sin precio recogido (solo enlace):</div><ul class="result-links">${group.links.map(l => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.title)} ↗</a></li>`).join('')}</ul>` : ''}</details>` : ''}</article>`;
}
function bestBanner(groups, qty) {
  const priced = groups.map(g => ({g, item: g.best})).filter(x => offerTotal(x.item) !== null && x.item.tax_status !== 'unknown');
  const exact = priced.filter(x => !x.item.near), pool = exact.length ? exact : priced;
  if (!pool.length) return '';
  const cheapest = pool.reduce((m, x) => offerTotal(x.item) < offerTotal(m.item) ? x : m);
  let html = `<p><strong>Lo más barato para este pedido:</strong> ${esc(cheapest.g.provider.name)} · ${euro(netTotal(cheapest.item))} sin IVA (${euro(offerTotal(cheapest.item))} con IVA, ${euro(netTotal(cheapest.item) / qty)}/ud sin IVA)${exact.length ? '' : ' · ninguna ficha coincide exactamente: precios de configuraciones parecidas'}</p>`;
  const own = pool.find(x => x.g.provider.own), rivals = pool.filter(x => !x.g.provider.own);
  if (own && rivals.length) {
    const rival = rivals.reduce((m, x) => offerTotal(x.item) < offerTotal(m.item) ? x : m), diff = (offerTotal(own.item) / offerTotal(rival.item) - 1) * 100;
    html += `<p>Nuestra web: ${euro(netTotal(own.item))} sin IVA · la competencia más barata es ${esc(rival.g.provider.name)} con ${euro(netTotal(rival.item))} sin IVA: ${Math.abs(diff) < 0.5 ? 'estamos igual' : diff < 0 ? `somos un ${Math.abs(diff).toFixed(1).replace('.', ',')} % más baratos` : `somos un ${diff.toFixed(1).replace('.', ',')} % más caros`}.</p>`;
  }
  return `<div class="best-banner">${html}</div>`;
}
function renderResults(items, qty, links = []) {
  cardsTool.items = items;
  const byProvider = new Map();
  for (const item of items) {
    if (!byProvider.has(item.provider)) byProvider.set(item.provider, []);
    byProvider.get(item.provider).push(item);
  }
  const groups = [...byProvider].map(([id, list]) => {
    list.sort(byRank);
    return {provider: providers.find(p => p.id === id) || {id, name: id, initials: id.slice(0, 2).toUpperCase()}, items: list, best: list[0]};
  }).sort((a, b) => byRank(a.best, b.best));
  $('tool-best').innerHTML = bestBanner(groups, qty);
  const cheapestId = groups.find(g => offerTotal(g.best) !== null && g.best.tax_status !== 'unknown')?.provider.id;
  groups.forEach(g => g.links = links.filter(l => l.provider === g.provider.id));
  $('tool-results').innerHTML = groups.length ? groups.map(g => offerCard(g, g.best, qty, g.provider.id === cheapestId && !g.best.near ? ['best'] : [])).join('')
    : `<div class="empty-box"><p><strong>${cardsTool.mode === 'generic' ? 'No hay nada recogido con ese nombre y esas opciones.' : 'Ninguna ficha recogida tiene todo esto.'}</strong></p><p class="auto-note">Prueba a poner «Cualquiera» en alguno de los pasos${cardsTool.mode === 'generic' ? ' o con otra palabra' : ' (por ejemplo el gramaje o el acabado), o vuelve a lo estándar'}.</p></div>`;
}
cardsTool.search = async function () {
  if (cardsTool.mode === 'generic') return searchGeneric();
  const state = cardsTool.state, qty = Number(state.quantity) || STANDARD.quantity, ticket = ++cardsTool.ticket;
  $('tool-summary').textContent = 'Buscando: ' + describeChoice();
  const params = new URLSearchParams({q: 'tarjetas de visita', limit: 200, offset: 0, quantity: qty, cards: JSON.stringify(toolBrief())});
  if (state.days) params.set('max_days', state.days);
  try {
    const data = await api('/api/catalog?' + params);
    if (ticket !== cardsTool.ticket) return;
    renderResults(data.items, qty);
  } catch (error) {
    $('tool-results').innerHTML = `<p class="auto-note warn">No se pudo buscar: ${esc(error.message)}</p>`;
  }
};
async function searchGeneric() {
  const qty = generic.quantity || 100, ticket = ++cardsTool.ticket;
  $('tool-summary').textContent = 'Buscando: ' + describeChoice();
  const params = new URLSearchParams({q: generic.query, limit: 200, offset: 0, quantity: qty});
  if (Object.keys(generic.filters).length) params.set('filters', JSON.stringify(generic.filters));
  if (generic.days) params.set('max_days', generic.days);
  try {
    const data = await api('/api/catalog?' + params);
    if (ticket !== cardsTool.ticket) return;
    renderResults(data.items, qty, data.unpriced || []);
  } catch (error) {
    $('tool-results').innerHTML = `<p class="auto-note warn">No se pudo buscar: ${esc(error.message)}</p>`;
  }
}
function chrome() {
  const generic_ = cardsTool.mode === 'generic';
  $('tool-title').textContent = generic_ ? `Resultados para «${generic.query}»` : 'Tarjetas de visita';
  $('tool-best').innerHTML = '';
  $('tool-results').innerHTML = '';
}
function manualFill() {
  const s = cardsTool.state;
  return {format: s.format, grams: (s.grams.match(/\d+/) || [''])[0], paper_type: s.paper_type, surface: s.surface, sides: /2/.test(s.pages) ? '2' : '1', finishing: s.finishing || 'Sin', quantity: s.quantity};
}
function dimensions(text) {
  const match = String(text).replace(/×/g, 'x').match(/(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?/i);
  if (!match) return null;
  let [w, h] = [match[1], match[2]].map(v => parseFloat(v.replace(',', '.')));
  if ((match[3] || '').toLowerCase() === 'cm' || Math.max(w, h) < 20) [w, h] = [w * 10, h * 10];
  return [Math.round(w), Math.round(h)].sort((a, b) => a - b).join('x');
}
// What a customer's text asked for, set on the buttons (the person can still change anything).
cardsTool.apply = function (item) {
  const s = cardsTool.state, form = cardsTool.form || {}, finishes = item.finishes || [];
  if (cardsTool.mode !== 'cards') {
    cardsTool.mode = 'cards';
    chrome();
  }
  Object.assign(s, STANDARD);
  if (item.quantity) s.quantity = item.quantity;
  if (item.sides) s.pages = item.sides === 2 ? '2 caras' : '1 cara';
  if (item.grams) s.grams = (form.grams || []).find(g => g.startsWith(item.grams + ' ')) || '';
  if (item.size) s.format = (form.format || []).find(f => dimensions(f) === dimensions(item.size)) || '';
  if (finishes.includes('mate')) s.surface = 'Mate';
  if (finishes.includes('brillo')) s.surface = 'Brillo';
  if (finishes.some(f => f === 'plastificado' || f === 'laminado')) s.finishing = (form.finishing || []).find(f => f.startsWith('Plastificado')) || s.finishing;
  if (finishes.includes('barniz')) s.finishing = (form.finishing || []).find(f => f.startsWith('Barniz')) || s.finishing;
  if (item.max_days) s.days = (DAY_CHOICES.find(([n]) => n >= item.max_days) || DAY_CHOICES[DAY_CHOICES.length - 1])[0];
  renderSteps();
  return cardsTool.search();
};
function change(key, value) {
  if (cardsTool.mode === 'generic') {
    if (key === 'quantity') generic.quantity = Math.max(1, Math.min(1000000, Number(value) || 100));
    else if (key === 'days') generic.days = Number(value);
    else if (key.startsWith('g:')) {
      if (value) generic.filters[key.slice(2)] = value;
      else delete generic.filters[key.slice(2)];
    }
    renderSteps();
    return cardsTool.search();
  }
  const state = cardsTool.state;
  state[key] = key === 'quantity' ? Math.max(1, Math.min(1000000, Number(value) || STANDARD.quantity)) : key === 'days' ? Number(value) : value;
  renderSteps();
  cardsTool.search();
}
window.initCardsTool = async function () {
  try {
    cardsTool.form = await api('/api/card-options');
  } catch {
    cardsTool.form = {types: [], format: [], pages: ['1 cara', '2 caras'], grams: [], paper_type: [], finishing: [], orientation: [], processing: []};
  }
  renderSteps();
  const steps = $('tool-steps');
  steps.addEventListener('click', event => {
    const pillButton = event.target.closest('.pill');
    if (pillButton) change(pillButton.dataset.key, pillButton.dataset.value);
    if (event.target.id === 'tool-reset') {
      if (cardsTool.mode === 'generic') Object.assign(generic, {filters: {}, quantity: 100, days: 0});
      else Object.assign(cardsTool.state, STANDARD);
      renderSteps();
      cardsTool.search();
    }
  });
  steps.addEventListener('change', event => {
    const target = event.target;
    if (target.matches('.pill-select') && target.value === '') return renderSteps();  // "Otro…" is only the label
    if (target.matches('select, input')) change(target.dataset.key, target.value);
  });
  $('tool-results').addEventListener('click', event => {
    const button = event.target.closest('.tool-manual');
    if (button) openManual(cardsTool.items[Number(button.dataset.index)], manualFill());
    if (event.target.closest('.tool-edit-manual')) {
      $('manual-box').open = true;
      $('manual-box').scrollIntoView({block: 'start'});
    }
  });
  cardsTool.onQuery($('cat-q').value.trim());
};
// What was typed in the finder decides the screen: nothing or business cards = the standard card; anything else = that product.
cardsTool.onQuery = async function (text) {
  if (!text || isCardText(text)) {
    if (cardsTool.mode !== 'cards') {
      cardsTool.mode = 'cards';
      chrome();
      renderSteps();
    }
    return cardsTool.search();
  }
  if (cardsTool.mode !== 'generic' || generic.query !== text) {
    const ticket = ++generic.ticket;
    cardsTool.mode = 'generic';
    Object.assign(generic, {query: text, filters: {}, quantity: 100, days: 0});
    try {
      generic.form = await api('/api/product-options?q=' + encodeURIComponent(text));
    } catch {
      generic.form = {groups: []};
    }
    if (ticket !== generic.ticket) return;
    chrome();
  }
  if (cardsTool.preset) {  // what a customer's text asked for
    const {quantity, days} = cardsTool.preset;
    if (quantity) generic.quantity = quantity;
    if (days) generic.days = (DAY_CHOICES.find(([n]) => n >= days) || DAY_CHOICES[DAY_CHOICES.length - 1])[0];
    cardsTool.preset = null;
  }
  renderSteps();
  return cardsTool.search();
};
