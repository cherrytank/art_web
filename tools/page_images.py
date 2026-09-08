"""Shared image slots and safe, non-overwriting imports for the local editor."""

import hashlib
from pathlib import Path
import shutil

from PIL import Image
from image_pipeline import SUPPORTED_EXTENSIONS


PAGE_IMAGE_LABELS = {
    "home": "首頁・封面",
    "about": "關於・學經歷封面",
    "philosophy": "關於・創作理念封面",
    "works": "作品・列表封面",
    "exhibitions": "展覽資訊・列表封面",
    "classes": "油畫教學・封面",
    "classes_detail": "油畫教學・下方圖片",
    "writings": "藝評文章・列表封面",
    "contact_logo": "聯絡我們・官方 Logo",
    "home_signature": "首頁・簽名",
    "contact_signature": "聯絡我們・簽名",
}


def import_page_image(value: str, asset_dir: Path) -> str:
    """Keep existing assets; give new imports content-based names to avoid collisions."""
    source = Path(value.strip()).expanduser()
    if not source.is_file():
        source = asset_dir / value.strip()
    if not value.strip() or not source.is_file():
        raise ValueError("找不到圖片，請按「選擇圖片」重新選取。")
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("請選擇 JPG、PNG、WebP 或 AVIF 圖片。")
    try:
        with Image.open(source) as image:
            if getattr(image, "is_animated", False) and image.format not in {"JPEG", "MPO"}:
                raise ValueError("請使用靜態圖片，不支援動態圖片。")
            image.verify()
    except OSError as error:
        raise ValueError("圖片無法讀取，請重新匯出或選擇其他圖片。") from error
    if source.resolve().parent == asset_dir.resolve():
        return source.name
    with source.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    filename = f"page-{digest.hexdigest()}{source.suffix.lower()}"
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / filename
    if not target.exists():
        shutil.copy2(source, target)
    return filename
