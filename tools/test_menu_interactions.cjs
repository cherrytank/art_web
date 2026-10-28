// 驗證跨選單焦點事件不會關閉新選單，且手機導覽不攔截連結。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/site.js'), 'utf8');
function element() {
  return { events: {}, attrs: {}, classList: { remove() {}, contains() { return true; }, toggle() {} },
    addEventListener(name, fn) { this.events[name] = fn; },
    setAttribute(name, value) { this.attrs[name] = value; },
    getAttribute(name) { return this.attrs[name]; } };
}
const menu = element(), nav = element();
const groups = Array.from({length: 3}, () => {
  const link = element(), submenu = {hidden: true};
  return Object.assign(element(), {link, submenu,
    contains(target) { return target === link; },
    querySelector(selector) { return selector === '.submenu-toggle' ? link : submenu; }});
});
const timers = new Map();
let timerId = 0;
const runTimers = () => { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); };
const windowMock = {innerWidth:1440, events:{}, matchMedia: () => ({matches:false, addEventListener() {}}), addEventListener(name, fn) { this.events[name] = fn; }};
vm.runInNewContext(source.slice(0, source.indexOf('const workSearch =')), {
  window: windowMock,
  setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
  clearTimeout: id => timers.delete(id),
  document: {activeElement:null, querySelector:s => s === '.menu-toggle' ? menu : nav,
    querySelectorAll: () => groups, addEventListener() {}}
});
groups[0].link.events.focus();
groups[1].events.pointerenter({pointerType:'mouse'});
groups[0].events.focusout({relatedTarget:groups[1].link});
runTimers();
assert.equal(groups[1].submenu.hidden, false);
// 滑鼠仍在下拉項目上，即使瀏覽器回報空焦點也不能隱藏連結。
groups[1].events.focusout({relatedTarget:null});
runTimers();
assert.equal(groups[1].submenu.hidden, false);
windowMock.events.resize();
assert.equal(groups[1].submenu.hidden, false);
// 短暫離開後移回，應取消關閉；真正離開後才收起。
groups[1].events.pointerleave({pointerType:'mouse'});
assert.equal(groups[1].submenu.hidden, false);
groups[1].events.pointerenter({pointerType:'mouse'});
runTimers();
assert.equal(groups[1].submenu.hidden, false);
groups[1].events.pointerleave({pointerType:'mouse'});
runTimers();
assert.equal(groups[1].submenu.hidden, true);
assert.equal(groups[1].link.events.click, undefined);
nav.events.click({target:{closest:() => groups[1].link}});
assert.equal(menu.attrs['aria-expanded'], 'false');
console.log('Navigation interaction regression checks passed.');
