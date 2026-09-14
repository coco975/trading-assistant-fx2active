const form = document.getElementById('login-form');
const pinInput = document.getElementById('pin');
const message = document.getElementById('login-message');

async function checkSession() {
  try {
    const response = await fetch('/api/auth/status', { cache: 'no-store' });
    if (!response.ok) return;
    const status = await response.json();
    if (!status.required || status.authenticated) {
      window.location.replace('/');
    }
  } catch (_) {
    // The form remains usable if the status probe fails.
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = 'Checking PIN…';

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pinInput.value.trim() }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      message.textContent = payload.error || 'Could not sign in.';
      pinInput.select();
      return;
    }
    window.location.replace('/');
  } catch (_) {
    message.textContent = 'Could not reach FX2Active. Check that the trading computer is still running.';
  }
});

checkSession();
