"""一個指令完成 Windows 打包：建立環境、安裝套件並產生 EXE。"""
import os
from pathlib import Path
import subprocess
import sys
import traceback


def run_step(label: str, command: list[str], root: Path, log) -> None:
    """即時顯示進度並保留完整輸出；所有子程序固定在專案根目錄執行。"""
    def emit(message: str) -> None:
        print(message, flush=True)
        log.write(message + "\n")
        log.flush()

    emit(f"\n--- {label} ---")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    with subprocess.Popen(
        command, cwd=root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    ) as process:
        for line in process.stdout:
            emit(line.rstrip("\r\n"))
        code = process.wait()
    if code:
        raise RuntimeError(f"{label}失敗（結束碼 {code}），請查看上方訊息與打包 Log。")


def build(root: Path, log) -> None:
    python = root / ".codex-work/exe-venv/Scripts/python.exe"
    if not python.is_file():
        run_step("建立專用 Python 環境", [sys.executable, "-m", "venv", str(python.parents[1])], root, log)
    run_step("檢查 Python 與視窗元件", [str(python), "-c",
        "import sys, tkinter; print(sys.executable); print(sys.version); "
        "app = tkinter.Tk(); app.withdraw(); app.update_idletasks(); app.destroy()"], root, log)
    run_step("安裝／確認打包套件（首次需要網路）", [str(python), "-m", "pip",
        "install", "--disable-pip-version-check", "--retries", "1", "--timeout", "30",
        "-r", str(root / "requirements-exe.txt")], root, log)
    run_step("產生 EXE（請先關閉舊的內容管理器）", [
        str(python), "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "SiteContentManager",
        "--distpath", str(root / "release"),
        "--workpath", str(root / ".codex-work/pyinstaller-build"),
        "--specpath", str(root / ".codex-work"),
        "--paths", str(root / "tools"),
        str(root / "tools/manager_launcher.py"),
    ], root, log)
    output = root / "release/SiteContentManager.exe"
    if not output.is_file():
        raise RuntimeError("打包程序結束，但找不到輸出的 EXE。")
    message = f"\n打包完成：{output}"
    print(message)
    log.write(message + "\n")


def main() -> int:
    if sys.platform != "win32":
        print("請在 Windows 上建立 Windows EXE。", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    log_path = root / ".codex-work/logs/build-exe.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"專案：{root}\n打包 Log：{log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"專案：{root}\n啟動 Python：{sys.executable}\n")
        try:
            build(root, log)
        except (Exception, KeyboardInterrupt) as error:
            traceback.print_exc(file=log)
            print(f"\n打包未完成：{error}\n詳細紀錄：{log_path}", file=sys.stderr)
            print("若顯示檔案被占用，請關閉舊 EXE 後重試；若環境已失效，請將 "
                  ".codex-work/exe-venv 改名後重試，程式會重新建立環境。", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
