"""Windows 管理器啟動入口：先選專案，再載入資料與編輯介面。"""
import argparse
import json
from pathlib import Path
import sys
import traceback
import os
import tempfile
from tkinter import Tk, filedialog, messagebox

from project_paths import configure_project, get_project_root


def main() -> int:
    # 視窗版 EXE 沒有主控台，將輸出導向紀錄，避免依賴 stdout 的程式失效。
    log_dir = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "ShenSiteManager"
    log_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = (log_dir / "manager.log").open("a", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, help="網站專案資料夾")
    parser.add_argument("--check", action="store_true", help="不顯示視窗的啟動檢查")
    parser.add_argument("--check-build", action="store_true", help="檢查所有入口並建置指定專案")
    parser.add_argument("--check-git", action="store_true", help="只讀檢查 EXE 能否呼叫本機 Git")
    parser.add_argument("--report", type=Path, help="將檢查結果寫入 JSON")
    args = parser.parse_args()
    app = None
    try:
        if args.project:
            configure_project(args.project)
        else:
            try:
                get_project_root()
            except ValueError:
                dialog = Tk()
                dialog.withdraw()
                selected = filedialog.askdirectory(parent=dialog, title="選擇網站資料夾（包含 content、templates、static）")
                dialog.destroy()
                if not selected:
                    return 0
                configure_project(Path(selected))
        from content_manager import ContentManager, PAGE_SECTIONS
        app = ContentManager()
        app.title(f"沈東榮網站內容管理器 — {get_project_root()}")
        if args.check or args.check_build or args.check_git:
            app.withdraw()
            for page, _label in PAGE_SECTIONS:
                app.workspace.show_page(page)
                for task in list(app.workspace.task_buttons):
                    app.workspace.show_task(task)
            app.update_idletasks()
            result = {"ok": True, "project": str(get_project_root()), "forms": len(app.workspace.forms)}
            if args.check_git:
                import git_publish
                result["git"] = git_publish.inspect(get_project_root())
            if args.check_build:
                import build_site
                result["pages"] = build_site.build().page_count
            if args.report:
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            app.destroy()
            return 0
        app.mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        (log_dir / "startup-error.log").write_text(details, encoding="utf-8")
        if args.report:
            args.report.write_text(json.dumps({"ok": False, "error": details}, ensure_ascii=False), encoding="utf-8")
        if app:
            app.destroy()
        if not (args.check or args.check_build or args.check_git):
            dialog = Tk()
            dialog.withdraw()
            messagebox.showerror("無法啟動管理器", details, parent=dialog)
            dialog.destroy()
        return 1


if __name__ == "__main__":
    sys.exit(main())
