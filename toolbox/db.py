# -*- coding: utf-8 -*-
"""JSON 数据库(JSON 表→SQLite+FTS5)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os
import re

# ===========================================================================

import json as _json
import zlib as _zlib
import base64 as _base64


def _db_sqlite():
    """延迟导入 sqlite3(保持 import 本模块无副作用)。"""
    import sqlite3
    return sqlite3


def db__encode(data: bytes) -> bytes:
    """明文 bytes → base64 → zlib 压缩 → 存库。"""
    return _zlib.compress(_base64.b64encode(data))


def db__decode(stored: bytes) -> bytes:
    """存库字节 → zlib 解压 → base64 解码 → 明文 bytes。"""
    return _base64.b64decode(_zlib.decompress(stored))


def db__incr_vacuum(c, n=1):
    """增删改计数,累计满阈值自动 VACUUM。"""
    try:
        c.execute("CREATE TABLE IF NOT EXISTS _meta (k TEXT PRIMARY KEY, v INTEGER)")
        c.execute("INSERT OR IGNORE INTO _meta (k, v) VALUES ('vacuum_counter', 0)")
        c.execute("UPDATE _meta SET v = v + ? WHERE k = 'vacuum_counter'", (n,))
        val = c.execute("SELECT v FROM _meta WHERE k='vacuum_counter'").fetchone()[0]
        if val >= 500:
            try:
                c.execute("VACUUM")
            except Exception:
                pass
            c.execute("UPDATE _meta SET v = 0 WHERE k = 'vacuum_counter'")
    except Exception:
        pass


def db__scan_json_files(root):
    """遍历 root 下的 JSON 文件。

    支持三种目录结构:
      1. root/                    → 直接扫描目录下的 *.json
      2. root/bundle/             → 每个子目录是一个 bundle,扫描其中的 *.json
      3. root/bundle/luac/        → 每个子目录的 luac 子目录里的 *.json

    返回 [(bundle, filename, fullpath)]。
    """
    out = []
    if not os.path.isdir(root):
        return out

    # 先检查: root 下是否直接有 .json 文件（模式 1）
    direct_jsons = [f for f in sorted(os.listdir(root))
                    if f.endswith('.json') and os.path.isfile(os.path.join(root, f))]
    if direct_jsons:
        for fn in direct_jsons:
            out.append((os.path.basename(root), fn, os.path.join(root, fn)))
        return out

    # 模式 2/3: 遍历子目录
    for bundle in sorted(os.listdir(root)):
        bdir = os.path.join(root, bundle)
        if not os.path.isdir(bdir):
            continue
        luac = os.path.join(bdir, "luac")
        if not os.path.isdir(luac):
            luac = bdir
        for fn in sorted(os.listdir(luac)):
            if fn.endswith(".json"):
                out.append((bundle, fn, os.path.join(luac, fn)))
    return out


def db__extract_records(d):
    """从表 JSON 提取记录数组。"""
    recs = d.get("records") or []
    if not recs and d.get("globals"):
        for v in d["globals"].values():
            if isinstance(v, list) and v and isinstance(v[0], (dict, list)):
                recs = v
                break
    return recs


def db__fts_text(obj):
    """把记录扁平化为 FTS 全文文本。"""
    if isinstance(obj, dict):
        parts = [f"{k}={_json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}"
                 for k, v in obj.items()]
        return " ".join(parts)
    return _json.dumps(obj, ensure_ascii=False)


def db__conn(db_path):
    sqlite3 = _db_sqlite()
    if not os.path.exists(db_path):
        return None, (f"Error: 数据库不存在: {db_path}(先跑 build)\n\n正确用法:\n  run('db', action='build', dir='数据目录', db='{db_path}')")
    return sqlite3.connect(db_path), None


def db__find_table(c, table_name):
    return c.execute("SELECT id FROM tables WHERE name=?", (table_name,)).fetchone()


def db_cmd_build(db_path, root_dir):
    sqlite3 = _db_sqlite()
    if not root_dir:
        return "Error: build 需要 dir。正确用法:\n  run('db', action='build', dir='数据目录', db='库路径')"
    if not os.path.isdir(root_dir):
        return f"Error: 数据目录不存在或不可读: {root_dir}"
    try:
        files = db__scan_json_files(root_dir)
    except Exception as e:
        return f"Error: 扫描数据目录失败: {e}"
    if not files:
        return f"Error: 数据目录下未找到任何 *.json: {root_dir}"
    # ── 初始化: 删旧库/建库/建表/FTS5。任何一步失败都返回清晰诊断(不裸抛到上层兜底) ──
    c = None
    try:
        if os.path.exists(db_path):
            os.remove(db_path)  # 重建语义: 先删旧库(占用中/无权限会抛, 走下方诊断)
        c = sqlite3.connect(db_path)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE tables (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            directory TEXT NOT NULL,
            rootName TEXT,
            recordCount INTEGER,
            path TEXT
        )""")
        c.execute("""CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            table_id INTEGER NOT NULL,
            row_idx INTEGER NOT NULL,
            data BLOB NOT NULL
        )""")
        c.execute("CREATE INDEX idx_records_table ON records(table_id)")
        c.execute("CREATE INDEX idx_records_tablerow ON records(table_id, row_idx)")
        try:
            c.execute("""CREATE VIRTUAL TABLE records_fts USING fts5(
                table_name UNINDEXED, row_idx UNINDEXED, content, tokenize='trigram'
            )""")
            _tok = "trigram"  # trigram: 中文子串直接走索引,10万级表也不用全表扫描
        except sqlite3.OperationalError:
            c.execute("""CREATE VIRTUAL TABLE records_fts USING fts5(
                table_name UNINDEXED, row_idx UNINDEXED, content, tokenize='unicode61'
            )""")
            _tok = "unicode61"  # 老 SQLite 无 trigram,中文回退全表扫描
        c.execute("CREATE TABLE IF NOT EXISTS _meta (k TEXT PRIMARY KEY, v INTEGER)")
        c.execute("INSERT OR IGNORE INTO _meta (k, v) VALUES ('vacuum_counter', 0)")
        c.execute("CREATE TABLE IF NOT EXISTS _cfg (k TEXT PRIMARY KEY, v TEXT)")
        c.execute("INSERT OR REPLACE INTO _cfg (k, v) VALUES ('fts_tokenizer', ?)", (_tok,))
    except sqlite3.OperationalError as e:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        if re.search(r'no such module|fts5', str(e), re.I):
            return f"Error: FTS5 不可用: {e}\n\n提示: 需要 SQLite 编译时包含 FTS5 扩展。Python 3.7+ 自带的 sqlite3 通常已包含"
        return (f"Error: 数据库初始化失败: {e}\n\n"
                f"提示: 检查 db 路径是否可写({db_path})、旧库是否被占用、磁盘空间是否充足")
    except Exception as e:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        return f"Error: 数据库初始化失败: {e}\n\n提示: 检查 db 路径是否可写({db_path})、旧库是否被占用、磁盘空间是否充足"

    total = len(files)
    lines = [f"扫描到 {total} 个 JSON 文件"]

    ok = skip = fail = 0
    dup_names = []  # 不同 bundle 下同名文件(表名唯一约束冲突)
    batch_r = []
    batch_f = []

    processed = 0
    try:
        for i, (bundle, fn, full) in enumerate(files):
            processed = i + 1
            name = fn[:-5]
            try:
                with open(full, "r", encoding="utf-8") as f:
                    d = _json.load(f)
            except Exception:
                fail += 1
                continue

            recs = db__extract_records(d)
            rootname = d.get("rootName") or ""
            try:
                c.execute(
                    "INSERT INTO tables (name, directory, rootName, recordCount, path) VALUES (?,?,?,?,?)",
                    (name, bundle, rootname, len(recs) if isinstance(recs, list) else 0, full))
            except sqlite3.IntegrityError:
                # 不同 bundle 同名文件: 表名唯一约束冲突 → 跳过该文件继续构建, 不整库回滚
                fail += 1
                dup_names.append((name, bundle))
                continue
            table_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

            if isinstance(recs, list):
                for idx, rec in enumerate(recs):
                    data = _json.dumps(rec, ensure_ascii=False)
                    batch_r.append((table_id, idx, db__encode(data.encode("utf-8"))))
                    batch_f.append((name, idx, db__fts_text(rec)))
                    if len(batch_r) >= 2000:
                        c.executemany("INSERT INTO records (table_id, row_idx, data) VALUES (?,?,?)", batch_r)
                        c.executemany("INSERT INTO records_fts (table_name, row_idx, content) VALUES (?,?,?)", batch_f)
                        batch_r = []
                        batch_f = []
                ok += 1
            else:
                skip += 1

            if (i + 1) % 500 == 0:
                lines.append(f"进度 {i+1}/{total} 已入 {ok} 跳过 {skip} 失败 {fail}")

        if batch_r:
            c.executemany("INSERT INTO records (table_id, row_idx, data) VALUES (?,?,?)", batch_r)
            c.executemany("INSERT INTO records_fts (table_name, row_idx, content) VALUES (?,?,?)", batch_f)
        c.commit()

        n_tables = c.execute("SELECT COUNT(*) FROM tables").fetchone()[0]
        n_records = c.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    except Exception as e:
        try:
            c.rollback()
        except Exception:
            pass
        return (f"Error: 构建中断: {e}\n\n已处理 {processed}/{total} 个文件"
                f"(正常入 {ok} 跳过 {skip} 失败 {fail})。提示: 检查源 JSON 目录可读性、db 所在磁盘空间")
    finally:
        c.close()
    size = os.path.getsize(db_path)
    lines.append(f"=== 构建完成 ===")
    lines.append(f"表: {n_tables}  记录: {n_records}  库大小: {size/1024/1024:.1f} MB")
    lines.append(f"(正常入 {ok}, 无记录跳过 {skip}, 失败 {fail})")
    if dup_names:
        shown = ", ".join(f"{n}@{b}" for n, b in dup_names[:8])
        lines.append(f"  [跳过同名表 {len(dup_names)} 个]: {shown}"
                     + (f" ... +{len(dup_names)-8}" if len(dup_names) > 8 else ""))
    return "\n".join(lines)


