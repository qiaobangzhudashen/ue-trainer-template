# -*- coding: utf-8 -*-
"""通用 UI:读 games/<slug>/game.yaml + items.txt 驱动.
用法: python app.py --game lostvillage --root D:\Steam\...\TheLostVillage
打包: tools/build.py 打成单 exe,双击即用.
"""
import argparse
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'engine'))
sys.path.insert(0, BASE)

try:
    import yaml
except ImportError:
    yaml = None

from engine import db as dbmod
from engine import lua_bridge as bridge
from engine import memory as memmod


def load_game(slug):
    import io
    path = os.path.join(BASE, 'games', slug, 'game.yaml')
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    if yaml:
        return yaml.safe_load(text)
    # 无 yaml 库时的最小解析:只读 exe/mod_rel/give_func 与 patches(aob/offset/on/off)
    cfg = {'patches': {}, 'toggles': {}, 'packs': []}
    import re
    m = re.search(r'^exe:\s*(.+)$', text, re.M)
    if m:
        cfg['exe'] = m.group(1).strip()
    m = re.search(r'^mod_rel:\s*(.+)$', text, re.M)
    if m:
        cfg['mod_rel'] = m.group(1).strip()
    return cfg


class App(tk.Tk):
    def __init__(self, slug, root):
        super().__init__()
        self.slug = slug
        self.cfg = load_game(slug)
        self.root_dir = root or ''
        self.title('UE Trainer - %s' % slug)
        self.geometry('860x640')
        self.mem = memmod.GameMemory(self.cfg) if self.cfg.get('patches') else None
        items_path = os.path.join(BASE, 'games', slug, 'items.txt')
        try:
            self.items = dbmod.load_items(items_path) if os.path.exists(items_path) else []
        except Exception as ex:
            messagebox.showerror('错误', 'items.txt 读取失败:\n%s' % ex)
            self.items = []
        self.status = tk.StringVar(value='就绪.库 %d 种.' % len(self.items))
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=8, pady=6)
        ttk.Label(top, text='游戏根目录:').pack(side='left')
        self.root_var = tk.StringVar(value=self.root_dir)
        ttk.Entry(top, textvariable=self.root_var, width=50).pack(side='left', padx=4)
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=8, pady=4)
        self.tab_item = ttk.Frame(nb)
        self.tab_toggle = ttk.Frame(nb)
        nb.add(self.tab_item, text='物品给予')
        nb.add(self.tab_toggle, text='开关/补丁')
        self._build_item()
        self._build_toggles()
        ttk.Label(self, textvariable=self.status).pack(fill='x', padx=8, pady=4)

    def _build_item(self):
        fr = ttk.Frame(self.tab_item)
        fr.pack(fill='x', padx=6, pady=6)
        ttk.Label(fr, text='搜索:').pack(side='left')
        self.kw = tk.StringVar()
        ent = ttk.Entry(fr, textvariable=self.kw, width=28)
        ent.pack(side='left', padx=4)
        ent.bind('<KeyRelease>', lambda e: self._filter())
        ttk.Label(fr, text='数量:').pack(side='left', padx=(10, 0))
        self.qty = tk.StringVar(value='99')
        ttk.Entry(fr, textvariable=self.qty, width=8).pack(side='left', padx=4)
        ttk.Button(fr, text='给予选中', command=self._give).pack(side='left', padx=6)
        self.tree = ttk.Treeview(self.tab_item, columns=('id', 'name', 'type'),
                                 show='headings', selectmode='extended', height=18)
        for c, w in (('id', 80), ('name', 200), ('type', 400)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w)
        self.tree.pack(fill='both', expand=True, padx=6, pady=4)
        self._filter()

    def _filter(self):
        kw = self.kw.get().strip()
        self.tree.delete(*self.tree.get_children())
        n = 0
        for it in self.items:
            if kw and kw not in str(it['id']) and kw not in it['name']:
                continue
            self.tree.insert('', 'end', iid=str(it['id']),
                             values=(it['id'], it['name'], it['type']))
            n += 1
            if n >= 2000:
                break

    def _paths(self):
        return bridge.game_paths(self.root_var.get(), self.cfg.get('mod_rel', ''))

    def _give(self):
        sel = [int(i) for i in self.tree.selection()]
        if not sel:
            messagebox.showinfo('提示', '先选中物品.')
            return
        try:
            q = int(self.qty.get())
        except ValueError:
            messagebox.showerror('错误', '数量必须是整数.')
            return
        p = self._paths()
        lines = ['lv_give %d %d' % (i, q) for i in sel]
        try:
            sz = os.path.getsize(p['log'])
        except OSError:
            sz = 0
        bridge.send_lines(p['cmd'], lines)
        self.status.set('已下发 %d 条,等游戏内到账.' % len(lines))
        threading.Thread(target=self._wait, args=(p['log'], sz, len(lines)),
                         daemon=True).start()

    def _wait(self, log, sz, n):
        out = bridge.wait_lvt(log, sz, n)
        self.after(0, lambda: self.status.set(
            '游戏回 %d 行.' % len(out) if out else '超时,去游戏内/日志确认.'))

    def _build_toggles(self):
        fr = ttk.Frame(self.tab_toggle)
        fr.pack(fill='x', padx=10, pady=10)
        for name, spec in (self.cfg.get('patches') or {}).items():
            v = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(fr, text='%s [%s]' % (spec.get('desc', name), name),
                                 variable=v,
                                 command=lambda n=name, vv=v: self._mem(n, vv.get()))
            cb.pack(anchor='w', pady=2)
        for key, tg in (self.cfg.get('toggles') or {}).items():
            v = tk.BooleanVar(value=False)
            ttk.Checkbutton(fr, text=tg.get('label', key), variable=v,
                            command=lambda t=tg, vv=v: self._toggle(t, vv.get())
                            ).pack(anchor='w', pady=4)
        for pack in self.cfg.get('packs') or []:
            ttk.Button(fr, text=pack['name'],
                       command=lambda p=pack: self._pack(p)).pack(anchor='w', pady=2)

    def _mem(self, name, on):
        if not self.mem:
            return
        ok, msg = self.mem.apply(name) if on else self.mem.restore(name)
        self.status.set(msg)

    def _toggle(self, tg, on):
        p = self._paths()
        line = tg['lua_on'] if on else tg['lua_off']
        try:
            sz = os.path.getsize(p['log'])
        except OSError:
            sz = 0
        bridge.send_lines(p['cmd'], [line])
        for n in tg.get('mem') or []:
            if self.mem:
                self.mem.apply(n) if on else self.mem.restore(n)
        self.status.set('已下发 %s.' % line)

    def _pack(self, pack):
        if not messagebox.askyesno('确认', '%s,确定发放吗?' % pack['name']):
            return
        p = self._paths()
        bridge.send_lines(p['cmd'],
                          ['lv_give %d %d' % (i, n) for i, n in pack['items']])
        self.status.set('礼包已下发.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default='lostvillage')
    ap.add_argument('--root', default='')
    a = ap.parse_args()
    App(a.game, a.root).mainloop()
