# -*- coding: utf-8 -*-
"""CE 桥接工具: 通过命名管道驱动 Cheat Engine,不点 CE 界面。

要求(缺一不可,失败时返回 Error + 自查提示,不抛异常):
  1. Cheat Engine 已启动,ce_mcp_bridge.lua 已加载(看到 MCP Server Listening)
  2. CE 已 attach 目标进程
  3. CE 设置 Extra 里关掉 "Query memory region routines"(否则扫保护页蓝屏)

默认桥: D:\\opencode\\ce-bridge\\ce_direct.py 同协议(4字节长度头+JSON-RPC);
可用环境变量 CE_BRIDGE_PIPE 覆盖管道名,CE_BRIDGE_PATH 覆盖桥脚本路径(备用)。
本模块 import 无副作用(pywin32 延迟到调用时)。
"""
import json
import os
import struct

PIPE = os.environ.get("CE_BRIDGE_PIPE", r"\\.\pipe\CE_MCP_Bridge_v99")

SETUP_HINT = (
    "自查: 1)CE是否启动并执行了 ce_mcp_bridge.lua "
    "(应看到 MCP Server Listening); 2)CE是否已attach游戏进程; "
    "3)管道名是否为 " + PIPE
)


def _call(method, params=None, timeout=30):
    """调一次管道。返回 (ok, result_or_error)。"""
    try:
        import win32file
    except ImportError:
        return False, "未安装 pywin32(pip install pywin32)"
    req = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    raw = json.dumps(req).encode("utf-8")
    try:
        h = win32file.CreateFile(
            PIPE, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None, win32file.OPEN_EXISTING, 0, None)
    except Exception as e:
        return False, f"连不上CE管道({e})。{SETUP_HINT}"
    try:
        win32file.WriteFile(h, struct.pack("<I", len(raw)))
        win32file.WriteFile(h, raw)
        (n,) = struct.unpack("<I", _read_exact(h, 4))
        if n > 16 * 1024 * 1024:
            return False, "CE 返回超限(>16MB),缩小范围重试"
        data = _read_exact(h, n)
    except Exception as e:
        return False, f"管道读写失败({e})。{SETUP_HINT}"
    finally:
        h.close()
    try:
        resp = json.loads(data.decode("utf-8", errors="replace"))
    except Exception as e:
        return False, f"CE 返回解析失败({e})"
    if "error" in resp:
        return False, str(resp["error"])
    return True, resp.get("result", resp)


def _read_exact(h, size):
    import win32file
    chunks, rest = [], size
    while rest > 0:
        chunk = win32file.ReadFile(h, rest)[1]
        if not chunk:
            raise ConnectionError("pipe closed")
        chunks.append(chunk)
        rest -= len(chunk)
    return b"".join(chunks)


def _fmt(ok, res, limit=6000):
    s = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, indent=1)
    if len(s) > limit:
        s = s[:limit] + f"\n...(已截断,共 {len(s)} 字符)"
    return ("" if ok else "Error: ") + s


