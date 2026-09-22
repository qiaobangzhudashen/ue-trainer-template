# -*- coding: utf-8 -*-
"""窗口/屏幕截图(pywin32 优先,缺失降级 ctypes)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os

# ===========================================================================

_PYWIN32 = None


def _has_pywin32():
    """是否安装了 pywin32(截图/鼠标键盘的优选实现)。"""
    global _PYWIN32
    if _PYWIN32 is None:
        try:
            import win32gui  # noqa: F401
            _PYWIN32 = True
        except ImportError:
            _PYWIN32 = False
    return _PYWIN32


_DPI_AWARE_DONE = False


def _ensure_dpi_aware():
    """设置进程 DPI 感知,保证窗口矩形/截图为物理像素。

    Windows 对"DPI 不感知"的进程报告的是虚拟缩放后的尺寸(125%/150% 高分屏下
    只有真实的一半),截图会变小、坐标会错位。设置 per-monitor 感知后,
    任意分辨率和缩放倍数下拿到的都是真实物理像素,与屏幕上所见完全一致。
    进程内设置一次,之后所有窗口 API 都生效。"""
    global _DPI_AWARE_DONE
    if _DPI_AWARE_DONE:
        return
    try:
        import ctypes
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness.restype = ctypes.HRESULT  # 必须声明, 否则失败只返回负值不抛异常
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        hr = shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        # S_OK=0 成功; E_ACCESSDENIED=-2147024891 表示进程已按 manifest 感知, 同样满足需求
        if hr >= 0 or hr == -2147024891:
            _DPI_AWARE_DONE = True
            return
    except Exception:
        pass
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware.restype = ctypes.c_bool
        if user32.SetProcessDPIAware():
            _DPI_AWARE_DONE = True
            return
    except Exception:
        pass
    # 两种方式都失败: 保持未设置, 下次调用再试(不静默吞掉失败) 


def _get_process_name(pid):
    """通过 PID 获取进程名(纯 ctypes, 两套截图实现共用)。"""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _match_window(windows, kw):
    """三级匹配窗口: 标题精确 → 标题模糊(取最短) → 进程名模糊。返回 (hwnd, title, pid) 或 None。"""
    kw = kw.lower().strip()
    if not kw:  # 空白关键词会匹配到任意窗口, 直接拒绝
        return None
    for hwnd, title, pid in windows:
        if title.lower() == kw:
            return hwnd, title, pid
    fuzz = [w for w in windows if kw in w[1].lower()]
    if fuzz:
        fuzz.sort(key=lambda w: len(w[1]))  # 标题越短越接近关键词本身
        return fuzz[0]
    for hwnd, title, pid in windows:
        if kw in _get_process_name(pid).lower():
            return hwnd, title, pid
    return None


# --- pywin32 实现(优选) -----------------------------------------------------

def _pw_enum_windows():
    """枚举所有可见窗口(有标题的),返回 [(hwnd, title, pid)]。"""
    import win32gui
    import win32process
    results = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                results.append((hwnd, title, pid))

    win32gui.EnumWindows(callback, None)
    return results


def _pw_capture_window(hwnd, save_path):
    """截取整个窗口(含标题栏/边框/底部状态栏)保存 PNG(PrintWindow 优先, 纯色则 fallback 到 ImageGrab)。
    DPI 感知由 _ensure_dpi_aware 保证, 任意分辨率/缩放下均为物理像素。返回保存路径。"""
    import win32gui, win32ui
    from ctypes import windll
    from PIL import Image, ImageGrab
    import time

    _ensure_dpi_aware()
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        raise ValueError(f"窗口尺寸异常: {w}x{h}")
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    try:
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)
        if windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2) == 0:  # PW_RENDERFULLCONTENT
            # PrintWindow 失败(DWM/DirectComposition 窗口)→ BitBlt 从窗口 DC 兜底
            windll.gdi32.BitBlt(saveDC.GetSafeHdc(), 0, 0, w, h, hwndDC, 0, 0, 0x00CC0020)
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)
    finally:
        # 先释放 DC(隐式释放选中对象),再删 bitmap,最后释放窗口 DC —— 顺序错会泄漏句柄
        # 清理失败不覆盖原始异常
        for _clean in (lambda: saveDC.DeleteDC(),
                       lambda: win32gui.DeleteObject(saveBitMap.GetHandle()),
                       lambda: mfcDC.DeleteDC(),
                       lambda: win32gui.ReleaseDC(hwnd, hwndDC)):
            try:
                _clean()
            except Exception:
                pass

    # 纯色占位 → 前台重抓(判空逻辑见 _is_blank)
    if _is_blank(img):
        try:
            win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)  # 恢复后重新取矩形(最小化时旧矩形是任务栏位置)
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
        except Exception:
            pass  # fallback 也失败就返回原图

    img.save(save_path)
    return save_path


# --- ctypes 实现(降级) ------------------------------------------------------

def _bih_type(ctypes):
    """ctypes 需要时再定义结构,避免 import 阶段依赖 ctypes。"""
    class _BITMAPINFOHEADER_(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]
    return _BITMAPINFOHEADER_


def _ct_enum_windows():
    """枚举所有可见窗口(纯 ctypes),返回 [(hwnd, title, pid)]。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    results = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, wintypes.LPARAM)
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    GetWindowTextW.restype = ctypes.c_int
    IsWindowVisible = user32.IsWindowVisible
    IsWindowVisible.argtypes = [wintypes.HWND]
    IsWindowVisible.restype = ctypes.c_bool
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(ctypes.c_uint)]
    GetWindowThreadProcessId.restype = ctypes.c_uint

    def callback(hwnd, _lparam):
        if not IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        if not title:
            return True
        pid = ctypes.c_uint(0)
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append((hwnd, title, pid.value))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return results


