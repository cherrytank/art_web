"""等待 Windows 釋放舊管理器後，將完整的新 EXE 移至固定位置。"""
from pathlib import Path
import sys
import time

# 由外部 Python 執行，讓舊版專案也能使用新版 EXE 的替換功能。
REPLACE_SCRIPT = '''
from pathlib import Path
import sys, time
source, target = map(Path, sys.argv[1:3])
for attempt in range(600):
    try:
        source.replace(target)
        print(f"已更新：{target}", flush=True)
        break
    except PermissionError:
        if attempt == 599:
            raise RuntimeError(f"等待關閉舊 EXE 逾時；新檔仍保留在 {source}，關閉後可手動替換。")
        time.sleep(1)
'''


def replace_when_available(source: Path, target: Path, attempts: int = 600) -> None:
    for attempt in range(attempts):
        try:
            source.replace(target)
            print(f"已更新：{target}", flush=True)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                raise RuntimeError(f"等待關閉舊 EXE 逾時；新檔仍保留在 {source}，關閉後可手動替換。")
            time.sleep(1)


if __name__ == "__main__":
    replace_when_available(Path(sys.argv[1]), Path(sys.argv[2]))