def db_cmd_tables(db_path, directory, filt, limit):
    c, err = db__conn(db_path)
    if err:
        return err
    q = "SELECT id, name, directory, rootName, recordCount FROM tables"
    conds, a = [], []
    if directory:
        conds.append("directory=?")
        a.append(directory)
    if filt:
        conds.append("name LIKE ?")
        a.append(f"%{filt}%")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY directory, name"
    if limit is not None:
        q += " LIMIT ?"
        a.append(limit)
    rows = c.execute(q, a).fetchall()
    c.close()
    if not rows:
        return f"未找到表({filt or '全部'})"
    lines = [f"=== 表清单(共 {len(rows)} 行) ==="]
    for tid, name, d, root, rc in rows:
        lines.append(f"  {name:50} [{d}] rc={rc} root={root or ''}")
    return "\n".join(lines)


def db__like_scan(c, keyword, table, limit):
    """中文关键词的兜底搜索: FTS 的 unicode61 分词把连续汉字整体当一个 token,
    子串搜索基本失效, 所以对含 CJK 的关键词走全表逐行扫描(内容解码后判断包含关系)。
    keyword 按空白拆词, 所有词都必须出现; 返回 [(table_name, row_idx, data), ...]。"""
    parts = [k for k in keyword.split() if k]
    q = "SELECT t.name, r.row_idx, r.data FROM records r JOIN tables t ON t.id = r.table_id"
    a = []
    if table:
        q += " WHERE t.name=?"
        a.append(table)
    q += " ORDER BY t.name, r.row_idx"
    rows = []
    for name, ridx, data in c.execute(q, a):
        try:
            text = db__decode(data).decode("utf-8", "replace")
        except Exception:
            continue
        if all(p in text for p in parts):
            rows.append((name, ridx, data))
            if len(rows) >= (limit or 20):
                break
    return rows


