# 沈東榮油畫藝術家網站

依照 `網站模板風格架構ppt.pptx` 製作的純靜態響應式網站。網站不使用資料庫或後端；文章與作品由 JSON 管理，再由 Python 產生固定格式的 HTML，可直接部署到 GitHub Pages。

## 最簡單的操作方式：內容管理視窗

第一次使用先安裝圖片處理套件：

```powershell
python -m pip install -r requirements.txt
```

之後直接用 Python 開啟管理介面：

```powershell
python tools/content_manager.py
```

管理介面有三個分頁：

- **新增作品**：填寫作品編號、名稱、年份、媒材與尺寸；主圖及多張局部圖都可用按鈕選擇，作品說明可稍後再補。
- **新增文章**：填寫標題、分類、摘要與正文；段落之間空一行即可。
- **網站維護**：重新最佳化全部圖片、產生網站、開啟本機預覽，或打開資料夾。

按下「儲存並更新網站」後，程式會自動複製原圖、產生手機與桌面圖片、建立固定格式資料，並更新列表與詳細頁。使用者不需要接觸 HTML。

## 本機預覽

需要 Python 3.10 以上，並先安裝 `requirements.txt` 內的套件。

```powershell
python tools/serve.py
```

瀏覽器開啟 `http://127.0.0.1:8000/`。停止預覽請按 `Ctrl+C`。

重新最佳化全部圖片並重建 HTML：

```powershell
python tools/build_site.py
```

輸出會放在 `dist/`。請勿直接修改 `dist/`，下次建置會重新產生。

## 新增作品

互動式輸入最簡單：

```powershell
python tools/add_content.py work
```

程式會詢問網址代稱、作品編號、名稱、年份、主圖、局部圖、媒材、尺寸與說明，完成後建立 `content/works/<slug>.json`，並自動重建作品列表與詳細頁。多張局部圖請用 `|` 分隔；也可重複使用 `--gallery` 參數。

圖片可以輸入完整路徑，程式會複製到 `static/assets/images/`；也可以先自行將圖片放入該資料夾，再輸入檔名。支援 WebP、JPG、PNG 與 AVIF，原圖可以保留較高解析度，建置流程會自動產生適合網站傳輸的版本。

## 圖片最佳化流程

不論使用 GUI、`add_content.py`、`build_site.py` 或 GitHub Pages 部署，都會執行同一套流程：

- 為每張圖片產生最接近 `480`、`800`、`1200`、`1800` 像素的 WebP 版本，不會放大原圖，也不會把超過網站顯示需求的 4K 原圖送到瀏覽器。
- HTML 自動加入 `srcset`、`sizes`、`width`、`height` 與非同步解碼設定。
- 首屏主圖優先下載；列表、文章列與頁面下方圖片延遲下載。
- 社群分享圖使用約 1200px 的壓縮版本，不再直接傳送大型 PNG。
- 原圖保留在 `static/assets/images/`，部署內容只使用 `dist/assets/images/responsive/` 的壓縮版本，請勿手動編輯 `dist/`。

若只想從命令列執行完整圖片最佳化與建置，也可以使用：

```powershell
python tools/add_content.py build
```

## 新增文章

```powershell
python tools/add_content.py article
```

文章分類固定為：

- `art-criticism`：藝術評論
- `painting-notes`：創作筆記
- `artwork-story`：作品故事

多個正文段落可在互動輸入時用 `|` 分隔。也可用參數一次建立：

```powershell
python tools/add_content.py article `
  --slug spring-light `
  --title "春日的光" `
  --date 2026-09-01 `
  --category painting-notes `
  --image "D:\photos\spring-light.jpg" `
  --image-alt "春日山林油畫" `
  --summary "記錄春日光線進入畫面的過程。" `
  --paragraph "我從一層薄薄的暖灰開始。" `
  --paragraph "等待顏料乾燥後，再加入遠方的光。"
```

文章 JSON 的 `body` 支援四種固定區塊：`lead`、`paragraph`、`heading`、`quote`。可參考 `content/articles/` 內的現有範例。

## 修改網站內容

- 個人基本資料：`content/site.json`
- 學經歷與創作理念：`content/about.json`
- 展覽紀錄：`content/exhibitions.json`
- 課程：`content/classes.json`
- 聯絡方式：`content/contact.json`
- 文章：`content/articles/*.json`
- 作品：`content/works/*.json`
- 共用版型：`templates/*.html`
- 視覺樣式：`static/css/styles.css`
- 行動選單與篩選：`static/js/site.js`

目前已依 `3_作品works/2026作品集.pptx` 收錄 20 件 2026 作品；`山行` 與 `荷塘春色` 的局部圖會在詳細頁形成可觸控左右滑動的圖庫。未提供的英文題名與作品文案保持留白，可日後透過管理視窗補入。

## GitHub Pages 部署

專案已包含 `.github/workflows/pages.yml`。推送到 `main` 後，GitHub Actions 會安裝 Pillow、自動最佳化圖片、執行 Python 建置、產生正確的社群分享網址，並部署 `dist/`。

1. 在 GitHub 建立空白 repository。
2. 在本資料夾執行：

```powershell
git init
git add .
git commit -m "Create artist portfolio site"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPOSITORY.git
git push -u origin main
```

3. 到 repository 的 **Settings → Pages**，將 **Source** 設為 **GitHub Actions**。
4. 等候 Actions 完成後即可取得公開網址。之後每次推送到 `main` 都會自動更新。

## 驗證

```powershell
python tools/validate_site.py
```

此指令會重新最佳化圖片並重建網站，檢查所有內部連結、響應式圖片、圖片尺寸、頁面標題、主標題與圖片替代文字。

## 動畫與無障礙

網站包含首頁分段進場、內頁捲動浮現、作品卡片、文章列、按鈕箭頭與手機選單動畫。手機版使用較短的動畫時間，減少等待感；若訪客在作業系統開啟「減少動態效果」，網站會自動停用動畫。
