# -*- coding: utf-8 -*-
"""toolbox.common: 包内共享小助手(长输出截断 + CLI/工具参数 coercion)。"""

MAX_LEN = 20000


def trunc(s, limit=MAX_LEN):
    """长输出截断,防止撑爆 agent 上下文。"""
    if isinstance(s, str) and len(s) > limit:
        return s[:limit] + f"\n...(已截断,共 {len(s)} 字符)"
    return s


def get_str(args, key, default=""):
    v = args.get(key, default)
    return default if v is None else str(v)


def get_int(args, key, default=0):
    """取整型参数,支持 0x 十六进制字符串。缺失回 default,格式错抛 ValueError。"""
    v = args.get(key, None)
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        raise ValueError(f"参数 {key} 必须是数字")
    return int(str(v), 0)


def get_float(args, key, default=0.0):
    v = args.get(key, None)
    if v is None or v == "":
        return default
    return float(v)