def db__tokenizer(c):
    """读库的 FTS 分词器(trigram/unicode61)。旧库无 _cfg 表时回 unicode61 语义。"""
    try:
        r = c.execute("SELECT v FROM _cfg WHERE k='fts_tokenizer'").fetchone()
        return r[0] if r else "unicode61"
    except Exception:
        return "unicode61"


def db_cmd_search(db_path, keyword, table, limit):
    c, err = db__conn(db_path)
    if err:
        return err
    if not keyword:
        c.close()
        return "Error: 缺少搜索关键词。正确用法:\n  run('db', action='search', keyword='要搜的词', db='库路径')"
    limit = limit if limit is not None else 20
    try:
        tok = db__tokenizer(c)
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', keyword))
        rows, source, fts_err = [], "", ""
        # trigram 只能服务 ≥3 字符的查询(2字词如"铁剑"无 trigram 可切,直接全表扫描)
        fts_ok = (tok == "trigram" and len(keyword.strip()) >= 3) or not has_cjk
        if fts_ok:
            q = ("SELECT fts.table_name, fts.row_idx, r.data "
                 "FROM records_fts fts "
                 "JOIN tables t ON t.name = fts.table_name "
                 "JOIN records r ON r.table_id = t.id AND r.row_idx = fts.row_idx "
                 "WHERE records_fts MATCH ?")
            a = [keyword]
            if table:
                q += " AND fts.table_name=?"
                a.append(table)
            q += " ORDER BY rank LIMIT ?"
            a.append(limit)
            try:
                rows = c.execute(q, a).fetchall()
                source = "FTS 全文索引" + ("(trigram中文子串)" if tok == "trigram" else "")
            except _db_sqlite().OperationalError as e:
                fts_err = str(e)
        if not rows and has_cjk:
            # 含中文且索引无命中(unicode61 旧库)→ 全表扫描兜底
            rows = db__like_scan(c, keyword, table, limit)
            source = "全表扫描"
        if not rows and not has_cjk and fts_err:
            c.close()
            return f"Error: 搜索失败: {fts_err}\n\n提示: FTS5 特殊字符需用引号包裹,如 keyword='\"搜索词\"'"
    except _db_sqlite().OperationalError as e:
        c.close()
        return f"Error: 搜索失败: {e}\n\n提示: FTS5 特殊字符需用引号包裹,如 keyword='\"搜索词\"'"
    c.close()
    if not rows:
        return f"未找到匹配: {keyword}"
    lines = [f"=== 搜索 \"{keyword}\"({source}, 命中 {len(rows)} 条) ==="]
    for tn, ridx, data in rows:
        try:
            raw = db__decode(data).decode("utf-8")
            obj = _json.loads(raw)
            if isinstance(obj, dict):
                items = [f"{k}={str(v)[:40]}" for k, v in list(obj.items())[:6]]
                snippet = " | ".join(items)
            else:
                snippet = str(obj)[:200]
        except Exception:
            snippet = str(data)[:200]
        lines.append(f"  [{tn} row#{ridx}] {snippet}")
    return "\n".join(lines)


