// 直接測試正式分類程式，確認每個下拉選單網址都能篩選正確內容。
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../static/js/site.js'), 'utf8');
const code = script.slice(script.indexOf('const articleFilters'), script.indexOf('const prefersReducedMotion'));
const categories = ['all', 'art-criticism', 'painting-notes', 'artwork-story', 'publications'];
for (const category of categories.slice(1)) {
  const buttons = categories.map(value => ({dataset: {articleFilter: value}, classList: {toggle() {}}, addEventListener(_, fn) {this.click = fn;}}));
  const rows = categories.slice(1).map(value => ({dataset: {category: value}, hidden: false}));
  vm.runInNewContext(code, {URLSearchParams, location: {search: `?category=${category}`}, document: {querySelectorAll: selector => selector === '[data-article-filter]' ? buttons : rows}});
  assert.deepEqual(rows.filter(row => !row.hidden).map(row => row.dataset.category), [category]);
}
console.log('Dropdown category checks passed.');
