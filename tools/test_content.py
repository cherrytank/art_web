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


class ContentTests(unittest.TestCase):
    def test_title_breaks_escape_html(self):
        self.assertEqual(build_site.display_title({"title": "<標題>"}), "&lt;標題&gt;")
        self.assertEqual(build_site.display_title({"title": "列表", "title_lines": ["第一行", "<第二行>"]}), "第一行<br>&lt;第二行&gt;")

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


if __name__ == "__main__":
    unittest.main()
