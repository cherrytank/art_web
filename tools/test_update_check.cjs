// 檢查版本更新、深層路徑、離線與防刷新循環。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/update-check.js'), 'utf8');
async function run({latest = 'bbbbbbbbbbbbbbbb', query = '', offline = false, editing = false, stored = null} = {}) {
  const state = {replaced: null};
  vm.runInNewContext(source, {
    URL, Date, AbortController, setTimeout: () => 1, clearTimeout() {}, setInterval() {},
    location: {protocol: 'https:', href: `https://example.test/repo/works/item/index.html?category=art${query}#photo`, replace: url => {state.replaced = url;}},
    document: {visibilityState: 'visible', currentScript: {dataset: {siteRoot: '../../'}},
      querySelector: () => ({content: 'aaaaaaaaaaaaaaaa'}), activeElement: {matches: () => editing}, addEventListener() {}},
    window: {addEventListener() {}},
    sessionStorage: {getItem: () => stored, setItem() {}},
    fetch: async (url, options) => {
      state.manifest = url; state.cache = options.cache;
      if (offline) throw Error('離線');
      return {ok: true, json: async () => ({version: latest})};
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  return state;
}
(async () => {
  const changed = await run();
  assert.equal(new URL(changed.manifest).pathname, '/repo/site-version.json');
  assert.equal(changed.cache, 'no-store');
  assert.match(changed.replaced, /category=art&__sitev=bbbbbbbbbbbbbbbb#photo$/);
  for (const options of [{latest:'aaaaaaaaaaaaaaaa'}, {latest:'bad'}, {offline:true}, {editing:true},
    {query:'&__sitev=cccccccccccccccc'}, {stored:String(Date.now())}]) {
    assert.equal((await run(options)).replaced, null);
  }
  console.log('Site update checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
