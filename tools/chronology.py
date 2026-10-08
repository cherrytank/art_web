"""Plain-text year/event format used by the local chronology editor."""
import re


def to_text(entries: list[dict]) -> str:
    return "\n\n".join("\n".join([str(entry["year"]), *entry["events"]]) for entry in entries)


def from_text(source: str) -> list[dict]:
    entries = []
    seen = set()
    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9]{4}", line) and int(line) > 0:
            if line in seen:
                raise ValueError(f"年份 {line} 重複，請將同年的事件放在一起。")
            seen.add(line)
            entries.append({"year": line, "events": []})
        elif not entries:
            raise ValueError("請先輸入四位數年份，再於下一行輸入事件；每行一件。")
        else:
            entries[-1]["events"].append(line)
    return entries
