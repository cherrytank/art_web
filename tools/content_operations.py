"""內容管理器的圖片匯入與刪除作業。"""
import json
from pathlib import Path

from page_images import import_page_image


def import_inline_images(value, asset_dir: Path) -> None:
    """遞迴匯入內文圖片，儲存後只留下網站檔名。"""
    if isinstance(value, dict):
        if value.get("type") == "image":
            value["src"] = import_page_image(value["src"], asset_dir)
        else:
            for child in value.values():
                import_inline_images(child, asset_dir)
    elif isinstance(value, list):
        for child in value:
            import_inline_images(child, asset_dir)


def delete_record(root: Path, path: Path, original: str) -> None:
    """不建立備份檔；作業失敗時用記憶體原文復原，避免引用只更新一半。"""
    content = (root / "content").resolve()
    path = path.resolve()
    if path.parent not in {content / name for name in ("works", "articles", "exhibition_details")} or path.suffix != ".json":
        raise ValueError("只能刪除作品、文章、出版品或展覽記錄。")
    if path.read_text(encoding="utf-8") != original:
        raise ValueError("資料已被其他程式修改，請重新載入後再刪除。")
    record = json.loads(original)
    changes = {}
    if path.parent.name == "exhibition_details":
        summary = content / "exhibitions.json"
        items = json.loads(summary.read_text(encoding="utf-8"))
        changes[summary] = [item for item in items if item.get("slug") != record["slug"]]
    if path.parent.name == "works":
        for detail in (content / "exhibition_details").glob("*.json"):
            item = json.loads(detail.read_text(encoding="utf-8"))
            if record["slug"] in item.get("selected_work_slugs", []):
                item["selected_work_slugs"] = [slug for slug in item["selected_work_slugs"] if slug != record["slug"]]
                changes[detail] = item
    originals = {source: source.read_bytes() for source in [path, *changes]}
    try:
        for target, data in changes.items():
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.unlink()
    except Exception:
        for source, data in originals.items():
            source.write_bytes(data)
        raise
