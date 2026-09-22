# -*- coding: utf-8 -*-
"""通用内存引擎: AOB 搜索 + 三种补丁 + 开关式恢复.

我是给 agent 看的源码,游戏相关只在 game.yaml 里,本文件一般不动.

补丁类型:
  bytes: 原地覆盖 N 字节 (nop / jmp短跳 / 改jcc),对应 CE 的 db XX.
  cave:  代码洞.原地写 E9 jmp 跳到 VirtualAllocEx 申请的内存,
        在洞里执行自定义字节后再 E9 跳回.对应 CE 的 alloc + jmp 脚本.

cave 字节约定 (避开运行时组装,用预组装 hex):
  - game.yaml 里写 cave_hex,不含最后跳回指令.
  - 引擎自动在末尾追加 E9 <rel32回原址+overwrite_len>.
  - 洞内部分支 (jne/je短跳) 由 agent 组装时一次算好 (见 tools/asm.py),
    引擎只管尾部统一跳回,洞内跳一律不出洞.
  - 外部变量 (CE 里 alloc(name,$8)+registersymbol 那套,洞里读写倍数/指针):
    用 data_size 声明字节数,洞内以 0xAAAAAAAAAAAAAAAA (8字节token)
    当立即数/地址占位,引擎分配后回填真实地址并清零.
    例: mov rax,0xAAAAAAAAAAAAAAAA / cmp qword ptr [rax],0
  - 组装工具: tools/asm.py (keystone,只在制作期用,运行时不需要).

AOB 三律 (沿用 lostvillage 实战):
  1. 只扫主模块 (pattern_scan_module),不全局扫.
  2. 特征码不得包含补丁位自身,否则打上补丁后重搜不到.
  3. 短 AOB 版本易失效,game.yaml 里留 version 字段,失效重走搜断反补丁.
"""
import re

try:
    from pymem import Pymem
    import pymem.process
    import pymem.pattern
    import pymem.memory
    _PYMEM_OK = True
    _PYMEM_ERR = ''
except Exception as ex:  # noqa: BLE001
    _PYMEM_OK = False
    _PYMEM_ERR = str(ex)

BACK_TOKEN = bytes.fromhex('DEADBEEFDEAD')  # 保留,命中即报错 (多出口不支持)
DATA_TOKEN = bytes.fromhex('AA' * 8)  # data_size 地址占位,引擎回填


def _rel32(src, dst):
    """src 处 E9 跳到 dst 的 rel32 (有符号32位)."""
    v = dst - (src + 5)
    return v.to_bytes(4, 'little', signed=True)


def _jmp_bytes(src, dst):
    return b'\xE9' + _rel32(src, dst)


