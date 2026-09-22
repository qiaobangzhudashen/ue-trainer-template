# -*- coding: utf-8 -*-
"""环境能力探测(info)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os

# ===========================================================================

def tool_deps(args):
    """探测当前环境可用的第三方库,agent 调用业务工具前可先看这里。

    run("info") 报告: PE/截图/OCR/GUI/描述/DB 各能力模块是否可用。
    """
    def _has(mod):
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    lines = []
    lines.append("=== agent 工具库环境探测 ===")

    pe_state = "capstone: " + ("✅ 可用(完整反汇编)" if _has("capstone")
                                else "⚠️ 缺失(disasm 降级为 hex dump)")
    lines.append(f"\n[pe]  PE 文件分析 (零外部依赖)\n  {pe_state}")

    # 截图
    shot_deps = []
    try:
        import ctypes, ctypes.wintypes  # noqa
        shot_deps.append("ctypes✅")
    except Exception:
        shot_deps.append("ctypes❌")
    try:
        import win32gui  # noqa
        shot_deps.append("pywin32✅")
    except Exception:
        shot_deps.append("pywin32❌(截图降级 ctypes)")
    try:
        from PIL import Image, ImageGrab  # noqa
        shot_deps.append("PIL✅")
    except Exception:
        shot_deps.append("PIL❌(截图无法保存)")
    _osname = os.name
    lines.append(f"\n[shot] 窗口/屏幕截图\n  依赖: {' | '.join(shot_deps)}\n  平台: {_osname}"
                 + ("" if _osname == "nt" else " (⚠️ 窗口截图需 Windows;跨平台仅建议用 PE/db)"))

    # OCR
    try:
        import paddleocr
        ocr_v = str(getattr(paddleocr, "__version__", ""))
        ocr_state = f"✅ 可用(PaddleOCR {ocr_v}, 2.x/3.x 自动适配)"
    except Exception:
        ocr_state = "❌ 未安装(pip install paddleocr,首次调用需联网下载模型)"
    try:
        from PIL import Image  # noqa
        ocr_pil = ""
    except Exception:
        ocr_pil = "(但 Pillow 缺失,无法读图)"
    lines.append(f"\n[ocr] 图片 OCR\n  {ocr_state}{ocr_pil}")

    # GUI(click/key)
    gui_deps = []
    for m in ("win32api", "win32con", "win32gui"):
        gui_deps.append(m + ("✅" if _has(m) else "❌"))
    lines.append(f"\n[gui] 鼠标/键盘自动化(click/key)\n  {' | '.join(gui_deps)} (需 Windows + pywin32)")

    # 图片描述
    try:
        from PIL import Image  # noqa
        desc_state = "✅ 可用"
    except Exception:
        desc_state = "❌ 需要 Pillow(pip install pillow)"
    lines.append(f"\n[describe] 图片视觉描述\n  {desc_state}")

    # DB
    db_state = "✅ 可用"
    try:
        import sqlite3
        c = sqlite3.connect(":memory:")
        try:
            c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        except Exception:
            db_state = "⚠️ sqlite3 可用但无 FTS5(全文搜索不可用,其余功能正常)"
        finally:
            c.close()
    except Exception:
        db_state = "❌ sqlite3 不可用"
    lines.append(f"\n[db] JSON 数据库 (SQLite+FTS5)\n  {db_state}")

    # CE 桥(命名管道,需 CE 启动+桥加载+已 attach)
    try:
        from .ce import PIPE
        import win32file  # noqa
        try:
            h = win32file.CreateFile(PIPE, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                     0, None, win32file.OPEN_EXISTING, 0, None)
            h.close()
            ce_state = "✅ 管道已通(CE 桥在线)"
        except Exception:
            ce_state = "❌ 管道不通(CE 未启动/桥未加载/未 attach,ce 工具会报自查提示)"
    except Exception as e:
        ce_state = f"❌ {e}"
    lines.append(f"\n[ce] CE 桥接\n  {ce_state}")

    lines.append("\n=== 用法速查 ===")
    lines.append('  import toolbox')
    lines.append('  toolbox.run("pe",   action="exports", path="file.dll")')
    lines.append('  toolbox.run("shot", action="list")')
    lines.append('  toolbox.run("ocr",  path="screenshot.png")')
    lines.append('  toolbox.run("db",   action="search", keyword="词", db="data.db", table="表名")')
    lines.append('  toolbox.run("ce",   action="scan", value="15000", type="dword")  # 需CE在线')
    lines.append('  toolbox.run("ce",   action="aob", pattern="48 8B ?? ?? 57")')
    lines.append('  toolbox.run("ce",   action="lbr", op="start")  # 回溯分支;read取数')
    lines.append('  toolbox.run("ce",   action="step", thread=111, count=80)  # 单步找解密')
    return "\n".join(lines)
