/* Bounded server admission needs an explicit, accessible fragment retry state.
 * Requests are queued by HTMX on the page; no polling timers or result cache.
 */
(function () {
  'use strict';

  function loader(event) {
    var element = event.detail && event.detail.elt;
    return element && element.matches('[data-analytics-fragment]') ? element : null;
  }

  document.addEventListener('htmx:beforeRequest', function (event) {
    var element = loader(event);
    if (!element) return;
    var status = element.querySelector('[data-analytics-status]');
    var retry = element.querySelector('[data-analytics-retry]');
    element.setAttribute('aria-busy', 'true');
    if (status) status.textContent = status.dataset.loading;
    if (retry) { retry.hidden = true; retry.disabled = true; }
  });

  document.addEventListener('htmx:afterRequest', function (event) {
    var element = loader(event);
    if (!element) return;
    element.setAttribute('aria-busy', 'false');
    if (event.detail.successful) return;
    // HTMX keeps the original skeleton on 503, timeout and network errors.
    // Never leave it saying "Loading" forever, and never auto-retry in a loop.
    var status = element.querySelector('[data-analytics-status]');
    var retry = element.querySelector('[data-analytics-retry]');
    if (status) status.textContent = status.dataset.error;
    if (retry) { retry.hidden = false; retry.disabled = false; }
  });

  document.addEventListener('click', function (event) {
    var retry = event.target.closest('[data-analytics-retry]');
    if (!retry || retry.disabled || !window.htmx) return;
    var element = retry.closest('[data-analytics-fragment]');
    if (!element) return;
    retry.disabled = true;
    window.htmx.trigger(element, 'analyticsretry');
  });
})();
