# toolbox（侦察 + CE 驱动工具包）

给 agent 用的跨项目通用工具：截图/OCR 看画面，PE/DB 查静态，CE 桥驱动搜断反。
成品写入（内存补丁/Lua 发奖）归 `ue-trainer-template/engine/`，本包的 `ce.write/eval` 只在开发期找点验证用。

## 布局

```
toolbox/
  __init__.py    统一入口 run()/CLI(延迟加载各模块)
  pe.py          PE 分析(导出/导入/依赖/反汇编/vtable/扫描/字符串)
  shot.py        窗口/屏幕截图 + shot_ocr
  ocr.py         图片 OCR(PaddleOCR 2.x/3.x)
  gui.py         click/key(验证点击用)
  describe.py    图片色块描述
  db.py          JSON→SQLite+FTS5(查 dump 表)
  ce.py          CE 桥接(搜/断/反/读写,走命名管道,不点 CE 界面)
  info.py        环境能力探测
  common.py      截断 + 参数 coercion
```

## 用法

```python
import toolbox
toolbox.run("pe", action="exports", path="game.dll")
toolbox.run("shot_ocr", window="游戏标题")
toolbox.run("ce", action="ping")
toolbox.run("info")
```

CLI：`python -m toolbox <工具> <参数=值> ...`（要在 `D:\github-ue` 下执行）。

结构化取值（绕开 20000 字截断）：直接调子模块函数，
如 `from toolbox.pe import pe_get_exports_detail`。

## 约定

- 所有 `run()` 返回字符串；失败以 `"Error: ..."` 开头（附用法提示）。
- `import toolbox` 无副作用：第三方依赖全部延迟到调用时加载。
- 历史：由单文件 `toolbox.py`（2629行）拆分而来，原文件备份在临时目录，不进仓库。
