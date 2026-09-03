"""Build the static site, including responsive delivery images."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from image_pipeline import ImageBuildReport, ResponsiveImage, build_responsive_images


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
DIST = ROOT / "dist"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAV_KEYS = ("home", "about", "works", "exhibitions", "classes", "writings", "contact")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
IMAGE_SOURCE = ROOT / "static" / "assets" / "images"
RESPONSIVE_OUTPUT = DIST / "assets" / "images" / "responsive"
IMAGE_CATALOG: dict[str, ResponsiveImage] = {}
HERO_IMAGE_SIZES = "(max-width: 760px) 100vw, 56vw"
CARD_IMAGE_SIZES = "(max-width: 760px) 100vw, 50vw"
DETAIL_IMAGE_SIZES = "(max-width: 760px) 100vw, 55vw"
ARTICLE_THUMB_SIZES = "(max-width: 760px) 100vw, 180px"


@dataclass(frozen=True)
class BuildReport:
    page_count: int
    images: ImageBuildReport


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def responsive_image(
    filename: str,
    alt: str,
    root: str,
    sizes: str,
    *,
    css_class: str = "",
    priority: bool = False,
) -> str:
    """Render an image that lets each device choose an appropriate width."""
    try:
        asset = IMAGE_CATALOG[filename]
    except KeyError as error:
        raise ValueError(f"圖片尚未納入最佳化流程：{filename}") from error

    image_root = f"{root}assets/images/responsive/"
    fallback = asset.preferred(1200)
    srcset = ", ".join(
        f"{image_root}{variant.filename} {variant.width}w"
        for variant in asset.variants
    )
    attributes = [
        f'src="{image_root}{fallback.filename}"',
        f'srcset="{srcset}"',
        f'sizes="{escape(sizes)}"',
        f'width="{asset.width}"',
        f'height="{asset.height}"',
        f'alt="{escape(alt)}"',
        'decoding="async"',
        'loading="eager"' if priority else 'loading="lazy"',
    ]
    if css_class:
        attributes.append(f'class="{escape(css_class)}"')
    if priority:
        attributes.append('fetchpriority="high"')
    return "<img " + " ".join(attributes) + ">"


def social_image_path(filename: str) -> str:
    """Return a compressed 1200px-class asset for social metadata."""
    try:
        asset = IMAGE_CATALOG[filename]
    except KeyError as error:
        raise ValueError(f"找不到社群分享圖片：{filename}") from error
    return f"responsive/{asset.preferred(1200).filename}"


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
        image_url = f"{SITE_URL}/assets/images/{social_image_path(social_image)}"
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
    main = render(
        read_text(TEMPLATES / "home.html"),
        home_image=responsive_image(
            "artist-working.webp",
            "油畫藝術家沈東榮於工作室創作",
            "",
            HERO_IMAGE_SIZES,
            priority=True,
        ),
        home_signature=responsive_image(
            "signature.webp",
            "沈東榮簽名",
            "",
            "(max-width: 760px) 38vw, 230px",
            css_class="home-signature",
        ),
    )
    write_page(
        "index.html",
        title=f"{site['name_zh']}｜{site['role_zh']}",
        description=site["tagline_zh"],
        main=main,
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
        education_url="index.html",
        philosophy_url="philosophy/index.html",
        portrait_image=responsive_image(
            "artist-portrait.webp",
            "沈東榮自畫像",
            "../",
            DETAIL_IMAGE_SIZES,
            priority=True,
        ),
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

    statement = render(
        read_text(TEMPLATES / "philosophy.html"),
        education_url="../index.html",
        philosophy_url="index.html",
        portrait_image=responsive_image(
            "artist-portrait.webp",
            "沈東榮自畫像",
            "../../",
            DETAIL_IMAGE_SIZES,
            priority=True,
        ),
        intro_zh=escape(data["intro_zh"]),
        intro_en=escape(data["intro_en"]),
        philosophy=escape(data["philosophy"]),
    )
    write_page(
        "about/philosophy/index.html",
        title=f"創作理念｜{site['name_zh']}",
        description=data["philosophy"],
        main=statement,
        root="../../",
        active="about",
        body_class="page-about page-philosophy",
    )


def work_card(work: dict[str, Any], root: str) -> str:
    search = " ".join(
        str(work.get(key, ""))
        for key in (
            "catalog_number",
            "title_zh",
            "title_en",
            "year",
            "medium_zh",
            "dimensions",
        )
    ).lower()
    title_en = (
        f'<small>{escape(work["title_en"])}</small>'
        if work.get("title_en")
        else ""
    )
    return (
        f'<article class="work-card" data-year="{escape(work["year"])}" '
        f'data-search="{escape(search)}"><a href="{root}works/{escape(work["slug"])}/index.html">'
        f'<div class="work-image">{responsive_image(work["image"], work["alt"], root, CARD_IMAGE_SIZES)}</div>'
        f'<div class="work-meta"><h2>{escape(work["title_zh"])}{title_en}</h2>'
        f'<p>{escape(work.get("catalog_number", ""))}<br>{escape(work["year"])}<br>'
        f'{escape(work["dimensions"])}</p></div></a></article>'
    )


def work_gallery(work: dict[str, Any], root: str) -> str:
    """Render one artwork image or a swipeable set of supplied detail images."""
    images = [work["image"], *work.get("gallery", [])]
    if len(images) == 1:
        return (
            '<figure class="work-gallery-single">'
            + responsive_image(
                images[0],
                work["alt"],
                root,
                DETAIL_IMAGE_SIZES,
                priority=True,
            )
            + "</figure>"
        )

    slides: list[str] = []
    for index, filename in enumerate(images):
        alt = work["alt"] if index == 0 else f'{work["alt"]}局部 {index}'
        slides.append(
            '<figure class="gallery-slide">'
            + responsive_image(
                filename,
                alt,
                root,
                DETAIL_IMAGE_SIZES,
                priority=index == 0,
            )
            + "</figure>"
        )
    count = len(images)
    return (
        f'<section class="work-gallery" data-gallery aria-label="{escape(work["title_zh"])}作品圖庫">'
        f'<div class="gallery-track" data-gallery-track>{"".join(slides)}</div>'
        '<div class="gallery-controls">'
        '<button type="button" data-gallery-prev aria-label="上一張作品圖片">←</button>'
        f'<p aria-live="polite"><span data-gallery-current>1</span> / {count}</p>'
        '<button type="button" data-gallery-next aria-label="下一張作品圖片">→</button>'
        "</div></section>"
    )


def build_works(site: dict[str, Any], works: list[dict[str, Any]]) -> None:
    works = sorted(works, key=lambda item: item.get("catalog_number", item["slug"]))
    works = sorted(works, key=lambda item: item["year"], reverse=True)
    years = sorted({str(work["year"]) for work in works}, reverse=True)
    year_options = "".join(f'<option value="{escape(year)}">{escape(year)}</option>' for year in years)
    main = render(
        read_text(TEMPLATES / "works-index.html"),
        root="../",
        hero_image=responsive_image(
            "artist-working.webp",
            "沈東榮於工作室創作",
            "../",
            HERO_IMAGE_SIZES,
            priority=True,
        ),
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
        descriptions = work.get("description", [])
        description = "".join(f"<p>{escape(text)}</p>" for text in descriptions)
        title_en_line = (
            f'<p class="detail-title-en">{escape(work["title_en"])}</p>'
            if work.get("title_en")
            else ""
        )
        detail = render(
            detail_template,
            root="../../",
            work_gallery=work_gallery(work, "../../"),
            year=escape(work["year"]),
            title_zh=escape(work["title_zh"]),
            title_en_line=title_en_line,
            catalog_number=escape(work.get("catalog_number", "")),
            medium_zh=escape(work["medium_zh"]),
            medium_en=escape(work["medium_en"]),
            dimensions=escape(work["dimensions"]),
            collection_row=collection_row,
            description_block=(f'<div class="prose">{description}</div>' if description else ""),
            slug=escape(work["slug"]),
        )
        write_page(
            f"works/{work['slug']}/index.html",
            title=f"{work['title_zh']}｜{site['name_zh']}",
            description=(
                descriptions[0]
                if descriptions
                else f'{work["title_zh"]}，{work["year"]}，{work["dimensions"]}。'
            ),
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
    main = render(
        read_text(TEMPLATES / "exhibitions.html"),
        root="../",
        hero_image=responsive_image(
            "work-yushan.webp",
            "夕陽映照山峰與秋色山林的油畫作品",
            "../",
            HERO_IMAGE_SIZES,
            priority=True,
        ),
        exhibitions=rows,
    )
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
        hero_image=responsive_image(
            "artist-studio.webp",
            "沈東榮於工作室進行油畫創作",
            "../",
            "100vw",
            priority=True,
        ),
        course_image=responsive_image(
            "work-white-flower.webp",
            "白花與藍色花器的油畫示範作品",
            "../",
            DETAIL_IMAGE_SIZES,
        ),
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
        f'{responsive_image(article["image"], article["image_alt"], root, ARTICLE_THUMB_SIZES)}'
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
        hero_image=responsive_image(
            "work-yushan.webp",
            "夕陽映照山峰與秋色山林的油畫作品",
            "../",
            HERO_IMAGE_SIZES,
            priority=True,
        ),
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
            article_image=responsive_image(
                article["image"],
                article["image_alt"],
                "../../",
                DETAIL_IMAGE_SIZES,
                priority=True,
            ),
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
        signature_image=responsive_image(
            "signature.webp",
            "沈東榮簽名",
            "../",
            "(max-width: 760px) 45vw, 330px",
            css_class="contact-signature",
        ),
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


def build() -> BuildReport:
    global IMAGE_CATALOG

    site = load_json(CONTENT / "site.json")
    works = load_records("works")
    articles = load_records("articles")

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "static" / "css", DIST / "assets" / "css")
    shutil.copytree(ROOT / "static" / "js", DIST / "assets" / "js")
    (DIST / "assets" / "images").mkdir(parents=True)
    shutil.copy2(ROOT / "static" / "favicon.svg", DIST / "assets" / "favicon.svg")
    IMAGE_CATALOG, image_report = build_responsive_images(IMAGE_SOURCE, RESPONSIVE_OUTPUT)

    build_home(site)
    build_about(site)
    build_works(site, works)
    build_exhibitions(site)
    build_classes(site)
    build_writings(site, articles)
    build_contact(site)
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    page_count = len(list(DIST.rglob("*.html")))
    report = BuildReport(page_count=page_count, images=image_report)
    print(
        f"Built {page_count} pages and {image_report.variant_count} responsive image variants "
        f"from {image_report.source_count} sources in {DIST}"
    )
    return report


if __name__ == "__main__":
    build()
