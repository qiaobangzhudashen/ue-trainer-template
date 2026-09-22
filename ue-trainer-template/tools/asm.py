# -*- coding: utf-8 -*-
"""制作期汇编 helper (运行时不需要,只有 agent 贴 cave_hex 时用).

依赖: pip install keystone-engine capstone
用法:
  python tools/asm.py --asm "pushfq|cmp dword ptr [rbx+0x20],2|jne code|..."
  python tools/asm.py --file cave.asm
输出 hex (贴进 game.yaml 的 cave_hex) + capstone 反汇编复核.

约定:
  - 洞内分支用 label, keystone 一次算好相对偏移,引擎不管洞内跳.
  - 洞尾不要写跳回 (引擎自动追加 E9 回原址+overwrite_len).
  - 外部变量地址用 0xAAAAAAAAAAAAAAAA 占位 (mov rax,0xAAAA...),
    引擎按 data_size 分配后回填.
"""
import argparse
import sys

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_64
except ImportError:
    print('缺 keystone-engine,跑: pip install keystone-engine')
    sys.exit(1)


def asm_to_hex(src, base=0):
    ks = Ks(KS_ARCH_X86, KS_MODE_64)
    # keystone 用 ; 分隔, label 用 : 结尾
    encoding, _ = ks.asm(src, base)
    return bytes(encoding).hex().upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asm', default='')
    ap.add_argument('--file', default='')
    a = ap.parse_args()
    src = a.asm.replace('|', '\n')
    if a.file:
        with open(a.file, encoding='utf-8') as f:
            src = f.read()
    hexs = asm_to_hex(src)
    print(hexs)
    print('len=%d' % (len(hexs) // 2))
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = False
        for ins in md.disasm(bytes.fromhex(hexs), 0x0):
            print('0x%x:\t%s\t%s' % (ins.address, ins.mnemonic, ins.op_str))
    except ImportError:
        pass


if __name__ == '__main__':
    main()
