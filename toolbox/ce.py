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
import time

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


def _tag(mnem, opstr=""):
    """指令标注(启发式,供 agent 速览trace用,不是定论)。

    [CRYPTO?] = 疑似加解密(xor/位移/乘且带立即数;xor同寄存器清零除外)。
    [CALL]/[BRANCH]/[RET] = 调用/分支/返回,顺藤找门时盯 CALL 上游。"""
    m = (mnem or "").lower()
    ops = (opstr or "").lower()
    if m in ("xor", "rol", "ror", "shl", "shr", "sal", "sar", "not", "neg",
             "imul", "aesenc", "aesdec", "aesimc"):
        if m == "xor":
            parts = [p.strip() for p in ops.split(",")]
            if len(parts) == 2 and parts[0] == parts[1]:
                return ""  # xor eax,eax = 清零惯用,不是加密
        if any(c.isdigit() for c in ops):
            return " [CRYPTO?]"
        return ""
    if m == "call":
        return " [CALL]"
    if m in ("ret", "retn", "retf"):
        return " [RET]"
    if m.startswith("j"):
        return " [BRANCH]"
    return ""


def _thread_ids(limit=100):
    """线程 id_int 列表。返回 (ok, ids_or_err)。"""
    ok, res = _call("get_thread_list", {"offset": 0, "limit": limit})
    if not ok:
        return False, res
    try:
        ids = [t.get("id_int") for t in (res.get("threads") or [])
               if isinstance(t, dict) and t.get("id_int") is not None]
        return True, ids
    except Exception as e:
        return False, f"线程列表解析失败: {e}"


def _ensure_dbg(interface=2):
    """确保调试器已附加(VEH=2 默认,隐蔽)。返回 (ok, err)。"""
    ok, res = _call("debug_is_debugging", {})
    if not ok:
        return False, res
    try:
        if isinstance(res, dict) and res.get("is_debugging"):
            return True, ""
    except Exception:
        pass
    ok2, res2 = _call("debug_process", {"interface": interface})
    if not ok2:
        return False, res2
    return True, ""


