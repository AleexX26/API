// Configuración de la pantalla: lo estándar con lo que arrancan los botones, los botones de cantidad y los proveedores
// que no deben salir en un producto. Se guarda en el servidor (/api/settings); solo el PC que aloja el comparador cambia.
// Se carga después de app.js y tarjetas.js (usa STANDARD, QUANTITIES, DAY_CHOICES, cardsTool, renderSteps, plain y currentQuery).
let screenSettings = {standard: {}, quantities: [], hidden: {}};
const FACTORY = {standard: {...STANDARD}, quantities: [...QUANTITIES]};
let draftHidden = {};

function applySettings() {
  Object.assign(STANDARD, FACTORY.standard, screenSettings.standard);
  QUANTITIES.splice(0, QUANTITIES.length, ...(screenSettings.quantities.length ? screenSettings.quantities : FACTORY.quantities));
  Object.assign(cardsTool.state, STANDARD);
}
async function loadSettings() {
  try { screenSettings = await api('/api/settings'); } catch { /* without settings the factory values are used */ }
  applySettings();
}
const hiddenProviders = () => {
  const asked = plain(currentQuery()), hidden = new Set();
  for (const [product, ids] of Object.entries(screenSettings.hidden || {})) if (asked.includes(plain(product))) ids.forEach(id => hidden.add(id));
  return hidden;
};

const SETTING_FIELDS = [
  ['quantity', 'Cantidad', 'number'], ['format', 'Tamaño', 'format'], ['pages', 'Caras', 'pages'], ['grams', 'Gramaje', 'grams'],
  ['paper_type', 'Papel', 'paper_type'], ['surface', 'Mate o brillo', 'surface'], ['finishing', 'Acabado', 'finishing'],
  ['inks', 'Colores', 'inks'], ['days', 'Entrega', 'days'],
];
function optionsFor(kind, current) {
  const form = cardsTool.form || {};
  const list = {
    format: (form.format || []).map(v => [v, shown('format', v)]), pages: [['1 cara', '1 cara'], ['2 caras', '2 caras']],
    grams: (form.grams || []).map(v => [v, shown('grams', v)]), paper_type: (form.paper_type || []).map(v => [v, v]),
    surface: [['', 'Cualquiera'], ['Mate', 'Mate'], ['Brillo', 'Brillo']],
    finishing: [['Sin', 'Sin acabado'], ...(form.finishing || []).filter(v => v !== 'Sin').map(v => [v, shown('finishing', v)])],
    inks: INK_CHOICES.map(([v, label]) => [v, label]), days: DAY_CHOICES.map(([v, label]) => [String(v), label]),
  }[kind] || [];
  if (current !== undefined && current !== null && !list.some(([v]) => String(v) === String(current))) list.unshift([String(current), String(current)]);
  return list;
}
function fillStandard(values) {
  $('settings-standard').innerHTML = SETTING_FIELDS.map(([key, label, kind]) => {
    const value = values[key];
    return kind === 'number'
      ? `<label>${label}<input id="set-${key}" type="number" min="1" max="1000000" value="${esc(value ?? 100)}"></label>`
      : `<label>${label}<select id="set-${key}">${optionsFor(kind, value).map(([v, text]) => `<option value="${esc(v)}"${String(v) === String(value ?? '') ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`;
  }).join('');
}
function renderRules() {
  const names = Object.fromEntries(providers.map(p => [p.id, p.name]));
  const rules = Object.entries(draftHidden);
  $('settings-rules').innerHTML = rules.length
    ? rules.map(([product, ids]) => `<li><span><strong>${esc(product)}</strong>: no sale ${esc(ids.map(id => names[id] || id).join(', '))}</span> <button type="button" class="outline rule-remove" data-product="${esc(product)}">Quitar</button></li>`).join('')
    : '<li class="auto-note">Ninguna regla: salen todos los proveedores que tengan el producto.</li>';
}
function openSettings() {
  draftHidden = JSON.parse(JSON.stringify(screenSettings.hidden || {}));
  fillStandard({...STANDARD, ...screenSettings.standard});
  $('settings-quantities').value = QUANTITIES.join(', ');
  $('settings-product').value = cardsTool.mode === 'generic' ? generic.query : 'tarjetas de visita';
  $('settings-providers').innerHTML = providers.filter(p => !p.own).map(p => `<label class="provider-check"><input type="checkbox" value="${esc(p.id)}"> ${esc(p.name)}</label>`).join('');
  $('settings-error').textContent = '';
  renderRules();
  $('settings-dialog').showModal();
}
async function saveSettings(event) {
  event.preventDefault();
  $('settings-error').textContent = '';
  try {
    const standard = {};
    for (const [key, , kind] of SETTING_FIELDS) {
      const raw = $('set-' + key).value;
      standard[key] = kind === 'number' || key === 'days' ? Number(raw) : raw;
    }
    const quantities = $('settings-quantities').value.split(/[,;\s]+/).filter(Boolean).map(Number);
    if (quantities.some(n => !Number.isInteger(n) || n < 1)) throw Error('Las cantidades deben ser números enteros separados por comas, por ejemplo 100, 250, 500');
    screenSettings = await api('/api/settings', {standard, quantities, hidden: draftHidden});
    applySettings();
    renderSteps();
    $('settings-dialog').close();
    toast('Configuración guardada');
    cardsTool.search();
  } catch (error) {
    $('settings-error').textContent = error.message;
  }
}
function initSettings() {
  $('settings-open').addEventListener('click', openSettings);
  $('close-settings').addEventListener('click', () => $('settings-dialog').close());
  $('settings-form').addEventListener('submit', saveSettings);
  $('settings-add-rule').addEventListener('click', () => {
    const product = $('settings-product').value.trim().toLowerCase().replace(/\s+/g, ' ');
    const ids = [...$('settings-providers').querySelectorAll('input:checked')].map(i => i.value);
    if (product.length < 2 || !ids.length) { $('settings-error').textContent = 'Escribe el producto y marca al menos un proveedor.'; return; }
    $('settings-error').textContent = '';
    draftHidden[product] = [...new Set([...(draftHidden[product] || []), ...ids])];
    $('settings-providers').querySelectorAll('input').forEach(i => { i.checked = false; });
    renderRules();
  });
  $('settings-rules').addEventListener('click', event => {
    const button = event.target.closest('.rule-remove');
    if (button) { delete draftHidden[button.dataset.product]; renderRules(); }
  });
  $('settings-reset').addEventListener('click', () => {
    fillStandard(FACTORY.standard);
    $('settings-quantities').value = FACTORY.quantities.join(', ');
    draftHidden = {};
    renderRules();
    $('settings-error').textContent = 'Valores de fábrica puestos: pulsa «Guardar» para quedarte con ellos.';
  });
}
