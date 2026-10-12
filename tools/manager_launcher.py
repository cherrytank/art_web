"""Windows executable entry point; choose data before importing site modules."""
import argparse
import json
from pathlib import Path
import sys
import traceback
from tkinter import Tk, filedialog, messagebox

from project_paths import configure_project, get_project_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, help="網站專案資料夾")
    parser.add_argument("--check", action="store_true", help="不顯示視窗的啟動檢查")
    parser.add_argument("--check-build", action="store_true", help="檢查所有入口並建置指定專案")
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
        if args.check or args.check_build:
            app.withdraw()
            for page, _label in PAGE_SECTIONS:
                app.workspace.show_page(page)
                for task in list(app.workspace.task_buttons):
                    app.workspace.show_task(task)
            app.update_idletasks()
            result = {"ok": True, "project": str(get_project_root()), "forms": len(app.workspace.forms)}
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
        if args.report:
            args.report.write_text(json.dumps({"ok": False, "error": details}, ensure_ascii=False), encoding="utf-8")
        if app:
            app.destroy()
        if not (args.check or args.check_build):
            dialog = Tk()
            dialog.withdraw()
            messagebox.showerror("無法啟動管理器", details, parent=dialog)
            dialog.destroy()
        return 1


if __name__ == "__main__":
    sys.exit(main())
