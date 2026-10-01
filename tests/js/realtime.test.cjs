const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const script = fs.readFileSync(path.resolve(__dirname, '../../static/js/realtime.js'), 'utf8');
function setup() {
  const handlers = {};
  const panel = { dataset: { pollEnabled: 'true' },
    addEventListener(name, fn) { handlers[name] = fn; } };
  const document = { hidden: false, getElementById: () => panel };
  let now = 100000;
  vm.runInNewContext(script, { document, Date: { now: () => now }, Math });
  return { panel, document, handlers, advance(ms) { now += ms; },
    blocked() {
      let prevented = false;
      handlers['htmx:beforeRequest']({ preventDefault() { prevented = true; } });
      return prevented;
    } };
}

test('hidden tabs and missing sites never poll', () => {
  const s = setup();
  assert.equal(s.blocked(), false);
  s.document.hidden = true;
  assert.equal(s.blocked(), true);
  s.document.hidden = false;
  s.panel.dataset.pollEnabled = 'false';
  assert.equal(s.blocked(), true);
});

test('errors back off and successful responses restore normal polling', () => {
  const s = setup();
  s.handlers['htmx:afterRequest']({ detail: { successful: false } });
  s.advance(5000);
  assert.equal(s.blocked(), true);
  s.advance(5000);
  assert.equal(s.blocked(), false);
  s.handlers['htmx:afterRequest']({ detail: { successful: false } });
  s.advance(10000);
  assert.equal(s.blocked(), true);
  s.advance(10000);
  assert.equal(s.blocked(), false);
  s.handlers['htmx:afterRequest']({ detail: { successful: true } });
  assert.equal(s.blocked(), false);
});
