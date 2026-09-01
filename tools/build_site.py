"""Build the complete static site from JSON content and HTML templates.

This project intentionally uses only Python's standard library so the same
command works locally and in GitHub Actions without installing dependencies.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
DIST = ROOT / "dist"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAV_KEYS = ("home", "about", "works", "exhibitions", "classes", "writings", "contact")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render(template: str, **values: object) -> str:
    """Replace small, explicit ``{{name}}`` slots in a trusted template."""
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    unresolved = sorted(set(re.findall(r"{{([a-z_]+)}}", template)))
    if unresolved:
        raise ValueError(f"Unresolved template values: {', '.join(unresolved)}")
    return template


def load_records(folder: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((CONTENT / folder).glob("*.json")):
        record = load_json(path)
        slug = record.get("slug", "")
        if not SLUG_RE.fullmatch(slug):
            raise ValueError(f"Invalid slug in {path}: {slug!r}")
        if path.stem != slug:
            raise ValueError(f"Filename and slug differ: {path.name} / {slug}")
        records.append(record)
    return records


def write_page(
    output: str,
    *,
    title: str,
    description: str,
    main: str,
    root: str,
    active: str,
    body_class: str,
    social_image: str = "og.png",
) -> None:
    base = read_text(TEMPLATES / "base.html")
    active_values = {
        f"{key}_active": 'aria-current="page"' if key == active else ""
        for key in NAV_KEYS
    }
    social_tags = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{escape(title)}">',
        f'<meta name="twitter:description" content="{escape(description)}">',
    ]
    if SITE_URL:
        page_path = output.removesuffix("index.html")
        page_url = f"{SITE_URL}/{page_path}".rstrip("/") + "/"
        image_url = f"{SITE_URL}/assets/images/{social_image}"
        social_tags.extend(
            [
                f'<link rel="canonical" href="{escape(page_url)}">',
                f'<meta property="og:url" content="{escape(page_url)}">',
                f'<meta property="og:image" content="{escape(image_url)}">',
                f'<meta name="twitter:image" content="{escape(image_url)}">',
            ]
        )
    document = render(
        base,
        title=escape(title),
        description=escape(description),
        root=root,
        body_class=body_class,
        main=main,
        year=date.today().year,
        social_meta="\n  ".join(social_tags),
        **active_values,
    )
    target = DIST / output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")


def build_home(site: dict[str, Any]) -> None:
    write_page(
        "index.html",
        title=f"{site['name_zh']}｜{site['role_zh']}",
        description=site["tagline_zh"],
        main=read_text(TEMPLATES / "home.html"),
        root="",
        active="home",
        body_class="page-home",
    )


def build_about(site: dict[str, Any]) -> None:
    data = load_json(CONTENT / "about.json")
    education = "".join(
        f'<div class="timeline-item"><time>{escape(item["year"])}</time>'
        f'<p>{escape(item["zh"])}<small>{escape(item["en"])}</small></p></div>'
        for item in data["education"]
    )
    positions = "".join(
        f'<p><time>{escape(item["period"])}</time><span>{escape(item["title"])}</span></p>'
        for item in data["positions"]
    )
    main = render(
        read_text(TEMPLATES / "about.html"),
        root="../",
        intro_zh=escape(data["intro_zh"]),
        intro_en=escape(data["intro_en"]),
        philosophy=escape(data["philosophy"]),
        education=education,
        positions=positions,
        current=escape(data["current"]),
    )
    write_page(
        "about/index.html",
        title=f"關於｜{site['name_zh']}",
        description=data["intro_zh"],
        main=main,
        root="../",
        active="about",
        body_class="page-about",
    )


def work_card(work: dict[str, Any], root: str) -> str:
    search = " ".join(
        str(work.get(key, ""))
        for key in ("title_zh", "title_en", "year", "medium_zh", "dimensions")
    ).lower()
    return (
        f'<article class="work-card" data-year="{escape(work["year"])}" '
        f'data-search="{escape(search)}"><a href="{root}works/{escape(work["slug"])}/index.html">'
        f'<div class="work-image"><img src="{root}assets/images/{escape(work["image"])}" '
        f'alt="{escape(work["alt"])}" loading="lazy"></div>'
        f'<div class="work-meta"><h2>{escape(work["title_zh"])}'
        f'<small>{escape(work["title_en"])}</small></h2>'
        f'<p>{escape(work["year"])}<br>{escape(work["dimensions"])}</p></div></a></article>'
    )


def build_works(site: dict[str, Any], works: list[dict[str, Any]]) -> None:
    works = sorted(works, key=lambda item: (item["year"], item["title_zh"]), reverse=True)
    years = sorted({str(work["year"]) for work in works}, reverse=True)
    year_options = "".join(f'<option value="{escape(year)}">{escape(year)}</option>' for year in years)
    main = render(
        read_text(TEMPLATES / "works-index.html"),
        root="../",
        year_options=year_options,
        work_count=len(works),
        works="".join(work_card(work, "../") for work in works),
    )
    write_page(
        "works/index.html",
        title=f"作品｜{site['name_zh']}",
        description="沈東榮油畫作品選集：自然風景、花卉與靜物。",
        main=main,
        root="../",
        active="works",
        body_class="page-works",
    )

    detail_template = read_text(TEMPLATES / "work-detail.html")
    for work in works:
        collection_row = ""
        if work.get("collection"):
            collection_row = f'<div><dt>典藏</dt><dd>{escape(work["collection"])}</dd></div>'
        description = "".join(f"<p>{escape(text)}</p>" for text in work.get("description", []))
        detail = render(
            detail_template,
            root="../../",
            image=escape(work["image"]),
            alt=escape(work["alt"]),
            year=escape(work["year"]),
            title_zh=escape(work["title_zh"]),
            title_en=escape(work["title_en"]),
            medium_zh=escape(work["medium_zh"]),
            medium_en=escape(work["medium_en"]),
            dimensions=escape(work["dimensions"]),
            collection_row=collection_row,
            description=description,
            slug=escape(work["slug"]),
        )
        write_page(
            f"works/{work['slug']}/index.html",
            title=f"{work['title_zh']}｜{site['name_zh']}",
            description=work.get("description", [work["title_zh"]])[0],
            main=detail,
            root="../../",
            active="works",
            body_class="page-work-detail",
            social_image=work["image"],
        )


def build_exhibitions(site: dict[str, Any]) -> None:
    items = load_json(CONTENT / "exhibitions.json")
    rows = "".join(
        f'<article class="exhibition-row"><time>{escape(item["year"])}</time>'
        f'<h3>《{escape(item["title"])}》</h3><p>{escape(item["venue"])}</p>'
        f'<p>{escape(item["city"])}</p></article>'
        for item in items
    )
    main = render(read_text(TEMPLATES / "exhibitions.html"), root="../", exhibitions=rows)
    write_page(
        "exhibitions/index.html",
        title=f"展覽資訊｜{site['name_zh']}",
        description="沈東榮歷年個展、藝術活動與展覽紀錄。",
        main=main,
        root="../",
        active="exhibitions",
        body_class="page-exhibitions",
    )


def build_classes(site: dict[str, Any]) -> None:
    data = load_json(CONTENT / "classes.json")
    schedule = "".join(f"<span>{escape(item)}</span>" for item in data["schedule"])
    features = "".join(
        f'<li><h3>{escape(item["title"])}</h3><p>{escape(item["text"])}</p></li>'
        for item in data["features"]
    )
    main = render(
        read_text(TEMPLATES / "classes.html"),
        root="../",
        title=escape(data["title"]),
        intro=escape(data["intro"]),
        course=escape(data["course"]),
        schedule=schedule,
        location=escape(data["location"]),
        features=features,
    )
    write_page(
        "classes/index.html",
        title=f"油畫教學｜{site['name_zh']}",
        description=data["intro"],
        main=main,
        root="../",
        active="classes",
        body_class="page-classes",
    )


def date_display(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y.%m.%d")


def article_row(article: dict[str, Any], root: str) -> str:
    return (
        f'<article class="article-row" data-category="{escape(article["category"])}">'
        f'<time datetime="{escape(article["date"])}">{date_display(article["date"])}</time>'
        f'<div><h2>{escape(article["title"])}</h2><p>{escape(article["category_en"])}・'
        f'{escape(article["category_zh"])}</p></div>'
        f'<img src="{root}assets/images/{escape(article["image"])}" '
        f'alt="{escape(article["image_alt"])}" loading="lazy">'
        f'<a href="{root}writings/{escape(article["slug"])}/index.html">Read article →</a></article>'
    )


def render_article_blocks(blocks: list[dict[str, str]]) -> str:
    output: list[str] = []
    for block in blocks:
        text = escape(block["text"])
        kind = block.get("type", "paragraph")
        if kind == "heading":
            output.append(f"<h2>{text}</h2>")
        elif kind == "quote":
            output.append(f"<blockquote>{text}</blockquote>")
        elif kind == "lead":
            output.append(f'<p class="lead">{text}</p>')
        elif kind == "paragraph":
            output.append(f"<p>{text}</p>")
        else:
            raise ValueError(f"Unsupported article block type: {kind}")
    return "".join(output)


def build_writings(site: dict[str, Any], articles: list[dict[str, Any]]) -> None:
    articles = sorted(articles, key=lambda item: item["date"], reverse=True)
    main = render(
        read_text(TEMPLATES / "writings-index.html"),
        root="../",
        articles="".join(article_row(article, "../") for article in articles),
    )
    write_page(
        "writings/index.html",
        title=f"藝評・文章｜{site['name_zh']}",
        description="沈東榮的藝術評論、創作筆記與作品故事。",
        main=main,
        root="../",
        active="writings",
        body_class="page-writings",
    )

    detail_template = read_text(TEMPLATES / "article-detail.html")
    for article in articles:
        detail = render(
            detail_template,
            root="../../",
            date=escape(article["date"]),
            date_display=date_display(article["date"]),
            category_zh=escape(article["category_zh"]),
            category_en=escape(article["category_en"]),
            title=escape(article["title"]),
            summary=escape(article["summary"]),
            image=escape(article["image"]),
            image_alt=escape(article["image_alt"]),
            body=render_article_blocks(article["body"]),
        )
        write_page(
            f"writings/{article['slug']}/index.html",
            title=f"{article['title']}｜{site['name_zh']}",
            description=article["summary"],
            main=detail,
            root="../../",
            active="writings",
            body_class="page-article-detail",
            social_image=article["image"],
        )


def build_contact(site: dict[str, Any]) -> None:
    data = load_json(CONTENT / "contact.json")
    main = render(
        read_text(TEMPLATES / "contact.html"),
        root="../",
        intro=escape(data["intro"]),
        email=escape(data["email"]),
        instagram_url=escape(data["instagram_url"]),
        instagram_handle=escape(data["instagram_handle"]),
    )
    write_page(
        "contact/index.html",
        title=f"聯絡我們｜{site['name_zh']}",
        description=data["intro"],
        main=main,
        root="../",
        active="contact",
        body_class="page-contact",
    )


def build() -> None:
    site = load_json(CONTENT / "site.json")
    works = load_records("works")
    articles = load_records("articles")

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "static" / "css", DIST / "assets" / "css")
    shutil.copytree(ROOT / "static" / "js", DIST / "assets" / "js")
    shutil.copytree(ROOT / "static" / "assets" / "images", DIST / "assets" / "images")
    shutil.copy2(ROOT / "static" / "favicon.svg", DIST / "assets" / "favicon.svg")

    build_home(site)
    build_about(site)
    build_works(site, works)
    build_exhibitions(site)
    build_classes(site)
    build_writings(site, articles)
    build_contact(site)
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    page_count = len(list(DIST.rglob("*.html")))
    print(f"Built {page_count} pages in {DIST}")


if __name__ == "__main__":
    build()