def db_cmd_row(db_path, table_name, row_idx):
    c, err = db__conn(db_path)
    if err:
        return err
    t = db__find_table(c, table_name)
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    r = c.execute("SELECT data FROM records WHERE table_id=? AND row_idx=?",
                  (t[0], row_idx)).fetchone()
    c.close()
    if not r:
        return f"Error: 表 {table_name} 没有第 {row_idx} 行\n\n提示: 行号从 0 开始,用 run('db', action='rows', table_name='{table_name}', db='库路径') 查看所有行"
    try:
        raw = db__decode(r[0]).decode("utf-8")
        obj = _json.loads(raw)
        return _json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(r[0])


def db_cmd_rows(db_path, table_name, start, limit):
    c, err = db__conn(db_path)
    if err:
        return err
    t = c.execute("SELECT id, recordCount FROM tables WHERE name=?", (table_name,)).fetchone()
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    rows = c.execute("SELECT row_idx, data FROM records WHERE table_id=? AND row_idx>=? ORDER BY row_idx LIMIT ?",
                     (t[0], start, limit if limit is not None else 10)).fetchall()
    c.close()
    if not rows:
        return f"表 {table_name} 无记录或超出范围"
    lines = [f"=== {table_name} 记录(共 {t[1]} 条,显示 {len(rows)} 条) ==="]
    for ridx, data in rows:
        try:
            raw = db__decode(data).decode("utf-8")
            obj = _json.loads(raw)
            if isinstance(obj, dict):
                items = [f"{k}={str(v)[:50]}" for k, v in list(obj.items())[:8]]
                lines.append(f"  [{ridx}] {' | '.join(items)}")
            else:
                lines.append(f"  [{ridx}] {str(obj)[:200]}")
        except Exception:
            lines.append(f"  [{ridx}] {data[:200]}")
    return "\n".join(lines)


