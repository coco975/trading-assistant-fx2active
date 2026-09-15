const ids = [
  'trading_enabled','allow_buys','allow_sells','symbol','fib_enabled','fib_retracement',
  'stop_buffer_pips','take_profit_mode','entry_trigger','max_open_positions',
  'sizing_mode','risk_percent','fixed_lot','fixed_cash_risk','execution_mode',
  'live_execution_enabled','allow_live_account','max_spread_pips','max_deviation_points',
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

function formatPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  const absolute = Math.abs(number);
  if (absolute >= 1000) return number.toFixed(2);
  if (absolute >= 10) return number.toFixed(3);
  return number.toFixed(5);
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString([], {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function updateSizingFields() {
  const mode = $('sizing_mode').value;
  $('risk-percent-row').classList.toggle('hidden', mode !== 'risk_percent');
  $('fixed-lot-row').classList.toggle('hidden', mode !== 'fixed_lot');
  $('fixed-cash-row').classList.toggle('hidden', mode !== 'fixed_cash');
}

function updateExecutionHelp() {
  const pending = $('execution_mode').value === 'pending_limit';
  $('entry_trigger').disabled = pending;
  $('execution-help').innerHTML = pending
    ? '<span>Pending Limit</span><span>Entry placed at the 78.6% Fib level</span>'
    : '<span>Market Execution</span><span>Uses the selected entry confirmation</span>';
}

function setForm(s) {
  $('trading_enabled').checked = s.trading_enabled;
  $('allow_buys').checked = s.allow_buys;
  $('allow_sells').checked = s.allow_sells;
  $('symbol').value = s.symbol || '';
  $('fib_enabled').checked = s.fib_enabled;
  $('fib_retracement').value = s.fib_retracement;
  $('stop_buffer_pips').value = s.stop_buffer_pips;
  $('take_profit_mode').value = s.take_profit_mode;
  $('entry_trigger').value = s.entry_trigger;
  $('max_open_positions').value = s.max_open_positions;
  $('sizing_mode').value = s.sizing_mode || 'risk_percent';
  $('risk_percent').value = s.risk_percent ?? 1;
  $('fixed_lot').value = s.fixed_lot ?? 0.01;
  $('fixed_cash_risk').value = s.fixed_cash_risk ?? 10;
  $('execution_mode').value = s.execution_mode || 'market_on_trigger';
  $('live_execution_enabled').checked = s.live_execution_enabled ?? false;
  $('allow_live_account').checked = s.allow_live_account ?? false;
  $('max_spread_pips').value = s.max_spread_pips ?? 0;
  $('max_deviation_points').value = s.max_deviation_points ?? 20;
  $('support_resistance').checked = s.poi.support_resistance;
  $('previous_swing').checked = s.poi.previous_swing;
  $('trendline').checked = s.poi.trendline;
  $('psychological_level').checked = s.poi.psychological_level;
  $('candle_confirmation').checked = s.poi.candle_confirmation;
  $('min_confirmations').value = s.poi.min_confirmations;
  updateSizingFields();
  updateExecutionHelp();
}

function getForm() {
  return {
    trading_enabled: $('trading_enabled').checked,
    allow_buys: $('allow_buys').checked,
    allow_sells: $('allow_sells').checked,
    symbol: $('symbol').value.trim(),
    timeframe: 'M15',
    fib_enabled: $('fib_enabled').checked,
    fib_retracement: Number($('fib_retracement').value),
    stop_buffer_pips: Number($('stop_buffer_pips').value),
    take_profit_mode: $('take_profit_mode').value,
    entry_trigger: $('entry_trigger').value,
    max_open_positions: Number($('max_open_positions').value),
    sizing_mode: $('sizing_mode').value,
    risk_percent: Number($('risk_percent').value),
    fixed_lot: Number($('fixed_lot').value),
    fixed_cash_risk: Number($('fixed_cash_risk').value),
    execution_mode: $('execution_mode').value,
    live_execution_enabled: $('live_execution_enabled').checked,
    allow_live_account: $('allow_live_account').checked,
    max_spread_pips: Number($('max_spread_pips').value),
    max_deviation_points: Number($('max_deviation_points').value),
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

function fibPrice(setup, percentage) {
  const high = Number(setup.swing_high);
  const low = Number(setup.swing_low);
  const ratio = Number(percentage) / 100;
  if (!Number.isFinite(high) || !Number.isFinite(low) || high <= low) return null;
  return String(setup.side).toUpperCase() === 'SELL'
    ? low + ((high - low) * ratio)
    : high - ((high - low) * ratio);
}

function renderFibSetup(setup, symbol='') {
  const content = $('fib-content');
  const sideBadge = $('fib-side');
  if (!setup) {
    content.classList.add('hidden');
    $('fib-status').textContent = 'Waiting for a qualifying setup.';
    sideBadge.textContent = '—';
    sideBadge.className = 'setup-badge neutral';
    return;
  }

  const side = String(setup.side || '').toUpperCase();
  const buy = side === 'BUY';
  sideBadge.textContent = side || 'SETUP';
  sideBadge.className = `setup-badge ${buy ? 'buy' : 'sell'}`;
  $('fib-status').textContent = `${symbol || 'Symbol'} • M15 • live setup map`;
  $('fib-path').textContent = buy ? 'Swing Low → Swing High' : 'Swing High → Swing Low';
  $('fib-swing-high').textContent = formatPrice(setup.swing_high);
  $('fib-swing-low').textContent = formatPrice(setup.swing_low);
  $('fib-entry').textContent = formatPrice(setup.entry);
  $('fib-stop').textContent = formatPrice(setup.stop_loss);
  $('fib-target').textContent = formatPrice(setup.take_profit);
  $('fib-rr').textContent = Number.isFinite(Number(setup.reward_to_risk))
    ? `${Number(setup.reward_to_risk).toFixed(2)}R`
    : '—';
  $('fib-swing-high-time').textContent = setup.swing_high_time ? formatTime(setup.swing_high_time) : '';
  $('fib-swing-low-time').textContent = setup.swing_low_time ? formatTime(setup.swing_low_time) : '';

  const configured = Number($('fib_retracement').value || 0.786) * 100;
  const rawLevels = [0, 23.6, 38.2, 50, 61.8, 71, configured, 78.6, 100];
  const uniqueLevels = [...new Set(rawLevels.map((value) => Number(value.toFixed(1))))];
  const levels = uniqueLevels.map((percentage) => ({
    percentage,
    price: fibPrice(setup, percentage)
  })).filter((item) => Number.isFinite(item.price)).sort((a, b) => b.price - a.price);

  const ladder = $('fib-levels');
  ladder.innerHTML = '';
  levels.forEach((level) => {
    const row = document.createElement('div');
    const isEntry = Math.abs(level.percentage - configured) < 0.11;
    const isHigh = Math.abs(level.price - Number(setup.swing_high)) < 1e-9;
    const isLow = Math.abs(level.price - Number(setup.swing_low)) < 1e-9;
    row.className = `fib-level${isEntry ? ' entry' : ''}${isHigh || isLow ? ' swing' : ''}`;

    const label = document.createElement('span');
    if (isHigh) label.textContent = `Swing High • ${level.percentage}%`;
    else if (isLow) label.textContent = `Swing Low • ${level.percentage}%`;
    else if (isEntry) label.textContent = `Entry • ${level.percentage}%`;
    else label.textContent = `${level.percentage}%`;

    const price = document.createElement('strong');
    price.textContent = formatPrice(level.price);
    row.append(label, price);
    ladder.append(row);
  });
  content.classList.remove('hidden');
}

function renderTradeLog(events=[]) {
  const list = $('trade-log-list');
  list.innerHTML = '';
  if (!events.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No trade activity recorded yet.';
    list.append(empty);
    return;
  }

  events.slice(0, 50).forEach((event) => {
    const row = document.createElement('div');
    row.className = 'trade-log-row';

    const fields = [
      formatTime(event.timestamp_utc),
      event.symbol || '—',
      event.event || '—',
      event.side || '—',
      event.price == null ? '—' : formatPrice(event.price),
      event.volume == null ? '—' : Number(event.volume).toFixed(2),
      event.status || '—'
    ];
    fields.forEach((value, index) => {
      const cell = document.createElement(index === 6 ? 'strong' : 'span');
      cell.textContent = value;
      if (index === 6) cell.className = `log-status ${String(event.status || '').toLowerCase()}`;
      row.append(cell);
    });
    list.append(row);
  });
}

async function loadTradeLog() {
  try {
    const r = await fetch('/api/trade-log', {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    renderTradeLog(Array.isArray(data.events) ? data.events : []);
  } catch (_) {
    renderTradeLog([]);
  }
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

    if (s.open_positions == null) {
      $('position-text').textContent = '—';
    } else {
      const pending = s.pending_orders ?? 0;
      $('position-text').textContent = `${s.open_positions} position(s) + ${pending} pending / ${s.max_open_positions}`;
    }

    renderFibSetup(s.last_setup, s.symbol);

    let message = s.message || 'FX2Active running';
    if (s.execution_result?.order_ticket) {
      message += ` Order #${s.execution_result.order_ticket}`;
    } else if (s.execution_result?.deal_ticket) {
      message += ` Deal #${s.execution_result.deal_ticket}`;
    }
    $('system-message').textContent = message;
  } catch (e) {
    setHealth('worker-health', false);
    setHealth('mt5-health', false);
    setHealth('account-health', false);
    $('worker-text').textContent = 'Unavailable';
    $('mt5-text').textContent = 'Unavailable';
    $('account-text').textContent = 'Unavailable';
    $('system-message').textContent = `Status error: ${e.message}`;
    renderFibSetup(null);
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
    await loadTradeLog();
  } catch (e) {
    mark(`System check failed: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'System Check';
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
    mark('Settings applied');
    setTimeout(async () => {
      await loadSystemStatus();
      await loadTradeLog();
    }, 500);
  } catch (e) {
    mark(`Update failed: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
  }
}

ids.forEach((id) => $(id).addEventListener('change', () => mark('Unsaved changes', 'busy')));
$('sizing_mode').addEventListener('change', updateSizingFields);
$('execution_mode').addEventListener('change', updateExecutionHelp);
$('apply').addEventListener('click', apply);
$('diagnose').addEventListener('click', diagnose);
$('close-diagnostics').addEventListener('click', () => $('diagnostic-card').classList.add('hidden'));
$('clear-trade-log').addEventListener('click', async () => {
  const button = $('clear-trade-log');
  button.disabled = true;
  try {
    const r = await fetch('/api/trade-log/clear', {method:'POST'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    renderTradeLog([]);
  } catch (e) {
    mark(`Could not clear trade log: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
  }
});

async function refreshDashboard() {
  await loadSystemStatus();
  await loadTradeLog();
}

renderTradeLog([]);
loadSettings().then(refreshDashboard);
setInterval(refreshDashboard, 3000);
