const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const panels = fs.readFileSync(path.join(root, 'templates/analytics/_overview_tables.html'), 'utf8');
const base = fs.readFileSync(path.join(root, 'templates/base.html'), 'utf8');
const htmx = fs.readFileSync(path.join(path.dirname(require.resolve('htmx.org')), 'htmx.js'), 'utf8');

function triggerAttributes(id) {
  const tag = panels.match(new RegExp(`<div[^>]*id="${id}"[^>]*>`))[0];
  return ['hx-trigger', 'hx-sync'].map(name => tag.match(new RegExp(`${name}="[^"]+"`))[0]).join(' ');
}

async function waitFor(predicate) {
  const deadline = Date.now() + 3000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error('Timed out waiting for HTMX');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

test('real HTMX queues Channels while Pages loads, then caches both panel results', async (t) => {
  const requests = [];
  let releasePages;
  let active = 0;
  let maxActive = 0;
  const server = http.createServer((req, res) => {
    requests.push(req.url);
    active += 1;
    maxActive = Math.max(maxActive, active);
    res.on('finish', () => { active -= 1; });
    const respond = () => {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`<p>Loaded ${req.url}</p>`);
    };
    if (req.url === '/pages') releasePages = respond;
    else respond();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const dom = new JSDOM(`<main>
    <div data-panel-group><button class="panel-tab" data-panel="pages-tab">Pages</button>
      <div id="pages-tab" class="panel-content hidden" data-lazy-panel hx-get="/pages"
        ${triggerAttributes('pages-tab')}>Loading…</div></div>
    <div data-panel-group><button class="panel-tab" data-panel="channels-tab">Channels</button>
      <div id="channels-tab" class="panel-content hidden" data-lazy-panel hx-get="/channels"
        ${triggerAttributes('channels-tab')}>Loading…</div></div>
    </main>`, {
    url: `http://127.0.0.1:${server.address().port}/`,
    runScripts: 'outside-only',
  });
  t.after(async () => {
    dom.window.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  });
  // jsdom requires an explicit XPath result type; browsers default to ANY_TYPE.
  const evaluate = dom.window.XPathExpression.prototype.evaluate;
  dom.window.XPathExpression.prototype.evaluate = function (node, type, result) {
    return evaluate.call(this, node, type ?? dom.window.XPathResult.ANY_TYPE, result);
  };
  dom.window.eval(htmx);
  for (const [, script] of base.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
    if (script.includes('Panel tabs') || script.includes('htmx:afterRequest')) {
      dom.window.eval(script);
    }
  }
  dom.window.htmx.config.defaultSettleDelay = 0;
  dom.window.htmx.process(dom.window.document.body);
  const document = dom.window.document;
  document.querySelector('[data-panel="pages-tab"]').click();
  await waitFor(() => releasePages);
  document.querySelector('[data-panel="channels-tab"]').click();
  // Repeated selections must not enqueue duplicate work after the first load.
  document.querySelector('[data-panel="channels-tab"]').click();
  document.querySelector('[data-panel="pages-tab"]').click();
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.deepEqual(requests, ['/pages']);
  releasePages();
  await waitFor(() => document.getElementById('channels-tab').dataset.loaded === 'true');
  assert.deepEqual(requests, ['/pages', '/channels']);
  assert.equal(maxActive, 1);
  assert.match(document.getElementById('pages-tab').textContent, /Loaded \/pages/);
  assert.match(document.getElementById('channels-tab').textContent, /Loaded \/channels/);
  document.querySelector('[data-panel="pages-tab"]').click();
  document.querySelector('[data-panel="channels-tab"]').click();
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.deepEqual(requests, ['/pages', '/channels']);
});
