// 保留圖片快取；只檢查小型版本清單，舊頁面最多自動更新一次。
(() => {
  const script = document.currentScript;
  const version = document.querySelector('meta[name="site-build"]')?.content;
  if (!script || !/^[a-f0-9]{16}$/.test(version || '') || !/^https?:$/.test(location.protocol)) return;
  const manifest = new URL(`${script.dataset.siteRoot}site-version.json`, location.href);
  let checking = false;
  let lastCheck = 0;
  async function checkVersion() {
    if (document.visibilityState === 'hidden' || checking || Date.now() - lastCheck < 60000) return;
    checking = true;
    lastCheck = Date.now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      // 每次使用新網址及 no-store，避免版本清單本身留在瀏覽器／CDN 快取。
      manifest.searchParams.set('check', String(Date.now()));
      const response = await fetch(manifest.href, {cache: 'no-store', signal: controller.signal});
      if (!response.ok) return;
      const latest = (await response.json()).version;
      if (!/^[a-f0-9]{16}$/.test(latest || '') || latest === version) return;
      const target = new URL(location.href);
      // 即使儲存空間不可用或部署節點尚未同步，也不能無限重新整理。
      if (target.searchParams.has('__sitev')) return;
      // 避免使用者正在填寫搜尋欄位時被打斷。
      if (document.activeElement?.matches('input, textarea, select, [contenteditable="true"]')) return;
      const key = `site-update:${manifest.pathname}:${target.pathname}`;
      try {
        const previous = Number(sessionStorage.getItem(key) || 0);
        if (Date.now() - previous < 1800000) return;
        sessionStorage.setItem(key, String(Date.now()));
      } catch { /* 隱私模式改用網址參數防止循環。 */ }
      target.searchParams.set('__sitev', latest);
      location.replace(target.href);
    } catch { /* 離線、逾時或部署中暫時失敗時，保留目前可用頁面。 */ }
    finally { clearTimeout(timeout); checking = false; }
  }
  checkVersion();
  window.addEventListener('pageshow', checkVersion);
  document.addEventListener('visibilitychange', checkVersion);
  setInterval(checkVersion, 60000);
})();
