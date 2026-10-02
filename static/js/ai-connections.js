/* Progressive, delegated controls; credentials never enter browser storage. */
(function () {
  'use strict';
  var copyTimer;
  function selectProvider(panel, id) {
    var guides = panel.querySelectorAll('[data-ai-guide]');
    var selected = panel.querySelector('[data-ai-guide="' + id + '"]');
    if (!selected) return;
    panel.dataset.aiEnhanced = 'true';
    panel.querySelectorAll('[data-ai-provider]').forEach(function (item) {
      if (item.dataset.aiProvider === id) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    });
    guides.forEach(function (guide) {
      guide.hidden = guide !== selected;
      guide.open = guide === selected;
    });
  }
  function enhance() {
    var panel = document.getElementById('ai-content');
    if (!panel || panel.dataset.aiEnhanced) return;
    var first = panel.querySelector('[data-ai-provider][aria-current]') || panel.querySelector('[data-ai-provider]');
    if (first) selectProvider(panel, first.dataset.aiProvider);
  }
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
      clearTimeout(copyTimer);
      copyTimer = setTimeout(function () { if (status) status.textContent = ''; }, 5000);
      return;
    }
    var reveal = event.target.closest('[data-ai-reveal]');
    if (reveal) {
      var secret = document.getElementById(reveal.dataset.aiReveal);
      if (secret) secret.type = secret.type === 'password' ? 'text' : 'password';
      return;
    }
    var provider = event.target.closest('[data-ai-provider]');
    if (provider) {
      var panel = provider.closest('#ai-content');
      if (panel) { event.preventDefault(); selectProvider(panel, provider.dataset.aiProvider); }
    }
  });
  document.addEventListener('keydown', function (event) {
    var provider = event.target.closest('[data-ai-provider]');
    if (!provider || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    var panel = provider.closest('#ai-content');
    if (!panel) return;
    var items = Array.from(panel.querySelectorAll('[data-ai-provider]'));
    var index = items.indexOf(provider);
    if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = items.length - 1;
    else index = (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    event.preventDefault();
    selectProvider(panel, items[index].dataset.aiProvider);
    items[index].focus();
  });
  document.addEventListener('toggle', function (event) {
    var current = event.target;
    if (!current.matches || !current.open) return;
    var selector = current.matches('[data-ai-access]') ? '[data-ai-access]' : current.matches('[data-ai-method]') ? '[data-ai-method]' : null;
    if (selector) document.querySelectorAll(selector).forEach(function (other) { if (other !== current) other.open = false; });
  }, true);
  function clearSecrets() {
    document.querySelectorAll('[data-ai-secret]').forEach(function (input) {
      input.value = ''; input.defaultValue = ''; input.removeAttribute('value'); input.type = 'password';
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance);
  else enhance();
  document.addEventListener('htmx:afterSwap', enhance);
  window.addEventListener('pagehide', clearSecrets);
  window.addEventListener('pageshow', function (event) { if (event.persisted) clearSecrets(); });
  document.addEventListener('htmx:beforeHistorySave', clearSecrets);
})();
