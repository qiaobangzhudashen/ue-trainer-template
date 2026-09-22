# -*- coding: utf-8 -*-
"""通用 UI:读 games/<slug>/game.yaml + items.txt 驱动.
用法: python app.py --game lostvillage --root D:\Steam\...\TheLostVillage
打包: tools/build.py 打成单 exe,双击即用 (自动定位+只补缺项部署+运行检测).

引擎分流 (互不影响):
- ue + ue4ss: 外部物品下发 + 开关/补丁 (山门路线, 回归机)
- unity-mono + none: 纯安装器, 不做外部下发, 进游戏用内挂窗口 (侠影录路线, 首验机)
- unity-il2cpp + ue4ss/bepinex-file: 预留, 按 game.yaml 切桥
缺 engine/bridge 字段即按 UE 旧行为回退.
"""
import argparse
import configparser
import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'engine'))
sys.path.insert(0, BASE)

try:
    import yaml
except ImportError:
    yaml = None

from engine import items as dbmod
from engine import lua_bridge as bridge
from engine import memory as memmod

try:
    from engine import deploy as deploymod
except ImportError:
    deploymod = None

try:
    from tools import steam_find
except ImportError:
    try:
        import steam_find as steam_find
    except ImportError:
        steam_find = None


def _exe_dir():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))


def _resource(*parts):
    """游戏数据文件定位: exe 同目录优先(打包后可直接改 yaml 不用重打),
    回退到源码 BASE(开发期)。"""
    exe_dir = _exe_dir()
    # ui/app.py 在 ui/ 下, exe 同目录结构为 games/<slug>/..., BASE 结构相同
    p1 = os.path.join(exe_dir, *parts)
    if os.path.exists(p1):
        return p1
    # frozen 时 __file__ 在 _MEIPASS, BASE 指向源码, 上面已处理; 这里回退源码
    return os.path.join(BASE, *parts)


def _payload_dir(slug):
    exe_dir = _exe_dir()
    p1 = os.path.join(exe_dir, 'games', slug, 'payload')
    if os.path.isdir(p1):
        return p1
    return os.path.join(BASE, 'games', slug, 'payload')


def _ini_path(slug):
    return os.path.join(_exe_dir(), '%s_setup.ini' % slug)


def load_game(slug):
    import io
    path = _resource('games', slug, 'game.yaml')
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    if yaml:
        cfg = yaml.safe_load(text) or {}
        cfg.setdefault('patches', {})
        cfg.setdefault('toggles', {})
        cfg.setdefault('packs', [])
        return cfg
    # 无 yaml 库时的最小解析:只读关键标量, patches 不解析 (UE 旧行为回退)
    cfg = {'patches': {}, 'toggles': {}, 'packs': []}
    import re
    for key in ('exe', 'engine', 'bridge', 'module', 'mod_rel', 'plugin_dll',
                'log_rel', 'tag', 'steam_app_id', 'game_dirname', 'give_func'):
        m = re.search(r'^%s:\s*(.+)$' % key, text, re.M)
        if m:
            cfg[key] = m.group(1).strip().strip("'\"")
    return cfg


def _has_exe(root, exe):
    if not root or not exe:
        return False
    if os.path.isfile(os.path.join(root, exe)):
        return True
    if steam_find is not None:
        try:
            return bool(steam_find.exe_path(root, exe))
        except Exception:
            pass
    return False


def _auto_root(cfg, slug, cli_root=''):
    if cli_root and _has_exe(cli_root, cfg.get('exe', '')):
        return cli_root
    ini = _ini_path(slug)
    try:
        cp = configparser.ConfigParser()
        cp.read(ini, encoding='utf-8')
        p = cp.get('game', 'root', fallback='')
        if p and _has_exe(p, cfg.get('exe', '')):
            return p
    except Exception:
        pass
    if steam_find is not None:
        try:
            found = steam_find.find_game(cfg.get('steam_app_id') or '',
                                         cfg.get('exe') or '',
                                         cfg.get('game_dirname') or '')
            if found:
                return found
        except Exception:
            pass
    return cli_root or ''


def _is_unity_installer(cfg):
    return (cfg.get('engine') or 'ue') != 'ue' and (cfg.get('bridge') or 'ue4ss') in ('none', 'bepinex-file')


