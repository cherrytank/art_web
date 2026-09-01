"""Friendly local desktop UI for adding works and articles.

The application uses Tkinter from Python's standard library. It writes the
same JSON records as ``add_content.py``, rebuilds the static site, and can run a
local preview server. No web backend or database is involved.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import webbrowser
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, font, messagebox
from tkinter import ttk

import add_content
import build_site


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_IMAGES = {".webp", ".jpg", ".jpeg", ".png", ".gif", ".avif"}
CATEGORY_LABELS = {
    "創作筆記": "painting-notes",
    "藝術評論": "art-criticism",
    "作品故事": "artwork-story",
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class ScrollableForm(ttk.Frame):
    """A responsive vertically scrollable frame for long forms."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self.canvas = __import__("tkinter").Canvas(
            self,
            background="#f6f2eb",
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, padding=(30, 24, 36, 34))
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.body.columnconfigure(1, weight=1)
        self.body.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._fit_width)
        self.canvas.bind("<Enter>", lambda _event: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _event: self.canvas.unbind_all("<MouseWheel>"))

    def _update_scroll_region(self, _event: object) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _fit_width(self, event: object) -> None:
        self.canvas.itemconfigure(self.window, width=getattr(event, "width"))

    def _wheel(self, event: object) -> None:
        delta = getattr(event, "delta", 0)
        self.canvas.yview_scroll(int(-delta / 120), "units")


