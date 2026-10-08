"""Friendly local desktop UI for content, image optimization, and preview."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from queue import Empty
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, font, messagebox, simpledialog
from tkinter import ttk

import add_content
import build_site
from image_pipeline import SUPPORTED_EXTENSIONS
from page_images import PAGE_IMAGE_LABELS, import_page_image
from content_format import EXAMPLES, blocks_to_markup, parse_markup
from local_jobs import LocalJob
import chronology


ROOT = Path(__file__).resolve().parents[1]
CATEGORY_LABELS = {
    "創作筆記": "painting-notes",
    "藝術評論": "art-criticism",
    "作品故事": "artwork-story",
    "出版品": "publications",
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class PreviewServer(ThreadingHTTPServer):
    # Windows otherwise permits two HTTPServer instances to bind the same port.
    allow_reuse_address = False


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
        self.action_bar = ttk.Frame(self, padding=(20, 12))
        self.action_bar.pack(side="bottom", fill="x")
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

    def combobox(self, label: str, variable: StringVar, values: list[str]) -> ttk.Combobox:
        ttk.Label(self.parent, text=f"{label} *", style="FieldLabel.TLabel").grid(
            row=self.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        widget = ttk.Combobox(
            self.parent,
            textvariable=variable,
            values=values,
            state="readonly",
        )
        widget.grid(row=self.row, column=1, columnspan=2, sticky="ew", pady=(4, 8))
        self.row += 1
        return widget

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

    def format_toolbar(self, widget: Text) -> None:
        """Insert editable examples; selected text can be made bold directly."""
        group = ttk.Frame(self.parent)
        group.grid(row=self.row, column=1, columnspan=2, sticky="w", pady=(3, 12))
        self.row += 1

        def insert(label: str) -> None:
            if label == "粗體" and widget.tag_ranges("sel"):
                text = widget.get("sel.first", "sel.last")
                widget.delete("sel.first", "sel.last")
                widget.insert("insert", f"**{text}**")
            else:
                prefix = "\n\n" if widget.get("1.0", "insert").strip() else ""
                widget.insert("insert", prefix + EXAMPLES[label] + "\n\n")
            widget.focus_set()
            widget.see("insert")

        for index, label in enumerate(EXAMPLES):
            ttk.Button(group, text=label, width=7, command=partial(insert, label)).grid(
                row=index // 4, column=index % 4, padx=(0, 5), pady=3)
        ttk.Button(group, text="格式教學", command=lambda: webbrowser.open(
            (ROOT / "docs" / "文字編輯教學.html").as_uri())).grid(row=1, column=3, padx=(0, 5), pady=3)

    def actions(self, save_command: object, preview_command: object) -> None:
        group = self.form.action_bar
        for child in group.winfo_children():
            child.destroy()
        ttk.Label(group, text="儲存只更新本機，不會上傳 GitHub。", style="Hint.TLabel").pack(side="left")
        ttk.Button(group, text="儲存變更", style="Primary.TButton", command=save_command).pack(side="right")
        ttk.Button(group, text="預覽已儲存內容", command=preview_command).pack(side="right", padx=10)

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
        fields.entry("典藏狀態", self.values["collection"], hint="已收藏請填「已收藏」；未收藏留白。網站只顯示狀態，不公開姓名。")
        self.description = fields.text(
            "作品說明",
            height=6,
            hint="可留白，日後於「編輯文字」補寫。空一行分段；下方按鈕可插入標題、背景框等格式。",
        )
        fields.format_toolbar(self.description)
        ttk.Checkbutton(self.body, text="設為精選作品", variable=self.featured).grid(
            row=fields.row, column=1, columnspan=2, sticky="w", pady=(8, 0)
        )
        fields.row += 1
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title_zh = self.values["title_zh"].get().strip()
        image_path = self.values["image"].get().strip()
        description = self.description.get("1.0", "end").strip()
        try:
            description_blocks = parse_markup(description)
        except ValueError as error:
            messagebox.showerror("文字格式錯誤", str(error))
            return
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
            "image": image_path,
            "gallery": gallery_paths,
            "alt": self.values["alt"].get().strip() or f"沈東榮油畫作品〈{title_zh}〉",
            "medium_zh": self.values["medium_zh"].get().strip() or "油彩、畫布",
            "medium_en": self.values["medium_en"].get().strip() or "Oil on canvas",
            "dimensions": self.values["dimensions"].get().strip() or "尺寸待補",
            "collection": self.values["collection"].get().strip(),
            "featured": bool(self.featured.get()),
            "description": description_blocks,
        }
        def complete():
            self.reset()
            self.app.finish_save(f"作品〈{title_zh}〉")
        import_record(self.app, "works", record, ("image", "gallery"), complete)

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
    def __init__(self, parent: ttk.Notebook, app: "ContentManager", mode: str = "all") -> None:
        super().__init__(parent)
        self.app = app
        self.current_selection = StringVar()
        self.current_choice_keys: dict[str, str] = {}
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
        ttk.Label(self.body, text="指定當期展覽", style="FieldLabel.TLabel").grid(
            row=fields.row, column=0, sticky="nw", padx=(0, 18), pady=(8, 3)
        )
        current_box = ttk.Frame(self.body)
        current_box.grid(row=fields.row, column=1, columnspan=2, sticky="ew", pady=(4, 3))
        current_box.columnconfigure(0, weight=1)
        self.current_selector = ttk.Combobox(
            current_box,
            textvariable=self.current_selection,
            state="readonly",
        )
        self.current_selector.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            current_box,
            text="設為當期",
            command=self.set_current_exhibition,
        ).grid(row=0, column=1, padx=(10, 0))
        fields.row += 1
        ttk.Label(
            self.body,
            text="可從所有既有展覽中選擇；設定後會自動取消前一個當期展覽。",
            style="Hint.TLabel",
            wraplength=580,
        ).grid(row=fields.row, column=1, columnspan=2, sticky="w", pady=(0, 16))
        fields.row += 1
        self.refresh_current_choices()
        if mode == "current":
            # Keep current-exhibition selection separate from creating a record.
            for child in self.body.winfo_children():
                if isinstance(child, ttk.Label) and child.cget("text") == "新增展覽":
                    child.configure(text="指定當期展覽")
                elif isinstance(child, ttk.Label) and str(child.cget("text")).startswith("填寫展覽資訊"):
                    child.configure(text="選擇既有展覽，按「設為當期」立即儲存並更新本機網站。")
            return
        if mode == "new":
            for child in self.body.winfo_children():
                if int(child.grid_info().get("row", 0)) >= 2:
                    child.grid_remove()
            fields.row = 2

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
            "cover_image": cover_path,
            "cover_alt": f"{title_zh}展覽主視覺",
            "poster_image": poster_path,
            "poster_alt": f"{title_zh}展覽海報",
            "introduction": [
                part.strip()
                for part in re.split(r"\n\s*\n", raw_intro)
                if part.strip()
            ],
            "gallery": gallery_paths,
            "selected_work_slugs": [
                work_slug
                for work_slug, variable in self.work_choices.items()
                if variable.get()
            ],
        }
        summary = {
            "year": year,
            "title": title_zh,
            "venue": venue,
            "city": city,
            "slug": slug,
        }
        if self.current.get():
            summary["current"] = True
        def complete():
            self.refresh_current_choices()
            self.reset()
            self.app.finish_save(f"展覽《{title_zh}》")
        import_record(self.app, "exhibition_details", record, ("cover_image", "poster_image", "gallery"), complete, summary=summary)

    def refresh_current_choices(self) -> None:
        summary_path = ROOT / "content" / "exhibitions.json"
        summaries = json.loads(summary_path.read_text(encoding="utf-8"))
        self.current_choice_keys.clear()
        selected_label = ""
        labels: list[str] = []
        for index, item in enumerate(summaries):
            base_label = f'{item.get("year", "")}｜{item.get("title", "")}｜{item.get("venue", "")}'
            label = f"{base_label}（目前）" if item.get("current") else base_label
            if label in self.current_choice_keys:
                label = f"{label} #{index + 1}"
            key = exhibition_key(item)
            labels.append(label)
            self.current_choice_keys[label] = key
            if item.get("current"):
                selected_label = label
        self.current_selector.configure(values=labels)
        self.current_selection.set(selected_label or (labels[0] if labels else ""))

    def set_current_exhibition(self) -> None:
        label = self.current_selection.get()
        selected_key = self.current_choice_keys.get(label)
        if not selected_key:
            messagebox.showwarning("尚未選擇展覽", "請先從清單選擇一個當期展覽。")
            return

        summary_path = ROOT / "content" / "exhibitions.json"
        summaries = json.loads(summary_path.read_text(encoding="utf-8"))
        selected_title = ""
        for item in summaries:
            item.pop("current", None)
            if exhibition_key(item) == selected_key:
                item["current"] = True
                selected_title = str(item.get("title", ""))
        if not selected_title:
            messagebox.showerror("設定失敗", "找不到所選展覽，請重新開啟管理介面後再試一次。")
            return

        summary_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.refresh_current_choices()
        self.app.finish_save(f"當期展覽《{selected_title}》")

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
        self.title_lines = fields.text("標題顯示換行", height=3, hint="選填：輸入完整標題，按 Enter 指定換行；留白由網頁自動換行。列表仍使用上方文章標題。")
        fields.entry("日期", self.values["date"], required=True, hint="格式：YYYY-MM-DD；出版品只知道年份時可填 YYYY。")
        fields.combobox("文章分類", self.values["category"], list(CATEGORY_LABELS))
        fields.image_picker("文章主圖", self.values["image"])
        fields.entry("圖片說明", self.values["image_alt"], hint="可留白自動使用文章標題。")
        fields.entry("文章摘要", self.values["summary"], required=True)
        self.body_text = fields.text(
            "文章正文",
            required=True,
            height=13,
            hint="空一行分段；用下方按鈕插入大標、小標、引言或背景框。格式教學附有完整範例。",
        )
        fields.format_toolbar(self.body_text)
        fields.actions(self.save, app.open_preview)

    def save(self) -> None:
        title = self.values["title"].get().strip()
        image_path = self.values["image"].get().strip()
        summary = self.values["summary"].get().strip()
        raw_body = self.body_text.get("1.0", "end").strip()
        try:
            body = parse_markup(raw_body)
        except ValueError as error:
            messagebox.showerror("文字格式錯誤", str(error))
            return
        if not title or not image_path or not summary or not raw_body:
            messagebox.showwarning("資料未完成", "請填寫文章標題、主圖、摘要與正文。")
            return
        if not valid_image(image_path):
            return
        article_date = self.values["date"].get().strip()
        try:
            build_site.date_display(article_date)
        except ValueError:
            messagebox.showerror("日期格式錯誤", "日期請使用 YYYY-MM-DD，例如 2026-09-01，或四位數年份。")
            return
        slug = self.values["slug"].get().strip() or generated_slug("article")
        try:
            slug = add_content.validate_slug(slug)
        except SystemExit as error:
            messagebox.showerror("無法儲存", str(error))
            return
        category = CATEGORY_LABELS[self.values["category"].get()]
        category_zh, category_en = add_content.CATEGORIES[category]
        record = {
            "kind": "article",
            "slug": slug,
            "title": title,
            "title_lines": [line.strip() for line in self.title_lines.get("1.0", "end").splitlines() if line.strip()],
            "date": article_date,
            "category": category,
            "category_zh": category_zh,
            "category_en": category_en,
            "image": image_path,
            "image_alt": self.values["image_alt"].get().strip() or f"文章〈{title}〉主圖",
            "summary": summary,
            "body": body,
        }
        def complete():
            self.reset()
            self.app.finish_save(f"文章〈{title}〉")
        import_record(self.app, "articles", record, ("image",), complete)

    def reset(self) -> None:
        for variable in self.values.values():
            variable.set("")
        self.values["date"].set(date.today().isoformat())
        self.values["category"].set("創作筆記")
        self.body_text.delete("1.0", "end")
        self.title_lines.delete("1.0", "end")
        self.canvas.yview_moveto(0)


class PageTextForm(ScrollableForm):
    """Edit existing page copy with labeled fields, without exposing JSON syntax."""

    def __init__(self, parent: ttk.Notebook, app: "ContentManager", page: str | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.page = page
        self.choice = StringVar(value="首頁")
        self.documents = {
            "首頁": "site.json", "學經歷與創作理念": "about.json",
            "油畫教學": "classes.json", "各頁簡介": "page_copy.json",
            "聯絡我們": "contact.json",
            "年表．大事記": "chronology.json",
        }
        self.refresh_documents()
        self.choice.set(next(iter(self.documents)))
        self.widgets: list[tuple[tuple, Text, str]] = []
        self.load_page()

    def refresh_documents(self) -> None:
        """Discover new records without restarting the local editor."""
        previous_path = self.documents.get(self.choice.get())
        self.documents = {key: value for key, value in self.documents.items() if "/" not in value}
        if self.page:
            allowed = {
                "home": {"site.json"}, "about": {"about.json"},
                "works": {"page_copy.json"}, "exhibitions": {"page_copy.json"},
                "classes": {"classes.json"}, "writings": {"page_copy.json"},
                "contact": {"contact.json"}, "chronology": {"chronology.json"},
            }[self.page]
            if "page_copy.json" in allowed:
                self.documents = {"頁面簡介": "page_copy.json"}
            self.documents = {key: value for key, value in self.documents.items() if value in allowed}
        for folder, label, title_key in [("articles", "文章", "title"), ("works", "作品", "title_zh"), ("exhibition_details", "展覽", "title_zh")]:
            if self.page and folder != {"works": "works", "writings": "articles", "exhibitions": "exhibition_details"}.get(self.page):
                continue
            for path in sorted((ROOT / "content" / folder).glob("*.json")):
                data = build_site.load_json(path)
                choice = f"{label}：{data[title_key]} ({path.stem})"
                relative = f"{folder}/{path.name}"
                self.documents[choice] = relative
                if relative == previous_path:
                    self.choice.set(choice)
                    self.loaded_choice = choice
        if hasattr(self, "selector") and self.selector.winfo_exists():
            self.selector.configure(values=list(self.documents))

    def load_page(self, reload: bool = True) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.widgets.clear()
        self.path = ROOT / "content" / self.documents[self.choice.get()]
        if reload:
            self.original = self.path.read_text(encoding="utf-8")
            self.data = json.loads(self.original)
        fields = FormFields(self)
        fields.heading("編輯內容", "選擇項目後修改。文字與主圖一起儲存；原檔會自動備份。")
        if len(self.documents) > 1:
            fields.combobox("編輯項目", self.choice, list(self.documents))
        for child in self.body.winfo_children():
            if isinstance(child, ttk.Combobox):
                self.selector = child
                child.configure(postcommand=self.refresh_documents)
                child.bind("<<ComboboxSelected>>", self.switch_page)
        self.loaded_choice = self.choice.get()
        specs = self.field_specs()
        for keys, label, mode in specs:
            value = self.get_value(keys)
            text = self.field_text(value, mode)
            if self.page and mode in {"text", "image", "category"}:
                variable = StringVar(value=text)
                widget = fields.combobox("分類", variable, list(CATEGORY_LABELS)) if mode == "category" else fields.entry(label, variable)
                widget.input_variable = variable  # Keep the Tk variable alive with its field.
            else:
                widget = fields.text(label, height=22 if mode == "chronology" else 14 if mode == "formatted" else 6 if mode == "long" else 3)
                widget.insert("1.0", text)
            if mode == "formatted":
                fields.format_toolbar(widget)
            if mode == "image":
                def choose(target=widget):
                    path = filedialog.askopenfilename(title="選擇圖片", filetypes=[("圖片", "*.jpg *.jpeg *.png *.webp *.avif")])
                    if path:
                        if isinstance(target, Text):
                            target.delete("1.0", "end")
                            target.insert("1.0", path)
                        else:
                            target.input_variable.set(path)
                ttk.Button(self.body, text="選擇圖片…", command=choose).grid(row=fields.row, column=1, sticky="w")
                fields.row += 1
            self.widgets.append((keys, widget, mode))
        if self.page == "chronology":
            ttk.Button(self.body, text="新增年份…", command=self.add_chronology_year).grid(row=fields.row, column=1, sticky="w", pady=12)
            fields.row += 1
        fields.actions(self.save, self.app.open_preview)
        self.canvas.yview_moveto(0)

    def field_specs(self) -> list[tuple]:
        name = self.path.name
        groups = {
            "site.json": [("home_intro", "首頁中文簡介"), ("home_intro_en", "首頁英文簡介"), ("portrait_caption", "首頁照片中文說明")],
            "about.json": [("intro_zh", "學經歷中文簡介"), ("intro_en", "學經歷英文簡介"), ("philosophy_intro_zh", "創作理念中文簡介"), ("philosophy_intro_en", "創作理念英文簡介"), ("philosophy", "創作理念全文")],
            "classes.json": [("intro", "課程簡介"), ("course", "課程內容"), ("location", "上課地點")],
            "page_copy.json": [("works_intro", "作品頁簡介"), ("exhibitions_intro", "展覽頁簡介"), ("writings_intro", "藝評文章簡介"), ("writings_quote", "藝評文章引言")],
            "contact.json": [("intro", "聯絡頁簡介"), ("email", "電子郵件")],
        }
        specs = [((key,), label, "long") for key, label in groups.get(name, [])]
        if name == "page_copy.json" and self.page:
            specs = [spec for spec in specs if spec[0][0].startswith(self.page + "_")]
        if name == "chronology.json":
            specs = [(("intro_zh",), "中文簡介", "long"), (("intro_en",), "英文簡介", "long"),
                     (("entries",), "年表（年份獨立一行，接著每行一件事件；空一行後輸入下一個年份）", "chronology")]
            if self.page == "chronology":
                specs = specs[:2]
                specs.extend((("entries", index, "events"), f'{entry["year"]} 年事件（每行一件；留白不顯示該年）', "lines")
                             for index, entry in enumerate(self.data["entries"]))
        if name == "classes.json":
            specs.append((("schedule",), "上課時間（每行一個時段）", "lines"))
            for index in range(len(self.data["features"])):
                specs.extend([(("features", index, "title"), f"特色 {index + 1} 標題", "text"), (("features", index, "text"), f"特色 {index + 1} 內容", "long")])
        if name == "about.json":
            for group, labels in [("education", {"year": "年份", "zh": "學歷", "en": "英文"}), ("positions", {"period": "任職期間", "title": "曾任職務"}), ("current", {"zh": "現任職務", "en": "英文"})]:
                if isinstance(self.data[group], list):
                    for index, item in enumerate(self.data[group]):
                        for key, label in labels.items():
                            if key in item:
                                specs.append(((group, index, key), f"{label} {index + 1}", "text"))
        if self.data.get("kind") == "article":
            self.data.setdefault("title_lines", [])
            specs = [(("title",), "文章標題（列表與搜尋用）", "text"), (("title_lines",), "標題顯示換行（每行一句；留白自動換行）", "lines"), (("date",), "日期 YYYY-MM-DD（也可只填四位數年份）", "text"), (("category",), "分類：創作筆記／藝術評論／作品故事／出版品（填一項）", "category"), (("summary",), "摘要", "long")]
            specs.append((("body",), "文章正文（支援格式）", "formatted"))
        if self.data.get("kind") == "work":
            for key in ("title_en", "catalog_number", "collection"):
                self.data.setdefault(key, "")
            self.data.setdefault("description", [])
            specs = [((key,), label, "text") for key, label in [
                ("title_zh", "作品中文名"), ("title_en", "作品英文名"), ("catalog_number", "作品編號"),
                ("year", "年份"), ("medium_zh", "中文媒材"), ("medium_en", "英文媒材"),
                ("dimensions", "尺寸"), ("collection", "典藏資訊（網站只顯示已收藏）")]]
            specs.append((("description",), "作品內文（可留白、支援格式）", "formatted"))
        if self.data.get("kind") == "exhibition":
            specs = [((key,), label, "text") for key, label in [
                ("title_zh", "展覽名稱"), ("title_en", "英文名稱"), ("year", "年份"),
                ("subtitle", "展覽類型"), ("artist", "藝術家"), ("date", "展期"),
                ("venue", "展覽地點"), ("city", "城市"), ("address", "地址"), ("opening_hours", "開放時間")]]
            specs.append((("introduction",), "展覽介紹", "formatted"))
            publication = self.data.setdefault("publication", {})
            for key, default in [("title", ""), ("image", ""), ("alt", ""), ("description", [])]:
                publication.setdefault(key, default)
            specs.extend([(("publication", "title"), "出版作品名稱（留白隱藏整區）", "text"),
                          (("publication", "image"), "出版品封面（選填）", "image"),
                          (("publication", "alt"), "出版品圖片說明", "text"),
                          (("publication", "description"), "出版品介紹", "formatted")])
        if self.page and self.data.get("kind") in {"article", "work", "exhibition"}:
            image_fields = {
                "article": [("image", "主圖", "image"), ("image_alt", "主圖說明", "text")],
                "work": [("image", "作品主圖", "image"), ("alt", "主圖說明", "text")],
                "exhibition": [("cover_image", "展覽封面", "image"), ("cover_alt", "封面說明", "text"),
                               ("poster_image", "展覽海報", "image"), ("poster_alt", "海報說明", "text")],
            }[self.data["kind"]]
            specs.extend(((key,), label, mode) for key, label, mode in image_fields)
        return specs

    def add_chronology_year(self) -> None:
        year = simpledialog.askinteger("新增年份", "輸入四位數年份（儲存後自動由新到舊排列）：", parent=self, minvalue=1000, maxvalue=9999)
        if year is None:
            return
        if any(str(item["year"]) == str(year) for item in self.data["entries"]):
            messagebox.showinfo("年份已存在", "請直接修改該年份的事件欄位。")
            return
        # Keep all unsaved fields while adding another year to the form.
        for keys, widget, mode in self.widgets:
            target = self.data
            for key in keys[:-1]:
                target = target[key]
            raw = self.input_text(widget)
            target[keys[-1]] = [line.strip() for line in raw.splitlines() if line.strip()] if mode == "lines" else raw
        self.data["entries"].append({"year": str(year), "events": []})
        self.data["entries"].sort(key=lambda item: int(item["year"]), reverse=True)
        self.load_page(reload=False)

    @staticmethod
    def input_text(widget) -> str:
        return widget.get("1.0", "end-1c") if isinstance(widget, Text) else widget.get()

    @staticmethod
    def field_text(value, mode: str) -> str:
        if mode == "chronology":
            return chronology.to_text(value)
        if mode == "category":
            return add_content.CATEGORIES[value][0]
        if mode == "formatted":
            return blocks_to_markup(value)
        return "\n".join(value) if mode == "lines" else str(value)

    def get_value(self, keys: tuple):
        value = self.data
        for key in keys:
            value = value[key]
        return value

    def has_changes(self) -> bool:
        if self.page == "chronology" and self.data != json.loads(self.original):
            return True
        for keys, widget, mode in self.widgets:
            old = self.get_value(keys)
            text = self.field_text(old, mode)
            if self.input_text(widget) != text:
                return True
        return False

    def switch_page(self, _event=None) -> None:
        if self.has_changes() and not messagebox.askyesno("尚未儲存", "切換頁面會捨棄尚未儲存的修改，確定切換嗎？"):
            self.choice.set(self.loaded_choice)
            return
        self.load_page()

    def save(self) -> None:
        if self.path.read_text(encoding="utf-8") != self.original:
            messagebox.showerror("檔案已更新", "此檔案已被其他程式修改。請重新選擇頁面，避免蓋掉新內容。")
            return
        updated = json.loads(json.dumps(self.data, ensure_ascii=False))
        for keys, widget, mode in self.widgets:
            target = updated
            for key in keys[:-1]:
                target = target[key]
            raw = self.input_text(widget)
            if raw == self.field_text(self.get_value(keys), mode):
                continue  # Keep legacy blocks and intentional whitespace unchanged.
            raw = raw.strip()
            if mode == "chronology":
                try:
                    target[keys[-1]] = chronology.from_text(raw)
                except ValueError as error:
                    messagebox.showerror("年表格式錯誤", str(error))
                    return
                continue
            if mode == "category":
                if raw not in CATEGORY_LABELS:
                    messagebox.showerror("分類錯誤", "請填入創作筆記、藝術評論、作品故事或出版品。")
                    return
                category = CATEGORY_LABELS[raw]
                updated["category"] = category
                updated["category_zh"], updated["category_en"] = add_content.CATEGORIES[category]
                continue
            if mode == "formatted":
                try:
                    target[keys[-1]] = parse_markup(raw)
                except ValueError as error:
                    messagebox.showerror("文字格式錯誤", str(error))
                    return
                continue
            target[keys[-1]] = [line.strip() for line in raw.splitlines() if line.strip()] if mode == "lines" else raw
        if updated.get("kind") == "work" and not updated["title_zh"]:
            messagebox.showerror("資料格式錯誤", "作品中文名不能空白。")
            return
        if self.page == "chronology":
            updated["entries"].sort(key=lambda item: int(item["year"]), reverse=True)
        if updated.get("kind") == "article":
            try:
                build_site.date_display(updated["date"])
                if not updated["title"]:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("資料格式錯誤", "文章標題不能空白，日期請填 YYYY-MM-DD 或四位數年份。")
                return
        if not messagebox.askyesno("儲存修改", f"確認更新「{self.loaded_choice}」並重新產生網站？"):
            return
        path, original = self.path, self.original
        image_keys = [keys for keys, _, mode in self.widgets if mode == "image"]

        def write(progress):
            progress("儲存文字與匯入出版品圖片…")
            for keys in image_keys:
                target = updated
                for key in keys[:-1]:
                    target = target[key]
                if target[keys[-1]]:
                    target[keys[-1]] = import_page_image(target[keys[-1]], ROOT / "static/assets/images")
            if path.read_text(encoding="utf-8") != original:
                raise ValueError("檔案已被其他程式修改，請重新載入。")
            backup = ROOT / ".codex-work" / "content-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup.mkdir(parents=True)
            shutil.copy2(path, backup / path.name)
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if updated.get("kind") == "exhibition":
                summary_path = ROOT / "content/exhibitions.json"
                summaries = build_site.load_json(summary_path)
                shutil.copy2(summary_path, backup / summary_path.name)
                for item in summaries:
                    if item.get("slug") == updated["slug"]:
                        item.update(title=updated["title_zh"], year=updated["year"], venue=updated["venue"], city=updated["city"])
                summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        def complete(_result):
            self.load_page()
            self.app.finish_save("網頁文字")
        self.app._run_job("儲存修改", write, complete)


class PageImageForm(ScrollableForm):
    """Choose a page and replace its image without editing templates or JSON."""

    def __init__(self, parent: ttk.Notebook, app: "ContentManager", page: str | None = None, records: bool = True) -> None:
        super().__init__(parent)
        self.app = app
        self.page = page
        self.records = records
        self.choice = StringVar(value=PAGE_IMAGE_LABELS["home"])
        self.image_path = StringVar()
        self.image_alt = StringVar()
        self.current_image = StringVar()
        self.targets: dict[str, tuple[Path, str | None, str, str]] = {}
        fields = FormFields(self)
        fields.heading("頁面封面圖片", "選擇頁面、挑選新圖片，再按儲存。各頁可獨立選圖，原圖不會被覆蓋；圖片會自動最佳化。")
        fields.combobox("要修改的頁面", self.choice, [])
        self.selector = next(child for child in self.body.winfo_children() if isinstance(child, ttk.Combobox))
        self.selector.configure(postcommand=self.refresh_choices)
        self.selector.bind("<<ComboboxSelected>>", self.switch_page)
        ttk.Label(self.body, textvariable=self.current_image, style="Hint.TLabel", wraplength=650).grid(
            row=fields.row, column=0, columnspan=3, sticky="w", pady=(4, 16)
        )
        fields.row += 1
        fields.image_picker("封面／主圖", self.image_path)
        fields.entry("圖片說明", self.image_alt, required=True, hint="請簡單描述圖片內容，供輔助閱讀及圖片放大時使用。")
        fields.actions(self.save, app.open_preview)
        self.refresh_choices()
        self.choice.set(next(iter(self.targets)))
        self.load_page()

    def refresh_choices(self) -> None:
        # Refresh when opening the menu, so newly created content is available immediately.
        targets = {
            label: (ROOT / "content/page_images.json", key, "image", "alt")
            for key, label in PAGE_IMAGE_LABELS.items()
            if not self.page or key == self.page or key.startswith(self.page + "_") or (self.page == "about" and key == "philosophy")
        }
        for folder, label, image_key, alt_key in [
            ("works", "作品主圖", "image", "alt"),
            ("articles", "文章封面", "image", "image_alt"),
            ("exhibition_details", "展覽封面", "cover_image", "cover_alt"),
        ]:
            if not self.records:
                continue
            if self.page and folder != {"works": "works", "writings": "articles", "exhibitions": "exhibition_details"}.get(self.page):
                continue
            for path in sorted((ROOT / "content" / folder).glob("*.json")):
                data = build_site.load_json(path)
                title = data.get("title_zh") or data.get("title") or path.stem
                targets[f"{label}：{title} ({path.stem})"] = (path, None, image_key, alt_key)
        self.targets = targets
        self.selector.configure(values=list(targets))

    def load_page(self) -> None:
        self.path, self.slot, self.image_key, self.alt_key = self.targets[self.choice.get()]
        self.original = self.path.read_text(encoding="utf-8")
        data = json.loads(self.original)
        record = data[self.slot] if self.slot else data
        self.original_image = record[self.image_key]
        self.original_alt = record[self.alt_key]
        self.image_path.set(self.original_image)
        self.image_alt.set(self.original_alt)
        self.loaded_choice = self.choice.get()
        self.current_image.set(f"目前圖片：{self.original_image}\n聯絡頁目前無獨立封面，可在此更換官方 Logo 與簽名。" if self.slot and self.slot.startswith("contact_") else f"目前圖片：{self.original_image}")

    def has_changes(self) -> bool:
        return self.image_path.get() != self.original_image or self.image_alt.get() != self.original_alt

    def switch_page(self, _event=None) -> None:
        if self.has_changes() and not messagebox.askyesno("尚未儲存", "切換頁面會捨棄尚未儲存的圖片設定，確定切換嗎？"):
            self.choice.set(self.loaded_choice)
            return
        self.load_page()

    def save(self) -> None:
        if not self.has_changes():
            messagebox.showinfo("尚未修改", "請先選擇新圖片或修改圖片說明。")
            return
        if not self.image_path.get().strip() or not self.image_alt.get().strip():
            messagebox.showwarning("資料未完成", "請選擇圖片並填寫圖片說明。")
            return
        try:
            if self.path.read_text(encoding="utf-8") != self.original:
                messagebox.showerror("檔案已更新", "資料已被其他程式修改。請重新選擇頁面，避免覆蓋新內容。")
                return
            if not messagebox.askyesno("儲存封面", f"確認更新「{self.loaded_choice}」的圖片並重新產生網站？"):
                return
        except OSError as error:
            messagebox.showerror("無法儲存圖片", str(error))
            return
        path, original = self.path, self.original
        slot, image_key, alt_key = self.slot, self.image_key, self.alt_key
        image_value, alt = self.image_path.get(), self.image_alt.get().strip()

        def write(progress):
            progress("驗證並匯入圖片…")
            filename = import_page_image(image_value, ROOT / "static/assets/images")
            if path.read_text(encoding="utf-8") != original:
                raise ValueError("資料已更新，請重新載入後再儲存。")
            updated = json.loads(original)
            record = updated[slot] if slot else updated
            record[image_key] = filename
            record[alt_key] = alt
            backup = ROOT / ".codex-work/content-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup.mkdir(parents=True)
            shutil.copy2(path, backup / path.name)
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        def complete(_result):
            self.load_page()
            self.app.finish_save("頁面圖片")
        self.app._run_job("儲存圖片", write, complete)


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
            ("文字格式教學", lambda: webbrowser.open((ROOT / "docs" / "文字編輯教學.html").as_uri()), "作品與文章的大標、小標、粗體、條列與背景框範例。"),
            ("開啟使用說明", lambda: open_folder(ROOT / "README.md"), "閱讀完整操作方式。"),
        ]
        for row, (label, command, note) in enumerate(actions, start=2):
            card = ttk.Frame(self, padding=(18, 14))
            card.grid(row=row, column=0, sticky="ew", pady=5)
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=label, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=note, style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
            ttk.Button(card, text="執行", command=command).grid(row=0, column=1, rowspan=2, padx=(20, 0))


PAGE_SECTIONS = [("home", "首頁"), ("about", "關於"), ("chronology", "大事記"),
                 ("works", "作品"), ("exhibitions", "展覽"), ("classes", "油畫教學"),
                 ("writings", "文章／出版品"), ("contact", "聯絡我們"), ("maintenance", "預覽與維護")]


def form_snapshot(form) -> tuple:
    """Read visible form inputs on the UI thread to detect unsaved new records."""
    values = []
    def visit(parent):
        for child in parent.winfo_children():
            if isinstance(child, Text):
                values.append(child.get("1.0", "end-1c"))
            elif isinstance(child, (ttk.Entry, ttk.Combobox)):
                values.append(child.get())
            visit(child)
    visit(form)
    for value in vars(form).values():
        if isinstance(value, BooleanVar):
            values.append(value.get())
        elif isinstance(value, dict):
            values.extend(item.get() for item in value.values() if isinstance(item, BooleanVar))
    return tuple(values)


class ManagerWorkspace(ttk.Frame):
    """One page sidebar, one task toolbar, and persistent drafts per task."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.forms = {}
        self.baselines = {}
        self.active_key = None
        sidebar = ttk.Frame(self, padding=(8, 12))
        sidebar.pack(side="left", fill="y")
        self.page_buttons = {}
        for page, label in PAGE_SECTIONS:
            button = ttk.Button(sidebar, text=label, width=15, command=lambda page=page: self.show_page(page))
            button.pack(fill="x", pady=3)
            self.page_buttons[page] = button
        main = ttk.Frame(self)
        main.pack(side="left", fill="both", expand=True)
        self.title = ttk.Label(main, style="FormTitle.TLabel", padding=(20, 12))
        self.title.pack(anchor="w")
        self.toolbar = ttk.Frame(main, padding=(20, 0, 20, 10))
        self.toolbar.pack(fill="x")
        self.content = ttk.Frame(main)
        self.content.pack(fill="both", expand=True)
        self.last_tasks = {}
        self.show_page("home")

    def show_page(self, page):
        if self.app.busy:
            return
        self.page = page
        self.title.configure(text=dict(PAGE_SECTIONS)[page])
        for key, button in self.page_buttons.items():
            button.state(["pressed"] if key == page else ["!pressed"])
        for child in self.toolbar.winfo_children():
            child.destroy()
        tasks = [("edit", "編輯內容")]
        if page == "maintenance":
            tasks = [("maintenance", "預覽與維護")]
        elif page != "chronology":
            tasks.append(("images", "頁面封面／圖片"))
        if page in {"works", "exhibitions", "writings"}:
            tasks.append(("new", {"works": "＋新增作品", "exhibitions": "＋新增展覽", "writings": "＋新增文章／出版品"}[page]))
        if page == "exhibitions":
            tasks.append(("current", "指定當期展覽"))
        self.task_buttons = {}
        for task, label in tasks:
            button = ttk.Button(self.toolbar, text=label, command=lambda task=task: self.show_task(task))
            button.pack(side="left", padx=(0, 8))
            self.task_buttons[task] = button
        self.show_task(self.last_tasks.get(page, tasks[0][0]))

    def show_task(self, task):
        if self.app.busy:
            return
        key = (self.page, task)
        for form in self.forms.values():
            form.pack_forget()
        if key not in self.forms:
            if task == "edit":
                form = PageTextForm(self.content, self.app, self.page)
            elif task == "images":
                form = PageImageForm(self.content, self.app, self.page, records=False)
            elif task == "maintenance":
                form = MaintenancePanel(self.content, self.app)
            elif task == "current":
                form = ExhibitionForm(self.content, self.app, mode="current")
            else:
                constructor = {"works": WorkForm, "writings": ArticleForm, "exhibitions": partial(ExhibitionForm, mode="new")}[self.page]
                form = constructor(self.content, self.app)
            self.forms[key] = form
            self.baselines[key] = form_snapshot(form)
        form = self.forms[key]
        if task == "current":
            form.refresh_current_choices()
        elif task == "edit":
            form.refresh_documents()
        self.forms[key].pack(fill="both", expand=True)
        self.active_key = key
        self.last_tasks[self.page] = task
        for name, button in self.task_buttons.items():
            button.state(["pressed"] if name == task else ["!pressed"])

    def dirty_forms(self):
        dirty = []
        for key, form in self.forms.items():
            if key[1] in {"maintenance", "current"}:
                continue
            changed = form.has_changes() if hasattr(form, "has_changes") else form_snapshot(form) != self.baselines[key]
            if changed:
                dirty.append(key)
        return dirty

    def mark_saved(self):
        if self.active_key:
            self.baselines[self.active_key] = form_snapshot(self.forms[self.active_key])


