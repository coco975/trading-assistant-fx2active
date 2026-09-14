const ids = [
  'trading_enabled','fib_enabled','fib_retracement','stop_buffer_pips','take_profit_mode',
  'entry_trigger','max_open_positions','support_resistance','previous_swing','trendline',
  'psychological_level','candle_confirmation','min_confirmations'
];

const $ = (id) => document.getElementById(id);
const status = $('status');
const dot = $('status-dot');

function mark(message, kind='ok') {
  status.textContent = message;
  dot.dataset.kind = kind;
}

function setForm(s) {
  $('trading_enabled').checked = s.trading_enabled;
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

async function load() {
  try {
    const r = await fetch('/api/settings', {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    setForm(await r.json());
    mark('Settings loaded from bot runtime');
  } catch (e) {
    mark(`Could not load settings: ${e.message}`, 'error');
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
    mark('Bot settings updated — worker will use these rules on the next evaluation');
  } catch (e) {
    mark(`Update failed: ${e.message}`, 'error');
  } finally {
    button.disabled = false;
  }
}

ids.forEach((id) => $(id).addEventListener('change', () => mark('Unsaved changes', 'busy')));
$('apply').addEventListener('click', apply);
load();
