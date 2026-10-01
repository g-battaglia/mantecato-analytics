/* Keep HTMX realtime inexpensive: hidden tabs pause, sync drops overlaps,
 * and failed requests back off without starting extra timers/listeners. */
(function () {
  "use strict";
  var panel = document.getElementById("realtime-content");
  if (!panel) return;
  var failures = 0;
  var retryAt = 0;
  panel.addEventListener("htmx:beforeRequest", function (event) {
    if (document.hidden || panel.dataset.pollEnabled !== "true" || Date.now() < retryAt) {
      event.preventDefault();
    }
  });
  panel.addEventListener("htmx:afterRequest", function (event) {
    if (event.detail.successful) {
      failures = 0;
      retryAt = 0;
    } else {
      failures = Math.min(failures + 1, 4);
      retryAt = Date.now() + 5000 * Math.pow(2, failures);
    }
  });
})();
