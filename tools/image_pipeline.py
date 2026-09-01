"""Create responsive WebP variants for the static site.

Original images stay in ``static/assets/images`` as the editable source. Every
site build creates delivery-sized copies in ``dist/assets/images/responsive``.
Keeping this work in one module lets the CLI, desktop UI, validation, and
GitHub Pages deployment share exactly the same image workflow.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError as error:  # pragma: no cover - depends on local environment
    raise RuntimeError(
        "缺少圖片處理套件 Pillow。請先執行：python -m pip install -r requirements.txt"
    ) from error


RESPONSIVE_WIDTHS = (480, 800, 1200, 1800)
SUPPORTED_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}
WEBP_QUALITY = 82
SAFE_STEM_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ImageVariant:
    """One generated image candidate."""

    width: int
    height: int
    filename: str
    size_bytes: int


@dataclass(frozen=True)
class ResponsiveImage:
    """Responsive metadata for one source image."""

    source_name: str
    width: int
    height: int
    variants: tuple[ImageVariant, ...]

    def preferred(self, target_width: int = 1200) -> ImageVariant:
        """Return the smallest candidate that meets the requested width."""
        for variant in self.variants:
            if variant.width >= target_width:
                return variant
        return self.variants[-1]


@dataclass(frozen=True)
class ImageBuildReport:
    """Summary shown by CLI and desktop UI after a build."""

    source_count: int
    variant_count: int
    source_bytes: int
    variant_bytes: int


def _candidate_widths(source_width: int) -> list[int]:
    widths = [width for width in RESPONSIVE_WIDTHS if width <= source_width]
    if not widths or widths[-1] != source_width:
        widths.append(source_width)
    return widths


def _web_image(image: Image.Image) -> Image.Image:
    """Normalize color mode while preserving transparency when present."""
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def _output_stem(source: Path) -> str:
    """Create a URL-safe, deterministic name for generated candidates."""
    lowered = source.stem.lower()
    if SAFE_STEM_RE.fullmatch(lowered):
        return lowered
    readable = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-") or "image"
    digest = hashlib.sha1(source.name.encode("utf-8")).hexdigest()[:8]
    return f"{readable}-{digest}"


def _generate_one(source: Path, output_dir: Path, output_stem: str) -> ResponsiveImage:
    try:
        with Image.open(source) as opened:
            if getattr(opened, "is_animated", False):
                raise ValueError("不支援動態圖片，請改用靜態 JPG、PNG、WebP 或 AVIF")
            image = _web_image(ImageOps.exif_transpose(opened))
    except (OSError, ValueError) as error:
        raise ValueError(f"無法處理圖片 {source.name}：{error}") from error

    variants: list[ImageVariant] = []
    for width in _candidate_widths(image.width):
        height = max(1, round(image.height * width / image.width))
        resized = image if width == image.width else image.resize((width, height), Image.Resampling.LANCZOS)
        filename = f"{output_stem}-{width}w.webp"
        target = output_dir / filename
        resized.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        variants.append(
            ImageVariant(
                width=width,
                height=height,
                filename=filename,
                size_bytes=target.stat().st_size,
            )
        )

    return ResponsiveImage(
        source_name=source.name,
        width=image.width,
        height=image.height,
        variants=tuple(variants),
    )


def build_responsive_images(
    source_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, ResponsiveImage], ImageBuildReport]:
    """Generate responsive variants for every supported source image."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(
        path for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    catalog: dict[str, ResponsiveImage] = {}
    used_stems: set[str] = set()
    for source in sources:
        output_stem = _output_stem(source)
        if output_stem in used_stems:
            digest = hashlib.sha1(source.name.encode("utf-8")).hexdigest()[:8]
            output_stem = f"{output_stem}-{digest}"
        used_stems.add(output_stem)
        catalog[source.name] = _generate_one(source, output_dir, output_stem)
    report = ImageBuildReport(
        source_count=len(sources),
        variant_count=sum(len(asset.variants) for asset in catalog.values()),
        source_bytes=sum(source.stat().st_size for source in sources),
        variant_bytes=sum(
            variant.size_bytes
            for asset in catalog.values()
            for variant in asset.variants
        ),
    )
    return catalog, report
