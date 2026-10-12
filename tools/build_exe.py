"""Build a self-contained Windows manager; website data stays editable outside it.

Run with the packaging environment: python tools/build_exe.py
Requires the pinned dependencies in requirements-exe.txt.
"""
from pathlib import Path
import subprocess
import sys


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("請在 Windows 上建立 Windows EXE。")
    root = Path(__file__).resolve().parents[1]
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "SiteContentManager",
        "--distpath", str(root / "release"),
        "--workpath", str(root / ".codex-work/pyinstaller-build"),
        "--specpath", str(root / ".codex-work"),
        "--paths", str(root / "tools"),
        str(root / "tools/manager_launcher.py"),
    ], check=True, cwd=root)
    print(f"EXE: {root / 'release/SiteContentManager.exe'}")


if __name__ == "__main__":
    main()
