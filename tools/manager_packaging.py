"""管理器背景打包：使用外部 Python，避免 EXE 遞迴啟動或覆寫自身。"""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import uuid


def start_process(command, **kwargs):
    """凍結版啟動外部工具前，暫時還原 Windows DLL 搜尋路徑。"""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return subprocess.Popen(command, **kwargs)
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    previous = ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(previous), previous)
    kernel.SetDllDirectoryW(None)
    try:
        return subprocess.Popen(command, **kwargs)
    finally:
        kernel.SetDllDirectoryW(previous.value or None)


def process_options(root: Path) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return dict(cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def find_python(root: Path) -> list[str]:
    candidates = [[str(root / ".codex-work/exe-venv/Scripts/python.exe")]]
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable])
    for name in ("py", "python", "python3"):
        executable = shutil.which(name)
        if executable:
            candidates.append([executable, "-3"] if name == "py" else [executable])
    for command in candidates:
        if not Path(command[0]).is_file(): continue
        try:
            with start_process([*command, "-c", "import sys; print('PACKAGING_PYTHON' if sys.version_info >= (3, 10) else 'OLD')"], **process_options(root)) as process:
                try:
                    output, _ = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    continue
                if process.returncode == 0 and "PACKAGING_PYTHON" in output:
                    return command
        except OSError:
            continue
    raise RuntimeError("找不到可用的 Python 3.10 以上版本。請安裝含 Tk 的 Python 並加入 PATH，重開管理器後再打包。使用 EXE 編輯網站不需要 Python，但打包需要。")


def package_manager(root: Path, progress) -> Path:
    if sys.platform != "win32":
        raise ValueError("EXE 打包功能需要 Windows。")
    script = root / "tools/build_exe.py"
    if not script.is_file():
        raise ValueError("找不到 tools/build_exe.py，請先同步完整專案程式碼。")
    progress("尋找打包用 Python…")
    python = find_python(root)
    # 每次獨立輸出，正在執行的 EXE 不會被覆寫。
    output_dir = root / "release" / (datetime.now().strftime("build-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    progress(f"打包輸出：{output_dir}")
    with start_process([*python, str(script), "--output-dir", str(output_dir)], **process_options(root)) as process:
        for line in process.stdout:
            if line.strip(): progress(line.strip())
        code = process.wait()
    if code:
        raise RuntimeError(f"打包失敗（結束碼 {code}）。請查看 Log 或 {root / '.codex-work/logs/build-exe.log'}。")
    result = output_dir / "SiteContentManager.exe"
    if not result.is_file():
        raise RuntimeError("打包程序已結束，但未找到新的 EXE，請查看 Log。")
    return result
