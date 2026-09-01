# 沈東榮油畫藝術家網站

依照 `網站模板風格架構ppt.pptx` 製作的純靜態響應式網站。網站不使用資料庫或後端；文章與作品由 JSON 管理，再由 Python 產生固定格式的 HTML，可直接部署到 GitHub Pages。

## 本機預覽

需要 Python 3.10 以上，不需安裝第三方套件。

```powershell
python tools/serve.py
```

瀏覽器開啟 `http://127.0.0.1:8000/`。停止預覽請按 `Ctrl+C`。

只重建 HTML：

```powershell
python tools/build_site.py
```

輸出會放在 `dist/`。請勿直接修改 `dist/`，下次建置會重新產生。

## 新增作品

互動式輸入最簡單：

```powershell
python tools/add_content.py work
```

程式會詢問網址代稱、作品名稱、年份、圖片、媒材、尺寸與說明，完成後建立 `content/works/<slug>.json`，並自動重建作品列表與詳細頁。

圖片可以輸入完整路徑，程式會複製到 `static/assets/images/`；也可以先自行將圖片放入該資料夾，再輸入檔名。建議使用 `.webp` 或經過壓縮的 `.jpg`。

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

目前原始的 `作品_文字檔.docx` 是 0 bytes 空檔，因此網站中的四件作品先依簡報所含圖片與可辨識欄位建立；其中標示「尺寸待補」的資料請在正式上線前更新。

## GitHub Pages 部署

專案已包含 `.github/workflows/pages.yml`。推送到 `main` 後，GitHub Actions 會執行 Python 建置、產生正確的社群分享網址，並部署 `dist/`。

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

此指令會重建網站，檢查所有內部連結、圖片、頁面標題、主標題與圖片替代文字。
