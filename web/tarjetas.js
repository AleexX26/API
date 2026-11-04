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
  return `<button type="button" class="pill${on ? ' on' : ''}" data-key="${esc(key)}" data-value="${esc(value)}" aria-pressed="${on}">${esc(label)}${tag ? ` <small>${tag}</small>` : ''}</button>`;
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
    html += `<select class="pill-select${onRest ? ' on' : ''}" data-key="${esc(field.key)}" aria-label="${esc(field.label)}: otras opciones"><option value="">Otro…</option>${rest.map(o => `<option value="${esc(o)}"${o === current ? ' selected' : ''}>${esc(shown(field.key, o))}</option>`).join('')}</select>`;
  }
  return `<div class="step"><div class="step-label">${esc(field.label)}</div><div class="pills" role="group" aria-label="${esc(field.label)}">${html}</div></div>`;
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
// ---- What was asked against what a page offers --------------------------------------------------------------
const plain = text => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const BASIC_WORDS = new Set(['clasica', 'estandar', 'basica', 'normal', 'standard']);  // "Tarjetas de visita clásicas" is the plain card
const STOP_WORDS = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'con', 'para', 'y', 'e', 'en', 'a', 'un', 'una', 'por']);
const stem = word => word.replace(/(es|s)$/, '');
const currentQuery = () => cardsTool.mode === 'generic' ? generic.query : 'tarjetas de visita';
// Words of the product name that are not in the search: "Tarjetas de visita con textura" has one more than "tarjetas de visita"
function titleExtras(item) {
  const asked = new Set(plain(currentQuery()).split(/[^a-z0-9]+/).filter(Boolean).map(stem));
  return plain(String(item.title).split(' · ')[0]).split(/[^a-z0-9]+/).filter(w => w.length > 1 && !/\d/.test(w))
    .map(stem).filter(w => !STOP_WORDS.has(w) && !asked.has(w) && !BASIC_WORDS.has(w)).length;
}
const dimsOf = text => {
  const m = plain(text).match(/(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm)?/);
  if (!m) return null;
  const k = m[3] === 'cm' ? 10 : 1;
  return [parseFloat(m[1].replace(',', '.')) * k, parseFloat(m[2].replace(',', '.')) * k];
};
const sidesOf = text => /4\s*\+\s*4|2 caras|dos caras|ambas/.test(plain(text)) ? 2 : /4\s*\+\s*0|1 cara|una cara/.test(plain(text)) ? 1 : null;
const familyOf = text => { const t = plain(text); return /estucado|cuche|couche/.test(t) ? 'estucado' : /offset/.test(t) ? 'offset' : /reciclad|kraft|ecolog/.test(t) ? 'reciclado' : /carton|cartulina/.test(t) ? 'carton' : null; };
// true when this part of a page's description is NOT what was asked (shown in neon red)
function differs(part, state) {
  const label = plain(part.label), group = plain(part.group);
  if (cardsTool.mode === 'generic') {
    const wanted = Object.entries(generic.filters).find(([name]) => plain(name) === group);
    return !!wanted && wanted[1] !== '' && !label.includes(plain(wanted[1]));
  }
  if (/formato/.test(group)) {
    const want = dimsOf(state.format), have = dimsOf(part.label);
    return !!want && !!have && !((Math.abs(want[0] - have[0]) < 1.5 && Math.abs(want[1] - have[1]) < 1.5) || (Math.abs(want[0] - have[1]) < 1.5 && Math.abs(want[1] - have[0]) < 1.5));
  }
  if (/papel/.test(group)) {
    const grams = (label.match(/(\d{2,4})\s*g/) || [])[1], askedGrams = (plain(state.grams).match(/\d+/) || [])[0];
    if (grams && askedGrams && grams !== askedGrams) return true;
    const family = familyOf(part.label), askedFamily = familyOf(state.paper_type);
    if (family && askedFamily && family !== askedFamily) return true;
    const surface = plain(state.surface);
    return !!surface && (surface === 'mate' ? /brillo|brillante/ : /mate/).test(label) && !label.includes(surface);
  }
  if (/impres/.test(group)) {
    const want = state.pages ? (/2/.test(state.pages) ? 2 : 1) : null, have = sidesOf(part.label);
    return !!want && !!have && want !== have;
  }
  if (/acabado/.test(group)) {
    const asked = plain(state.finishing), has = /plastific|barniz|laminad|relieve|soft|uvi/.test(label);
    if (!asked) return false;
    return asked === 'sin' ? has : !label.includes(asked.split(' ')[0]);
  }
  return false;
}
// The description of a page, with the parts that differ from the request in neon red
function whatHtml(item) {
  const wanted = item.spec.filter(x => ['Formato', 'Papel', 'Impresión', 'Acabados', 'Realización'].includes(x.group) || /formato|papel|impres|acabado|realiz/i.test(x.group)).slice(0, 5);
  const parts = wanted.length ? wanted : item.spec.slice(0, 3);
  const state = cardsTool.state;
  return parts.map(x => differs(x, state) ? `<span class="neon" title="No es lo que pides: otra opción"><span class="sr-only">Distinto de lo que pides: </span>${esc(x.label)}</span>` : esc(x.label)).join(' · ');
}
function offerTotal(item) {return item.at ? withIva(Number(item.at.total), item.tax_status) : null;}  // with VAT: what the offers are ranked by
const netOf = (value, tax) => tax === 'gross' ? Number(value) / IVA : Number(value);  // without VAT: what is shown first
function netTotal(item) {return netOf(item.at.total, item.tax_status);}
function offerRank(item) {
  const total = offerTotal(item);
  return [item.near ? 1 : 0, total === null ? 1 : 0, total ?? 0];
}
// Inside one provider: first the product that is what was asked (its name has no extra words), then the nearest, then the cheapest
function byRelevance(a, b) {return titleExtras(a) - titleExtras(b) || byRank(a, b);}
function byRank(a, b) {
  const x = offerRank(a), y = offerRank(b);
  return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
}
const MAX_COLUMNS = 4;  // providers in a row
const STALE_DAYS = 30;
const ageDays = item => Math.max(0, Math.floor((Date.now() - new Date(item.observed_at).getTime()) / 864e5));
// A line above the results when some provider's prices are old: they are read by hand, so they age
function staleNotice(groups) {
  const old = groups.filter(g => g.best && ageDays(g.best) > STALE_DAYS).map(g => `${g.provider.name} (${ageDays(g.best)} días)`);
  return old.length ? `<p class="stale-note"><strong>Aviso:</strong> precios con más de ${STALE_DAYS} días en ${esc(old.join(', '))}. Conviene volver a recogerlos (opción 1 de Herramientas).</p>` : '';
}
function chips(item, qty) {
  const tier = (item.prices || []).find(x => Number(x[0]) === qty) || (item.prices || [])[0], out = [];
  out.push(item.shipping === 'included' ? ['ok', 'Envío incluido'] : item.shipping === 'excluded' ? ['warn', 'Envío aparte'] : ['warn', 'Envío sin confirmar']);
  if (tier && tier[2] != null) out.push(['', `Entrega ~${tier[2]} días`]);
  if (item.tax_status === 'unknown') out.push(['warn', 'IVA sin confirmar']);
  if (item.at?.estimated) out.push(['warn', item.at.between ? `Estimado entre ${item.at.between[0]} y ${item.at.between[1]} uds` : 'Precio estimado']);
  const age = ageDays(item);
  out.push([age > STALE_DAYS ? 'warn' : '', age <= 0 ? 'Leído hoy' : `Leído hace ${age} día${age === 1 ? '' : 's'}${age > STALE_DAYS ? ' ⚠' : ''}`]);
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
  return `<tr><td><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)} ↗</a>${item.near ? `<div class="auto-note warn">${esc(item.near)}</div>` : ''}</td><td>${price}</td><td>${whatHtml(item)}</td></tr>`;
}
// Our price against each rival's (both without VAT): more than them = profit margin (green), less = red.
// Our margin on this order: net sale price minus the supplier cost at this exact quantity (the Excel's "pvp proveedor").
function marginOf(item, qty) {
  if (!item || !item.costs || item.tax_status !== 'net' || !item.at || item.at.estimated || offerTotal(item) === null) return null;
  const cost = Number(item.costs[String(qty)]), sale = netTotal(item);
  if (!cost || !sale) return null;
  const profit = sale - cost;
  return {cost, profit, pct: profit / sale * 100, kind: profit < -0.005 ? 'down' : 'up'};
}
const signed = n => (n > 0.005 ? '+' : n < -0.005 ? '−' : '') + euro(Math.abs(n));
const percent = n => Math.abs(n).toFixed(1).replace('.', ',') + ' %';
function marginHtml(item, qty) {
  const m = marginOf(item, qty);
  if (!m) return '';
  return `<div class="margin-line ${m.kind}"><span>Coste ${euro(m.cost)}</span><strong>Beneficio ${signed(m.profit)} (${m.profit < 0 ? '−' : ''}${percent(m.pct)})</strong>${m.kind === 'down' ? '<em>Por debajo del coste</em>' : ''}</div>`;
}
function diffOf(mineGroup, theirGroup) {
  const mine = netTotal(mineGroup.best), theirs = netTotal(theirGroup.best), diff = mine - theirs;
  const kind = Math.abs(diff) < 0.005 ? 'same' : diff > 0 ? 'up' : 'down', sign = diff > 0 ? '+' : diff < 0 ? '−' : '';
  const pct = theirs ? Math.abs(diff / theirs * 100).toFixed(1).replace('.', ',') : '0';
  return {kind, money: kind === 'same' ? 'igual' : `${sign}${euro(Math.abs(diff))}`, percent: kind === 'same' ? '' : `${sign}${pct} %`};
}
const hasPrice = g => !!g.best && offerTotal(g.best) !== null && g.best.tax_status !== 'unknown';
// On each rival's card, on the left: how our price differs from theirs.
function diffSide(group, groups) {
  const own = groups.find(g => g.provider.own);
  if (group.provider.own || !own || !hasPrice(own) || !hasPrice(group)) return '';
  const d = diffOf(own, group);
  return `<div class="diff-side"><span class="diff-label">Nuestra web</span><strong class="diff ${d.kind}">${d.money}</strong>${d.percent ? `<small class="diff ${d.kind}">${d.percent}</small>` : ''}</div>`;
}
// Our shop with no price collected for this search: its own page(s) as links, so every product shows at least our web.
function ownLinksCard(group) {
  const p = group.provider, [first, ...rest] = group.links;
  const link = l => `<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.title)} ↗</a>`;
  return `<article class="offer own no-price"><div class="offer-head"><span class="monogram">${esc(p.initials)}</span><div><strong>${esc(p.name)}</strong> <span class="tag own">Nuestra web</span></div></div>
 <div class="offer-price"><div><div class="big muted">Sin precio aquí</div><div class="per">El precio está en nuestra web</div></div></div>
 <p class="offer-what">${esc(first.title)}</p>
 <div class="offer-actions"><a class="go-button" href="${esc(first.url)}" target="_blank" rel="noopener noreferrer">Ver en nuestra web ↗</a><button type="button" class="outline tool-manual-link" data-provider="${esc(p.id)}" data-url="${esc(first.url)}" data-title="${esc(first.title)}">✎ Anotar precio</button></div>
 ${rest.length ? `<ul class="result-links">${rest.slice(0, 4).map(l => `<li>${link(l)}</li>`).join('')}</ul>` : ''}</article>`;
}
function offerCard(group, best, qty, badges, groups = []) {
  if (!best) return ownLinksCard(group);
  const p = group.provider, index = cardsTool.items.indexOf(best), others = group.items.filter(i => i !== best);
  const classes = ['offer', badges.includes('best') ? 'best' : '', p.own ? 'own' : '', best.near ? 'near' : ''].filter(Boolean).join(' ');
  return `<article class="${classes}"><div class="offer-head"><span class="monogram">${esc(p.initials)}</span><div><strong>${esc(p.name)}</strong>${p.own ? ' <span class="tag own">Nuestra web</span>' : ''}${badges.includes('best') ? ' <span class="tag best">Más barato</span>' : ''}</div></div>
 <div class="offer-price">${diffSide(group, groups)}<div>${priceBlock(best, qty)}</div></div>
 ${p.own ? marginHtml(best, qty) : ''}
 <div class="offer-meta">${chips(best, qty)}</div>
 <p class="offer-what">${whatHtml(best)}</p>
 ${best.near ? `<p class="offer-near">Precio de la ficha por defecto: ${esc(best.near)}. Quizá en su web se pueda pedir lo tuyo a otro precio.</p>` : ''}
 <div class="offer-actions"><a class="go-button" href="${esc(best.url)}" target="_blank" rel="noopener noreferrer">Ver ficha ↗</a>${p.own && offerTotal(best) !== null && best.tax_status !== 'unknown' ? `<button type="button" class="outline tool-copy" data-index="${index}">📋 Copiar para el cliente</button>` : ''}<button type="button" class="outline tool-manual" data-index="${index}">✎ ${best.near ? 'Anotar el precio real' : 'Anotar precio'}</button>${best.manual ? '<button type="button" class="outline tool-edit-manual">✎ Editar el precio anotado</button>' : ''}</div>
 ${others.length || group.links?.length ? `<details class="auto-more-products"><summary>Ver más (${others.length + (group.links?.length || 0)})</summary>${others.length ? `<div class="comparison-box"><table><thead><tr><th>Ficha</th><th>Precio</th><th>Qué es</th></tr></thead><tbody>${others.map(i => otherRow(i, qty)).join('')}</tbody></table></div>` : ''}${group.links?.length ? `<div class="auto-note">Páginas sin precio recogido (solo enlace):</div><ul class="result-links">${group.links.map(l => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.title)} ↗</a></li>`).join('')}</ul>` : ''}</details>` : ''}</article>`;
}
// Text ready to paste in the customer's email: OUR sale price only (never supplier names or costs)
function customerText(item, qty) {
  const parts = item.spec.filter(x => /formato|papel|impres|acabado|realiz/i.test(x.group)).slice(0, 5).map(x => x.label);
  const tier = (item.prices || []).find(x => Number(x[0]) === qty) || (item.prices || [])[0];
  const net = netTotal(item), total = offerTotal(item), plainTitle = String(item.title).split(' · ')[0];
  const lines = [plainTitle, parts.length ? 'Características: ' + parts.join(', ') : '', `Cantidad: ${qty.toLocaleString('es-ES')} uds`,
    `Precio: ${euro(net)} sin IVA (${euro(total)} con IVA 21 %) · ${euro(net / qty)}/ud sin IVA`,
    item.shipping === 'included' ? 'Envío incluido' : '', tier && tier[2] != null ? `Entrega aproximada: ${tier[2]} días` : ''];
  return lines.filter(Boolean).join('\n');
}
async function copyText(text) {
  try {await navigator.clipboard.writeText(text); return true;} catch {}
  const area = document.createElement('textarea');  // fallback when the page is not a secure context
  area.value = text; area.className = 'sr-only'; document.body.appendChild(area); area.select();
  let ok = false;
  try {ok = document.execCommand('copy');} catch {}
  area.remove();
  return ok;
}
function bestBanner(groups, qty) {
  const priced = groups.map(g => ({g, item: g.best})).filter(x => x.item && offerTotal(x.item) !== null && x.item.tax_status !== 'unknown');
  const exact = priced.filter(x => !x.item.near), pool = exact.length ? exact : priced;
  if (!pool.length) return '';
  const cheapest = pool.reduce((m, x) => offerTotal(x.item) < offerTotal(m.item) ? x : m);
  const own = pool.find(x => x.g.provider.own), rivals = pool.filter(x => !x.g.provider.own);
  const rival = rivals.length ? rivals.reduce((m, x) => offerTotal(x.item) < offerTotal(m.item) ? x : m) : null;
  let us = '';
  if (own && rival) {
    const d = diffOf(own.g, rival.g);
    const words = d.kind === 'same' ? 'Cobramos lo mismo que' : d.kind === 'up' ? 'Cobramos más que' : 'Cobramos menos que';
    us = `<p class="hero-us"><span>${words} ${esc(rival.g.provider.name)}, el proveedor más barato:</span> <strong class="diff ${d.kind}">${d.money}${d.percent ? ` (${d.percent})` : ''}</strong></p>`;
  }
  const m = own ? marginOf(own.item, qty) : null;
  const margin = m ? `<p class="hero-margin ${m.kind}">Nuestro beneficio sobre el coste del proveedor: <strong>${signed(m.profit)} (${m.profit < 0 ? '−' : ''}${percent(m.pct)})</strong>${m.kind === 'down' ? ' · por debajo del coste' : ''}</p>` : '';
  const note = exact.length ? '' : '<p class="hero-note">Ninguna ficha coincide exactamente: son precios de configuraciones parecidas.</p>';
  return `<div class="best-banner"><p class="hero-label">Lo más barato para este pedido</p><div class="hero-main"><span class="hero-name">${esc(cheapest.g.provider.name)}</span><span class="hero-price">${euro(netTotal(cheapest.item))} <small>sin IVA</small></span></div><p class="hero-sub">${euro(offerTotal(cheapest.item))} con IVA · ${euro(netTotal(cheapest.item) / qty)}/ud sin IVA</p>${us}${margin}${note}</div>`;
}
function renderResults(allItems, qty, allLinks = []) {
  const hidden = typeof hiddenProviders === 'function' ? hiddenProviders() : new Set();  // providers the person chose not to see for this product
  const items = allItems.filter(i => !hidden.has(i.provider)), links = allLinks.filter(l => !hidden.has(l.provider));
  cardsTool.items = items;
  const byProvider = new Map();
  for (const item of items) {
    if (!byProvider.has(item.provider)) byProvider.set(item.provider, []);
    byProvider.get(item.provider).push(item);
  }
  const groups = [...byProvider].map(([id, list]) => {
    list.sort(byRelevance);
    return {provider: providers.find(p => p.id === id) || {id, name: id, initials: id.slice(0, 2).toUpperCase()}, items: list, best: list[0]};
  }).sort((a, b) => (a.provider.own ? 1 : 0) - (b.provider.own ? 1 : 0) || byRank(a.best, b.best));  // our web goes last
  groups.forEach(g => g.links = links.filter(l => l.provider === g.provider.id));
  const own = providers.find(p => p.own);
  if (own && !byProvider.has(own.id)) {  // nothing priced for our web in this search: show at least its page(s)
    const ownLinks = links.filter(l => l.provider === own.id);
    if (ownLinks.length) groups.push({provider: own, items: [], best: null, links: ownLinks});
  }
  const cheapestId = groups.find(g => hasPrice(g))?.provider.id;
  const card = g => offerCard(g, g.best, qty, g.provider.id === cheapestId && !g.best?.near ? ['best'] : [], groups);
  const ownGroup = groups.find(g => g.provider.own), rivals = groups.filter(g => !g.provider.own);
  // Our web goes first, above the green box of the cheapest; the other providers go below, from cheapest to dearest
  $('tool-best').innerHTML = (ownGroup ? card(ownGroup) : '') + bestBanner(groups, qty) + staleNotice(groups);
  // Columns: as many as providers up to 4 in a row, and the rows are balanced (5 = 3 + 2, 7 = 4 + 3); the cards fill the width
  $('tool-results').className = 'tool-results cols-' + (rivals.length ? Math.ceil(rivals.length / Math.ceil(rivals.length / MAX_COLUMNS)) : 1);
  $('tool-results').innerHTML = rivals.length ? rivals.map(card).join('')
    : groups.length ? '<div class="empty-box"><p class="auto-note">Ningún otro proveedor tiene esto con lo que has elegido.</p></div>' 
    : `<div class="empty-box"><p><strong>${cardsTool.mode === 'generic' ? 'No hay nada recogido con ese nombre y esas opciones.' : 'Ninguna ficha recogida tiene todo esto.'}</strong></p><p class="auto-note">Prueba a poner «Cualquiera» en alguno de los pasos${cardsTool.mode === 'generic' ? ' o con otra palabra' : ' (por ejemplo el gramaje o el acabado), o vuelve a lo estándar'}.</p></div>`;
}
cardsTool.search = async function () {
  if (cardsTool.mode === 'generic') return searchGeneric();
  const state = cardsTool.state, qty = Number(state.quantity) || STANDARD.quantity, ticket = ++cardsTool.ticket;
  $('tool-summary').textContent = 'Buscando: ' + describeChoice();
  const params = new URLSearchParams({q: 'tarjetas de visita', limit: 1000, offset: 0, quantity: qty, cards: JSON.stringify(toolBrief())});
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
  const params = new URLSearchParams({q: generic.query, limit: 1000, offset: 0, quantity: qty});
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
// The manual-price dialog starts on what is chosen on the screen: the card buttons, or the product that was searched
function manualFillFor() {
  if (cardsTool.mode !== 'generic') return manualFill();
  const f = generic.filters, pick = name => Object.entries(f).find(([k]) => plain(k) === name)?.[1] || '';
  return {format: pick('formato'), grams: '', paper_type: '', surface: '', sides: '1', finishing: 'Sin', quantity: generic.quantity};
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
  // The cards of the providers are in #tool-results, ours (on top) is in #tool-best
  for (const box of [$('tool-results'), $('tool-best')]) box.addEventListener('click', event => {
    const button = event.target.closest('.tool-manual'), link = event.target.closest('.tool-manual-link'), copy = event.target.closest('.tool-copy');
    if (copy) {
      const item = cardsTool.items[Number(copy.dataset.index)], qty = cardsTool.mode === 'generic' ? (generic.quantity || 100) : (Number(cardsTool.state.quantity) || STANDARD.quantity);
      copyText(customerText(item, qty)).then(ok => toast(ok ? 'Copiado: pégalo en el email del cliente' : 'No se pudo copiar'));
    }
    if (button) openManual(cardsTool.items[Number(button.dataset.index)], manualFillFor());
    if (link) openManual({provider: link.dataset.provider, url: link.dataset.url, title: link.dataset.title}, manualFillFor());
    if (event.target.closest('.tool-edit-manual')) {
      $('manual-box').open = true;
      $('manual-box').scrollIntoView({block: 'start'});
    }
  });
  if (!cardsTool.ticket && !generic.ticket) cardsTool.onQuery($('cat-q').value.trim());  // initCatalog may already have searched
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
