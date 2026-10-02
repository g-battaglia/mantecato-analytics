const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync('static/js/ai-connections.js', 'utf8');

function fixture() {
  const dom = new JSDOM(`<section id="ai-content"><input id="token" type="password" value="synthetic-secret" data-ai-secret>
    <button data-ai-copy="token">Copy</button><button data-ai-reveal="token">Show</button>
    <p data-ai-copy-status data-success="Copied" data-failure="Select manually"></p>
    <details data-ai-access id="one"></details><details data-ai-access id="two"></details>
    <a data-ai-provider="claude" href="#ai-guide-claude" aria-current="true"></a>
    <a data-ai-provider="chatgpt" href="#ai-guide-chatgpt"></a>
    <details id="ai-guide-claude" data-ai-guide="claude" open></details>
    <details id="ai-guide-chatgpt" data-ai-guide="chatgpt"></details>
    <details data-ai-method id="token-method"></details><details data-ai-method id="agent-method"></details>
    </section>`,
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
  assert.equal(dom.window.document.getElementById('token').defaultValue, '');
  assert.equal(dom.window.document.getElementById('token').hasAttribute('value'), false);
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

test('one provider guide is shown with mouse and keyboard selection', async () => {
  const dom = fixture();await tick();
  const doc = dom.window.document;
  const claude = doc.getElementById('ai-guide-claude');
  const chatgpt = doc.getElementById('ai-guide-chatgpt');
  assert.equal(claude.hidden, false);
  assert.equal(chatgpt.hidden, true);
  const choice = doc.querySelector('[data-ai-provider="chatgpt"]');
  choice.click();
  assert.equal(choice.getAttribute('aria-current'), 'true');
  assert.equal(claude.hidden, true);
  assert.equal(chatgpt.open, true);
  choice.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}));
  assert.equal(doc.activeElement.dataset.aiProvider, 'claude');
  assert.equal(claude.hidden, false);
  assert.equal(chatgpt.hidden, true);
  assert.equal(dom.window.location.hash, '');
  dom.window.close();
});

test('provider enhancement initializes again after an HTMX replacement', async () => {
  const dom = fixture();await tick();
  const doc = dom.window.document;
  doc.getElementById('ai-content').outerHTML = `<section id="ai-content">
    <a data-ai-provider="grok" href="#ai-guide-grok" aria-current="true"></a>
    <details id="ai-guide-grok" data-ai-guide="grok"></details>
  </section>`;
  doc.dispatchEvent(new dom.window.Event('htmx:afterSwap'));
  assert.equal(doc.getElementById('ai-guide-grok').open, true);
  assert.equal(doc.getElementById('ai-content').dataset.aiEnhanced, 'true');
  dom.window.close();
});

test('alternative setup methods open independently from permission editors', async () => {
  const dom = fixture();await tick();
  const doc = dom.window.document;
  doc.getElementById('one').open = true;
  doc.getElementById('token-method').open = true;await tick();
  doc.getElementById('agent-method').open = true;await tick();
  assert.equal(doc.getElementById('token-method').open, false);
  assert.equal(doc.getElementById('agent-method').open, true);
  assert.equal(doc.getElementById('one').open, true);
  dom.window.close();
});
