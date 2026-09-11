"""Small, safe text format shared by the editor, CLI and static page builder.

No raw HTML or executable markup is accepted. Existing string paragraphs and
typed article blocks remain readable without a content migration.
"""
from __future__ import annotations

import html
import re


PREFIXES = {"### ": "subheading", "## ": "heading", "> ": "quote", "! ": "lead", "- ": "list"}
TYPES = {"paragraph", "heading", "subheading", "lead", "quote", "box", "list"}
EXAMPLES = {
    "大標": "## 請輸入段落大標",
    "小標": "### 請輸入段落小標",
    "引言": "! 請輸入較醒目的開場文字。",
    "引用框": "> 請輸入引用或重點文字。",
    "背景框": "::: box\n請輸入補充說明。\n可直接換行。\n:::",
    "條列": "- 第一項\n- 第二項",
    "粗體": "**重點文字**",
}


def normalize_blocks(value: list) -> list[dict[str, str]]:
    blocks = []
    for item in value:
        block = {"type": "paragraph", "text": item} if isinstance(item, str) else dict(item)
        kind = block.get("type", "paragraph")
        if kind not in TYPES or not isinstance(block.get("text"), str):
            raise ValueError(f"不支援的文字區塊：{kind}")
        blocks.append({"type": kind, "text": block["text"]})
    return blocks


def parse_markup(source: str) -> list[dict[str, str]]:
    """Blank lines separate paragraphs; typed markers start independent blocks."""
    blocks: list[dict[str, str]] = []
    lines: list[str] = []
    kind = "paragraph"
    in_box = False

    def flush() -> None:
        nonlocal lines
        if lines:
            blocks.append({"type": kind, "text": "\n".join(lines)})
        lines = []

    for line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if in_box:
            if line == ":::":
                flush()
                in_box = False
                kind = "paragraph"
            else:
                lines.append(line[1:] if line.startswith("\\") else line)
            continue
        if not line.strip():
            flush()
            kind = "paragraph"
            continue
        if line == "::: box":
            flush()
            kind, in_box = "box", True
            continue
        if line == ":::" or line.startswith("::: "):
            raise ValueError("背景框請以 ::: box 開始，並以獨立一行 ::: 結束。")
        if line.startswith("\\"):
            if kind != "paragraph":
                flush()
                kind = "paragraph"
            lines.append(line[1:])
            continue
        marker = next((prefix for prefix in PREFIXES if line.startswith(prefix)), None)
        if marker:
            new_kind = PREFIXES[marker]
            if kind != new_kind:
                flush()
            kind = new_kind
            lines.append(line[len(marker):])
        else:
            if kind != "paragraph":
                flush()
                kind = "paragraph"
            lines.append(line)
    if in_box:
        raise ValueError("背景框尚未結束，請在框內文字後面加入獨立一行 :::。")
    flush()
    return blocks


def blocks_to_markup(value: list) -> str:
    inverse = {kind: prefix for prefix, kind in PREFIXES.items()}
    output = []
    for block in normalize_blocks(value):
        kind, text = block["type"], block["text"]
        if kind == "box":
            body = "\n".join("\\" + line if line == ":::" or line.startswith("\\") else line for line in text.split("\n"))
            output.append(f"::: box\n{body}\n:::")
        elif kind in inverse:
            output.append("\n".join(inverse[kind] + line for line in text.split("\n")))
        else:
            output.append("\n".join("\\" + line if line.startswith((*PREFIXES, ":::", "\\")) else line for line in text.split("\n")))
    return "\n\n".join(output)


def inline_text(text: str) -> str:
    """Escape first, then allow only paired **bold** markers."""
    return re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", html.escape(text, quote=True))


def render_blocks(value: list) -> str:
    output = []
    for block in normalize_blocks(value):
        kind, text = block["type"], inline_text(block["text"])
        if not text.strip():
            continue
        if kind == "list":
            output.append("<ul>" + "".join(f"<li>{line}</li>" for line in text.split("\n")) + "</ul>")
        else:
            tags = {"paragraph": ("p", ""), "heading": ("h2", ""), "subheading": ("h3", ""),
                    "lead": ("p", ' class="lead"'), "quote": ("blockquote", ""),
                    "box": ("div", ' class="text-box"')}
            tag, attributes = tags[kind]
            output.append(f"<{tag}{attributes}>{text}</{tag}>")
    return "".join(output)


def plain_summary(value: list) -> str:
    return next((re.sub(r"\*\*([^*\n]+)\*\*", r"\1", block["text"]) for block in normalize_blocks(value) if block["text"].strip()), "")
