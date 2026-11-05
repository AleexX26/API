// Import of a Print24 price-matrix capture pasted by hand. No cookies, tokens or headers are read or sent.
const $ = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
const euro = value => new Intl.NumberFormat('es-ES', {style: 'currency', currency: 'EUR'}).format(Number(value));
const KEYS = ['format', 'paper', 'sides', 'finishing', 'orientation', 'inks'];

function say(kind, html) {$('result').className = kind; $('result').innerHTML = html;}

async function loadStored() {
  try {
    const res = await fetch('/api/print24/captures'), data = await res.json();
    $('stored').innerHTML = data.items.length ? data.items.map(item => `<div class="card"><h3>${esc(item.name)}</h3><small>Leído ${esc(item.observed_at.slice(0, 16).replace('T', ' '))} · ${esc(item.spec.map(x => x.label).join(' · '))}</small>
      <table><thead><tr><th>Cantidad</th><th>Total sin IVA (con envío del plazo)</th><th>Días</th></tr></thead><tbody>${item.rows.map(r => `<tr><td>${r.quantity.toLocaleString('es-ES')}</td><td>${euro(r.total_net)}</td><td>${r.delivery_days ?? ''}</td></tr>`).join('')}</tbody></table></div>`).join('')
      : '<p class="note">Todavía no hay ninguna captura importada.</p>';
  } catch (error) {
    $('stored').textContent = 'No se pudo leer la lista: ' + error.message;
  }
}

async function send(event) {
  event.preventDefault();
  const configuration = {};
  for (const key of KEYS) configuration[key] = $('f-' + key).value;
  let payload = null;
  if ($('payload').value.trim()) {
    try {payload = JSON.parse($('payload').value);} catch {return say('bad', 'El Payload no es un JSON válido (pega el contenido de la pestaña Payload en vista «source», o déjalo vacío).');}
  }
  $('send').disabled = true;
  say('', 'Importando…');
  try {
    const res = await fetch('/api/print24/captures/price-matrix', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({response: $('response').value, configuration, request_payload: payload})});
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Revisa los campos: ' + JSON.stringify(data.detail));
    say('ok', `Importado: ${data.prices} precios (${data.quantities.join(', ')} uds × ${data.deliveries.join(', ')}) en ${data.products} productos.<ul>${data.checks.map(c => `<li>${esc(c)}</li>`).join('')}</ul>`);
    $('response').value = '';
    loadStored();
  } catch (error) {
    say('bad', esc(error.message));
  } finally {
    $('send').disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('capture').addEventListener('submit', send);
  loadStored();
});
