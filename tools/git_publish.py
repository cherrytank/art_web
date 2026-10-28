"""以各台電腦自己的 Git 身分同步及發布，不儲存帳密或強制覆寫遠端。"""
import os
from pathlib import Path
import shutil
import subprocess
from manager_log import logger

SOURCE_PATHS = ("content", "static", "templates", "tools", "requirements.txt", "requirements-exe.txt", ".github", ".gitignore", "README.md")


def find_git() -> str:
    executable = shutil.which("git")
    if executable:
        return executable
    # 從檔案總管開 EXE 時，PATH 可能尚未包含 Git for Windows。
    for directory in (os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
        for relative in ("Git/cmd/git.exe", "Programs/Git/cmd/git.exe"):
            path = Path(directory) / relative
            if path.is_file():
                return str(path)
    raise ValueError("找不到 Git。請安裝 Git for Windows，或重新開啟管理器以載入新的 PATH。")


def git(root: Path, *args: str) -> str:
    # 不寫入提交說明或整組參數，避免把內容與憑證留在紀錄。
    logger.info("Git 執行：%s", args[0] if args else "（無參數）")
    environment = os.environ.copy()
    environment.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    environment.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    try:
        result = subprocess.run([find_git(), *args], cwd=root, env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        logger.error("Git 操作逾時：%s", args[0])
        raise ValueError("Git 操作逾時。請確認網路與登入狀態後重試；沒有強制推送。") from error
    if result.returncode:
        logger.error("Git 結束碼 %s：%s", result.returncode, result.stderr.strip() or result.stdout.strip())
        raise ValueError(f"Git {' '.join(args[:2])} 失敗：\n{result.stderr.strip() or result.stdout.strip()}\n\n請在此專案的終端機確認 Git 登入與權限，管理器不會詢問或保存密碼。")
    logger.info("Git 完成：%s，結束碼 0", args[0])
    return result.stdout.strip()


def inspect(root: Path) -> str:
    top = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root.resolve():
        raise ValueError("目前網站資料夾不是 Git 專案根目錄，請重新選擇專案。")
    branch = git(root, "branch", "--show-current")
    remote = git(root, "remote", "get-url", "origin")
    if branch != "main":
        raise ValueError(f"目前分支是 {branch or 'detached HEAD'}。此網站只在 main 推送後部署，請先自行確認並切換 main。")
    return f"專案：{root}\n分支：{branch}\n遠端：{remote}\n{git(root, 'status', '--short') or '沒有未提交的修改'}"


def sync(root: Path, progress) -> str:
    inspect(root)
    if git(root, "status", "--porcelain"):
        raise ValueError("本機有未提交修改，不能直接同步。請先提交或自行處理修改後重試；管理器不會自動藏起或覆蓋檔案。")
    progress("下載團隊最新版本…")
    git(root, "fetch", "origin", "main")
    git(root, "merge", "--ff-only", "refs/remotes/origin/main")
    return "同步完成。請重新開啟管理器，載入最新內容。"


def publish(root: Path, message: str, progress, build) -> str:
    inspect(root)
    if git(root, "diff", "--cached", "--name-only"):
        raise ValueError("已有暫存中的檔案，請先自行提交或取消暫存後再發布，避免誤提交其他工作。")
    for key in ("user.name", "user.email"):
        git(root, "config", "--get", key)
    progress("檢查遠端是否有其他人的更新…")
    git(root, "fetch", "origin", "main")
    behind = int(git(root, "rev-list", "--count", "HEAD..refs/remotes/origin/main"))
    if behind:
        raise ValueError(f"遠端有 {behind} 筆本機尚未整合的提交。請先同步；若已修改檔案，請用 Git 提交並合併團隊更新後再發布。沒有推送或覆蓋檔案。")
    progress("驗證並建置本機網站…")
    build(progress=progress)
    paths = [name for name in SOURCE_PATHS if (root / name).exists()]
    changed = git(root, "status", "--porcelain", "--", *paths)
    if changed:
        progress("提交網站修改…")
        git(root, "add", "--", *paths)
        if git(root, "diff", "--cached", "--name-only"):
            git(root, "commit", "-m", message)
    progress("推送到 origin/main…")
    git(root, "push", "origin", "HEAD:main")
    return "推送成功。GitHub Actions 已可接手部署；推送成功不代表部署已完成，請至 GitHub Actions 查看結果。"