def tool_ce(args):
    """CE 桥接。run("ce", action=..., ...)。

    action 子命令:
      ping      连通性(顺带确认CE版本/是否attach)
      scan      首扫数值(value=<值> type=<dword|float|...>)
      next      收窄(scan_type=<exact|increased|decreased|changed|unchanged> [value=...])
      results   取扫描结果(limit=N,默认50)
      aob       特征码扫描(pattern="AA BB ?? .." [module=主模块名] [limit=N])
      dis       反汇编(address=<地址> [count=N])
      read      读内存(address=<地址> size=<字节数>)
      write     写内存(address=<地址> bytes=<十进制逗号分隔,如144,144>)
      rint      按类型读数(address=<地址> [type=dword|float|...])
      wint      按类型写数(address=<地址> value=<值> [type=...],高危先确认地址)
      rstr      读内存字符串(address=<地址> [size=256] [wide=0/1])
      watch     硬件断点(address=<地址> [access=r|w|rw] [id=...],最多4个;≈F5/F6)
      hits      取断点命中([id=...])
      unwatch   删断点(id=...)
      eval      执行CE Lua(code=<lua代码>)
      signature 唯一AOB(address=<代码地址>;慢,全内存扫,只对定稿地址用)
      aa        执行AA脚本(script=<含[ENABLE]文本>;先aacheck验语法)
      aacheck   只验AA语法不执行(script=<文本>)
      asm       单条汇编→机器码(instruction="mov eax, 1" [address=...])
      refs      找哪些代码引用该地址(address=<地址> [limit=N])
      rtti      vtable指针认C++类名(address=<地址>)
      dissect   结构体剖析(address=<基址> [size=256])
      ptrchain  指针链求值(base="game.exe+0x1234" offsets="0x10,0x20,0x8")
      psearch   内存字符串搜索(string=<文本> [wide=0/1] [limit=N])
      analyze   函数调用/跳转分析(address=<函数入口> [count=200])
      instr     单条指令详情(address=<地址>)
      pause/unpause 冻结/恢复目标进程(稳定读数用)
      threads   列线程(id_int 供 lbr/step 用)
      lbr       LBR分支回溯:op=start开记录→用户做触发动作→op=read取最近分支对并标注(往前找关键调用,零单步)
      step      单步trace:冻住thread单步count条,逐条记RIP+指令+[CRYPTO?/CALL/BRANCH]标注(往后找解密,完事自动恢复跑)
      dbgdetach 摘掉调试器(trace季结束时调)

    地址接受 "game.exe+0x1234" 或 "0x..." 字符串。
    返回字符串;失败返回 "Error: ..."。"""
    from .common import get_str, get_int

    action = get_str(args, "action", "").lower()
    valid = {"ping", "scan", "next", "results", "aob", "dis", "read",
             "write", "watch", "hits", "unwatch", "eval",
             "signature", "aa", "aacheck", "asm", "refs", "rtti",
             "dissect", "ptrchain", "psearch", "analyze", "instr",
             "pause", "unpause", "rint", "wint", "rstr",
             "threads", "lbr", "step", "dbgdetach"}
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
            mod = get_str(args, "module", "")
            if mod:
                # 限定主模块(技能铁律:不用全局 aobscan,卡UI约10秒)
                ok, res = _call("aob_scan_module",
                                {"pattern": pat, "module": mod, "limit": get_int(args, "limit", 10)})
            else:
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

        if action == "signature":
            addr = get_str(args, "address", "")
            if not addr:
                return ("Error: signature 需要 address(慢: 全内存扫, 只对代码地址用)。用法:\n"
                        "  run('ce', action='signature', address='game.exe+0x5000')")
            ok, res = _call("generate_signature", {"address": addr})
            return _fmt(ok, res)

        if action == "aa":
            script = get_str(args, "script", "")
            if not script:
                return ("Error: aa 需要 script(AA 脚本, 含 [ENABLE]/[DISABLE])。用法:\n"
                        "  run('ce', action='aa', script='[ENABLE]\\n...')  # 先 aacheck 验语法")
            ok, res = _call("auto_assemble", {"script": script})
            return _fmt(ok, res)

        if action == "aacheck":
            script = get_str(args, "script", "")
            if not script:
                return "Error: aacheck 需要 script(只验语法不执行)"
            ok, res = _call("auto_assemble_check", {"script": script})
            return _fmt(ok, res, 2000)

        if action == "asm":
            inst = get_str(args, "instruction", "")
            if not inst:
                return ("Error: asm 需要 instruction。用法:\n"
                        "  run('ce', action='asm', instruction='mov eax, 1')")
            p = {"instruction": inst}
            if get_str(args, "address", ""):
                p["address"] = get_str(args, "address")
            ok, res = _call("assemble_instruction", p)
            return _fmt(ok, res, 1000)

        if action == "refs":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: refs 需要 address(找哪些代码引用该地址)"
            ok, res = _call("find_references", {"address": addr, "limit": get_int(args, "limit", 50)})
            return _fmt(ok, res)

        if action == "rtti":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: rtti 需要 address(vtable 指针, 认 C++ 类名)"
            ok, res = _call("get_rtti_classname", {"address": addr})
            return _fmt(ok, res, 1000)

        if action == "dissect":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: dissect 需要 address(结构体基址)"
            ok, res = _call("dissect_structure",
                            {"address": addr, "size": get_int(args, "size", 256)})
            return _fmt(ok, res)

        if action == "ptrchain":
            base = get_str(args, "base", "")
            offs = get_str(args, "offsets", "")
            if not base or not offs:
                return ("Error: ptrchain 需要 base+offsets。用法:\n"
                        "  run('ce', action='ptrchain', base='game.exe+0x1234', offsets='0x10,0x20,0x8')")
            try:
                arr = [int(x, 0) for x in offs.split(",")]
            except ValueError:
                return "Error: offsets 格式错误,应为逗号分隔(如 0x10,0x20,0x8)"
            ok, res = _call("read_pointer_chain", {"base": base, "offsets": arr})
            return _fmt(ok, res)

        if action == "psearch":
            s = get_str(args, "string", "")
            if not s:
                return "Error: psearch 需要 string(内存字符串搜索)"
            ok, res = _call("search_string", {"string": s,
                                              "wide": get_str(args, "wide", "") not in ("", "0", "false"),
                                              "limit": get_int(args, "limit", 20)})
            return _fmt(ok, res)

        if action == "analyze":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: analyze 需要 address(函数入口, 画调用/跳转)"
            ok, res = _call("analyze_function",
                            {"address": addr, "max_instructions": get_int(args, "count", 200)})
            return _fmt(ok, res)

        if action == "instr":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: instr 需要 address(单条指令详情)"
            ok, res = _call("get_instruction_info", {"address": addr})
            return _fmt(ok, res, 2000)

        if action == "pause":
            ok, res = _call("pause_process", {})
            return _fmt(ok, res, 1000)

        if action == "unpause":
            ok, res = _call("unpause_process", {})
            return _fmt(ok, res, 1000)

        if action == "rint":
            addr = get_str(args, "address", "")
            if not addr:
                return ("Error: rint 需要 address(按类型读数,比裸字节直观)。用法:\n"
                        "  run('ce', action='rint', address='0x...', type='float')")
            typ = get_str(args, "type", "dword")
            if typ not in ("byte", "word", "dword", "qword", "float", "double"):
                return f"Error: 未知 type {typ!r},应为 byte/word/dword/qword/float/double"
            ok, res = _call("read_integer", {"address": addr, "type": typ})
            return _fmt(ok, res, 1000)

        if action == "wint":
            addr = get_str(args, "address", "")
            if not addr or get_str(args, "value", "") == "":
                return ("Error: wint 需要 address+value(高危,先确认地址)。用法:\n"
                        "  run('ce', action='wint', address='0x...', value='9999', type='dword')")
            typ = get_str(args, "type", "dword")
            if typ not in ("byte", "word", "dword", "qword", "float", "double"):
                return f"Error: 未知 type {typ!r},应为 byte/word/dword/qword/float/double"
            try:
                val = float(args["value"]) if typ in ("float", "double") else int(str(args["value"]), 0)
            except ValueError:
                return "Error: value 格式错误(整数支持0x十六进制)"
            ok, res = _call("write_integer", {"address": addr, "value": val, "type": typ})
            return _fmt(ok, res, 1000)

        if action == "rstr":
            addr = get_str(args, "address", "")
            if not addr:
                return "Error: rstr 需要 address(读内存字符串,认物品名用)"
            ok, res = _call("read_string", {"address": addr,
                                            "max_length": get_int(args, "size", 256),
                                            "wide": get_str(args, "wide", "") not in ("", "0", "false")})
            return _fmt(ok, res, 2000)

        if action == "threads":
            ok, res = _call("get_thread_list", {"offset": get_int(args, "offset", 0),
                                                "limit": get_int(args, "limit", 100)})
            if not ok:
                return _fmt(ok, res)
            try:
                lines = [f"线程 {len(res.get('threads') or [])} 个(thread= 传 id_int):"]
                for t in (res.get("threads") or [])[:100]:
                    lines.append(f"  id={t.get('id_int')} hex={t.get('id_hex')}")
                return "\n".join(lines)
            except Exception:
                return _fmt(True, res)

        if action == "lbr":
            # LBR 分支记录:往前找关键调用,零单步,游戏几乎无感知。
            # 流程: lbr op=start → 用户做触发动作 → lbr op=read(自动关)。
            op = get_str(args, "op", "start").lower()
            if op not in ("start", "read"):
                return "Error: lbr 需要 op=start|read"
            ok, err = _ensure_dbg(get_int(args, "interface", 2))
            if not ok:
                return _fmt(False, err)
            tsel = get_str(args, "thread", "all")
            if tsel.lower() == "all":
                ok, tids = _thread_ids()
                if not ok:
                    return _fmt(False, tids)
            else:
                try:
                    tids = [int(tsel, 0)]
                except ValueError:
                    return "Error: thread 应为数字 id(先 run('ce', action='threads') 看)或 all"
            if op == "start":
                fails = []
                for tid in tids:
                    ok, res = _call("debug_set_last_branch_recording",
                                    {"thread_id": tid, "enabled": True})
                    if not ok:
                        fails.append(f"{tid}:{res}"[:100])
                if fails and len(fails) == len(tids):
                    return _fmt(False, "LBR 开启全部失败: " + "; ".join(fails[:3]))
                return (f"LBR 已开({len(tids) - len(fails)}/{len(tids)} 线程)。"
                        f"现在去游戏里做触发动作,然后 run('ce', action='lbr', op='read')"
                        + (f" 失败:{fails[:3]}" if fails else ""))
            # op == read: 取各线程最近分支对,反查目标指令并标注,读完即关
            pairs_cap = min(max(get_int(args, "pairs", 16), 1), 32)
            out = ["[LBR 分支回溯(每行: from → to 处指令,往前找关键调用)]"]
            total = 0
            for tid in tids:
                ok, res = _call("debug_get_last_branch_record", {"thread_id": tid})
                _call("debug_set_last_branch_recording", {"thread_id": tid, "enabled": False})
                if not ok:
                    continue
                try:
                    recs = res.get("records") or []
                except Exception:
                    continue
                if not recs:
                    continue
                out.append(f"--- thread {tid} (最近 {min(len(recs), pairs_cap)} 对) ---")
                for r in recs[-pairs_cap:]:
                    if total >= 96:
                        out.append("...(对数超限,加 pairs 调小范围)")
                        break
                    total += 1
                    try:
                        frm, to = r.get("from_address"), r.get("to_address")
                    except Exception:
                        continue
                    okd, resd = _call("get_instruction_info", {"address": to})
                    if okd and isinstance(resd, dict):
                        text = str(resd.get("instruction", "?"))
                        parts = text.split(None, 1)
                        mn = parts[0].lower() if parts else ""
                        ops = parts[1] if len(parts) > 1 else ""
                        if resd.get("is_call"):
                            flag = " [CALL]"
                        elif resd.get("is_ret"):
                            flag = " [RET]"
                        elif resd.get("is_jump"):
                            flag = " [BRANCH]"
                        else:
                            flag = _tag(mn, ops)
                        line = f"{frm} → {to}: {text}{flag}"
                    else:
                        line = f"{frm} → {to}: (指令详情失败)"
                    out.append(line)
                if total >= 96:
                    break
            if total == 0:
                return "LBR 无记录(触发动作可能没命中代码分支,或线程选错,换 thread 重试)"
            return _fmt(True, "\n".join(out), 12000)

        if action == "step":
            # 单步采样:冻住一条线程,N 步内每步记 RIP+指令+标注,找解密/跟调用链。
            # 用法: pause 住目标界面(或悬停加密值)→ step → 看 [CRYPTO?]/[CALL]。
            ok, err = _ensure_dbg(get_int(args, "interface", 2))
            if not ok:
                return _fmt(False, err)
            tsel = get_str(args, "thread", "")
            if tsel:
                try:
                    tid = int(tsel, 0)
                except ValueError:
                    return "Error: thread 应为数字 id(先 run('ce', action='threads') 看)"
            else:
                ok, tids = _thread_ids(limit=20)
                if not ok or not tids:
                    return _fmt(False, tids if not ok else "无线程(游戏是否在跑?)")
                tid = tids[0]
            count = min(max(get_int(args, "count", 80), 1), 300)
            stop_ret = get_str(args, "stop", "") == "ret"
            method = "step_over" if get_str(args, "over", "") not in ("", "0", "false") else "step_into"
            ok, res = _call("debug_break_thread", {"thread_id": tid})
            if not ok:
                return _fmt(False, f"冻线程失败: {res}(换个 thread 或确认游戏在跑)")
            rip = None
            for _ in range(12):  # 等线程停稳
                ok, res = _call("debug_get_context", {"thread_id": tid})
                if ok:
                    try:
                        rip = res.get("registers", {}).get("RIP") or res.get("registers", {}).get("Eip")
                    except Exception:
                        rip = None
                    if rip:
                        break
                time.sleep(0.25)
            if not rip:
                _call("debug_continue", {"method": "run"})
                return _fmt(False, "线程没停住(可能该线程正睡大觉,换个 thread 重试)")
            try:
                init_regs = res.get("registers", {}) if isinstance(res, dict) else {}
            except Exception:
                init_regs = {}
            out = [f"[单步 trace thread={tid} 起点 {rip} 方法={method}"
                   + (" 遇ret停" if stop_ret else "") + "]",
                   "初始关键寄存器: " + ", ".join(
                       f"{k}={init_regs.get(k)}" for k in ("RAX", "RBX", "RCX", "RDX", "RSI", "RDI") if init_regs.get(k))]
            for i in range(count):
                oki, resi = _call("get_instruction_info", {"address": rip})
                if not oki or not isinstance(resi, dict):
                    out.append(f"#{i} {rip}: (指令详情失败,停止)")
                    break
                text = str(resi.get("instruction", "?"))
                parts = text.split(None, 1)
                mn = parts[0].lower() if parts else ""
                ops = parts[1] if len(parts) > 1 else ""
                size = resi.get("size", "?")
                if resi.get("is_call"):
                    flag = " [CALL]"
                elif resi.get("is_ret"):
                    flag = " [RET]"
                elif resi.get("is_jump"):
                    flag = " [BRANCH]"
                else:
                    flag = _tag(mn, ops)
                out.append(f"#{i} {rip} [{size}B] {text}{flag}")
                if stop_ret and (resi.get("is_ret") or mn in ("ret", "retn", "retf")):
                    out.append("(遇 ret,按 stop=ret 停止;函数可能返回,看调用方请对上层地址 lbr)")
                    break
                okc, _resc = _call("debug_continue", {"method": method})
                if not okc:
                    out.append("(单步继续失败,停止)")
                    break
                rip2 = None
                for _ in range(6):
                    okr, resr = _call("debug_get_context", {"thread_id": tid})
                    if okr:
                        try:
                            rip2 = (resr.get("registers", {}).get("RIP")
                                    or resr.get("registers", {}).get("Eip"))
                        except Exception:
                            rip2 = None
                        if rip2:
                            break
                    time.sleep(0.1)
                if not rip2:
                    out.append("(取不到新 RIP,停止)")
                    break
                rip = rip2
            _call("debug_continue", {"method": "run"})  # 松开线程,游戏恢复跑
            out.append("(线程已恢复跑;调试器保持附加,用完 run('ce', action='dbgdetach') 摘掉)")
            return _fmt(True, "\n".join(out), 12000)

        if action == "dbgdetach":
            ok, res = _call("debug_detach", {})
            return _fmt(ok, res, 1000)

    except ValueError as e:
        return f"Error: 参数格式错误 - {e}"
    except Exception as e:
        return f"Error: {e}\n\n这是 ce 工具的异常。正确用法:\n" + tool_ce.__doc__
    return "Error: 未知分支"