def db_cmd_info(db_path, table_name):
    c, err = db__conn(db_path)
    if err:
        return err
    t = c.execute("SELECT name, directory, rootName, recordCount, path FROM tables WHERE name=?",
                  (table_name,)).fetchone()
    c.close()
    if not t:
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    lines = [f"=== {t[0]} ===", f"目录: {t[1]}", f"rootName: {t[2]}",
             f"记录数: {t[3]}", f"源文件: {t[4]}"]
    return "\n".join(lines)


def db_cmd_count(db_path):
    c, err = db__conn(db_path)
    if err:
        return err
    n_t = c.execute("SELECT COUNT(*) FROM tables").fetchone()[0]
    n_r = c.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    size = os.path.getsize(db_path)
    c.close()
    return f"表: {n_t}  记录: {n_r}  库大小: {size/1024/1024:.1f} MB"


def db_cmd_add_record(db_path, table_name, json_text):
    c, err = db__conn(db_path)
    if err:
        return err
    try:
        obj = _json.loads(json_text)
    except Exception as e:
        c.close()
        return f"Error: JSON 解析失败: {e}\n\n提示: JSON 必须是合法格式,如: {{\"name\":\"test\",\"value\":123}}"
    t = db__find_table(c, table_name)
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    table_id = t[0]
    mx = c.execute("SELECT COALESCE(MAX(row_idx), -1) FROM records WHERE table_id=?", (table_id,)).fetchone()[0]
    new_idx = mx + 1
    data = _json.dumps(obj, ensure_ascii=False)
    c.execute("INSERT INTO records (table_id, row_idx, data) VALUES (?,?,?)",
              (table_id, new_idx, db__encode(data.encode("utf-8"))))
    c.execute("INSERT INTO records_fts (table_name, row_idx, content) VALUES (?,?,?)",
              (table_name, new_idx, db__fts_text(obj)))
    c.execute("UPDATE tables SET recordCount = recordCount + 1 WHERE id=?", (table_id,))
    c.commit()
    db__incr_vacuum(c)
    c.commit()
    c.close()
    return f"{table_name} 已追加记录(row#{new_idx})\n{_json.dumps(obj, ensure_ascii=False, indent=2)}"


