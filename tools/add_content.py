"""Create a new article or work record, then rebuild the static site."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path

import build_site
from image_pipeline import SUPPORTED_EXTENSIONS


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "static" / "assets" / "images"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORIES = {
    "art-criticism": ("藝術評論", "Art Criticism"),
    "painting-notes": ("創作筆記", "Painting Notes"),
    "artwork-story": ("作品故事", "Artwork Story"),
}


def ask(value: str | None, label: str, default: str = "") -> str:
    if value:
        return value.strip()
    suffix = f" [{default}]" if default else ""
    answer = input(f"{label}{suffix}: ").strip()
    return answer or default


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit("slug 僅能使用小寫英文字母、數字與連字號，例如: spring-light")
    return slug


def prepare_image(value: str) -> str:
    source = Path(value).expanduser()
    if source.is_file():
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            choices = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise SystemExit(f"圖片格式不支援，請使用：{choices}")
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        target = ASSET_DIR / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target.name
    existing = ASSET_DIR / value
    if not existing.is_file():
        raise SystemExit(f"找不到圖片：{value}\n請提供完整路徑，或先將圖片放進 {ASSET_DIR}")
    if existing.suffix.lower() not in SUPPORTED_EXTENSIONS:
        choices = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise SystemExit(f"圖片格式不支援，請使用：{choices}")
    return existing.name


def save_record(folder: str, slug: str, record: dict, force: bool) -> Path:
    target = ROOT / "content" / folder / f"{slug}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise SystemExit(f"內容已存在：{target}\n若確定要覆寫，請加上 --force")
    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def add_article(args: argparse.Namespace) -> Path:
    slug = validate_slug(ask(args.slug, "網址代稱 slug"))
    title = ask(args.title, "文章標題")
    article_date = ask(args.date, "日期 YYYY-MM-DD", date.today().isoformat())
    try:
        date.fromisoformat(article_date)
    except ValueError as error:
        raise SystemExit("日期格式需為 YYYY-MM-DD") from error
    category = ask(args.category, "分類 art-criticism / painting-notes / artwork-story", "painting-notes")
    if category not in CATEGORIES:
        raise SystemExit(f"分類必須是：{', '.join(CATEGORIES)}")
    image = prepare_image(ask(args.image, "主圖檔名或完整路徑"))
    image_alt = ask(args.image_alt, "圖片替代文字")
    summary = ask(args.summary, "文章摘要")
    paragraphs = args.paragraph or []
    if not paragraphs:
        raw = ask(None, "正文段落（多段請用 | 分隔）")
        paragraphs = [part.strip() for part in raw.split("|") if part.strip()]
    category_zh, category_en = CATEGORIES[category]
    record = {
        "kind": "article",
        "slug": slug,
        "title": title,
        "date": article_date,
        "category": category,
        "category_zh": category_zh,
        "category_en": category_en,
        "image": image,
        "image_alt": image_alt,
        "summary": summary,
        "body": [
            {"type": "lead" if index == 0 else "paragraph", "text": paragraph}
            for index, paragraph in enumerate(paragraphs)
        ],
    }
    return save_record("articles", slug, record, args.force)


def add_work(args: argparse.Namespace) -> Path:
    slug = validate_slug(ask(args.slug, "網址代稱 slug"))
    title_zh = ask(args.title_zh, "作品中文名")
    title_en = ask(args.title_en, "作品英文名")
    year = ask(args.year, "年份", str(date.today().year))
    image = prepare_image(ask(args.image, "作品圖片檔名或完整路徑"))
    alt = ask(args.alt, "圖片替代文字")
    medium_zh = ask(args.medium_zh, "媒材（中文）", "油彩、畫布")
    medium_en = ask(args.medium_en, "媒材（英文）", "Oil on canvas")
    dimensions = ask(args.dimensions, "尺寸", "尺寸待補")
    collection = ask(args.collection, "典藏資訊（可留白）")
    description = ask(args.description, "作品說明")
    record = {
        "kind": "work",
        "slug": slug,
        "title_zh": title_zh,
        "title_en": title_en,
        "year": year,
        "image": image,
        "alt": alt,
        "medium_zh": medium_zh,
        "medium_en": medium_en,
        "dimensions": dimensions,
        "collection": collection,
        "featured": bool(args.featured),
        "description": [description],
    }
    return save_record("works", slug, record, args.force)


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slug")
    parser.add_argument("--image")
    parser.add_argument("--force", action="store_true", help="覆寫同名內容")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="新增網站文章或作品並重建 HTML")
    subparsers = parser.add_subparsers(dest="command", required=True)

    article = subparsers.add_parser("article", help="新增文章")
    add_common_flags(article)
    article.add_argument("--title")
    article.add_argument("--date")
    article.add_argument("--category", choices=CATEGORIES)
    article.add_argument("--image-alt")
    article.add_argument("--summary")
    article.add_argument("--paragraph", action="append", help="可重複使用以加入多個段落")

    work = subparsers.add_parser("work", help="新增作品")
    add_common_flags(work)
    work.add_argument("--title-zh")
    work.add_argument("--title-en")
    work.add_argument("--year")
    work.add_argument("--alt")
    work.add_argument("--medium-zh")
    work.add_argument("--medium-en")
    work.add_argument("--dimensions")
    work.add_argument("--collection")
    work.add_argument("--description")
    work.add_argument("--featured", action="store_true")

    subparsers.add_parser("build", help="最佳化所有圖片並重建 HTML")
    return parser


def main() -> None:
    args = create_parser().parse_args()
    if args.command == "article":
        target = add_article(args)
        print(f"已新增文章資料：{target}")
    elif args.command == "work":
        target = add_work(args)
        print(f"已新增作品資料：{target}")
    build_site.build()


if __name__ == "__main__":
    main()
