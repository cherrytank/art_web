"""多圖格式與不建立備份的刪除測試。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_site
from content_format import parse_markup, blocks_to_markup, plain_summary
from content_operations import delete_record, import_inline_images


class ContentOperationsTests(unittest.TestCase):
    def test_inline_images_roundtrip_and_safe_render(self):
        text = '第一段\n\n![細部說明](picture.jpg)\n\n## 第二段'
        blocks = parse_markup(text)
        self.assertEqual(blocks_to_markup(blocks), text)
        self.assertEqual(plain_summary(blocks), '第一段')
        with patch.object(build_site, 'responsive_image', return_value='<img>'):
            html = build_site.render_article_blocks(blocks)
            self.assertLess(html.index('第一段'), html.index('<img>'))
            self.assertLess(html.index('<img>'), html.index('第二段'))
            with self.assertRaises(ValueError):
                build_site.inline_content_image('../private.png', '說明')

    def test_inline_import_converts_nested_paths(self):
        data = {'body': parse_markup('![說明](C:/photo.jpg)')}
        with patch('content_operations.import_page_image', return_value='imported.jpg'):
            import_inline_images(data, Path('assets'))
        self.assertEqual(data['body'][0]['src'], 'imported.jpg')

    def test_delete_work_cleans_references_without_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'content/works/test.json'
            detail = root / 'content/exhibition_details/show.json'
            for path in (work, detail): path.parent.mkdir(parents=True, exist_ok=True)
            original = json.dumps({'kind':'work', 'slug':'test'})
            work.write_text(original)
            detail.write_text(json.dumps({'selected_work_slugs':['test', 'other']}))
            delete_record(root, work, original)
            self.assertFalse(work.exists())
            self.assertEqual(json.loads(detail.read_text())['selected_work_slugs'], ['other'])
            self.assertFalse((root / '.codex-work/content-backups').exists())

    def test_delete_current_exhibition_and_reject_stale_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / 'content/exhibition_details/show.json'
            record.parent.mkdir(parents=True)
            original = json.dumps({'kind':'exhibition', 'slug':'show'})
            record.write_text(original)
            summary = root / 'content/exhibitions.json'
            summary.write_text(json.dumps([{'slug':'show','current':True}, {'title':'保留'}]))
            with self.assertRaises(ValueError): delete_record(root, record, '{}')
            delete_record(root, record, original)
            self.assertEqual(json.loads(summary.read_text(encoding='utf-8')), [{'title':'保留'}])

    def test_failed_deletion_restores_references_without_backup_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / 'content/exhibition_details/show.json'
            record.parent.mkdir(parents=True)
            original = json.dumps({'kind':'exhibition', 'slug':'show'})
            record.write_text(original)
            summary = root / 'content/exhibitions.json'
            before = json.dumps([{'slug':'show','current':True}])
            summary.write_text(before)
            with patch.object(Path, 'unlink', side_effect=PermissionError('檔案被占用')):
                with self.assertRaises(PermissionError): delete_record(root, record, original)
            self.assertEqual(record.read_text(), original)
            self.assertEqual(summary.read_text(), before)
            self.assertFalse((root / '.codex-work').exists())


if __name__ == '__main__': unittest.main()