def db_cmd_add_table(db_path, name, directory, root_name, json_text):
    c, err = db__conn(db_path)
    if err:
        return err
    if db__find_table(c, name):
        c.close()
        return f"Error: 表已存在: {name}\n\n提示: 用 run('db', action='delete', sub='table', table_name='{name}', db='库路径') 先删除旧表"
    obj = None
    if json_text:
        try:
            obj = _json.loads(json_text)
        except Exception as e:
            c.close()
            return f"Error: JSON 解析失败: {e}\n\n提示: JSON 必须是合法格式,如: {{\"name\":\"test\",\"value\":123}}"
    c.execute("INSERT INTO tables (name, directory, rootName, recordCount, path) VALUES (?,?,?,?,?)",
              (name, directory or "", root_name or "", 1 if obj is not None else 0, ""))
    table_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    if obj is not None:
        data = _json.dumps(obj, ensure_ascii=False)
        c.execute("INSERT INTO records (table_id, row_idx, data) VALUES (?,?,?)",
                  (table_id, 0, db__encode(data.encode("utf-8"))))
        c.execute("INSERT INTO records_fts (table_name, row_idx, content) VALUES (?,?,?)",
                  (name, 0, db__fts_text(obj)))
    c.commit()
    db__incr_vacuum(c)
    c.commit()
    c.close()
    return f"已新建表 {name}(目录 {directory or '-'})"


def db_cmd_delete_record(db_path, table_name, row_idx):
    c, err = db__conn(db_path)
    if err:
        return err
    t = db__find_table(c, table_name)
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    table_id = t[0]
    r = c.execute("SELECT data FROM records WHERE table_id=? AND row_idx=?", (table_id, row_idx)).fetchone()
    if not r:
        c.close()
        return f"Error: 表 {table_name} 没有第 {row_idx} 行\n\n提示: 行号从 0 开始,用 run('db', action='rows', table_name='{table_name}', db='库路径') 查看所有行"
    try:
        deleted = db__decode(r[0]).decode("utf-8")
    except Exception:
        deleted = "(无法解码)"
    c.execute("DELETE FROM records WHERE table_id=? AND row_idx=?", (table_id, row_idx))
    c.execute("DELETE FROM records_fts WHERE table_name=? AND row_idx=?", (table_name, row_idx))
    # compact: 把被删行后面的行号全部减1,消除空洞
    c.execute("UPDATE records SET row_idx = row_idx - 1 WHERE table_id=? AND row_idx > ?", (table_id, row_idx))
    c.execute("UPDATE records_fts SET row_idx = row_idx - 1 WHERE table_name=? AND row_idx > ?", (table_name, row_idx))
    c.execute("UPDATE tables SET recordCount = MAX(0, recordCount - 1) WHERE id=?", (table_id,))
    c.commit()
    db__incr_vacuum(c)
    c.commit()
    c.close()
    return f"{table_name} 第 {row_idx} 行已删除\n内容: {deleted[:200]}"


def db_cmd_delete_table(db_path, table_name):
    c, err = db__conn(db_path)
    if err:
        return err
    t = db__find_table(c, table_name)
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    n = c.execute("SELECT COUNT(*) FROM records WHERE table_id=?", (t[0],)).fetchone()[0]
    c.execute("DELETE FROM records WHERE table_id=?", (t[0],))
    c.execute("DELETE FROM records_fts WHERE table_name=?", (table_name,))
    c.execute("DELETE FROM tables WHERE id=?", (t[0],))
    c.commit()
    db__incr_vacuum(c, n + 1)
    c.commit()
    c.close()
    return f"已删除表 {table_name}({n} 条记录)"


