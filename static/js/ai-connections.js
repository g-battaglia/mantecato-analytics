/* Delegated controls survive HTMX swaps; credentials never enter storage. */
(function () {
  'use strict';
  document.addEventListener('click', async function (event) {
    var copy = event.target.closest('[data-ai-copy]');
    if (copy) {
      var input = document.getElementById(copy.dataset.aiCopy);
      var status = document.querySelector('[data-ai-copy-status]');
      if (!input || copy.disabled) return;
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(input.value);
        if (status) status.textContent = status.dataset.success;
      } catch (_) {
        if (input.type === 'password') input.type = 'text';
        input.focus(); input.select();
        if (status) status.textContent = status.dataset.failure;
      }
    }
    var reveal = event.target.closest('[data-ai-reveal]');
    if (reveal) {
      var secret = document.getElementById(reveal.dataset.aiReveal);
      if (secret) secret.type = secret.type === 'password' ? 'text' : 'password';
    }
    var provider = event.target.closest('[data-ai-provider]');
    if (provider) {
      var guide = document.getElementById('ai-guide-' + provider.dataset.aiProvider);
      if (guide) guide.open = true;
    }
  });
  document.addEventListener('toggle', function (event) {
    var current = event.target;
    if (current.matches && current.matches('[data-ai-access]') && current.open) {
      document.querySelectorAll('[data-ai-access]').forEach(function (other) {
        if (other !== current) other.open = false;
      });
    }
  }, true);
  function clearSecrets() {
    document.querySelectorAll('[data-ai-secret]').forEach(function (input) {
      input.value = ''; input.removeAttribute('value'); input.defaultValue = ''; input.type = 'password';
    });
  }
  window.addEventListener('pagehide', clearSecrets);
  window.addEventListener('pageshow', function (event) { if (event.persisted) clearSecrets(); });
  document.addEventListener('htmx:beforeHistorySave', clearSecrets);
})();
