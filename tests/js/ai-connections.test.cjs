const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync('static/js/ai-connections.js', 'utf8');

function fixture() {
  const dom = new JSDOM(`<input id="token" type="password" value="synthetic-secret" data-ai-secret>
    <button data-ai-copy="token">Copy</button><button data-ai-reveal="token">Show</button>
    <p data-ai-copy-status data-success="Copied" data-failure="Select manually"></p>
    <details data-ai-access id="one"></details><details data-ai-access id="two"></details>
    <a data-ai-provider="claude"></a><details id="ai-guide-claude"></details>`,
    { runScripts: 'outside-only', url: 'https://analytics.example.test/settings/ai-connections/' });
  dom.window.eval(script);
  return dom;
}
const tick = () => new Promise(resolve => setTimeout(resolve, 15));

test('clipboard fallback selects text and announces failure without storage', async () => {
  const dom = fixture();
  dom.window.document.querySelector('[data-ai-copy]').click();
  await tick();
  const input = dom.window.document.getElementById('token');
  assert.equal(input.type, 'text');
  assert.equal(input.selectionEnd, input.value.length);
  assert.equal(dom.window.document.querySelector('[role="status"]')?.textContent || dom.window.document.querySelector('[data-ai-copy-status]').textContent, 'Select manually');
  assert.equal(dom.window.localStorage.length, 0);
  dom.window.close();
});

test('successful copy, delegated provider controls and show-once clearing', async () => {
  const dom = fixture();
  let copied;
  Object.defineProperty(dom.window.navigator, 'clipboard', { value: { writeText: async value => { copied = value; } } });
  dom.window.document.querySelector('[data-ai-copy]').click();await tick();
  assert.equal(copied, 'synthetic-secret');
  dom.window.document.querySelector('[data-ai-provider]').click();
  assert.equal(dom.window.document.getElementById('ai-guide-claude').open, true);
  dom.window.dispatchEvent(new dom.window.Event('pagehide'));
  assert.equal(dom.window.document.getElementById('token').value, '');
  dom.window.close();
});

test('at most one permission editor stays open', async () => {
  const dom = fixture();
  dom.window.document.getElementById('one').open = true;await tick();
  dom.window.document.getElementById('two').open = true;await tick();
  assert.equal(dom.window.document.getElementById('one').open, false);
  assert.equal(dom.window.document.getElementById('two').open, true);
  dom.window.close();
});
