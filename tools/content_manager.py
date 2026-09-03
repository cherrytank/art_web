"""Friendly local desktop UI for content, image optimization, and preview."""

from __future__ import annotations

import json
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
from image_pipeline import SUPPORTED_EXTENSIONS


ROOT = Path(__file__).resolve().parents[1]
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

    def image_picker(
        self,
        label: str,
        variable: StringVar,
        required: bool = True,
        *,
        multiple: bool = False,
    ) -> None:
        text = f"{label} *" if required else label
        ttk.Label(self.parent, text=text, style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        ttk.Entry(self.parent, textvariable=variable).grid(
            row=self.row, column=1, sticky="ew", pady=(4, 3)
        )
        picker = self._choose_images if multiple else self._choose_image
        ttk.Button(
            self.parent,
            text="選擇多張…" if multiple else "選擇圖片…",
            command=lambda: picker(variable),
        ).grid(row=self.row, column=2, sticky="e", padx=(10, 0), pady=(4, 3))
        self.row += 1
        ttk.Label(
            self.parent,
            text=(
                "可一次複選多張局部圖；網站會自動做成左右滑動圖庫。"
                if multiple
                else "支援 WebP、JPG、PNG、AVIF；儲存時會自動產生手機與桌面尺寸。"
            ),
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

    @staticmethod
    def _choose_images(variable: StringVar) -> None:
        paths = filedialog.askopenfilenames(
            title="選擇局部圖片",
            filetypes=[
                ("網站圖片", "*.webp *.jpg *.jpeg *.png *.gif *.avif"),
                ("所有檔案", "*.*"),
            ],
        )
        if paths:
            variable.set(" | ".join(paths))


class WorkForm(ScrollableForm):
    def __init__(self, parent: ttk.Notebook, app: "ContentManager") -> None:
        super().__init__(parent)
        self.app = app
        self.values = {
            "slug": StringVar(),
            "catalog_number": StringVar(),
            "title_zh": StringVar(),
            "title_en": StringVar(),
            "year": StringVar(value=str(date.today().year)),
            "image": StringVar(),
            "gallery": StringVar(),
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
        fields.entry("作品編號", self.values["catalog_number"], hint="例如：026021；可供作品頁搜尋。")
        fields.entry("作品中文名", self.values["title_zh"], required=True)
        fields.entry("作品英文名", self.values["title_en"], hint="沒有正式英文題名時可留白，網站不會自行翻譯。")
        fields.entry("年份", self.values["year"], required=True)
        fields.image_picker("作品圖片", self.values["image"])
        fields.image_picker("局部圖片", self.values["gallery"], required=False, multiple=True)
        fields.entry("圖片說明", self.values["alt"], hint="提供給看不到圖片的使用者；可留白自動產生。")
        fields.entry("媒材（中文）", self.values["medium_zh"])
        fields.entry("媒材（英文）", self.values["medium_en"])
        fields.entry("尺寸", self.values["dimensions"], hint="例如：45 × 53 cm・10F")
        fields.entry("典藏資訊", self.values["collection"], hint="沒有可留白。")
        self.description = fields.text(
            "作品說明",
            height=6,
            hint="文案尚未完成時可以留白，日後再補即可。",
        )
        ttk.Checkbutton(self.body, text="設為精選作品", variable=self.featured).grid(
            row=fields.row, column=1, columnspan=2, sticky="w", pady=(8, 0)
        )
        fields.row += 1
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title_zh = self.values["title_zh"].get().strip()
        image_path = self.values["image"].get().strip()
        description = self.description.get("1.0", "end").strip()
        if not title_zh or not image_path:
            messagebox.showwarning("資料未完成", "請填寫作品中文名並選擇作品圖片。")
            return
        if not valid_image(image_path):
            return
        gallery_paths = [
            part.strip()
            for part in self.values["gallery"].get().split("|")
            if part.strip()
        ]
        if any(not valid_image(path) for path in gallery_paths):
            return
        slug = self.values["slug"].get().strip() or generated_slug("work")
        try:
            slug = add_content.validate_slug(slug)
            image = add_content.prepare_image(image_path)
            gallery = [add_content.prepare_image(path) for path in gallery_paths]
        except SystemExit as error:
            messagebox.showerror("無法儲存", str(error))
            return
        record = {
            "kind": "work",
            "slug": slug,
            "catalog_number": self.values["catalog_number"].get().strip(),
            "title_zh": title_zh,
            "title_en": self.values["title_en"].get().strip(),
            "year": self.values["year"].get().strip() or str(date.today().year),
            "image": image,
            "gallery": gallery,
            "alt": self.values["alt"].get().strip() or f"沈東榮油畫作品〈{title_zh}〉",
            "medium_zh": self.values["medium_zh"].get().strip() or "油彩、畫布",
            "medium_en": self.values["medium_en"].get().strip() or "Oil on canvas",
            "dimensions": self.values["dimensions"].get().strip() or "尺寸待補",
            "collection": self.values["collection"].get().strip(),
            "featured": bool(self.featured.get()),
            "description": [description] if description else [],
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


class ExhibitionForm(ScrollableForm):
    def __init__(self, parent: ttk.Notebook, app: "ContentManager") -> None:
        super().__init__(parent)
        self.app = app
        self.values = {
            "slug": StringVar(),
            "year": StringVar(value=str(date.today().year)),
            "title_zh": StringVar(),
            "title_en": StringVar(),
            "subtitle": StringVar(value="沈東榮油畫個展"),
            "artist": StringVar(value="沈東榮 Laurent Shen"),
            "date": StringVar(),
            "venue": StringVar(),
            "city": StringVar(),
            "address": StringVar(),
            "opening_hours": StringVar(),
            "cover_image": StringVar(),
            "poster_image": StringVar(),
            "gallery": StringVar(),
        }
        self.current = BooleanVar(value=False)
        fields = FormFields(self)
        fields.heading(
            "新增展覽",
            "填寫展覽資訊、選擇主視覺與現場照片；儲存後會同時更新展覽列表與詳細頁。",
        )
        fields.entry("網址代稱", self.values["slug"], hint="可留白自動產生；若自行填寫，請使用英文小寫、數字與連字號。")
        fields.entry("年份", self.values["year"], required=True)
        fields.entry("展覽名稱", self.values["title_zh"], required=True)
        fields.entry("英文名稱", self.values["title_en"], hint="沒有正式英文名稱時可留白。")
        fields.entry("展覽類型", self.values["subtitle"], hint="例如：沈東榮油畫個展")
        fields.entry("藝術家", self.values["artist"])
        fields.entry("展期", self.values["date"], required=True, hint="例如：2026.07.01–2026.09.30")
        fields.entry("展覽地點", self.values["venue"], required=True)
        fields.entry("城市", self.values["city"], required=True)
        fields.entry("地址", self.values["address"])
        fields.entry("開放時間", self.values["opening_hours"])
        fields.image_picker("展覽主視覺", self.values["cover_image"])
        fields.image_picker("展覽海報／邀請卡", self.values["poster_image"])
        fields.image_picker("展場照片", self.values["gallery"], multiple=True)
        self.introduction = fields.text(
            "展覽介紹",
            required=True,
            height=10,
            hint="段落之間請空一行，網站會自動套用固定格式。",
        )
        ttk.Checkbutton(self.body, text="設為當期展覽", variable=self.current).grid(
            row=fields.row, column=1, columnspan=2, sticky="w", pady=(8, 12)
        )
        fields.row += 1

        ttk.Label(self.body, text="展出作品", style="FieldLabel.TLabel").grid(
            row=fields.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        work_box = ttk.Frame(self.body)
        work_box.grid(row=fields.row, column=1, columnspan=2, sticky="ew", pady=(4, 8))
        work_box.columnconfigure(0, weight=1)
        work_box.columnconfigure(1, weight=1)
        self.work_choices: dict[str, BooleanVar] = {}
        work_files = sorted((ROOT / "content" / "works").glob("*.json"))
        for index, path in enumerate(work_files):
            work = json.loads(path.read_text(encoding="utf-8"))
            variable = BooleanVar(value=False)
            self.work_choices[work["slug"]] = variable
            label = f'{work.get("catalog_number", "")}　{work["title_zh"]}'.strip()
            ttk.Checkbutton(work_box, text=label, variable=variable).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 18),
                pady=3,
            )
        fields.row += 1
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title_zh = self.values["title_zh"].get().strip()
        year = self.values["year"].get().strip() or str(date.today().year)
        exhibition_date = self.values["date"].get().strip()
        venue = self.values["venue"].get().strip()
        city = self.values["city"].get().strip()
        cover_path = self.values["cover_image"].get().strip()
        poster_path = self.values["poster_image"].get().strip()
        gallery_paths = [
            part.strip()
            for part in self.values["gallery"].get().split("|")
            if part.strip()
        ]
        raw_intro = self.introduction.get("1.0", "end").strip()
        if not all((title_zh, exhibition_date, venue, city, cover_path, poster_path, gallery_paths, raw_intro)):
            messagebox.showwarning(
                "資料未完成",
                "請填寫展覽名稱、展期、地點、城市與介紹，並選擇主視覺、海報及至少一張展場照片。",
            )
            return
        if any(not valid_image(path) for path in [cover_path, poster_path, *gallery_paths]):
            return

        slug = self.values["slug"].get().strip() or generated_slug("exhibition")
        try:
            slug = add_content.validate_slug(slug)
            cover_image = add_content.prepare_image(cover_path)
            poster_image = add_content.prepare_image(poster_path)
            gallery = [add_content.prepare_image(path) for path in gallery_paths]
        except SystemExit as error:
            messagebox.showerror("無法儲存", str(error))
            return

        record = {
            "kind": "exhibition",
            "slug": slug,
            "year": year,
            "title_zh": title_zh,
            "title_en": self.values["title_en"].get().strip(),
            "subtitle": self.values["subtitle"].get().strip() or "沈東榮油畫個展",
            "artist": self.values["artist"].get().strip() or "沈東榮 Laurent Shen",
            "date": exhibition_date,
            "venue": venue,
            "city": city,
            "address": self.values["address"].get().strip(),
            "opening_hours": self.values["opening_hours"].get().strip(),
            "cover_image": cover_image,
            "cover_alt": f"{title_zh}展覽主視覺",
            "poster_image": poster_image,
            "poster_alt": f"{title_zh}展覽海報",
            "introduction": [
                part.strip()
                for part in re.split(r"\n\s*\n", raw_intro)
                if part.strip()
            ],
            "gallery": gallery,
            "selected_work_slugs": [
                work_slug
                for work_slug, variable in self.work_choices.items()
                if variable.get()
            ],
        }
        if not save_record_with_confirmation("exhibition_details", slug, record):
            return

        summary_path = ROOT / "content" / "exhibitions.json"
        summaries = json.loads(summary_path.read_text(encoding="utf-8"))
        if self.current.get():
            for item in summaries:
                item.pop("current", None)
        summary = {
            "year": year,
            "title": title_zh,
            "venue": venue,
            "city": city,
            "slug": slug,
        }
        if self.current.get():
            summary["current"] = True
        summaries = [
            item
            for item in summaries
            if item.get("slug") != slug and item.get("title") != title_zh
        ]
        summaries.append(summary)
        summaries.sort(key=lambda item: str(item.get("year", "")), reverse=True)
        summary_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.app.finish_save(f"展覽《{title_zh}》")
        self.reset()

    def reset(self) -> None:
        for variable in self.values.values():
            variable.set("")
        self.values["year"].set(str(date.today().year))
        self.values["subtitle"].set("沈東榮油畫個展")
        self.values["artist"].set("沈東榮 Laurent Shen")
        self.current.set(False)
        for variable in self.work_choices.values():
            variable.set(False)
        self.introduction.delete("1.0", "end")
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
            text="在這裡重新最佳化所有圖片、產生網站、預覽結果或打開資料夾。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 24))
        actions = [
            ("最佳化圖片並重建網站", app.rebuild, "重新產生各種圖片尺寸與所有 HTML。"),
            ("開啟網站預覽", app.open_preview, "在瀏覽器查看目前網站。"),
            ("打開作品資料夾", lambda: open_folder(ROOT / "content" / "works"), "查看作品 JSON 資料。"),
            ("打開展覽資料夾", lambda: open_folder(ROOT / "content" / "exhibition_details"), "查看展覽詳細頁 JSON 資料。"),
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
            text="新增作品、展覽與文章・自動最佳化圖片・更新網站・本機預覽",
            style="AppSubtitle.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        notebook.add(WorkForm(notebook, self), text="  新增作品  ")
        notebook.add(ExhibitionForm(notebook, self), text="  新增展覽  ")
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
            report = build_site.build()
        except Exception as error:  # noqa: BLE001 - UI must surface all build errors
            messagebox.showerror("建置失敗", str(error))
            self.status.set("網站建置失敗")
            return
        summary = build_summary(report)
        self.status.set(f"{summary}・{datetime.now():%H:%M:%S}")
        messagebox.showinfo("完成", f"網站已重新產生。\n\n{summary}")

    def finish_save(self, label: str) -> None:
        try:
            report = build_site.build()
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("資料已儲存，但網站建置失敗", str(error))
            self.status.set("內容已儲存・網站建置失敗")
            return
        summary = build_summary(report)
        self.status.set(f"{label}已儲存・{summary}")
        if messagebox.askyesno(
            "新增完成",
            f"{label}已儲存，圖片已最佳化並更新網站。\n\n{summary}\n\n要立即開啟預覽嗎？",
        ):
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


def build_summary(report: build_site.BuildReport) -> str:
    return (
        f"{report.page_count} 個頁面・"
        f"{report.images.source_count} 張原圖產生 {report.images.variant_count} 個響應式版本"
    )


def valid_image(value: str) -> bool:
    path = Path(value).expanduser()
    suffix = path.suffix.lower() if path.suffix else Path(value).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        messagebox.showerror(
            "圖片格式不支援",
            "請使用 WebP、JPG、PNG 或 AVIF。GIF、TIFF、PSD 請先另存成靜態網站圖片。",
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