def tool_ce(args):
    """CE 桥接。run("ce", action=..., ...)。

    action 子命令:
      ping      连通性(顺带确认CE版本/是否attach)
      scan      首扫数值(value=<值> type=<dword|float|...>)
      next      收窄(scan_type=<exact|increased|decreased|changed|unchanged> [value=...])
      results   取扫描结果(limit=N,默认50)
      aob       特征码扫描(pattern="AA BB ?? .." [limit=N])
      dis       反汇编(address=<地址> [count=N])
      read      读内存(address=<地址> size=<字节数>)
      write     写内存(address=<地址> bytes=<十进制逗号分隔,如144,144>)
      watch     硬件断点(address=<地址> [access=r|w|rw] [id=...],最多4个)
      hits      取断点命中([id=...])
      unwatch   删断点(id=...)
      eval      执行CE Lua(code=<lua代码>)

    地址接受 "game.exe+0x1234" 或 "0x..." 字符串。
    返回字符串;失败返回 "Error: ..."。"""
    from .common import get_str, get_int

    action = get_str(args, "action", "").lower()
    valid = {"ping", "scan", "next", "results", "aob", "dis", "read",
             "write", "watch", "hits", "unwatch", "eval"}
    if action not in valid:
        return f"Error: 未知 action {action!r},应为 {sorted(valid)}\n\n正确用法:\n" + tool_ce.__doc__

    try:
        if action == "ping":
            ok, res = _call("ping")
            return _fmt(ok, res, 1000)

        if action == "scan":
            value = get_str(args, "value", "")
            if not value:
                return "Error: scan 需要 value。用法:\n  run('ce', action='scan', value='15000', type='dword')"
            ok, res = _call("scan_all", {"value": value, "type": get_str(args, "type", "dword")})
            return _fmt(ok, res)

        if action == "next":
            p = {"scan_type": get_str(args, "scan_type", "exact")}
            if args.get("value") not in (None, ""):
                p["value"] = get_str(args, "value")
            ok, res = _call("next_scan", p)
            return _fmt(ok, res)

        if action == "results":
            ok, res = _call("get_scan_results",
                            {"offset": get_int(args, "offset", 0), "limit": get_int(args, "limit", 50)})
            return _fmt(ok, res)

        if action == "aob":
            pat = get_str(args, "pattern", "")
            if not pat:
                return "Error: aob 需要 pattern。用法:\n  run('ce', action='aob', pattern='48 8B ?? ?? 57', limit=10)"
            ok, res = _call("aob_scan", {"pattern": pat, "limit": get_int(args, "limit", 10)})
            return _fmt(ok, res)

        if action == "dis":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: dis 需要 address。用法:\n  run('ce', action='dis', address='game.exe+0x5000', count=20)"
            ok, res = _call("disassemble", {"address": addr, "count": get_int(args, "count", 20)})
            return _fmt(ok, res)

        if action == "read":
            addr = get_str(args, "address", "")
            size = get_int(args, "size", 0)
            if not addr or size <= 0:
                return "Error: read 需要 address+size。用法:\n  run('ce', action='read', address='0x...', size=16)"
            ok, res = _call("read_memory", {"address": addr, "size": size})
            return _fmt(ok, res, 2000)

        if action == "write":
            addr = get_str(args, "address", "")
            byts = get_str(args, "bytes", "")
            if not addr or not byts:
                return ("Error: write 需要 address+bytes(高危,先确认地址)。用法:\n"
                        "  run('ce', action='write', address='0x...', bytes='144,144')")
            try:
                barr = [int(x, 0) for x in byts.split(",")]
            except ValueError:
                return "Error: bytes 格式错误,应为十进制逗号分隔(如 144,144)"
            ok, res = _call("write_memory", {"address": addr, "bytes": barr})
            return _fmt(ok, res, 1000)

        if action == "watch":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: watch 需要 address。用法:\n  run('ce', action='watch', address='0x...', access='w')"
            acc = get_str(args, "access", "w")
            bid = get_str(args, "id", "") or ("w_" + addr[-8:])
            ok, res = _call("set_data_breakpoint",
                            {"address": addr, "id": bid, "access_type": acc, "size": get_int(args, "size", 4)})
            return _fmt(ok, res)

        if action == "hits":
            p = {}
            if get_str(args, "id", ""):
                p["id"] = get_str(args, "id")
            ok, res = _call("get_breakpoint_hits", p)
            return _fmt(ok, res)

        if action == "unwatch":
            bid = get_str(args, "id", "")
            if not bid:
                return "Error: unwatch 需要 id"
            ok, res = _call("remove_breakpoint", {"id": bid})
            return _fmt(ok, res, 1000)

        if action == "eval":
            code = get_str(args, "code", "")
            if not code:
                return "Error: eval 需要 code(Lua 代码)"
            ok, res = _call("evaluate_lua", {"code": code})
            return _fmt(ok, res, 4000)

    except ValueError as e:
        return f"Error: 参数格式错误 - {e}"
    except Exception as e:
        return f"Error: {e}\n\n这是 ce 工具的异常。正确用法:\n" + tool_ce.__doc__
    return "Error: 未知分支"
