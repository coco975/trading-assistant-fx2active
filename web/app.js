const ids = [
  'trading_enabled','allow_buys','allow_sells','fib_enabled','fib_retracement',
  'stop_buffer_pips','take_profit_mode','entry_trigger','max_open_positions',
  'support_resistance','previous_swing','trendline','psychological_level',
  'candle_confirmation','min_confirmations'
];

const $ = (id) => document.getElementById(id);
const status = $('status');
const dot = $('status-dot');

function mark(message, kind='ok') {
  status.textContent = message;
  dot.dataset.kind = kind;
}

function setHealth(id, ok) {
  $(id).dataset.state = ok ? 'ok' : 'error';
}

function setForm(s) {
  $('trading_enabled').checked = s.trading_enabled;
  $('allow_buys').checked = s.allow_buys;
  $('allow_sells').checked = s.allow_sells;
  $('fib_enabled').checked = s.fib_enabled;
  $('fib_retracement').value = s.fib_retracement;
  $('stop_buffer_pips').value = s.stop_buffer_pips;
  $('take_profit_mode').value = s.take_profit_mode;
  $('entry_trigger').value = s.entry_trigger;
  $('max_open_positions').value = s.max_open_positions;
  $('support_resistance').checked = s.poi.support_resistance;
  $('previous_swing').checked = s.poi.previous_swing;
  $('trendline').checked = s.poi.trendline;
  $('psychological_level').checked = s.poi.psychological_level;
  $('candle_confirmation').checked = s.poi.candle_confirmation;
  $('min_confirmations').value = s.poi.min_confirmations;
}

function getForm() {
  return {
    trading_enabled: $('trading_enabled').checked,
    allow_buys: $('allow_buys').checked,
    allow_sells: $('allow_sells').checked,
    timeframe: 'M15',
    fib_enabled: $('fib_enabled').checked,
    fib_retracement: Number($('fib_retracement').value),
    stop_buffer_pips: Number($('stop_buffer_pips').value),
    take_profit_mode: $('take_profit_mode').value,
    entry_trigger: $('entry_trigger').value,
    max_open_positions: Number($('max_open_positions').value),
    poi: {
      support_resistance: $('support_resistance').checked,
      previous_swing: $('previous_swing').checked,
      trendline: $('trendline').checked,
      psychological_level: $('psychological_level').checked,
      candle_confirmation: $('candle_confirmation').checked,
      min_confirmations: Number($('min_confirmations').value)
    }
  };
}

async function loadSettings() {
  try {
    const r = await fetch('/api/settings', {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    setForm(await r.json());
    mark('Settings loaded');
  } catch (e) {
    mark(`Could not load settings: ${e.message}`, 'error');
  }
}

async function loadSystemStatus() {
  try {
    const r = await fetch('/api/system/status', {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const s = await r.json();

    setHealth('worker-health', !!s.worker_online);
    $('worker-text').textContent = s.worker_online ? 'Online' : 'Offline';

    setHealth('mt5-health', !!s.mt5_connected);
    $('mt5-text').textContent = s.mt5_connected ? 'Connected' : 'Not connected';

    setHealth('account-health', !!s.account_connected);
    $('account-text').textContent = s.account_connected
      ? `${s.account_server || 'Logged in'} ${s.account_login_masked || ''}`.trim()
      : 'Not logged in';

    $('position-text').textContent = s.open_positions == null
      ? '—'
      : `${s.open_positions} / ${s.max_open_positions}`;
    $('system-message').textContent = s.message || 'Local system running';
  } catch (e) {
    setHealth('worker-health', false);
    setHealth('mt5-health', false);
    setHealth('account-health', false);
    $('worker-text').textContent = 'Unavailable';
    $('mt5-text').textContent = 'Unavailable';
    $('account-text').textContent = 'Unavailable';
    $('system-message').textContent = `Status error: ${e.message}`;
  }
}

function renderDiagnostics(report) {
  const list = $('diagnostic-list');
  list.innerHTML = '';
  const checks = report.checks || [];
  checks.forEach((check) => {
    const row = document.createElement('div');
    row.className = `diagnostic-row ${check.ok ? 'pass' : 'fail'}`;
    const badge = document.createElement('span');
    badge.className = 'diagnostic-badge';
    badge.textContent = check.ok ? 'OK' : 'CHECK';
    const copy = document.createElement('span');
    const title = document.createElement('strong');
    title.textContent = check.name;
    const msg = document.createElement('small');
    msg.textContent = check.message;
    copy.append(title, msg);
    row.append(badge, copy);
    list.append(row);
  });
  $('diagnostic-card').classList.remove('hidden');
}

async function diagnose() {
  const button = $('diagnose');
  button.disabled = true;
  button.textContent = 'Checking…';
  try {
    const r = await fetch('/api/system/diagnose', {method:'POST'});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    renderDiagnostics(data);
    await loadSystemStatus();
  } catch (e) {
    mark(`System check failed: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Run system check';
  }
}

async function apply() {
  const button = $('apply');
  button.disabled = true;
  mark('Applying settings…', 'busy');
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(getForm())
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    setForm(data.settings);
    mark('Applied — worker will use these rules on the next strategy check');
    setTimeout(loadSystemStatus, 500);
  } catch (e) {
    mark(`Update failed: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
  }
}

ids.forEach((id) => $(id).addEventListener('change', () => mark('Unsaved changes', 'busy')));
$('apply').addEventListener('click', apply);
$('diagnose').addEventListener('click', diagnose);
$('close-diagnostics').addEventListener('click', () => $('diagnostic-card').classList.add('hidden'));

loadSettings();
loadSystemStatus();
setInterval(loadSystemStatus, 3000);