def _ct_capture_window(hwnd, save_path):
    """截取整个窗口(含标题栏/边框/状态栏)保存 PNG(纯 ctypes: PrintWindow + BitBlt 兜底)。返回保存路径。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    _ensure_dpi_aware()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"窗口大小无效: {width}x{height}")

    hdc_window = user32.GetWindowDC(hwnd)  # 整窗 DC, BitBlt 兜底时也含标题栏
    if not hdc_window:
        raise RuntimeError("GetDC 失败")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
    gdi32.SelectObject(hdc_mem, hbmp)

    img = None
    try:
        PW_RENDERFULLCONTENT = 0x00000002
        result = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        if result == 0:
            gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_window, 0, 0, 0x00CC0020)

        from PIL import Image
        BIH = _bih_type(ctypes)
        bih = BIH()
        bih.biSize = ctypes.sizeof(BIH)
        bih.biWidth = width
        bih.biHeight = -height
        bih.biPlanes = 1
        bih.biBitCount = 32
        bih.biCompression = 0

        pixel_data = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, height, pixel_data, ctypes.byref(bih), 0)

        img = Image.frombuffer("RGBA", (width, height), pixel_data, "raw", "BGRA", 0, 1)
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_window)

    # 纯色占位 → 前台重抓(判空逻辑见 _is_blank;ctypes 路径用 user32,不碰 win32gui)
    if img is not None and _is_blank(img):
        try:
            from PIL import ImageGrab
            import time
            # ctypes 路径=没装 pywin32, 用 user32 恢复窗口(不 import win32gui, 那是死代码)
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            user32.GetWindowRect(hwnd, ctypes.byref(rect))  # 恢复后重新取矩形(最小化时旧矩形是任务栏位置)
            img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        except Exception:
            pass  # fallback 也失败就返回抓到的图
    img.save(save_path)
    return save_path


def _ct_capture_screen(save_path, monitor_index=0):
    """截取整个屏幕保存 PNG(纯 ctypes, 支持多显示器序号)。返回保存路径。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    _ensure_dpi_aware()

    if monitor_index > 0:
        monitors = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.POINTER(wintypes.RECT), ctypes.c_int32)

        def monitor_cb(hmon, hdc, lprect, ldata):
            monitors.append(wintypes.RECT(lprect.contents))
            return True

        user32.EnumDisplayMonitors(0, 0, EnumProc(monitor_cb), 0)
        if not monitors:
            rect = wintypes.RECT()
            user32.GetWindowRect(user32.GetDesktopWindow(), ctypes.byref(rect))
        elif monitor_index < len(monitors):
            rect = monitors[monitor_index]
        else:
            rect = monitors[0]
    else:
        rect = wintypes.RECT()
        user32.GetWindowRect(user32.GetDesktopWindow(), ctypes.byref(rect))

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    hdc_screen = user32.GetDC(0)
    if not hdc_screen:
        raise RuntimeError("GetDC(0) 失败")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    if not hdc_mem:
        user32.ReleaseDC(0, hdc_screen)
        raise RuntimeError("CreateCompatibleDC 失败")
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    if not hbmp:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        raise RuntimeError("CreateCompatibleBitmap 失败")
    gdi32.SelectObject(hdc_mem, hbmp)

    try:
        gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, rect.left, rect.top, 0x00CC0020)

        from PIL import Image
        BIH = _bih_type(ctypes)
        bih = BIH()
        bih.biSize = ctypes.sizeof(BIH)
        bih.biWidth = width
        bih.biHeight = -height
        bih.biPlanes = 1
        bih.biBitCount = 32
        bih.biCompression = 0

        pixel_data = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, height, pixel_data, ctypes.byref(bih), 0)

        img = Image.frombuffer("RGBA", (width, height), pixel_data, "raw", "BGRA", 0, 1)
        img.save(save_path)
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
    return save_path


# --- 统一入口 --------------------------------------------------------------