class FormFields:
    def __init__(self, form: ScrollableForm) -> None:
        self.form = form
        self.parent = form.body
        self.row = 0

    def heading(self, title: str, note: str) -> None:
        ttk.Label(self.parent, text=title, style="FormTitle.TLabel").grid(
            row=self.row, column=0, columnspan=3, sticky="w", pady=(0, 5)
        )
        self.row += 1
        ttk.Label(self.parent, text=note, style="Hint.TLabel", wraplength=690).grid(
            row=self.row, column=0, columnspan=3, sticky="ew", pady=(0, 22)
        )
        self.row += 1

    def entry(
        self,
        label: str,
        variable: StringVar,
        *,
        required: bool = False,
        hint: str = "",
    ) -> ttk.Entry:
        text = f"{label} *" if required else label
        ttk.Label(self.parent, text=text, style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        entry = ttk.Entry(self.parent, textvariable=variable)
        entry.grid(row=self.row, column=1, columnspan=2, sticky="ew", pady=(4, 3))
        self.row += 1
        if hint:
            ttk.Label(self.parent, text=hint, style="Hint.TLabel", wraplength=580).grid(
                row=self.row, column=1, columnspan=2, sticky="w", pady=(0, 8)
            )
            self.row += 1
        return entry

    def image_picker(self, label: str, variable: StringVar, required: bool = True) -> None:
        text = f"{label} *" if required else label
        ttk.Label(self.parent, text=text, style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        ttk.Entry(self.parent, textvariable=variable).grid(
            row=self.row, column=1, sticky="ew", pady=(4, 3)
        )
        ttk.Button(
            self.parent,
            text="選擇圖片…",
            command=lambda: self._choose_image(variable),
        ).grid(row=self.row, column=2, sticky="e", padx=(10, 0), pady=(4, 3))
        self.row += 1
        ttk.Label(
            self.parent,
            text="支援 WebP、JPG、PNG、GIF、AVIF；建議圖片寬度 1600–2400 px。",
            style="Hint.TLabel",
        ).grid(row=self.row, column=1, columnspan=2, sticky="w", pady=(0, 8))
        self.row += 1

    def combobox(self, label: str, variable: StringVar, values: list[str]) -> None:
        ttk.Label(self.parent, text=f"{label} *", style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        ttk.Combobox(
            self.parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(row=self.row, column=1, columnspan=2, sticky="ew", pady=(4, 8))
        self.row += 1

    def text(self, label: str, *, required: bool = False, height: int = 6, hint: str = "") -> Text:
        text = f"{label} *" if required else label
        ttk.Label(self.parent, text=text, style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        widget = Text(
            self.parent,
            height=height,
            wrap="word",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Microsoft JhengHei UI", 10),
            undo=True,
        )
        widget.grid(row=self.row, column=1, columnspan=2, sticky="ew", pady=(4, 3))
        self.row += 1
        if hint:
            ttk.Label(self.parent, text=hint, style="Hint.TLabel", wraplength=580).grid(
                row=self.row, column=1, columnspan=2, sticky="w", pady=(0, 8)
            )
            self.row += 1
        return widget

    def actions(self, save_command: object, preview_command: object) -> None:
        group = ttk.Frame(self.parent)
        group.grid(row=self.row, column=1, columnspan=2, sticky="e", pady=(25, 0))
        ttk.Button(group, text="開啟目前網站", command=preview_command).pack(side="left", padx=(0, 10))
        ttk.Button(group, text="儲存並更新網站", style="Primary.TButton", command=save_command).pack(side="left")
        self.row += 1

    @staticmethod
    def _choose_image(variable: StringVar) -> None:
        path = filedialog.askopenfilename(
            title="選擇作品圖片",
            filetypes=[
                ("網站圖片", "*.webp *.jpg *.jpeg *.png *.gif *.avif"),
                ("所有檔案", "*.*"),
            ],
        )
        if path:
            variable.set(path)


class WorkForm(ScrollableForm):
    def __init__(self, parent: ttk.Notebook, app: "ContentManager") -> None:
        super().__init__(parent)
        self.app = app
        self.values = {
            "slug": StringVar(),
            "title_zh": StringVar(),
            "title_en": StringVar(),
            "year": StringVar(value=str(date.today().year)),
            "image": StringVar(),
            "alt": StringVar(),
            "medium_zh": StringVar(value="油彩、畫布"),
            "medium_en": StringVar(value="Oil on canvas"),
            "dimensions": StringVar(),
            "collection": StringVar(),
        }
        self.featured = BooleanVar(value=True)
        fields = FormFields(self)
        fields.heading("新增作品", "填寫作品資料並選擇圖片。儲存後，作品列表與詳細頁會一起更新。")
        fields.entry("網址代稱", self.values["slug"], hint="可留白自動產生；若自行填寫，請使用英文小寫、數字與連字號。")
        fields.entry("作品中文名", self.values["title_zh"], required=True)
        fields.entry("作品英文名", self.values["title_en"], hint="可留白，網站將暫時沿用中文名。")
        fields.entry("年份", self.values["year"], required=True)
        fields.image_picker("作品圖片", self.values["image"])
        fields.entry("圖片說明", self.values["alt"], hint="提供給看不到圖片的使用者；可留白自動產生。")
        fields.entry("媒材（中文）", self.values["medium_zh"])
        fields.entry("媒材（英文）", self.values["medium_en"])
        fields.entry("尺寸", self.values["dimensions"], hint="例如：45 × 53 cm・10F")
        fields.entry("典藏資訊", self.values["collection"], hint="沒有可留白。")
        self.description = fields.text("作品說明", required=True, height=6)
        ttk.Checkbutton(self.body, text="設為精選作品", variable=self.featured).grid(
            row=fields.row, column=1, columnspan=2, sticky="w", pady=(8, 0)
        )
        fields.row += 1
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title_zh = self.values["title_zh"].get().strip()
        image_path = self.values["image"].get().strip()
        description = self.description.get("1.0", "end").strip()
        if not title_zh or not image_path or not description:
            messagebox.showwarning("資料未完成", "請填寫作品中文名、作品圖片與作品說明。")
            return
        if not valid_image(image_path):
            return
        slug = self.values["slug"].get().strip() or generated_slug("work")
        try:
            slug = add_content.validate_slug(slug)
            image = add_content.prepare_image(image_path)
        except SystemExit as error:
            messagebox.showerror("無法儲存", str(error))
            return
        title_en = self.values["title_en"].get().strip() or title_zh
        record = {
            "kind": "work",
            "slug": slug,
            "title_zh": title_zh,
            "title_en": title_en,
            "year": self.values["year"].get().strip() or str(date.today().year),
            "image": image,
            "alt": self.values["alt"].get().strip() or f"沈東榮油畫作品〈{title_zh}〉",
            "medium_zh": self.values["medium_zh"].get().strip() or "油彩、畫布",
            "medium_en": self.values["medium_en"].get().strip() or "Oil on canvas",
            "dimensions": self.values["dimensions"].get().strip() or "尺寸待補",
            "collection": self.values["collection"].get().strip(),
            "featured": bool(self.featured.get()),
            "description": [description],
        }
        if save_record_with_confirmation("works", slug, record):
            self.app.finish_save(f"作品〈{title_zh}〉")
            self.reset()

    def reset(self) -> None:
        for key, variable in self.values.items():
            variable.set("")
        self.values["year"].set(str(date.today().year))
        self.values["medium_zh"].set("油彩、畫布")
        self.values["medium_en"].set("Oil on canvas")
        self.featured.set(True)
        self.description.delete("1.0", "end")
        self.canvas.yview_moveto(0)


class ArticleForm(ScrollableForm):
    def __init__(self, parent: ttk.Notebook, app: "ContentManager") -> None:
        super().__init__(parent)
        self.app = app
        self.values = {
            "slug": StringVar(),
            "title": StringVar(),
            "date": StringVar(value=date.today().isoformat()),
            "category": StringVar(value="創作筆記"),
            "image": StringVar(),
            "image_alt": StringVar(),
            "summary": StringVar(),
        }
        fields = FormFields(self)
        fields.heading("新增文章", "填寫標題、分類與正文。每個空白行會自動分成新的文章段落。")
        fields.entry("網址代稱", self.values["slug"], hint="可留白自動產生；若自行填寫，請使用英文小寫、數字與連字號。")
        fields.entry("文章標題", self.values["title"], required=True)
        fields.entry("日期", self.values["date"], required=True, hint="格式：YYYY-MM-DD")
        fields.combobox("文章分類", self.values["category"], list(CATEGORY_LABELS))
        fields.image_picker("文章主圖", self.values["image"])
        fields.entry("圖片說明", self.values["image_alt"], hint="可留白自動使用文章標題。")
        fields.entry("文章摘要", self.values["summary"], required=True)
        self.body_text = fields.text(
            "文章正文",
            required=True,
            height=13,
            hint="第一段會以較大的引言呈現；段落之間請空一行。",
        )
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title = self.values["title"].get().strip()
        image_path = self.values["image"].get().strip()
        summary = self.values["summary"].get().strip()
        raw_body = self.body_text.get("1.0", "end").strip()
        if not title or not image_path or not summary or not raw_body:
            messagebox.showwarning("資料未完成", "請填寫文章標題、主圖、摘要與正文。")
            return
        if not valid_image(image_path):
            return
        article_date = self.values["date"].get().strip()
        try:
            date.fromisoformat(article_date)
        except ValueError:
            messagebox.showerror("日期格式錯誤", "日期請使用 YYYY-MM-DD，例如 2026-09-01。")
            return
        slug = self.values["slug"].get().strip() or generated_slug("article")
        try:
            slug = add_content.validate_slug(slug)
            image = add_content.prepare_image(image_path)
        except SystemExit as error:
            messagebox.showerror("無法儲存", str(error))
            return
        category = CATEGORY_LABELS[self.values["category"].get()]
        category_zh, category_en = add_content.CATEGORIES[category]
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw_body) if part.strip()]
        record = {
            "kind": "article",
            "slug": slug,
            "title": title,
            "date": article_date,
            "category": category,
            "category_zh": category_zh,
            "category_en": category_en,
            "image": image,
            "image_alt": self.values["image_alt"].get().strip() or f"文章〈{title}〉主圖",
            "summary": summary,
            "body": [
                {"type": "lead" if index == 0 else "paragraph", "text": paragraph}
                for index, paragraph in enumerate(paragraphs)
            ],
        }
        if save_record_with_confirmation("articles", slug, record):
            self.app.finish_save(f"文章〈{title}〉")
            self.reset()

    def reset(self) -> None:
        for variable in self.values.values():
            variable.set("")
        self.values["date"].set(date.today().isoformat())
        self.values["category"].set("創作筆記")
        self.body_text.delete("1.0", "end")
        self.canvas.yview_moveto(0)


class MaintenancePanel(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app: "ContentManager") -> None:
        super().__init__(parent, padding=34)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="網站維護", style="FormTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="不需要指令列：可以在這裡重建網站、預覽結果或打開資料夾。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 24))
        actions = [
            ("重新產生網站", app.rebuild, "將現有資料重新整理成 HTML。"),
            ("開啟網站預覽", app.open_preview, "在瀏覽器查看目前網站。"),
            ("打開作品資料夾", lambda: open_folder(ROOT / "content" / "works"), "查看作品 JSON 資料。"),
            ("打開文章資料夾", lambda: open_folder(ROOT / "content" / "articles"), "查看文章 JSON 資料。"),
            ("打開圖片資料夾", lambda: open_folder(add_content.ASSET_DIR), "管理已上傳的圖片。"),
            ("開啟使用說明", lambda: open_folder(ROOT / "README.md"), "閱讀完整操作方式。"),
        ]
        for row, (label, command, note) in enumerate(actions, start=2):
            card = ttk.Frame(self, padding=(18, 14))
            card.grid(row=row, column=0, sticky="ew", pady=5)
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=label, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=note, style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
            ttk.Button(card, text="執行", command=command).grid(row=0, column=1, rowspan=2, padx=(20, 0))


class ContentManager(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("沈東榮網站內容管理器")
        self.geometry("880x800")
        self.minsize(720, 620)
        self.configure(background="#eee8df")
        self.preview_server: ThreadingHTTPServer | None = None
        self.preview_thread: threading.Thread | None = None
        self.status = StringVar(value="準備就緒")
        self._configure_style()

        header = ttk.Frame(self, padding=(28, 20, 28, 16), style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="沈東榮網站內容管理器", style="AppTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="新增作品與文章・更新靜態網站・本機預覽",
            style="AppSubtitle.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        notebook.add(WorkForm(notebook, self), text="  新增作品  ")
        notebook.add(ArticleForm(notebook, self), text="  新增文章  ")
        notebook.add(MaintenancePanel(notebook, self), text="  網站維護  ")

        status_bar = ttk.Label(self, textvariable=self.status, style="Status.TLabel", anchor="w")
        status_bar.pack(fill="x", padx=18, pady=(0, 12))
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _configure_style(self) -> None:
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(family="Microsoft JhengHei UI", size=10)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#f6f2eb", foreground="#2a2722", font=default_font)
        style.configure("Header.TFrame", background="#302b26")
        style.configure("AppTitle.TLabel", background="#302b26", foreground="#f6f2eb", font=("Microsoft JhengHei UI", 18, "bold"))
        style.configure("AppSubtitle.TLabel", background="#302b26", foreground="#cfc3b5")
        style.configure("FormTitle.TLabel", font=("Microsoft JhengHei UI", 18, "bold"))
        style.configure("FieldLabel.TLabel", font=("Microsoft JhengHei UI", 10, "bold"))
        style.configure("CardTitle.TLabel", font=("Microsoft JhengHei UI", 11, "bold"))
        style.configure("Hint.TLabel", foreground="#746d64")
        style.configure("Status.TLabel", background="#eee8df", foreground="#625b53", padding=(8, 5))
        style.configure("TEntry", padding=8, fieldbackground="#ffffff")
        style.configure("TCombobox", padding=7, fieldbackground="#ffffff")
        style.configure("TButton", padding=(12, 8))
        style.configure("Primary.TButton", background="#3a342e", foreground="#ffffff", padding=(16, 9))
        style.map("Primary.TButton", background=[("active", "#1f1c19")])

    def rebuild(self) -> None:
        try:
            build_site.build()
        except Exception as error:  # noqa: BLE001 - UI must surface all build errors
            messagebox.showerror("建置失敗", str(error))
            self.status.set("網站建置失敗")
            return
        self.status.set(f"網站已更新・{datetime.now():%H:%M:%S}")
        messagebox.showinfo("完成", "網站已重新產生。")

    def finish_save(self, label: str) -> None:
        try:
            build_site.build()
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("資料已儲存，但網站建置失敗", str(error))
            self.status.set("內容已儲存・網站建置失敗")
            return
        self.status.set(f"{label}已儲存・網站已更新")
        if messagebox.askyesno("新增完成", f"{label}已儲存並更新網站。\n\n要立即開啟預覽嗎？"):
            self.open_preview()

    def open_preview(self) -> None:
        try:
            build_site.build()
            if self.preview_server is None:
                handler = partial(QuietHandler, directory=str(build_site.DIST))
                self.preview_server = ThreadingHTTPServer(("127.0.0.1", 8000), handler)
                self.preview_thread = threading.Thread(
                    target=self.preview_server.serve_forever,
                    name="site-preview",
                    daemon=True,
                )
                self.preview_thread.start()
        except OSError:
            # Another local preview is already using port 8000; opening it is safe.
            pass
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("無法開啟預覽", str(error))
            return
        webbrowser.open("http://127.0.0.1:8000/")
        self.status.set("本機預覽：http://127.0.0.1:8000/")

    def close(self) -> None:
        if self.preview_server is not None:
            self.preview_server.shutdown()
            self.preview_server.server_close()
        self.destroy()


def generated_slug(prefix: str) -> str:
    return f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}"


def valid_image(value: str) -> bool:
    path = Path(value).expanduser()
    suffix = path.suffix.lower() if path.suffix else Path(value).suffix.lower()
    if suffix not in SUPPORTED_IMAGES:
        messagebox.showerror(
            "圖片格式不支援",
            "請使用 WebP、JPG、PNG、GIF 或 AVIF。TIFF、PSD 等格式請先另存成網站圖片。",
        )
        return False
    return True


def save_record_with_confirmation(folder: str, slug: str, record: dict) -> bool:
    try:
        add_content.save_record(folder, slug, record, False)
        return True
    except SystemExit as error:
        target = ROOT / "content" / folder / f"{slug}.json"
        if target.exists() and messagebox.askyesno("內容已存在", "同名內容已存在，確定要覆寫嗎？"):
            add_content.save_record(folder, slug, record, True)
            return True
        if not target.exists():
            messagebox.showerror("無法儲存", str(error))
        return False


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.resolve().as_uri())


def main() -> None:
    app = ContentManager()
    if "--check" in sys.argv:
        app.withdraw()
        app.update_idletasks()
        app.close()
        print("Content manager UI initialized successfully.")
        return
    app.mainloop()


if __name__ == "__main__":
    main()