class ContentManager(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("沈東榮網站內容管理器")
        self.geometry("1120x820")
        self.minsize(1040, 680)
        self.configure(background="#eee8df")
        self.preview_server: ThreadingHTTPServer | None = None
        self.preview_thread: threading.Thread | None = None
        self.status = StringVar(value="準備就緒")
        self.busy = False
        self._configure_style()

        header = ttk.Frame(self, padding=(28, 20, 28, 16), style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="沈東榮網站內容管理器", style="AppTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="左側選頁面 → 選擇工作 → 編輯 → 儲存變更｜切換頁面會保留草稿",
            style="AppSubtitle.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        self.workspace = ManagerWorkspace(self, self)
        self.workspace.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=18, pady=(0, 4))
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
        self._run_job("更新網站", lambda progress: build_site.build(progress=progress), self._built)

    def _built(self, report) -> None:
        self.status.set(build_summary(report))
        messagebox.showinfo("完成", "網站已更新。\n" + build_summary(report))

    def finish_save(self, label: str) -> None:
        self.workspace.mark_saved()
        def complete(report):
            self.status.set(f"{label}已儲存・{build_summary(report)}")
        self._run_job(f"{label}已儲存，正在更新網站", lambda progress: build_site.build(progress=progress), complete)

    def open_preview(self) -> None:
        if self.workspace.dirty_forms() and not messagebox.askyesno("尚有未儲存內容", "預覽只會顯示已儲存的版本，未儲存的輸入會保留。\n仍要開啟預覽嗎？"):
            return
        def work(progress):
            build_site.build(progress=progress)
            return self._launch_preview()
        self._run_job("準備最新預覽", work, self._preview_opened)

    def _launch_preview(self) -> str:
        if self.preview_server is None:
            handler = partial(QuietHandler, directory=str(ROOT / "dist"))
            try:
                server = PreviewServer(("127.0.0.1", 8000), handler)
            except OSError:
                # Never open an unrelated service that happens to own port 8000.
                server = PreviewServer(("127.0.0.1", 0), handler)
            self.preview_server = server
            self.preview_thread = threading.Thread(target=server.serve_forever, daemon=True, name="site-preview")
            self.preview_thread.start()
        url = f"http://127.0.0.1:{self.preview_server.server_port}/"
        webbrowser.open(url)
        return url

    def _preview_opened(self, url: str) -> None:
        self.status.set(f"本機預覽：{url}（關閉管理器會停止預覽）")

    def _run_job(self, label, work, complete) -> None:
        if self.busy:
            return
        self.busy = True
        self.status.set(label + "…首次處理新圖片可能需要幾分鐘")
        self.progress.start(12)
        controls = []

        def disable(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Combobox, ttk.Checkbutton, ttk.Notebook)):
                    controls.append((widget, widget.state()))
                    widget.state(["disabled"])
                disable(widget)
        disable(self)
        job = LocalJob(work)
        self.active_job = job
        job.start()

        def poll():
            try:
                while True:
                    event, value = job.events.get_nowait()
                    if event == "progress":
                        self.status.set(value)
                        continue
                    self.busy = False
                    self.progress.stop()
                    for widget, states in controls:
                        if widget.winfo_exists():
                            widget.state(["!disabled", *states])
                    if event == "error":
                        self.status.set("處理失敗；已儲存的資料仍保留，可修正後重試")
                        messagebox.showerror("處理失敗", value)
                    else:
                        complete(value)
                    return
            except Empty:
                self.after(75, poll)
        self.after(75, poll)

    def close(self) -> None:
        if self.busy:
            messagebox.showinfo("工作進行中", "正在處理圖片或更新網站，請等進度完成後再關閉。視窗仍可正常操作。")
            return
        if self.workspace.dirty_forms() and not messagebox.askyesno("尚有未儲存內容", "部分頁面仍有未儲存的輸入。\n確定捨棄這些輸入並關閉？"):
            return
        if self.preview_server is not None:
            self.preview_server.shutdown()
            self.preview_server.server_close()
        self.destroy()