def db_cmd_update(db_path, table_name, row_idx, json_text):
    c, err = db__conn(db_path)
    if err:
        return err
    try:
        obj = _json.loads(json_text)
    except Exception as e:
        c.close()
        return f"Error: JSON 解析失败: {e}\n\n提示: JSON 必须是合法格式,如: {{\"name\":\"test\",\"value\":123}}"
    t = db__find_table(c, table_name)
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    table_id = t[0]
    r = c.execute("SELECT data FROM records WHERE table_id=? AND row_idx=?", (table_id, row_idx)).fetchone()
    if not r:
        c.close()
        return f"Error: 表 {table_name} 没有第 {row_idx} 行\n\n提示: 行号从 0 开始,用 run('db', action='rows', table_name='{table_name}', db='库路径') 查看所有行"
    try:
        old = db__decode(r[0]).decode("utf-8")
    except Exception:
        old = "(无法解码)"
    data = _json.dumps(obj, ensure_ascii=False)
    c.execute("UPDATE records SET data=? WHERE table_id=? AND row_idx=?",
              (db__encode(data.encode("utf-8")), table_id, row_idx))
    c.execute("UPDATE records_fts SET content=? WHERE table_name=? AND row_idx=?",
              (db__fts_text(obj), table_name, row_idx))
    c.commit()
    db__incr_vacuum(c)
    c.commit()
    c.close()
    return f"{table_name} 第 {row_idx} 行已更新\n旧: {old[:200]}\n新: {_json.dumps(obj, ensure_ascii=False)[:200]}"


def db_cmd_vacuum(db_path):
    c, err = db__conn(db_path)
    if err:
        return err
    c.execute("VACUUM")
    c.execute("INSERT OR IGNORE INTO _meta (k, v) VALUES ('vacuum_counter', 0)")
    c.execute("UPDATE _meta SET v = 0 WHERE k = 'vacuum_counter'")
    c.commit()
    c.close()
    return "数据库已手动整理(VACUUM)"


