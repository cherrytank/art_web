// Unit-level navigation checks; no browser or third-party packages required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/site.js'), 'utf8');
const navigation = source.slice(source.indexOf('function readVisit('), source.indexOf("document.querySelectorAll('[data-gallery]')"));

function environment(path, hash = '', saved = {}) {
  const state = { storage: new Map(Object.entries(saved)), scrolled: false, category: '', filtered: false };
  const card = { id: 'work-026012' };
  const link = { href: 'https://example.test/works/work-026012/index.html', closest: () => card, addEventListener: (_, callback) => { state.click = callback; } };
  const back = { href: '../index.html', textContent: '返回作品列表' };
  const row = { matches: () => true, scrollIntoView: () => { state.scrolled = true; } };
  const context = {
    URL, location: { origin: 'https://example.test', pathname: path, search: '', hash },
    sessionStorage: {getItem: key => state.storage.get(key), setItem: (key, value) => state.storage.set(key, value)},
    document: {
      querySelectorAll: () => [link],
      querySelector: selector => selector === '[data-return-link]' ? back : { dataset: { articleFilter: 'art-criticism' } },
      getElementById: () => row,
    },
    workSearch: { value: '玉山' }, workYear: { value: '2026' },
    filterWorks: () => { state.filtered = true; },
    articleFilters: [{ dataset: { articleFilter: 'art-criticism' }, click: () => {state.category = 'art-criticism';} }],
    requestAnimationFrame: callback => callback(),
    window: { addEventListener: (_, callback) => {state.restore = callback;} },
  };
  vm.runInNewContext(navigation, context);
  return { state, context, back };
}

const exhibitionPath = '/exhibitions/verdant-emergence-2026/index.html';
const from = environment(exhibitionPath);
from.state.click();
const stored = Object.fromEntries(from.state.storage);
const detail = environment('/works/work-026012/index.html', '', stored);
assert.equal(detail.back.href, `https://example.test${exhibitionPath}#work-026012`);
assert.equal(detail.back.textContent, '← 返回展出作品');
const returned = environment(exhibitionPath, '#work-026012', stored);
returned.state.restore();
assert.equal(returned.state.scrolled, true);
assert.equal(returned.context.workSearch.value, '玉山');
assert.equal(returned.context.workYear.value, '2026');
assert.equal(returned.state.category, 'art-criticism');
const direct = environment('/works/work-026012/index.html');
assert.equal(direct.back.href, '../index.html');
const external = environment('/works/work-026012/index.html', '', {
  'return:/works/work-026012/index.html': JSON.stringify({url: 'https://other.test/works/index.html'}),
});
assert.equal(external.back.href, '../index.html');
console.log('Navigation checks passed: source, anchor, filters, direct-entry fallback, same-origin restriction.');