class App(tk.Tk):
    def __init__(self, slug, root):
        super().__init__()
        self.slug = slug
        self.cfg = load_game(slug)
        self.exe = self.cfg.get('exe') or ''
        self.root_dir = _auto_root(self.cfg, slug, root or '')
        self.title('Trainer - %s (%s)' % (slug, self.cfg.get('engine') or 'ue'))
        self.geometry('860x640' if not _is_unity_installer(self.cfg) else '560x380')
        self.mem = memmod.GameMemory(self.cfg) if self.cfg.get('patches') else None
        items_path = _resource('games', slug, 'items.txt')
        try:
            self.items = dbmod.load_items(items_path) if os.path.exists(items_path) else []
        except Exception as ex:
            messagebox.showerror('错误', 'items.txt 读取失败:\n%s' % ex)
            self.items = []
        self.status = tk.StringVar(value='就绪.库 %d 种.' % len(self.items))
        self.st_dir = tk.StringVar()
        self.st_dep = tk.StringVar()
        self.st_game = tk.StringVar()
        self._build()
        self.refresh_status()

    def _save_root(self):
        try:
            cp = configparser.ConfigParser()
            cp['game'] = {'root': self.root_var.get()}
            with open(_ini_path(self.slug), 'w', encoding='utf-8') as f:
                cp.write(f)
        except Exception:
            pass

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=8, pady=6)
        ttk.Label(top, text='游戏根目录:').pack(side='left')
        self.root_var = tk.StringVar(value=self.root_dir)
        ttk.Entry(top, textvariable=self.root_var, width=50).pack(side='left', padx=4)
        ttk.Button(top, text='浏览', command=self.do_browse).pack(side='left')
        ttk.Button(top, text='一键部署', command=self.do_deploy).pack(side='left', padx=4)
        if (self.cfg.get('steam_app_id') or ''):
            ttk.Button(top, text='启动游戏', command=self.do_launch).pack(side='left')
        st = ttk.Frame(self)
        st.pack(fill='x', padx=8)
        ttk.Label(st, textvariable=self.st_dir).pack(anchor='w')
        ttk.Label(st, textvariable=self.st_dep).pack(anchor='w')
        ttk.Label(st, textvariable=self.st_game).pack(anchor='w')
        if _is_unity_installer(self.cfg):
            ttk.Label(self, text='说明: 安装器只补缺失文件, 不动存档和别人的插件.\n'
                                 '部署时游戏必须完全退出, 进游戏用内挂窗口.',
                      foreground='gray').pack(fill='x', padx=8, pady=6)
            ttk.Label(self, textvariable=self.status).pack(fill='x', padx=8, pady=4)
            return
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=8, pady=4)
        self.tab_item = ttk.Frame(nb)
        self.tab_toggle = ttk.Frame(nb)
        nb.add(self.tab_item, text='物品给予')
        nb.add(self.tab_toggle, text='开关/补丁')
        self._build_item()
        self._build_toggles()
        ttk.Label(self, textvariable=self.status).pack(fill='x', padx=8, pady=4)

    # ---- 通用: 定位/部署/状态 (UE/Unity 共用, 只补缺项) ----
    def do_browse(self):
        d = filedialog.askdirectory(title='选择游戏根目录 (含 %s 那层)' % self.exe)
        if not d:
            return
        self.root_var.set(d)
        self._save_root()
        self.refresh_status()

    def do_launch(self):
        app_id = (self.cfg.get('steam_app_id') or '').strip()
        if not app_id:
            return
        try:
            os.startfile('steam://rungameid/%s' % app_id)
        except Exception as ex:
            messagebox.showerror('错误', '调起 Steam 失败:\n%s' % ex)

    def _running(self):
        if steam_find is not None:
            try:
                return steam_find.game_running(self.exe)
            except Exception:
                pass
        import subprocess
        try:
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % self.exe, '/NH'],
                                 capture_output=True, text=True, timeout=10).stdout
            return self.exe.lower() in out.lower()
        except Exception:
            return False

    def refresh_status(self):
        root = self.root_var.get()
        ok_dir = _has_exe(root, self.exe)
        if ok_dir:
            self.st_dir.set('目录: 已找到 (%s)' % root)
        elif root:
            self.st_dir.set('目录: 无效 (该目录下没有 %s), 点浏览' % self.exe)
        else:
            self.st_dir.set('目录: 未找到 (先确认 Steam 里装好游戏, 再点浏览)')
        if ok_dir:
            if _is_unity_installer(self.cfg):
                if deploymod is None:
                    self.st_dep.set('MOD: 未知 (deploy 桥缺失)')
                else:
                    dll_ok, hijack_ok = deploymod.bepinex_status(root, self.cfg.get('plugin_dll') or '')
                    b = 'BepInEx: 已安装' if hijack_ok else 'BepInEx: 未安装 (点一键部署)'
                    m = 'MOD: 已部署' if dll_ok else 'MOD: 未部署 (点一键部署)'
                    self.st_dep.set('%s; %s' % (b, m))
            else:
                p = bridge.game_paths(root, self.cfg.get('mod_rel', ''))
                mod_ok = os.path.isfile(os.path.join(p['moddir'], 'Scripts', 'main.lua'))
                self.st_dep.set('Mod: %s' % ('已部署' if mod_ok else '未部署 (点一键部署)'))
        else:
            self.st_dep.set('Mod: 未知 (先定位目录)')
        self.st_game.set('游戏: 运行中 (部署前先完全退出)' if self._running() else '游戏: 未运行')

    def do_deploy(self):
        root = self.root_var.get()
        if not _has_exe(root, self.exe):
            messagebox.showerror('错误', '游戏目录无效, 先自动定位或点浏览.')
            return
        if self._running():
            messagebox.showerror('游戏运行中', '检测到游戏正在运行.\n完全退出游戏后再点部署 (文件被锁住拷不进去).')
            self.refresh_status()
            return
        try:
            if _is_unity_installer(self.cfg):
                if deploymod is None:
                    messagebox.showerror('错误', 'deploy 桥缺失.')
                    return
                ok, msg = self._deploy_unity(root)
            else:
                ok, msg = self._deploy_ue(root)
        except Exception as ex:
            messagebox.showerror('错误', '部署失败:\n%s' % ex)
            return
        self._save_root()
        self.refresh_status()
        messagebox.showinfo('完成', msg)

    def _deploy_unity(self, root):
        """BepInEx 安装：缺项补齐 + 自家 DLL 版本不一致则覆盖。"""
        dll = self.cfg.get('plugin_dll') or ''
        payload = _payload_dir(self.slug)
        ok, msg, changed = deploymod.ensure_bepinex_present(root, dll, payload)
        # 版本更新：payload 与已安装大小不一致则覆盖（ensure 只补缺项）
        src = os.path.join(payload, 'BepInEx', 'plugins', dll)
        if dll and not os.path.isfile(src):
            src = os.path.join(payload, dll)
        dst = os.path.join(root, 'BepInEx', 'plugins', dll)
        if dll and os.path.isfile(src) and os.path.isfile(dst):
            try:
                if os.path.getsize(src) != os.path.getsize(dst):
                    shutil.copyfile(src, dst)
                    ok, changed = True, True
                    msg += '；MOD 已更新到新版本'
            except OSError:
                pass
        if changed:
            msg += '\n经 Steam 启动游戏（补完需重启一次游戏）。'
        return ok, msg

    def _deploy_ue(self, root):
        """UE 部署: 只补缺项 (Scripts/*.lua + cmd.txt + mods.txt), 已有不碰."""
        p = bridge.game_paths(root, self.cfg.get('mod_rel', ''))
        src_scripts = os.path.join(_exe_dir(), 'games', self.slug, 'Scripts')
        if not os.path.isdir(src_scripts):
            src_scripts = os.path.join(BASE, 'games', self.slug, 'Scripts')
        scripts_dst = os.path.join(p['moddir'], 'Scripts')
        os.makedirs(scripts_dst, exist_ok=True)
        n_add = 0
        if os.path.isdir(src_scripts):
            for fn in os.listdir(src_scripts):
                if not fn.endswith('.lua'):
                    continue
                src = os.path.join(src_scripts, fn)
                dst = os.path.join(scripts_dst, fn)
                if os.path.exists(dst):
                    continue
                shutil.copyfile(src, dst)
                n_add += 1
        else:
            # 回退: 通用 Lua 模板当 main.lua (新游戏未填真链时先跑通桥)
            tpl = _resource('lua', 'template_main.lua')
            dst = os.path.join(scripts_dst, 'main.lua')
            if not os.path.exists(dst) and os.path.isfile(tpl):
                shutil.copyfile(tpl, dst)
                n_add += 1
        if not os.path.exists(p['cmd']):
            open(p['cmd'], 'w').close()
        mod_name = os.path.basename((self.cfg.get('mod_rel') or '').rstrip('/\\')) or 'GameTrainer'
        os.makedirs(os.path.dirname(p['modstxt']), exist_ok=True)
        line = '%s : 1\n' % mod_name
        cur = ''
        if os.path.exists(p['modstxt']):
            with open(p['modstxt'], encoding='utf-8', errors='replace') as f:
                cur = f.read()
        if mod_name not in cur:
            with open(p['modstxt'], 'a', encoding='ascii') as f:
                f.write(line)
        return True, 'Mod 已部署 (补 %d 个脚本). 若游戏正在运行, 按一次 Ctrl+R; 否则下次启动生效.' % n_add

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
            if int(spec.get('data_size', 0) or 0):
                # cave 数据区补丁:先开补丁(分配洞),再在这里写倍数/开关值
                row = ttk.Frame(fr)
                row.pack(anchor='w', padx=(24, 0))
                dv = tk.StringVar(value=str(spec.get('data_default', '')))
                ttk.Entry(row, textvariable=dv, width=10).pack(side='left')
                ttk.Button(row, text='写%s数据' % name,
                           command=lambda n=name, vv=dv,
                           dt=spec.get('data_type', 'qword'): self._wdata(n, vv.get(), dt)
                           ).pack(side='left', padx=4)
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

    def _wdata(self, name, text, fmt):
        if not self.mem:
            return
        try:
            value = float(text) if fmt in ('float', 'double') else int(text, 0)
        except ValueError:
            messagebox.showerror('错误', '数据必须是数字(整数支持0x十六进制).')
            return
        ok, msg = self.mem.write_cave_data(name, value, fmt)
        if not ok:
            messagebox.showerror('写入失败', msg + '\n(先勾选打开该补丁再写)')
            return
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
