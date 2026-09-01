"""Validate generated HTML, local links, images, titles, and page headings."""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import build_site


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images_without_alt = 0
        self.h1_count = 0
        self.title_depth = 0
        self.title_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        elif tag in {"img", "script"} and values.get("src"):
            self.links.append(values["src"] or "")
        elif tag == "link" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "img" and not (values.get("alt") or "").strip():
            self.images_without_alt += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_text += data


def local_target(page: Path, link: str) -> Path | None:
    parts = urlsplit(link)
    if parts.scheme or parts.netloc or link.startswith(("#", "mailto:", "tel:")):
        return None
    path = unquote(parts.path)
    if not path:
        return None
    target = (page.parent / path).resolve()
    if path.endswith("/"):
        target /= "index.html"
    return target


def main() -> None:
    build_site.build()
    errors: list[str] = []
    dist_root = build_site.DIST.resolve()
    pages = sorted(build_site.DIST.rglob("*.html"))

    for page in pages:
        source = page.read_text(encoding="utf-8")
        if "{{" in source or "}}" in source:
            errors.append(f"{page}: unresolved template marker")
        parser = PageParser()
        parser.feed(source)
        if not parser.title_text.strip():
            errors.append(f"{page}: missing title")
        if parser.h1_count != 1:
            errors.append(f"{page}: expected one h1, found {parser.h1_count}")
        if parser.images_without_alt:
            errors.append(f"{page}: {parser.images_without_alt} image(s) missing alt text")
        for link in parser.links:
            target = local_target(page, link)
            if target is None:
                continue
            try:
                target.relative_to(dist_root)
            except ValueError:
                errors.append(f"{page}: link escapes dist: {link}")
                continue
            if not target.exists():
                errors.append(f"{page}: broken local link: {link}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"Validated {len(pages)} HTML pages: links, assets, titles, h1, and alt text are valid.")


if __name__ == "__main__":
    main()
