"""Fast regression checks for editorial formatting, privacy and the local UI.

Run: python -m unittest discover -s tools -p "test_*.py"
GUI checks are skipped if Tk cannot open a display (for example, Linux CI).
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import build_site
from content_format import blocks_to_markup, parse_markup, render_blocks, plain_summary
from page_images import PAGE_IMAGE_LABELS, import_page_image
from PIL import Image
from image_pipeline import build_responsive_images


class ContentTests(unittest.TestCase):
    def test_work_numbers_are_numeric_ascending_before_year(self):
        works = [
            {"slug": "small", "catalog_number": "9", "year": "2026"},
            {"slug": "large", "catalog_number": "10", "year": "2025"},
            {"slug": "newest", "catalog_number": "026021", "year": "2026"},
            {"slug": "empty", "catalog_number": "", "year": "2027"},
            {"slug": "missing", "year": "2028"},
        ]
        self.assertEqual([work["slug"] for work in build_site.sort_works(works)],
                         ["small", "large", "newest", "empty", "missing"])
        self.assertEqual(works[0]["slug"], "small")

    def test_every_page_slot_uses_configured_image_and_options(self):
        for slot in PAGE_IMAGE_LABELS:
            with patch.object(build_site, "load_json", return_value={slot: {"image": "chosen.png", "alt": "替換說明"}}):
                with patch.object(build_site, "responsive_image", return_value="rendered") as render:
                    self.assertEqual(build_site.page_image(slot, "../", "55vw", priority=True), "rendered")
                    render.assert_called_once_with("chosen.png", "替換說明", "../", "55vw", priority=True)

    def test_title_breaks_escape_html(self):
        self.assertEqual(build_site.display_title({"title": "<標題>"}), "&lt;標題&gt;")
        self.assertEqual(build_site.display_title({"title": "列表", "title_lines": ["第一行", "<第二行>"]}), "第一行<br>&lt;第二行&gt;")

    def test_formatted_work_reaches_detail_html_and_plain_metadata(self):
        work = build_site.load_records("works")[0]
        work["description"] = parse_markup("! **作品引言**\n\n## 大標\n\n::: box\n補充文字\n:::")
        with patch.object(build_site, "responsive_image", return_value="<img>"), patch.object(build_site, "write_page") as write:
            build_site.build_works(build_site.load_json(build_site.CONTENT / "site.json"), [work])
        detail = write.call_args.kwargs
        self.assertEqual(detail["description"], "作品引言")
        self.assertIn('class="work-body formatted-content"', detail["main"])
        self.assertIn('<h2>大標</h2>', detail["main"])
        self.assertIn('<div class="text-box">補充文字</div>', detail["main"])

    def test_collector_names_are_not_rendered_or_searchable(self):
        record = {"title_zh": "測試", "slug": "test", "year": 2026, "dimensions": "10F", "image": "test.png", "alt": "測試", "collection": "私人姓名收藏"}
        with patch.object(build_site, "responsive_image", return_value="<img>"):
            card = build_site.work_card(record, "../")
        self.assertNotIn("私人姓名", card)
        self.assertIn("已收藏", card)
        self.assertEqual(build_site.collection_label({"collection": ""}), "")


class EditorTests(unittest.TestCase):
    def setUp(self):
        import tkinter
        import content_manager
        self.manager = content_manager
        try:
            self.window = tkinter.Tk()
            self.window.withdraw()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        self.addCleanup(self.window.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(build_site.CONTENT, self.root / "content")
        self.root_patch = patch.object(content_manager, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.app = Mock()
        self.panel = content_manager.PageTextForm(content_manager.ttk.Notebook(self.window), self.app)

    def test_all_page_fields_load_without_changes(self):
        for choice in self.panel.documents:
            self.panel.choice.set(choice)
            self.panel.load_page()
            self.assertFalse(self.panel.has_changes(), choice)
            self.assertTrue(self.panel.widgets, choice)

    def test_edit_save_backup_and_title_line_breaks(self):
        choice = next(key for key, value in self.panel.documents.items() if value == "articles/covered-colors.json")
        self.panel.choice.set(choice)
        self.panel.load_page()
        original = self.panel.original
        widget = next(widget for keys, widget, _ in self.panel.widgets if keys == ("title_lines",))
        widget.delete("1.0", "end")
        widget.insert("1.0", "第一行\n第二行")
        self.assertTrue(self.panel.has_changes())
        with patch.object(self.manager.messagebox, "askyesno", return_value=True):
            self.panel.save()
        data = json.loads(self.panel.path.read_text(encoding="utf-8"))
        self.assertEqual(data["title_lines"], ["第一行", "第二行"])
        self.assertEqual(data["body"], json.loads(original)["body"])
        backups = list((self.root / ".codex-work/content-backups").rglob("*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
        self.app.finish_save.assert_called_once()

    def test_external_edits_are_not_overwritten(self):
        self.panel.path.write_text(self.panel.original + "\n", encoding="utf-8")
        with patch.object(self.manager.messagebox, "showerror") as error:
            self.panel.save()
        error.assert_called_once()
        self.app.finish_save.assert_not_called()

    def select_record(self, folder):
        self.panel.choice.set(next(key for key, value in self.panel.documents.items() if value.startswith(folder + "/")))
        self.panel.load_page()
        return next(widget for _, widget, mode in self.panel.widgets if mode == "formatted")

    def test_existing_work_and_article_body_can_be_replaced_and_reordered(self):
        for folder, field in [("works", "description"), ("articles", "body")]:
            with self.subTest(folder=folder):
                widget = self.select_record(folder)
                before = json.loads(self.panel.original)
                source = "## 新大標\n\n新段落 **重點**\n\n::: box\n補充\n:::"
                widget.delete("1.0", "end")
                widget.insert("1.0", source)
                with patch.object(self.manager.messagebox, "askyesno", return_value=True):
                    self.panel.save()
                after = json.loads(self.panel.original)
                self.assertEqual(after[field], parse_markup(source))
                for key, value in before.items():
                    if key != field:
                        self.assertEqual(after[key], value, key)
                self.assertFalse(self.panel.has_changes())

    def test_invalid_body_and_cancel_leave_record_unchanged(self):
        widget = self.select_record("works")
        original = self.panel.original
        widget.insert("end", "\n\n::: box\n沒有結尾")
        with patch.object(self.manager.messagebox, "showerror") as error:
            self.panel.save()
        error.assert_called_once()
        self.assertEqual(self.panel.path.read_text(encoding="utf-8"), original)
        widget.delete("1.0", "end")
        widget.insert("1.0", "新的內文")
        with patch.object(self.manager.messagebox, "askyesno", return_value=False):
            self.panel.save()
        self.assertEqual(self.panel.path.read_text(encoding="utf-8"), original)
        self.app.finish_save.assert_not_called()

    def test_new_record_appears_without_restarting_and_keeps_unsaved_edits(self):
        widget = self.select_record("works")
        widget.insert("end", "尚未儲存的文字")
        new_record = dict(self.panel.data, slug="new-test", title_zh="新的作品")
        (self.root / "content/works/new-test.json").write_text(json.dumps(new_record), encoding="utf-8")
        self.panel.refresh_documents()
        self.assertIn("works/new-test.json", self.panel.documents.values())
        self.assertTrue(self.panel.has_changes())
        self.assertIn("尚未儲存的文字", widget.get("1.0", "end"))

    def test_work_body_can_be_cleared(self):
        widget = self.select_record("works")
        widget.delete("1.0", "end")
        with patch.object(self.manager.messagebox, "askyesno", return_value=True):
            self.panel.save()
        self.assertEqual(json.loads(self.panel.original)["description"], [])

    def image_panel(self):
        return self.manager.PageImageForm(self.manager.ttk.Notebook(self.window), self.app)

    def make_image(self, folder, color):
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / "cover.png"
        Image.new("RGB", (40, 60), color).save(image)
        return image

    def test_image_editor_loads_all_main_and_detail_pages(self):
        panel = self.image_panel()
        self.assertGreater(len(panel.targets), len(PAGE_IMAGE_LABELS))
        for choice in panel.targets:
            panel.choice.set(choice)
            panel.load_page()
            self.assertFalse(panel.has_changes())
            self.assertTrue(panel.image_path.get())
            self.assertTrue(panel.image_alt.get())

    def test_cover_save_is_independent_and_keeps_backup(self):
        panel = self.image_panel()
        image = self.make_image(self.root / "import", "red")
        before = json.loads(panel.original)
        panel.image_path.set(str(image))
        panel.image_alt.set("新的首頁封面")
        with patch.object(self.manager.messagebox, "askyesno", return_value=True):
            panel.save()
        data = json.loads(panel.path.read_text(encoding="utf-8"))
        self.assertNotEqual(data["home"]["image"], before["home"]["image"])
        self.assertEqual(data["home"]["alt"], "新的首頁封面")
        self.assertEqual(data["works"], before["works"])
        self.assertTrue((self.root / "static/assets/images" / data["home"]["image"]).exists())
        self.assertEqual(len(list((self.root / ".codex-work/content-backups").rglob("page_images.json"))), 1)
        self.app.finish_save.assert_called_once()

    def test_same_filename_imports_do_not_overwrite_each_other(self):
        assets = self.root / "static/assets/images"
        first = self.make_image(self.root / "first", "red")
        second = self.make_image(self.root / "second", "blue")
        first_name = import_page_image(str(first), assets)
        first_bytes = (assets / first_name).read_bytes()
        second_name = import_page_image(str(second), assets)
        self.assertNotEqual(first_name, second_name)
        self.assertEqual((assets / first_name).read_bytes(), first_bytes)
        self.assertEqual(import_page_image(str(first), assets), first_name)
        self.assertEqual(import_page_image(first_name, assets), first_name)

    def test_imported_cover_uses_responsive_and_lightbox_pipeline(self):
        assets = self.root / "static/assets/images"
        name = import_page_image(str(self.make_image(self.root / "new", "white")), assets)
        catalog, report = build_responsive_images(assets, self.root / "output")
        with patch.object(build_site, "IMAGE_CATALOG", catalog), patch.object(build_site, "load_json", return_value={"works": {"image": name, "alt": "新封面"}}):
            html = build_site.page_image("works", "../", "55vw", priority=True, lightbox=True)
        self.assertEqual(report.source_count, 1)
        self.assertIn('srcset=', html)
        self.assertIn('width="40" height="60"', html)
        self.assertIn('data-lightbox-src=', html)
        self.assertIn('fetchpriority="high"', html)
        self.assertIn(name.removesuffix(".png"), html)

    def test_missing_image_does_not_change_settings(self):
        panel = self.image_panel()
        before = panel.original
        panel.image_path.set(str(self.root / "missing.png"))
        with patch.object(self.manager.messagebox, "askyesno", return_value=True), patch.object(self.manager.messagebox, "showerror") as error:
            panel.save()
        error.assert_called_once()
        self.assertEqual(panel.path.read_text(encoding="utf-8"), before)
        self.app.finish_save.assert_not_called()

    def test_article_cover_updates_its_record_only(self):
        panel = self.image_panel()
        panel.choice.set(next(key for key, target in panel.targets.items() if target[0].name == "covered-colors.json"))
        panel.load_page()
        original = json.loads(panel.original)
        panel.image_path.set(str(self.make_image(self.root / "new", "green")))
        with patch.object(self.manager.messagebox, "askyesno", return_value=True):
            panel.save()
        data = json.loads(panel.path.read_text(encoding="utf-8"))
        self.assertNotEqual(data["image"], original["image"])
        self.assertEqual(data["body"], original["body"])
        self.assertEqual(data["title_lines"], original["title_lines"])

    def test_cover_cancel_and_external_edits_do_not_save(self):
        panel = self.image_panel()
        panel.image_alt.set("未儲存")
        with patch.object(self.manager.messagebox, "askyesno", return_value=False):
            panel.save()
        self.assertEqual(panel.path.read_text(encoding="utf-8"), panel.original)
        panel.path.write_text(panel.original + "\n", encoding="utf-8")
        with patch.object(self.manager.messagebox, "showerror") as error:
            panel.save()
        error.assert_called_once()
        self.app.finish_save.assert_not_called()


class FormattingTests(unittest.TestCase):
    def test_all_formats_roundtrip(self):
        source = "## 大標\n\n### 小標\n\n! 引言\n\n段落\n換行 **重點**\n\n> 引用\n> 第二行\n\n- 甲\n- 乙\n\n::: box\n背景框\n\n第二段\n:::"
        blocks = parse_markup(source)
        self.assertEqual([block["type"] for block in blocks], ["heading", "subheading", "lead", "paragraph", "quote", "list", "box"])
        self.assertEqual(parse_markup(blocks_to_markup(blocks)), blocks)
        rendered = render_blocks(blocks)
        for token in ["<h2>", "<h3>", 'class="lead"', "<strong>重點</strong>", "<blockquote>", "<ul><li>甲</li><li>乙</li></ul>", 'class="text-box"']:
            self.assertIn(token, rendered)

    def test_html_is_escaped_and_summary_is_plain(self):
        blocks = parse_markup('**<script>alert(1)</script>**\n<img src=x onerror="alert(2)">')
        rendered = render_blocks(blocks)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("<strong>&lt;script&gt;", rendered)
        self.assertEqual(plain_summary(parse_markup("**重點**")), "重點")

    def test_legacy_paragraphs_and_reserved_markers(self):
        paragraphs = ["一般文字", "## 普通文字\n\\路徑", "::: 不是框"]
        self.assertEqual([block["text"] for block in parse_markup(blocks_to_markup(paragraphs))], paragraphs)
        self.assertEqual(render_blocks(["舊作品說明"]), "<p>舊作品說明</p>")
        self.assertEqual(parse_markup(""), [])
        for path in (build_site.CONTENT / "articles").glob("*.json"):
            blocks = json.loads(path.read_text(encoding="utf-8"))["body"]
            self.assertEqual(parse_markup(blocks_to_markup(blocks)), blocks)

    def test_invalid_boxes_are_rejected(self):
        for source in ["::: box\n未關閉", "::: other\n文字\n:::", ":::"]:
            with self.assertRaises(ValueError):
                parse_markup(source)


if __name__ == "__main__":
    unittest.main()
