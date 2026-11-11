/* Exercise the actual builder, not a standalone imitation of its queue. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync('static/js/dashboard_builder.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function fixture(count = 8) {
  const widgets = Array.from({length: count}, (_, i) => ({id: `w${i}`, type: 'kpi', metric: 'pageviews'}));
  const config = {dateRange: '30d', filters: [], widgets};
  const dom = new JSDOM(`<div id="builder-root" data-preview-url="/dashboards/example/preview-widget/">
    <div class="grid-stack"></div><div id="empty-hint"></div>
    <div id="cfg-drawer"></div><div id="cfg-overlay"></div><div id="cfg-filters"></div>
    <div id="b-dash-filters"></div><div id="advanced-panel"></div><div id="json-error"></div>
    <select id="b-dateRange"><option>30d</option><option>7d</option><option>24h</option></select>
    <textarea id="b-json"></textarea>
    <form id="builder-form"><input name="csrfmiddlewaretoken" value="synthetic-csrf"></form>
    <script id="dash-config" type="application/json">${JSON.stringify(config)}</script>
    </div>`, {runScripts: 'outside-only'});
  const {window} = dom;
  const doc = window.document;
  for (const id of ['cfg-type', 'cfg-source', 'cfg-close', 'cfg-add-filter', 'cfg-apply',
    'btn-add-widget', 'btn-advanced', 'btn-json-apply', 'btn-save', 'b-name', 'f-name',
    'f-description', 'f-config']) {
    const element = doc.createElement('input');
    element.id = id;
    doc.body.appendChild(element);
  }
  const grid = doc.querySelector('.grid-stack');
  window.GridStack = {init: () => ({
    addWidget: options => {
      const element = doc.createElement('div');
      element.className = 'grid-stack-item';
      element.innerHTML = options.content;
      grid.appendChild(element);
      return element;
    },
    save: () => [], on: () => {}, removeWidget: element => element.remove(),
    removeAll: () => grid.replaceChildren(),
  })};
  const calls = [];
  let active = 0;
  let peakActive = 0;
  window.fetch = (url, options) => {
    active += 1;
    peakActive = Math.max(peakActive, active);
    return new Promise(resolve => {
      calls.push({url, options, body: JSON.parse(options.body), respond: (html = 'fresh', status = 200) => {
        active -= 1;
        resolve({ok: status === 200, redirected: false, text: async () => html});
      }});
    });
  };
  window.eval(script);
  const host = id => doc.querySelector(`[data-wid="${id}"] .wpreview`);
  const changeRange = range => {
    const select = doc.getElementById('b-dateRange');
    select.value = range;
    select.dispatchEvent(new window.Event('change'));
  };
  async function finish() {
    // Each completed body should release exactly one successor, never a burst.
    for (let i = 0; i < calls.length; i += 1) {
      calls[i].respond();
      await tick();
    }
  }
  return {dom, doc, calls, host, changeRange, finish, peak: () => peakActive};
}

test('eight initial widget previews run serially and all finish without admission overload', async () => {
  const f = fixture();
  try {
    assert.equal(f.calls.length, 1);
    await f.finish();
    assert.equal(f.calls.length, 8);
    assert.equal(f.peak(), 1);
    assert.deepEqual(f.calls.map(call => call.body.widget.id), Array.from({length: 8}, (_, i) => `w${i}`));
    for (let i = 0; i < 8; i += 1) assert.equal(f.host(`w${i}`).textContent, 'fresh');
  } finally { f.dom.window.close(); }
});

test('rapid period/filter changes coalesce pending previews and suppress the stale in-flight response', async () => {
  const f = fixture();
  try {
    for (let i = 0; i < 100; i += 1) f.changeRange(i % 2 ? '7d' : '24h');
    f.dom.window.prompt = () => 'country:eq:IT';
    f.doc.querySelector('#b-dash-filters button').click();
    assert.equal(f.calls.length, 1);
    f.calls[0].respond('stale response');
    await tick();
    assert.equal(f.host('w0').textContent.includes('stale response'), false);
    // Finish only the remaining calls; the first one was already completed.
    for (let i = 1; i < f.calls.length; i += 1) {
      assert.equal(f.calls[i].body.dashboardDateRange, '7d');
      assert.deepEqual(f.calls[i].body.dashboardFilters, ['country:eq:IT']);
      f.calls[i].respond('latest period');
      await tick();
    }
    assert.equal(f.calls.length, 9); // One old active + one newest job per widget.
    assert.equal(f.peak(), 1);
    for (let i = 0; i < 8; i += 1) assert.equal(f.host(`w${i}`).textContent, 'latest period');
  } finally { f.dom.window.close(); }
});

test('a failed preview does not poison the queue and can be retried explicitly', async () => {
  const f = fixture(2);
  try {
    f.calls[0].respond('', 503);
    await tick();
    assert.match(f.host('w0').textContent, /Preview failed/);
    assert.equal(f.calls.length, 2);
    const retry = f.host('w0').querySelector('[data-act="retry"]');
    retry.click(); retry.click();
    assert.equal(f.calls.length, 2);
    f.calls[1].respond();
    await tick();
    assert.equal(f.calls.length, 3);
    assert.equal(f.calls[2].body.widget.id, 'w0');
    f.calls[2].respond('retried');
    await tick();
    assert.equal(f.host('w0').textContent, 'retried');
    assert.equal(f.peak(), 1);
  } finally { f.dom.window.close(); }
});

test('deleting a queued widget prevents its fetch and deleting the active widget prevents stale rendering', async () => {
  const f = fixture();
  try {
    f.doc.querySelector('[data-wid="w0"] [data-act="del"]').click();
    f.doc.querySelector('[data-wid="w3"] [data-act="del"]').click();
    await f.finish();
    assert.equal(f.calls.length, 7);
    assert.equal(f.calls.some(call => call.body.widget.id === 'w3'), false);
    assert.equal(f.host('w0'), null);
    assert.equal(f.peak(), 1);
  } finally { f.dom.window.close(); }
});

test('replacing configuration clears pending work even when widget IDs are reused', async () => {
  const f = fixture();
  try {
    f.doc.getElementById('b-json').value = JSON.stringify({dateRange: '7d', filters: [],
      widgets: [{id: 'w0', type: 'kpi', metric: 'visits'}]});
    f.doc.getElementById('btn-json-apply').click();
    f.calls[0].respond('old config');
    await tick();
    assert.equal(f.host('w0').textContent.includes('old config'), false);
    assert.equal(f.calls.length, 2);
    assert.equal(f.calls[1].body.widget.metric, 'visits');
    f.calls[1].respond('new config');
    await tick();
    assert.equal(f.host('w0').textContent, 'new config');
    assert.equal(f.peak(), 1);
  } finally { f.dom.window.close(); }
});