def _find_window(keyword):
    """按标题/进程名匹配窗口,返回 (hwnd, title, pid) 或 (None, None, None)。
    枚举失败(非 Windows/权限不足等)兜底返回 None,不抛异常。"""
    try:
        if _has_pywin32():
            windows = _pw_enum_windows()
        else:
            windows = _ct_enum_windows()
        hit = _match_window(windows, keyword)
        return hit if hit else (None, None, None)
    except Exception:
        return None, None, None


def _is_blank(img):
    """纯色占位检测(UWP/DirectComposition 窗口 PrintWindow 常返回纯黑/纯白/纯灰)。

    灰度极差 <=1 即判空白。pywin32/ctypes 两条截图路径共用,阈值改一处即可。"""
    try:
        lo, hi = img.convert("L").getextrema()
        return hi - lo <= 1
    except Exception:
        return False


def _capture_window(hwnd, save_path):
    """截取窗口客户区保存 PNG。pywin32 优先,异常/缺失自动降级 ctypes。返回保存路径。"""
    if _has_pywin32():
        try:
            return _pw_capture_window(hwnd, save_path)
        except Exception:
            pass  # pywin32 路径失败 → 降级 ctypes
    return _ct_capture_window(hwnd, save_path)


def tool_screenshot(args):
    """窗口/屏幕截图,保存为 PNG。

    run("shot", window=..., output=..., monitor=..., action=...)

    参数:
      window   窗口标题或进程名关键词(精确→模糊→进程名三级匹配)。省略=截全屏
      output   输出文件路径(默认 data/screenshots/screenshot_<时间戳>.png)
      monitor  显示器序号(0=主显示器,默认0)
      action   "list"=列出所有窗口

    截图内容为整个窗口(含标题栏/边框/底部状态栏),自动适配 DPI 缩放
    (125%/150% 等),任意分辨率下均为物理像素;OCR 归一化坐标与 click
    都以整窗为基准,一一对应。
    """
    import time
    action = str(args.get("action", "")).lower()
    output = args.get("output", "")
    window_kw = args.get("window", "")

    if action == "list":
        try:
            windows = _pw_enum_windows() if _has_pywin32() else _ct_enum_windows()
        except Exception as e:
            return f"Error: 枚举窗口失败 - {e}"
        lines = [f"可见窗口 {len(windows)} 个:"]
        for hwnd, title, pid in windows:
            proc = _get_process_name(pid)
            lines.append(f"  pid={pid:6}  proc={proc:30}  title={title}")
        return "\n".join(lines)

    if not output:
        screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        output = os.path.join(screenshots_dir, f"screenshot_{ts}.png")

    try:
        monitor = int(args.get("monitor", "0"))
    except (ValueError, TypeError):
        return "Error: monitor 参数必须是数字"

    try:
        if window_kw and window_kw.lower() not in ("screen", "desktop", "full"):
            hwnd, title, pid = _find_window(window_kw)
            if hwnd is None:
                return ("Error: 未找到匹配 '" + window_kw + "' 的窗口。\n\n正确用法:\n"
                        "  run('shot', window='窗口标题或进程名关键词')  # 模糊匹配\n"
                        "  run('shot', action='list')  # 先列出所有窗口看有哪些可匹配")
            saved = _capture_window(hwnd, output)
            proc = _get_process_name(pid)
            return f"窗口截图已保存: {saved}\n  窗口标题: {title}\n  进程: {proc} (pid={pid})"
        else:
            saved = _ct_capture_screen(output, monitor)
            return f"屏幕截图已保存: {saved}\n  显示器: {monitor}"
    except Exception as e:
        return f"Error: {e}\n\n这是截图工具的异常。正确用法:\n" + tool_screenshot.__doc__


def tool_screenshot_ocr(args):
    """截取窗口截图并直接 OCR,一步到位返回文字。不需要中间图片文件。
    window: 窗口标题关键词(可选),不填则截全屏
    lang: OCR 语言,默认 ch"""
    import tempfile, os as _os
    window_kw = args.get("window", "")
    lang = str(args.get("lang", "ch"))

    tmp_path = _os.path.join(tempfile.gettempdir(), f"_shot_ocr_{_os.getpid()}.png")
    try:
        if window_kw:
            hwnd, title, pid = _find_window(window_kw)
            if hwnd is None:
                return f"Error: 未找到标题含 '{window_kw}' 的窗口"
            _capture_window(hwnd, tmp_path)
        else:
            _ct_capture_screen(tmp_path, 0)

        from .ocr import tool_ocr
        ocr_result = tool_ocr({"path": tmp_path, "lang": lang})
        prefix = f"窗口 '{title}'" if window_kw else "全屏"
        return f"[{prefix} 截图 OCR]\n{ocr_result}"
    except Exception as e:
        return f"Error: 截图 OCR 失败 - {e}"
    finally:
        try:
            if _os.path.exists(tmp_path):
                _os.unlink(tmp_path)
        except Exception:
            pass