class GameMemory:
    """一游戏一实例.构造时传入 game.yaml 解析后的 dict."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.exe = cfg['exe']
        self.pm = None
        self.pid = None
        self.addrs = {}   # patch名 -> AOB基址
        self.caves = {}   # patch名 -> 申请的洞地址
        self.orig = {}    # patch名 -> 原字节 (cave类:原地被jmp覆盖的字节)

    # ---- 进程 ----
    def _ensure(self):
        if not _PYMEM_OK:
            return False, '缺 pymem,跑: pip install pymem (%s)' % _PYMEM_ERR
        try:
            ent = pymem.process.process_from_name(self.exe)
            pid = int(ent.th32ProcessID)
        except Exception:
            return False, '游戏未运行 (%s)' % self.exe
        if self.pm is None or self.pid != pid:
            try:
                if self.pm is not None:
                    try:
                        self.pm.close_process()
                    except Exception:
                        pass
                pm = Pymem()
                pm.open_process_from_id(pid)
                self.pm, self.pid = pm, pid
                self.addrs, self.caves, self.orig = {}, {}, {}
            except Exception as ex:
                return False, '附加失败: %s (试管理员运行)' % ex
        return True, ''

    def _resolve(self, name):
        if name in self.addrs:
            return self.addrs[name]
        spec = self.cfg['patches'][name]
        # Unity(IL2CPP)等游戏代码在 GameAssembly.dll，主模块名由 game.yaml 的 module 指定
        mod_name = self.cfg.get('module') or self.exe
        mod = pymem.process.module_from_name(self.pm.process_handle, mod_name)
        addr = pymem.pattern.pattern_scan_module(
            self.pm.process_handle, mod, re.escape(bytes.fromhex(spec['aob'])))
        if not addr:
            return None
        self.addrs[name] = addr
        return addr

    # ---- 开关 ----
    def apply(self, name):
        ok, msg = self._ensure()
        if not ok:
            return False, msg
        spec = self.cfg['patches'][name]
        try:
            base = self._resolve(name)
            if not base:
                return False, '%s: AOB 未命中 (游戏可能更新了)' % name
            target = base + int(spec.get('offset', 0))
            if spec['type'] == 'bytes':
                return self._apply_bytes(name, target, spec)
            if spec['type'] == 'cave':
                return self._apply_cave(name, target, spec)
            return False, '%s: 未知 type %s' % (name, spec['type'])
        except Exception as ex:
            return False, '%s: %s' % (name, ex)

    def restore(self, name):
        ok, msg = self._ensure()
        if not ok:
            return True, '%s: 游戏未运行,视为已关' % name
        spec = self.cfg['patches'][name]
        try:
            base = self._resolve(name)
            if not base:
                return False, '%s: AOB 未命中' % name
            target = base + int(spec.get('offset', 0))
            if spec['type'] == 'bytes':
                off = bytes.fromhex(spec['off_bytes'])
                self.pm.write_bytes(target, off, len(off))
                return True, '%s 已关 (字节恢复)' % name
            if spec['type'] == 'cave':
                orig = self.orig.get(name)
                if orig is None:
                    orig = bytes.fromhex(spec['off_bytes'])
                self.pm.write_bytes(target, orig, len(orig))
                cave = self.caves.pop(name, None)
                if cave:
                    try:
                        pymem.memory.free_memory(self.pm.process_handle, cave)
                    except Exception:
                        pass
                self.orig.pop(name, None)
                return True, '%s 已关 (跳回恢复,洞已释放)' % name
            return False, '%s: 未知 type' % name
        except Exception as ex:
            return False, '%s: %s' % (name, ex)

    # ---- bytes ----
    def _apply_bytes(self, name, target, spec):
        on = bytes.fromhex(spec['on_bytes'])
        self.pm.write_bytes(target, on, len(on))
        back = self.pm.read_bytes(target, len(on)).hex().upper()
        if back != spec['on_bytes'].upper():
            return False, '%s: 写后校验不符 (%s)' % (name, back)
        return True, '%s 已开 @%s' % (name, hex(target))

    # ---- cave ----
    def _apply_cave(self, name, target, spec):
        """原地 overwrite_len 字节写 E9->cave,洞执行完跳回 target+overwrite_len."""
        ow_len = int(spec.get('overwrite_len', 5))
        if ow_len < 5:
            return False, '%s: cave要求 overwrite_len>=5 (放得下E9)' % name
        ret_addr = target + ow_len
        # 1. 备份原字节 (恢复用)
        if name not in self.orig:
            self.orig[name] = self.pm.read_bytes(target, ow_len)
        # 2. 组装洞字节
        body = bytes.fromhex(spec['cave_hex'])
        if BACK_TOKEN in body:
            # 洞内多出口暂不支持,保持单出口尾部回;复杂分支请在 CE 内收敛成单出口再贴
            return False, '%s: 洞内 6字节 DEADBEEF 标记暂不支持,保持单出口尾部回' % name
        data_size = int(spec.get('data_size', 0))
        if DATA_TOKEN in body and not data_size:
            return False, '%s: 洞内有地址占位但未声明 data_size' % name
        # 3. 先申请内存才能算出真实 rel32;布局 [body][E9回5字节][data区]
        total = len(body) + 5 + data_size
        cave = pymem.memory.allocate_memory(self.pm.process_handle, max(total, 64))
        if not cave:
            return False, '%s: VirtualAllocEx 失败' % name
        data_addr = cave + len(body) + 5
        if DATA_TOKEN in body:
            body = body.replace(DATA_TOKEN, data_addr.to_bytes(8, 'little'))
        # 回跳: cave+len(body) 处 E9 -> ret_addr
        back_ins = b'\xE9' + _rel32(cave + len(body), ret_addr)
        self.pm.write_bytes(cave, body + back_ins, len(body) + 5)
        # 原地跳洞: target 处 E9 -> cave,剩余字节 nop 垫平
        fwd = _jmp_bytes(target, cave)
        pad = b'\x90' * (ow_len - 5)
        self.pm.write_bytes(target, fwd + pad, ow_len)
        self.caves[name] = cave
        # 校验首字节是 E9
        if self.pm.read_bytes(target, 1).hex().upper() != 'E9':
            return False, '%s: 跳转写入校验失败' % name
        extra = ' 数据区%s' % hex(data_addr) if data_size else ''
        return True, '%s 已开 原地%s->洞%s->回%s%s' % (
            name, hex(target), hex(cave), hex(ret_addr), extra)

    def apply_all(self):
        return [self.apply(n) for n in self.cfg.get('patches', {})]

    def restore_all(self):
        return [self.restore(n) for n in self.cfg.get('patches', {})]

    def cave_data(self, name):
        """cave 补丁的数据区地址 (UI 写倍数/开关值用);无则返回 None."""
        spec = self.cfg['patches'][name]
        if spec['type'] != 'cave' or not int(spec.get('data_size', 0)):
            return None
        cave = self.caves.get(name)
        if not cave:
            return None
        return cave + len(bytes.fromhex(spec['cave_hex'])) + 5

    def write_cave_data(self, name, value, fmt='qword'):
        """往 cave 数据区写一个数(倍数/开关值)。补丁须先开(洞已分配)。

        fmt: byte/word/dword/qword/float/double。返回 (ok, msg)。"""
        if not _PYMEM_OK:
            return False, '未安装 pymem: %s' % _PYMEM_ERR
        ok, msg = self._ensure()
        if not ok:
            return False, msg
        addr = self.cave_data(name)
        if not addr:
            return False, '%s: 数据区不可用(非 cave/无 data_size/补丁未开)' % name
        fn = {'byte': 'write_uchar', 'word': 'write_short', 'dword': 'write_int',
              'qword': 'write_longlong', 'float': 'write_float',
              'double': 'write_double'}.get(fmt)
        if not fn:
            return False, '未知格式 %r,应为 byte/word/dword/qword/float/double' % fmt
        try:
            getattr(self.pm, fn)(addr, value)
        except Exception as ex:
            return False, '%s: 写入失败 %s' % (name, ex)
        back = self.pm.read_bytes(addr, 8).hex().upper()
        return True, '%s 数据区%s=%s(%s) 回读%s' % (name, hex(addr), value, fmt, back)
