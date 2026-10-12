"""Keep editable website data outside the frozen application's temp folder."""
from pathlib import Path
import sys

_project_root: Path | None = None


def is_project(path: Path) -> bool:
    return all((path / item).exists() for item in (
        "content/site.json", "templates/base.html", "static/css/styles.css"))


def configure_project(path: Path) -> None:
    global _project_root
    path = path.resolve()
    if not is_project(path):
        raise ValueError("請選擇包含 content、templates、static 的網站專案資料夾。")
    _project_root = path


def get_project_root() -> Path:
    if _project_root is not None:
        return _project_root
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        for path in (executable_dir, executable_dir.parent):
            if is_project(path):
                return path
        raise ValueError("找不到網站資料夾，請透過管理器啟動程式選擇專案。")
    return Path(__file__).resolve().parents[1]
