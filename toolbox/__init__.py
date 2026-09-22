# -*- coding: utf-8 -*-
"""
toolbox — 跨项目通用工具库(CLI + import 双入口, agent 优先)。

══════════════════════════════════════════════════════════════
  用法一: CLI 模式(在 D:\\skills 下执行)
══════════════════════════════════════════════════════════════
  python -m toolbox -help                   列出所有工具
  python -m toolbox <工具> <参数=值> ...     调用工具(参数必须 key=value 形式)

══════════════════════════════════════════════════════════════
  用法二: import 模式(各子模块延迟加载,import 本包无副作用)
══════════════════════════════════════════════════════════════
  import toolbox
  toolbox.run("pe", action="exports", path="steam.dll")
  toolbox.run("shot_ocr", window="TIM")
  toolbox.run("ocr", path="screenshot.png")
  toolbox.run("db", action="search", keyword="Steam", db="data.db")
  toolbox.run("ce", action="ping")
  toolbox.run("info")  # 环境能力探测(调任何工具前可先看)

  结构化取值(绕开字符串截断): from toolbox.pe import pe_get_exports_detail

工具列表(10 个):
  pe              PE 文件分析(导出/导入/依赖/反汇编/vtable/扫描/字符串)
  shot            窗口/屏幕截图(按标题/进程名匹配,可列出窗口,多显示器)
  shot_ocr        截图+OCR 一步到位,直接返回文字
  click           鼠标点击(窗口归一化坐标或屏幕像素坐标)
  key             键盘按键(回车/ESC/快捷键等)
  image_describe  图片视觉描述(降采样+色块分割,让 agent 认出图像内容)
  ocr             图片 OCR 识别(中英文,自动适配 PaddleOCR 2.x/3.x)
  db              JSON 数据库(JSON 表→SQLite+FTS5,增删改查+全文搜索)
  ce              CE 桥接(搜值/AOB/反汇编/读写/断点,走命名管道)
  info            环境能力探测 + 用法速查

别名(兼容): pe_analyze→pe, screenshot→shot, screenshot_ocr→shot_ocr,
            describe→image_describe

设计:
  - 所有工具返回字符串:成功返回内容,失败返回 "Error: ..."(附用法提示)
  - 长输出自动截断(20000 字符);结构化需求直接调子模块函数
  - import 本模块无副作用(第三方依赖全部延迟到调用时加载)
"""
import importlib
import sys

from .common import trunc

# 短名 → (模块, 函数, 一句话描述, 参数说明)
TOOLS_META = {
    "pe": (
        "toolbox.pe",
        "tool_pe_analyze",
        "PE 文件分析(导出/导入/依赖/反汇编/vtable/扫描/字符串)",
        "path=<PE文件路径> action=<exports|imports|deps|disasm|vtable|scan|strings> [keyword=...] [target=...] [size=...] [kw=...] [pattern=...] [null_stop=...]",
    ),
    "shot": (
        "toolbox.shot",
        "tool_screenshot",
        "窗口/屏幕截图(按标题/进程名匹配,可列出窗口,多显示器)",
        "[window=<标题/进程名关键词>] [output=<保存路径>] [monitor=<序号>] [action=list]",
    ),
    "shot_ocr": (
        "toolbox.shot",
        "tool_screenshot_ocr",
        "截图+OCR一步到位,直接返回窗口/全屏的文字",
        "[window=<窗口标题关键词>] [lang=<ch|en>]",
    ),
    "click": (
        "toolbox.gui",
        "tool_click",
        "鼠标点击。配合 ocr/shot_ocr 坐标用。归一化坐标(window模式)或屏幕像素坐标",
        "x=<坐标> y=<坐标> [window=<窗口标题>] [button=<left|right|middle>] [clicks=<次数>] [delay=<等待秒数>]",
    ),
    "key": (
        "toolbox.gui",
        "tool_key",
        "发送键盘按键(回车/ESC/快捷键等)",
        "keys=<按键序列,如enter或ctrl+c> [delay=<等待秒数>]",
    ),
    "image_describe": (
        "toolbox.describe",
        "tool_image_describe",
        "图片视觉描述(降采样+色块分割,输出位置+颜色+形状+占比,让agent认出图像内容)",
        "path=<图片路径> [grid=<采样宽度8-64默认32>] [merge=<颜色合并阈值0-255默认30>]",
    ),
    "ocr": (
        "toolbox.ocr",
        "tool_ocr",
        "图片 OCR 识别(中英文,返回文本行+置信度+归一化坐标,自动适配 2.x/3.x)",
        "path=<图片路径> [lang=<ch|en>]",
    ),
    "db": (
        "toolbox.db",
        "tool_db",
        "JSON 数据库(JSON表→SQLite+FTS5,增删改查+全文搜索)",
        "action=<build|tables|search|row|rows|info|count|extract|vacuum|add|delete|update> [db=<库>] [dir=<数据目录>] [keyword=...] [table=<表名,search用>] [table_name=<表名,row/rows/info用>] [filter=...] [row_idx=N] [start=N] [limit=N] [json=...] [sub=record|table] [directory=...] [root=...] [out=<目录>]",
    ),
    "ce": (
        "toolbox.ce",
        "tool_ce",
        "CE 桥接(搜值/AOB/反汇编/读写内存/硬件断点,走命名管道,不点CE界面)",
        "action=<ping|scan|next|results|aob|dis|read|write|watch|hits|unwatch|eval> [value=...] [type=dword] [scan_type=exact] [pattern=...] [address=...] [count=N] [size=N] [bytes=144,144] [access=w] [id=...] [code=...] [limit=N] [offset=N]",
    ),
    "info": (
        "toolbox.info",
        "tool_deps",
        "环境能力探测 + 用法速查(调任何工具前可先看哪些能力可用)",
        "(无参数)",
    ),
}

