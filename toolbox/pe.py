# -*- coding: utf-8 -*-
"""PE 文件分析(零外部依赖)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os
import re
import struct
from bisect import bisect_right

# ===========================================================================

def pe__layout(b, e_lfanew):
    """PE 布局偏移(纯算术,不加校验): 返回 (coff, size_of_opt, opt, is_pe32p, dd)."""
    coff = e_lfanew + 4
    size_of_opt = struct.unpack_from('<H', b, coff + 16)[0]
    opt = coff + 20
    is_pe32p = (struct.unpack_from('<H', b, opt)[0] == 0x20b)
    dd = opt + (112 if is_pe32p else 96)
    return coff, size_of_opt, opt, is_pe32p, dd


def pe__read_header(b):
    """Return (is_pe32p, sections, opt_hdr_off). sections: [(va, vs, raw)]"""
    if len(b) < 64:  # PE 头最小 64 字节(含 PE 签名偏移), 更小不可能是 PE
        raise ValueError('文件过小(<64字节), 不是 PE 文件')
    if b[:2] != b'MZ':
        raise ValueError('不是 PE(MZ) 文件')
    e_lfanew = struct.unpack_from('<I', b, 0x3C)[0]
    if e_lfanew + 26 > len(b):  # e_lfanew 越界(需再读 2 字节 magic): 畸形文件, 避免后续晦涩的 struct.error
        raise ValueError('e_lfanew 越界, 不是合法 PE 文件')
    if b[e_lfanew:e_lfanew + 4] != b'PE\x00\x00':
        raise ValueError('not a valid PE signature')
    coff, size_of_opt, opt, is_pe32p, _ = pe__layout(b, e_lfanew)
    if size_of_opt < (112 if is_pe32p else 96):  # 可选头小于标准大小: 数据目录偏移无效
        raise ValueError('可选头过小, 不是合法 PE 文件')
    if opt + size_of_opt > len(b):  # 可选头声明长度超出文件: 截断文件, 避免后续 struct.error
        raise ValueError('可选头越界(文件被截断), 不是合法 PE 文件')
    num_sections = struct.unpack_from('<H', b, coff + 2)[0]
    sec_off = opt + size_of_opt
    sections = []
    for i in range(num_sections):
        s = sec_off + i * 40
        if s + 40 > len(b):  # 截断文件: 节表不完整则停止解析
            break
        vs = struct.unpack_from('<I', b, s + 8)[0]
        va = struct.unpack_from('<I', b, s + 12)[0]
        raw = struct.unpack_from('<I', b, s + 20)[0]
        sections.append((va, vs, raw))
    return is_pe32p, sections, opt


def pe__rva_to_offset(rva, sections):
    """RVA to file offset. Returns None if unmapped (no fallback, no dirty data).
    raw=0 的节(.bss 等未初始化数据)在文件里没有内容, 不参与映射。"""
    for va, vs, raw in sections:
        if raw == 0:
            continue
        if va <= rva < va + vs:
            return rva - va + raw
    return None


def pe__read_cstr(b, off):
    if off is None or off < 0 or off >= len(b):
        return ''
    end = off
    while end < len(b) and b[end] != 0:
        end += 1
    return b[off:end].decode('ascii', errors='replace')


def pe__load(path):
    with open(path, 'rb') as f:
        b = f.read()
    is64, sections, opt = pe__read_header(b)
    image_base = struct.unpack_from('<Q', b, opt + 24)[0] if is64 else struct.unpack_from('<I', b, opt + 28)[0]
    return b, is64, sections, image_base


def pe_get_exports(path):
    """Export function name list."""
    return [n for n, _, _, _ in pe_get_exports_detail(path)]


def pe_get_exports_detail(path):
    """[(name, rva, ordinal, forwarder), ...]. rva = 导出函数入口 RVA; forwarder 非空 = 前向导出."""
    b, _, sections, _ = pe__load(path)
    return pe__exports_from_buf(b, sections)


def pe__exports_from_buf(b, sections):
    """从已加载的 PE 字节解析导出表 (disasm/vtable 复用, 避免重复读盘).
    返回 [(name, rva, ordinal, forwarder)]; forwarder 非空 = 前向导出(转发目标, 如 "KERNEL32.Thunk")."""
    e_lfanew = struct.unpack_from('<I', b, 0x3C)[0]
    _, _, _, _, dd = pe__layout(b, e_lfanew)
    if dd + 8 > len(b):  # 数据目录越界: 截断文件
        return []
    exp_rva, exp_size = struct.unpack_from('<II', b, dd)
    if exp_rva == 0 or exp_size == 0:
        return []
    exp_off = pe__rva_to_offset(exp_rva, sections)
    if exp_off is None or exp_off + 40 > len(b):
        return []
    base_ord = struct.unpack_from('<I', b, exp_off + 16)[0]
    num_funcs = struct.unpack_from('<I', b, exp_off + 20)[0]
    num_names = struct.unpack_from('<I', b, exp_off + 24)[0]
    funcs_rva = struct.unpack_from('<I', b, exp_off + 28)[0]
    names_rva = struct.unpack_from('<I', b, exp_off + 32)[0]
    ords_rva = struct.unpack_from('<I', b, exp_off + 36)[0]
    funcs_off = pe__rva_to_offset(funcs_rva, sections)
    names_off = pe__rva_to_offset(names_rva, sections)
    ords_off = pe__rva_to_offset(ords_rva, sections)
    if None in (funcs_off, names_off, ords_off):
        return []
    out = []
    for i in range(num_names):
        np = names_off + i * 4
        op = ords_off + i * 2
        if np + 4 > len(b) or op + 2 > len(b):
            break
        name_off = pe__rva_to_offset(struct.unpack_from('<I', b, np)[0], sections)
        name = pe__read_cstr(b, name_off)
        idx = struct.unpack_from('<H', b, op)[0]
        if idx >= num_funcs:  # 畸形 PE: ordinal 索引越界, 跳过避免读函数表外数据
            continue
        fp = funcs_off + idx * 4
        if fp + 4 > len(b):
            continue
        func_rva = struct.unpack_from('<I', b, fp)[0]
        forwarder = ""
        if exp_size and exp_rva <= func_rva < exp_rva + exp_size:
            # 函数表项指向导出目录内部 = 前向导出(字符串如 "KERNEL32.Thunk"), 不是代码入口
            forwarder = pe__read_cstr(b, pe__rva_to_offset(func_rva, sections))
        out.append((name, func_rva, base_ord + idx, forwarder))
    return out


def pe_get_imports(path):
    """[(dll_name_lower, [func,...]), ...]. func: import-by-name entries; ordinal=@<n>."""
    b, is64, sections, _ = pe__load(path)
    e_lfanew = struct.unpack_from('<I', b, 0x3C)[0]
    _, _, _, _, dd = pe__layout(b, e_lfanew)
    if dd + 16 > len(b):  # 数据目录越界: 截断文件
        return []
    imp_rva, imp_size = struct.unpack_from('<II', b, dd + 8)
    if imp_rva == 0 or imp_size == 0:
        return []
    off = pe__rva_to_offset(imp_rva, sections)
    if off is None:
        return []
    thunk_sz = 8 if is64 else 4
    thunk_fmt = '<Q' if is64 else '<I'
    ord_flag = 1 << 63 if is64 else 1 << 31
    name_mask = 0x7fffffffffffffff if is64 else 0x7fffffff  # by-name 时清掉 ordinal 标志位,保留完整 RVA
    result = []
    guard = 0
    desc_max = min(imp_size // 20, 512) if imp_size else 512  # 描述符表大小界定, 防畸形文件越界
    while off is not None and off + 20 <= len(b) and guard < desc_max:
        guard += 1
        olt, td, fc, name_rva, ft = struct.unpack_from('<IIIII', b, off)
        if (olt, td, fc, name_rva, ft) == (0, 0, 0, 0, 0):  # 整个描述符全零才算表尾
            break
        dll_name = pe__read_cstr(b, pe__rva_to_offset(name_rva, sections)).lower()
        thunk_rva = olt if olt else ft
        funcs = []
        if thunk_rva:
            t = pe__rva_to_offset(thunk_rva, sections)
            if t is not None:
                i = 0
                while i < 4096:
                    p = t + i * thunk_sz
                    if p + thunk_sz > len(b):
                        break
                    v = struct.unpack_from(thunk_fmt, b, p)[0]
                    if v == 0:
                        break
                    if v & ord_flag:
                        funcs.append(f'@{v & 0xffff}')
                    else:
                        fn_off = pe__rva_to_offset(v & name_mask, sections)
                        if fn_off is not None:
                            name = pe__read_cstr(b, fn_off + 2)
                            if name:  # 读取失败/为空串则跳过, 避免污染导入名列表
                                funcs.append(name)
                    i += 1
        if dll_name:
            result.append((dll_name, funcs))
        off += 20
    return result


def pe_get_deps(path):
    """DLL dependency names only (deduplicated, order preserved, lowercase)."""
    seen = []
    for dll, _ in pe_get_imports(path):
        if dll not in seen:
            seen.append(dll)
    return seen


def pe_collect_strings(b, sections, minlen=5):
    """RVA to ASCII string mapping (for resolving memory references during disassembly)."""
    smap = {}
    for va, vs, raw in sections:
        if raw == 0:  # .bss 等未初始化节: 文件里没有数据, 跳过防把文件头当节内容
            continue
        chunk = b[raw:raw + vs]
        i = 0
        while i < len(chunk):
            j = i
            while j < len(chunk) and 0x20 <= chunk[j] < 0x7f:
                j += 1
            if j - i >= minlen:
                smap.setdefault(va + i, chunk[i:j].decode('ascii', 'replace'))
            i = j + 1
    return smap


def pe__exp_map(exps_all):
    """导出表 [(name, rva, ordinal, forwarder)] → {rva: [names]}。

    反汇编逐指令注解时 O(1) 命中;原逐条线性扫全表,大 size 下很慢。"""
    m = {}
    for n, r, _, _ in exps_all:
        m.setdefault(r, []).append(n)
    return m


def pe__resolve_imm(v, exps, smap, skeys, image_base):
    """Immediate to export name / string reference annotation。

    exps 推荐传 pe__exp_map() 的 dict;旧式 [(name, rva)] list 仍兼容(慢)。"""
    ann = []
    if isinstance(exps, dict):
        names = exps.get(v)
        if names:
            ann.extend(f'导出:{nm}' for nm in names)
    else:
        for nm, rva in exps:
            if rva == v:
                ann.append(f'导出:{nm}')
    i = bisect_right(skeys, v) - 1
    if i >= 0:
        sk = skeys[i]
        if 0 <= v - sk < len(smap[sk]):
            ann.append(f'str:"{smap[sk][v - sk:v - sk + 48]}"')
    return ' | '.join(ann)


def pe_disasm(path, target, size=0x300):
    """反汇编指定 RVA 或导出函数,返回格式化文本。

    需要 capstone 才有完整反汇编;未安装则降级为 hex dump + call/jmp 标注。
    """
    b, is64, sections, image_base = pe__load(path)
    exps_all = pe__exports_from_buf(b, sections)
    exps = pe__exp_map(exps_all)
    smap = pe_collect_strings(b, sections)
    skeys = sorted(smap)

    if target.lower().startswith('0x') or target.isdigit():
        rva = int(target, 0)
        label = f'RVA {target}'
    else:
        hit = [x for x in exps_all if x[0].lower() == target.lower()]
        if not hit:
            hint = " (如为十六进制 RVA 请加 0x 前缀)" if target.isdigit() else ""
            return f"Error: 导出 '{target}' 未找到{hint}。已有: {[n for n, _, _, _ in exps_all]}"
        _n, rva, _o, fwd = hit[0]
        if fwd:
            return f"{target} 是前向导出(转发至 {fwd}), 无本地代码可反汇编"
        label = target

    off = pe__rva_to_offset(rva, sections)
    if off is None:
        return f"Error: RVA 0x{rva:x} 映射失败"
    code = b[off:off + size]
    va = image_base + rva
    lines = [f";; === {label} @ ImageBase+0x{rva:x} = 0x{va:x}  size=0x{size:x}  ({'64' if is64 else '32'}位) ==="]

    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64, CS_OP_IMM, CS_OP_MEM
        from capstone.x86 import X86_REG_RIP
        md = Cs(CS_ARCH_X86, CS_MODE_64 if is64 else CS_MODE_32)
        md.detail = True
        for insn in md.disasm(code, va):
            bh = ' '.join(f'{x:02x}' for x in insn.bytes)
            ann = ''
            if insn.mnemonic in ('call', 'jmp') or insn.mnemonic.startswith('j'):
                for op in insn.operands:
                    if op.type == CS_OP_IMM:
                        r = op.imm - image_base if op.imm >= image_base else op.imm
                        a = pe__resolve_imm(r, exps, smap, skeys, image_base)
                        if a:
                            ann = f'  ; -> {a}'
            for op in insn.operands:
                # 绝对寻址(base=0)或 x64 RIP-relative(base=RIP, disp 已是绝对地址)才注解
                if op.type == CS_OP_MEM and op.mem.index == 0 and op.mem.disp and op.mem.base in (0, X86_REG_RIP):
                    r = op.mem.disp - image_base if op.mem.disp >= image_base else op.mem.disp
                    a = pe__resolve_imm(r, exps, smap, skeys, image_base)
                    if a:
                        ann = f'  ; -> {a}'
            mark = '  ; ***' if insn.mnemonic in ('call', 'ret', 'retn') or insn.mnemonic.startswith('j') else ''
            lines.append(f"0x{insn.address:08x}: {bh:26s} {insn.mnemonic:7s} {insn.op_str:38s}{ann}{mark}")
    except ImportError:
        lines.append(";; (capstone 未安装,降级为 hex dump + call/jmp 标注)")
        lines.append(pe__disasm_fallback(code, va, image_base, is64, exps, smap, skeys))
    return "\n".join(lines)


def pe__disasm_fallback(code, va, image_base, is64, exps, smap, skeys):
    """无 capstone 时的降级:逐行 hex dump,标注 E8/E9/FF15 调用目标。返回文本。"""
    lines = []
    i = 0
    while i < len(code):
        addr = va + i
        b = code[i]

        # call rel32 (E8) / jmp rel32 (E9)
        if b in (0xE8, 0xE9) and i + 5 <= len(code):
            mnem = 'call' if b == 0xE8 else 'jmp'
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = addr + 5 + rel
            r = target - image_base if target >= image_base else target
            ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
            bh = ' '.join(f'{x:02x}' for x in code[i:i+5])
            note = f'  ; -> {ann}' if ann else ''
            lines.append(f"0x{addr:08x}: {bh:26s} {mnem:7s} 0x{target:x}{note}  ; ***")
            i += 5
            continue

        # call/jmp [iat] — FF 15 / FF 25 (6-byte); x64 为 RIP 相对寻址, 目标 = 下一条指令 + 符号扩展 disp32
        if b == 0xFF and i + 6 <= len(code) and code[i+1] in (0x15, 0x25):
            mnem = 'call' if code[i+1] == 0x15 else 'jmp'
            bh = ' '.join(f'{x:02x}' for x in code[i:i+6])
            if is64:
                d32 = struct.unpack_from('<i', code, i + 2)[0]
                slot = addr + 6 + d32  # 存放函数指针的槽位地址
                r = slot - image_base if slot >= image_base else slot
                ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
                note = f'  ; => 槽位 0x{slot:x}' + (f' ({ann})' if ann else '')
                lines.append(f"0x{addr:08x}: {bh:26s} {mnem:7s} qword ptr [rip+0x{d32:x}]{note}  ; ***")
            else:
                indirect = struct.unpack_from('<I', code, i + 2)[0]
                r = indirect - image_base if indirect >= image_base else indirect
                ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
                note = f'  ; -> {ann}' if ann else ''
                lines.append(f"0x{addr:08x}: {bh:26s} {mnem:7s} dword ptr [0x{indirect:x}]{note}  ; ***")
            i += 6
            continue

        # ret (C3) / ret imm16 (C2 xx xx)
        if b == 0xC3:
            bh = f'{b:02x}'
            lines.append(f"0x{addr:08x}: {bh:26s} ret{'':7s}{'':38s}  ; ***")
            i += 1
            continue
        if b == 0xC2 and i + 3 <= len(code):
            imm = struct.unpack_from('<H', code, i + 1)[0]
            bh = ' '.join(f'{x:02x}' for x in code[i:i+3])
            lines.append(f"0x{addr:08x}: {bh:26s} ret{'':7s} 0x{imm:x}{'':30s}  ; ***")
            i += 3
            continue

        # short conditional jumps (7x) / short jmp (EB)
        if (0x70 <= b <= 0x7F or b == 0xEB) and i + 2 <= len(code):
            rel = struct.unpack_from('<b', code, i + 1)[0]
            target = addr + 2 + rel
            jcc_names = ['jo','jno','jb','jae','je','jne','jbe','ja',
                         'js','jns','jp','jnp','jl','jge','jle','jg']
            mnem = 'jmp' if b == 0xEB else jcc_names[b - 0x70]
            bh = f'{b:02x} {code[i+1]:02x}'
            lines.append(f"0x{addr:08x}: {bh:26s} {mnem:7s} 0x{target:x}{'':30s}  ; ***")
            i += 2
            continue

        # push imm32 (68 xx xx xx xx) — often string/constant refs
        if b == 0x68 and i + 5 <= len(code):
            imm = struct.unpack_from('<I', code, i + 1)[0]
            r = imm - image_base if imm >= image_base else imm
            ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
            bh = ' '.join(f'{x:02x}' for x in code[i:i+5])
            note = f'  ; -> {ann}' if ann else ''
            lines.append(f"0x{addr:08x}: {bh:26s} push{'':7s} 0x{imm:x}{note}")
            i += 5
            continue

        # mov reg, imm32/imm64 (B8-BF; 64 位为 REX.W + B8-BF)
        if is64 and i + 1 < len(code) and code[i] == 0x48 and 0xB8 <= code[i+1] <= 0xBF and i + 10 <= len(code):
            imm = struct.unpack_from('<Q', code, i + 2)[0]
            r = imm - image_base if imm >= image_base else imm
            ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
            bh = ' '.join(f'{x:02x}' for x in code[i:i+10])
            reg = ['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi'][code[i+1] - 0xB8]
            note = f'  ; -> {ann}' if ann else ''
            lines.append(f"0x{addr:08x}: {bh:26s} mov{'':7s} {reg}, 0x{imm:x}{note}")
            i += 10
            continue
        if not is64 and 0xB8 <= b <= 0xBF and i + 5 <= len(code):
            imm = struct.unpack_from('<I', code, i + 1)[0]
            r = imm - image_base if imm >= image_base else imm
            ann = pe__resolve_imm(r, exps, smap, skeys, image_base)
            bh = ' '.join(f'{x:02x}' for x in code[i:i+5])
            reg = ['eax','ecx','edx','ebx','esp','ebp','esi','edi'][b - 0xB8]
            note = f'  ; -> {ann}' if ann else ''
            lines.append(f"0x{addr:08x}: {bh:26s} mov{'':7s} {reg}, 0x{imm:x}{note}")
            i += 5
            continue

        # 其他: raw hex dump, 每行 1 字节
        bh = f'{b:02x}'
        lines.append(f"0x{addr:08x}: {bh}")
        i += 1
    return "\n".join(lines)


def pe_vtable(path, rva, max_slots=128, null_stop=3):
    """展开 vtable 槽位,返回格式化文本。"""
    b, is64, sections, image_base = pe__load(path)
    exps = pe__exp_map(pe__exports_from_buf(b, sections))
    smap = pe_collect_strings(b, sections)
    skeys = sorted(smap)
    ptr_size = 8 if is64 else 4
    fmt = '<Q' if is64 else '<I'
    lines = [f";; === vtable @ RVA 0x{rva:x}  ({'64' if is64 else '32'}位)  null_stop={null_stop} ==="]
    null_streak = 0
    for i in range(max_slots):
        off = pe__rva_to_offset(rva + i * ptr_size, sections)
        if off is None or off + ptr_size > len(b):
            lines.append(f"  [{i}] (越界/节结束)")
            break
        v = struct.unpack_from(fmt, b, off)[0]
        if v == 0:
            null_streak += 1
            if null_streak >= null_stop:
                lines.append(f"  [{i}] x{null_streak} NULL (连续空槽,vtable 结束)")
                break
            lines.append(f"  [{i}] NULL")
            continue
        null_streak = 0
        r = v - image_base if v >= image_base else v
        tag2 = pe__resolve_imm(r, exps, smap, skeys, image_base)
        lines.append(f"  [{i}] 0x{v:x}  (RVA 0x{r:x})  {('-> ' + tag2) if tag2 else ''}")
    return "\n".join(lines)


def pe_scan(directory, pattern=None, keyword=None):
    """扫描目录中匹配的 PE 文件,分析组件互连和系统依赖广度。返回格式化文本。"""
    from collections import defaultdict
    if pattern:
        SELF = re.compile(pattern, re.I)
    else:
        SELF = re.compile(r'\b(?:ace|sguard|tenbount|tersafe|gdp)(?:_\w+)?\b', re.I)  # 兼容 sguard_x64.sys 等后缀, 词边界防 interface.dll 误匹配
    SYS_HOT = re.compile(
        r'\b(?:ws2_32|wininet|winhttp|wsock|crypt|wintrust|bcrypt|ncrypt|advapi32|ntdll|psapi|'
        r'iphlpapi|secur32|schannel|userenv|wtsapi32|setupapi|version|dbghelp|winmm|ole32|shell32|gdi32)\b', re.I)
    targets = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith(('.dll', '.exe', '.sys')) and SELF.search(f):
                if keyword is None or re.search(re.escape(keyword), f, re.I):
                    targets.append(os.path.join(root, f))
    if not targets:
        return f"在 {directory} 中未找到匹配 /{SELF.pattern}/ 的 PE 文件"
    self_edges = defaultdict(set)
    sys_deps = defaultdict(set)
    fail = []
    for p in sorted(targets):
        fname = os.path.basename(p).lower()
        try:
            for dll in pe_get_deps(p):
                if SELF.search(dll):
                    self_edges[fname].add(dll)
                else:
                    sys_deps[dll].add(fname)
        except Exception as e:
            fail.append((fname, str(e)))
    lines = [f"=== 自家组件互连({len(targets)} 个组件)==="]
    any_edge = False
    for k in sorted(self_edges):
        if self_edges[k]:
            any_edge = True
            lines.append(f"  {k} -> {', '.join(sorted(self_edges[k]))}")
    if not any_edge:
        lines.append("  (无静态自家依赖 — 全动态 LoadLibrary 加载)")
    if fail:
        shown = fail[:10]
        lines.append(f"  [解析失败 {len(fail)} 个]: {shown}" + (f" ... +{len(fail)-10}" if len(fail) > 10 else ""))
    lines.append(f"\n=== 系统DLL广度: {len(sys_deps)} 个 ===")
    lines.append("--- 网络/加密/系统探测(移植敏感)---")
    hot = [(s, sys_deps[s]) for s in sorted(sys_deps) if SYS_HOT.search(s)]
    for s, users in hot:
        lines.append(f"  {s:16} <- {len(users)} 组件")
    lines.append(f"--- 其余 {len(sys_deps) - len(hot)} 个 ---")
    rest = sorted(s for s in sys_deps if not SYS_HOT.search(s))
    lines.append("  " + ", ".join(rest))
    return "\n".join(lines)


DEFAULT_KW = {
    '内存/注入': r'\b(?:mem(?:ory)?|inject(?:or)?|hook|patch|virtualprotect)\b|篡改|注入',
    '调试/转储': r'\b(?:debug(?:ger)?|dump|minidump|x64dbg|attach|detach)\b|cheat.?engine|转储',
    '加速/外挂': r'\b(?:speed|hack|cheat|macro)\b|外挂|变速|加速|宏|脚本',
    '进程/模块': r'\b(?:enum(?:erate)?(?:proc)?|module|psapi|toolhelp|blacklist)\b|进程|枚举|黑名单',
    '驱动/内核': r'\b(?:driver|kernel|ssdt|callback|notify|ioctl)\b|\.sys|驱动|内核',
    '网络/回连': r'\b(?:socket|connect|server|report|upload|heartbeat|recv|send)\b|心跳|上报|回连',
    '文件/完整性': r'\b(?:hash|md5|sha\d*|signature|verify|integrity|crc\d*)\b|完整|校验|签名',
    '系统信息': r'\b(?:mac|cpu|hwid|machine|finger(?:print)?|device)\b|硬件|指纹',
}


def pe_strings(path, kw_csv=None):
    """提取 PE 文件中的可读字符串,按类别筛选。返回格式化文本。"""
    if kw_csv:
        kws = {'自定义': '|'.join(re.escape(x) for x in kw_csv.split(','))}
    else:
        kws = DEFAULT_KW
    with open(path, 'rb') as f:
        b = f.read()
    asc = set(re.findall(rb'[\x20-\x7e]{5,80}', b))
    # UTF-16LE 扫描: 段内严格 2 字节对齐(可打印字符 + \x00 高位), 消除正则的奇偶错位与切段问题
    u16 = set()
    i = 0
    n = len(b)
    while i + 1 < n:
        if 0x20 <= b[i] <= 0x7e and b[i + 1] == 0:
            j = i + 2
            while j + 1 < n and 0x20 <= b[j] <= 0x7e and b[j + 1] == 0:
                j += 2
            if (j - i) // 2 >= 5:  # 至少 5 个字符
                u16.add(b[i:j])
            i = j  # 跳过已扫描的连续段
        else:
            i += 1
    alls = {s.decode('ascii', 'replace') for s in asc} | {s.decode('utf-16le', 'replace').strip() for s in u16}
    lines = [f"=== {path}: {len(alls)} 条字符串,按类别筛 ==="]
    for cat, pat in kws.items():
        rx = re.compile(pat, re.I)
        hits = sorted({s for s in alls if rx.search(s)})
        if hits:
            lines.append(f"\n[{cat}] {len(hits)} 条")
            for h in hits[:15]:
                lines.append(f"   {h}")
            if len(hits) > 15:
                lines.append(f"   ... +{len(hits) - 15}")
    return "\n".join(lines)


def tool_pe_analyze(args):
    """PE 文件分析(32/64 位)。

    run("pe", action=..., path=..., ...)

    action 子命令:
      exports   导出表(名称+RVA+序号),keyword 按名称过滤
      imports   导入表(依赖DLL+函数数),keyword 按DLL名过滤
      deps      依赖DLL名(去重)
      disasm    反汇编(target=导出名或RVA,size=字节数默认0x300,需capstone无则降级)
      vtable    展开vtable(target=RVA,null_stop=连续空槽数默认3)
      scan      扫描目录看组件依赖广度(pattern=自定义正则,默认匹配ACE/SGuard系列;keyword 按文件名过滤)
      strings   提取字符串按类别筛(kw=自定义关键词逗号分隔)

    返回字符串;失败返回 "Error: ..."。长输出自动截断(20000字符)。"""
    path = args.get("path", "")
    action = str(args.get("action", "")).lower()
    if not action or not path:
        return "Error: 用法不对。以下是完整说明:\n\n" + tool_pe_analyze.__doc__
    valid = {"exports", "imports", "deps", "disasm", "vtable", "scan", "strings"}
    if action not in valid:
        return f"Error: 未知 action {action!r},应为 {sorted(valid)}\n\n正确用法:\n" + tool_pe_analyze.__doc__

    _MAX = 20000

    def _trunc(s):
        return s if len(s) <= _MAX else s[:_MAX] + f"\n...(已截断,共 {len(s)} 字符)"

    try:
        if action == "exports":
            kws = [k.strip() for k in str(args.get("keyword", "")).split(",") if k.strip()] if args.get("keyword") else []
            exps = pe_get_exports_detail(path)
            if not exps:
                return f"{path}: 无导出表(可能不是 DLL/不是 PE)"
            lines = [f"{path}: 导出表 {len(exps)} 个:"]
            shown = 0
            for n, r, o, f in exps:
                if kws and not any(k.lower() in n.lower() for k in kws if k.strip()):
                    continue
                fwd = f"  → 转发 {f}" if f else ""
                lines.append(f"  {n:30} RVA=0x{r:x}  ord={o}{fwd}")
                shown += 1
            if kws:
                lines.insert(1, f"  (keyword 过滤后 {shown} 个)")
            return _trunc("\n".join(lines))

        if action == "imports":
            kws = [k.strip() for k in str(args.get("keyword", "")).split(",") if k.strip()] if args.get("keyword") else []
            imps = pe_get_imports(path)
            if not imps:
                return f"{path}: 无导入表"
            lines = [f"{path}: 导入表 {len(imps)} 个 DLL:"]
            shown = 0
            for dll, funcs in imps:
                if kws and not any(k.lower() in dll.lower() for k in kws if k.strip()):
                    continue
                lines.append(f"  {dll}  [{len(funcs)}]")
                shown += 1
            if kws:
                lines.insert(1, f"  (keyword 过滤后 {shown} 个)")
            return _trunc("\n".join(lines))

        if action == "deps":
            deps = pe_get_deps(path)
            if not deps:
                return f"{path}: 无依赖 DLL"
            return f"{path}: 依赖 {len(deps)} 个 DLL:\n  " + "\n  ".join(deps)

        if action == "disasm":
            target = args.get("target", "")
            if not target:
                return "Error: disasm 需要 target。正确用法:\n  run('pe', action='disasm', path='文件', target='导出名或RVA', size=0x200)\n  先用 run('pe', action='exports', path='文件') 查看有哪些导出名"
            size = int(str(args.get("size")), 0) if args.get("size") else 0x300
            return _trunc(pe_disasm(path, str(target), size))

        if action == "vtable":
            rva_raw = args.get("target") or args.get("rva", "")
            if not rva_raw:
                return "Error: vtable 需要 RVA。正确用法:\n  run('pe', action='vtable', path='文件', target=0x18000, null_stop=3)"
            null_stop = int(str(args.get("null_stop", "3")), 0)
            return _trunc(pe_vtable(path, int(str(rva_raw), 0), null_stop=null_stop))

        if action == "scan":
            pat = args.get("pattern") or None
            return _trunc(pe_scan(path, pattern=pat, keyword=args.get("keyword") or None))

        if action == "strings":
            kw = args.get("kw") or None
            return _trunc(pe_strings(path, kw))

    except Exception as e:
        return f"Error: {e}\n\n这是 pe 工具的异常。正确用法:\n" + tool_pe_analyze.__doc__
