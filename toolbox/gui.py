# -*- coding: utf-8 -*-
"""鼠标键盘控制(需 pywin32)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
from .shot import _find_window, _ensure_dpi_aware

# ===========================================================================

def tool_click(args):
    """鼠标点击。支持点击窗口内归一化坐标(配合 ocr/shot_ocr 的坐标用)或屏幕绝对坐标。
    window: 窗口标题关键词(可选)。填了则 x/y 是该整个窗口(含标题栏)的归一化坐标(0-1,与 shot 截图/OCR 一致)
    不填 window 则 x/y 是屏幕像素绝对坐标。
    x: X 坐标(归一化时 0-1, 绝对时像素)
    y: Y 坐标(归一化时 0-1, 绝对时像素)
    button: left(默认)/right/middle
    clicks: 点击次数, 默认 1(双击填 2)
    delay: 点击后等待秒数(给界面响应), 默认 0.5"""
    try:
        import win32gui, win32api, win32con
    except ImportError:
        return "Error: click 需要 pywin32 (pip install pywin32)"
    import time

    window_kw = args.get("window", "")
    try:
        x = float(args.get("x", -1))
        y = float(args.get("y", -1))
        clicks = int(args.get("clicks", 1))
        delay = float(args.get("delay", 0.5))
    except (ValueError, TypeError):
        return "Error: x/y/clicks/delay 参数必须是数字"
    button = str(args.get("button", "left"))

    if x < 0 or y < 0:
        return "Error: 缺少 x 或 y 坐标"

    target_title = ""
    if window_kw:
        hwnd, target_title, _ = _find_window(window_kw)
        if hwnd is None:
            return f"Error: 未找到标题含 '{window_kw}' 的窗口"
        # 归一化坐标 → 整个窗口(含标题栏)的屏幕坐标, 与 shot 全窗口截图/OCR 坐标基准一致
        # (钳制到 [0,1],防止点到窗口外)
        _ensure_dpi_aware()
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception as e:
            return f"Error: 窗口查询失败(可能已关闭) - {e}"
        w, h = right - left, bottom - top
        # w-1/h-1: 归一化 1.0 落在窗口最后一像素, 避免 int() 截断出界 1px
        screen_x = int(left + x * max(w - 1, 0))
        screen_y = int(top + y * max(h - 1, 0))
    else:
        screen_x = int(x)
        screen_y = int(y)

    btn_map = {
        "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
        "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
        "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
    }
    if button not in btn_map:
        return f"Error: 未知按钮 '{button}',应为 left/right/middle"
    down_flag, up_flag = btn_map[button]

    try:
        win32api.SetCursorPos((screen_x, screen_y))
        time.sleep(0.05)
        for _ in range(clicks):
            win32api.mouse_event(down_flag, 0, 0, 0, 0)
            win32api.mouse_event(up_flag, 0, 0, 0, 0)
            time.sleep(0.05)
    except Exception as e:
        return f"Error: 点击失败 - {e}"

    time.sleep(delay)

    pos = f"归一化({x:.2f},{y:.2f})" if window_kw else f"像素({screen_x},{screen_y})"
    return f"已{button}点击 {pos}{f' 窗口{target_title}' if target_title else ''} ×{clicks}"


def tool_key(args):
    """发送键盘按键。用于自动化操作(回车/ESC/快捷键等)。
    keys: 按键序列, 用 + 连接组合键。如 "enter" "ctrl+c" "alt+tab" "shift+a"
    支持的修饰键: ctrl/alt/shift/win
    支持的常用键: enter/esc/tab/space/backspace/delete/up/down/left/right/home/end/f1-f12
    普通字母数字直接写。
    delay: 按键后等待秒数, 默认 0.3"""
    try:
        import win32api, win32con
    except ImportError:
        return "Error: key 需要 pywin32 (pip install pywin32)"
    import time

    keys_str = str(args.get("keys", ""))
    try:
        delay = float(args.get("delay", 0.3))
    except (ValueError, TypeError):
        return "Error: delay 参数必须是数字"

    if not keys_str:
        return "Error: 缺少 keys 参数"

    vk_map = {
        "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
        "tab": 0x09, "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
        "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
        "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
        "f11": 0x7A, "f12": 0x7B,
    }

    parts = [p.strip().lower() for p in keys_str.split("+")]

    modifiers = []
    main_key = None
    for p in parts:
        if p in ("ctrl", "alt", "shift", "win"):
            modifiers.append(p)
        elif p in vk_map:
            if main_key is not None:
                return "Error: 不能同时按多个主键 (组合键格式: ctrl+c)"
            main_key = vk_map[p]
        elif len(p) == 1 and p.isascii() and p.isalnum():  # isascii 排除中文字符(ord>255 会截断成错误虚拟键)
            if main_key is not None:
                return "Error: 不能同时按多个主键 (组合键格式: ctrl+c)"
            main_key = ord(p.upper())
        else:
            return f"Error: 无法识别的键 '{p}'"

    if main_key is None:
        return "Error: 缺少主键 (组合键需含主键, 如 ctrl+c)"

    try:
        mod_codes = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
        for m in modifiers:
            win32api.keybd_event(mod_codes[m], 0, 0, 0)
        win32api.keybd_event(main_key, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(main_key, 0, win32con.KEYEVENTF_KEYUP, 0)
        for m in reversed(modifiers):
            win32api.keybd_event(mod_codes[m], 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        return f"Error: 按键失败 - {e}"

    time.sleep(delay)
    return f"已按键: {keys_str}"