# 旧版长名/别名 → 短名
ALIASES = {
    "pe_analyze": "pe",
    "screenshot": "shot",
    "screenshot_ocr": "shot_ocr",
    "describe": "image_describe",
}

# 直接函数调用兼容: toolbox.pe_get_exports(...) 等(延迟加载,PEP 562)
_LAZY_ATTRS = {
    "tool_pe_analyze": "pe",
    "pe_get_exports": "pe",
    "pe_get_exports_detail": "pe",
    "pe_get_imports": "pe",
    "pe_get_deps": "pe",
    "pe_disasm": "pe",
    "pe_vtable": "pe",
    "pe_scan": "pe",
    "pe_strings": "pe",
    "tool_screenshot": "shot",
    "tool_screenshot_ocr": "shot",
    "tool_ocr": "ocr",
    "tool_click": "gui",
    "tool_key": "gui",
    "tool_image_describe": "describe",
    "tool_db": "db",
    "tool_ce": "ce",
    "tool_deps": "info",
}


def __getattr__(name):
    if name in _LAZY_ATTRS:
        mod = importlib.import_module("toolbox." + _LAZY_ATTRS[name])
        return getattr(mod, name)
    raise AttributeError(f"module 'toolbox' has no attribute {name!r}")


def _load(tool):
    mod_name, func_name, _, _ = TOOLS_META[tool]
    return getattr(importlib.import_module(mod_name), func_name)


def run(tool, **kwargs):
    """统一入口: import toolbox 后一行调用任意工具(CLI 与库共用同一套工具)。

    参数:
      tool     工具短名(旧版长名也接受,见 ALIASES)
      **kwargs  该工具的参数,全部用关键字传递。
    返回: 字符串(成功=结果文本,失败="Error: ...")
    """
    tool = ALIASES.get(tool, tool)
    if tool not in TOOLS_META:
        return (f"Error: 未知工具 {tool!r},可选: {', '.join(sorted(TOOLS_META))}\n\n"
                f"正确用法示例:\n"
                f"  run('pe', action='exports', path='steam.dll')\n"
                f"  run('shot', window='窗口关键词')\n"
                f"  run('ocr', path='screenshot.png')\n"
                f"  run('ce', action='ping')\n"
                f"  run('info')")
    return trunc(_load(tool)(kwargs))


def print_help():
    print(__doc__)
    print("\n工具清单:")
    for name, (_, _, desc, params) in TOOLS_META.items():
        print(f"\n  {name}")
        print(f"    {desc}")
        print(f"    参数: {params}")
    print(f"\n旧版别名: {', '.join(f'{k}→{v}' for k, v in ALIASES.items())}")


def main(argv):
    # 强制 UTF-8 输出: 避免 Windows 控制台/子进程管道下中文乱码
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, 'reconfigure'):
            _s.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    # 无参或 -help → 打印清单
    if len(argv) == 1 or argv[1] in ("-help", "--help", "-h", "help"):
        print_help()
        return 0

    name = ALIASES.get(argv[1], argv[1])
    if name not in TOOLS_META:
        print(f"Error: 未知工具 '{argv[1]}'\n")
        print_help()
        return 1

    fn = _load(name)

    # 解析剩余参数:key=value 形式
    args = {}
    for arg in argv[2:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                print(f"Error: 参数格式错误 '{arg}' (等号前缺少参数名)")
                return 1
            if not v:
                print(f"Error: 参数 '{k}' 缺少值 (格式: {k}=<值>)")
                return 1
            if k in args:
                print(f"Error: 重复参数 '{k}'")
                return 1
            args[k] = v
        else:
            # 裸标志一律报错: 所有工具参数均为 key=value 形式
            print(f"Error: 未知参数 '{arg}' (参数需要 key=value 形式, 如 button=right)")
            return 1

    result = fn(args)
    print(trunc(result) if isinstance(result, str) else result)
    return 0 if not str(result).startswith("Error") else 1


__all__ = ["run", "print_help", "main", "TOOLS_META", "ALIASES"] + sorted(_LAZY_ATTRS)