def generated_slug(prefix: str) -> str:
    return f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}"


def exhibition_key(item: dict) -> str:
    """Return a stable identifier for both detailed and legacy exhibition rows."""
    slug = str(item.get("slug", "")).strip()
    if slug:
        return f"slug:{slug}"
    legacy_parts = (
        str(item.get("year", "")),
        str(item.get("title", "")),
        str(item.get("venue", "")),
        str(item.get("city", "")),
    )
    return "legacy:" + "|".join(legacy_parts)


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


def import_record(app, folder: str, record: dict, image_fields: tuple, complete, *, summary=None) -> None:
    """Capture GUI values first; all image validation/copying happens off-thread."""
    target = ROOT / "content" / folder / f'{record["slug"]}.json'
    original = target.read_text(encoding="utf-8") if target.exists() else None
    if original is not None and not messagebox.askyesno("內容已存在", "同名內容已存在，確定要備份後覆寫嗎？"):
        return

    def work(progress):
        updated = json.loads(json.dumps(record, ensure_ascii=False))
        for key in image_fields:
            values = updated[key] if isinstance(updated[key], list) else [updated[key]]
            names = []
            for value in values:
                progress(f"匯入圖片：{Path(value).name}")
                names.append(import_page_image(value, ROOT / "static/assets/images"))
            updated[key] = names if isinstance(updated[key], list) else names[0]
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != original:
            raise ValueError("同名內容已被其他程式更新，請重新載入後再儲存。")
        backup = ROOT / ".codex-work/content-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup.mkdir(parents=True)
        if original is not None:
            shutil.copy2(target, backup / target.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if summary is not None:
            summary_path = ROOT / "content/exhibitions.json"
            summaries = build_site.load_json(summary_path)
            shutil.copy2(summary_path, backup / summary_path.name)
            if summary.get("current"):
                for item in summaries:
                    item.pop("current", None)
            summaries = [item for item in summaries if item.get("slug") != record["slug"]]
            summaries.append(summary)
            summaries.sort(key=lambda item: str(item.get("year", "")), reverse=True)
            summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    app._run_job("匯入圖片並儲存", work, lambda _result: complete())


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