def db_cmd_extract(db_path, table_name, out_dir):
    c, err = db__conn(db_path)
    if err:
        return err
    t = c.execute("SELECT id, name, directory, rootName, recordCount FROM tables WHERE name=?",
                  (table_name,)).fetchone()
    if not t:
        c.close()
        return f"Error: 未找到表: {table_name}\n\n提示: 用 run('db', action='tables', db='库路径') 查看有哪些表"
    rows = c.execute("SELECT data FROM records WHERE table_id=? ORDER BY row_idx", (t[0],)).fetchall()
    c.close()
    if not rows:
        return f"表 {table_name} 无记录"
    recs = [_json.loads(db__decode(r[0]).decode("utf-8")) for r in rows]
    out = {
        "source": "toolbox-db-extract",
        "directory": t[2],
        "fileName": t[1],
        "rootName": t[3],
        "recordCount": len(recs),
        "records": recs,
    }
    out_dir = out_dir or os.path.join(os.path.dirname(db_path), "extract")
    os.makedirs(out_dir, exist_ok=True)
    safe_name = re.sub(r'[^A-Za-z0-9_.\-\u4e00-\u9fff]', '_', t[1]) or "table"  # 表名净化, 防路径穿越
    out_path = os.path.join(out_dir, safe_name + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(out, f, ensure_ascii=False, indent=1)
    return f"已导出 {len(recs)} 条 → {out_path}"


def tool_db(args):
    """JSON 数据库工具。把大量 JSON 表构建成 SQLite + FTS5,支持增删改查和全文搜索。

    run("db", action=..., db=..., ...)

    build 输入格式:
      dir 指向的目录下放 .json 文件,每个文件 = 一张表。
      文件名(去掉.json) = 表名。
      JSON 格式: {"records": [{...}, {...}], "rootName": "可选"}
      records 数组中每个元素 = 一行记录。
      也支持 {"globals": {"key": [...]}} 格式(自动提取第一个 list)。

      目录结构支持:
        dir=xxx/          → 直接放 *.json
        dir=xxx/bundle/   → 每个子目录是一个 bundle,含 luac/ 子目录

    action 子命令:
      build    dir=<数据目录> [db=<库路径>]         构建/重建(默认库: ./lua-tables.db)
      tables   [db=<库>] [filter=<关键词>] [limit=N]
      search   keyword=<关键词> [db=<库>] [table=<表名>] [limit=N]
      row      table_name=<表名> row_idx=<行号> [db=<库>]
      rows     table_name=<表名> [db=<库>] [start=0] [limit=10]
      info     table_name=<表名> [db=<库>]
      count    [db=<库>]
      extract  table_name=<表名> [db=<库>] [out=<目录>]
      vacuum   [db=<库>]
      add      sub="record" table_name=<表名> json=<JSON> [db=<库>]
      add      sub="table" table_name=<表名> [db=<库>] [directory=<目录>] [root=<名称>] [json=<JSON>]
      delete   sub="record" table_name=<表名> row_idx=<行号> [db=<库>]
      delete   sub="table" table_name=<表名> [db=<库>]
      update   table_name=<表名> row_idx=<行号> json=<JSON> [db=<库>]

    db 默认 ./lua-tables.db。行号从 0 开始。增删改累计500次自动 VACUUM。"""
    action = str(args.get("action", "")).lower()
    if not action:
        return "Error: 缺少 action。完整用法:\n" + tool_db.__doc__

    db_path = args.get("db") or os.path.join(os.getcwd(), "lua-tables.db")

    valid = {"build", "tables", "search", "row", "rows", "info", "count",
             "extract", "vacuum", "add", "delete", "update"}
    if action not in valid:
        return f"Error: 未知 action {action!r},应为 {sorted(valid)}\n\n完整用法:\n" + tool_db.__doc__

    try:
        if action == "build":
            root_dir = args.get("dir", "")
            if not root_dir:
                return "Error: build 需要 dir。正确用法:\n  run('db', action='build', dir='数据目录', db='库路径')"
            return db_cmd_build(db_path, root_dir)

        if action == "tables":
            return db_cmd_tables(db_path, args.get("directory"),
                                 args.get("filter"),
                                 int(args["limit"]) if args.get("limit") else None)

        if action == "search":
            kw = args.get("keyword", "")
            return db_cmd_search(db_path, kw, args.get("table"),
                                 int(args["limit"]) if args.get("limit") else None)

        if action == "row":
            table_name = args.get("table_name", "")
            row_idx = int(args.get("row_idx", 0))
            return db_cmd_row(db_path, table_name, row_idx)

        if action == "rows":
            table_name = args.get("table_name", "")
            start = int(args.get("start", 0))
            limit = int(args["limit"]) if args.get("limit") else None
            return db_cmd_rows(db_path, table_name, start, limit)

        if action == "info":
            table_name = args.get("table_name", "")
            return db_cmd_info(db_path, table_name)

        if action == "count":
            return db_cmd_count(db_path)

        if action == "extract":
            table_name = args.get("table_name", "")
            return db_cmd_extract(db_path, table_name, args.get("out"))

        if action == "vacuum":
            return db_cmd_vacuum(db_path)

        if action == "add":
            sub = args.get("sub", "")
            if sub == "record":
                return db_cmd_add_record(db_path,
                                         args.get("table_name", ""), args.get("json", ""))
            elif sub == "table":
                return db_cmd_add_table(db_path,
                                        args.get("table_name", ""),
                                        args.get("directory"), args.get("root"), args.get("json"))
            return "Error: add 需要 record 或 table 子命令。正确用法:\n  run('db', action='add', sub='record', table_name='表名', json='{\"k\":\"v\"}', db='库路径')\n  run('db', action='add', sub='table', table_name='新表名', db='库路径')"

        if action == "delete":
            sub = args.get("sub", "")
            if sub == "record":
                return db_cmd_delete_record(db_path,
                                            args.get("table_name", ""), int(args.get("row_idx", 0)))
            elif sub == "table":
                return db_cmd_delete_table(db_path, args.get("table_name", ""))
            return "Error: delete 需要 record 或 table 子命令。正确用法:\n  run('db', action='delete', sub='record', table_name='表名', row_idx=0, db='库路径')\n  run('db', action='delete', sub='table', table_name='表名', db='库路径')"

        if action == "update":
            table_name = args.get("table_name", "")
            row_idx = int(args.get("row_idx", 0))
            return db_cmd_update(db_path, table_name, row_idx, args.get("json", ""))

    except Exception as e:
        return f"Error: {e}\n\n这是 db 工具的异常。正确用法:\n" + tool_db.__doc__
