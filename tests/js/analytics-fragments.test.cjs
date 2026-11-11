const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync('static/js/analytics-fragments.js', 'utf8');

function fixture(attribute = 'data-analytics-fragment') {
  const dom = new JSDOM(`<div id="widget" ${attribute}>
    <span data-analytics-status data-loading="Loading" data-error="Try again" role="status">Loading</span>
    <button data-analytics-retry hidden><span>Retry</span></button></div><div id="other"></div>`,
    {runScripts: 'outside-only'});
  const calls = [];
  dom.window.htmx = {trigger: (element, event) => calls.push([element.id, event])};
  dom.window.eval(script);
  const document = dom.window.document;
  const widget = document.getElementById('widget');
  const button = widget.querySelector('button');
  const status = widget.querySelector('[role="status"]');
  const emit = (name, successful, elt = widget) => document.dispatchEvent(
    new dom.window.CustomEvent(name, {detail: {elt, successful}}));
  return {dom, widget, button, status, calls, emit};
}

for (const attribute of ['data-analytics-fragment', 'data-lazy-panel']) {
 test(`${attribute} exposes manual retry instead of an endless spinner`, () => {
  const {dom, widget, button, status, calls, emit} = fixture(attribute);
  emit('htmx:beforeRequest');
  assert.equal(widget.getAttribute('aria-busy'), 'true');
  emit('htmx:afterRequest', false);
  assert.equal(status.textContent, 'Try again');
  assert.equal(button.hidden, false);
  assert.equal(widget.getAttribute('aria-busy'), 'false');
  button.querySelector('span').click();
  button.querySelector('span').click();
  assert.deepEqual(calls, [['widget', 'analyticsretry']]);
  emit('htmx:beforeRequest');
  assert.equal(status.textContent, 'Loading');
  assert.equal(button.hidden, true);
  emit('htmx:afterRequest', true);
  assert.equal(widget.getAttribute('aria-busy'), 'false');
  assert.equal(button.hidden, true);
  dom.window.close();
 });
}

test('unrelated requests never alter a widget or allocate retry timers', () => {
  const {dom, widget, button, emit} = fixture();
  const other = dom.window.document.getElementById('other');
  emit('htmx:afterRequest', false, other);
  assert.equal(button.hidden, true);
  assert.equal(widget.hasAttribute('aria-busy'), false);
  dom.window.close();
});
