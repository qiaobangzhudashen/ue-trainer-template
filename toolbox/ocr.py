# -*- coding: utf-8 -*-
"""图片 OCR(PaddleOCR 2.x/3.x 自动适配)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os

# ===========================================================================

_ocr_cache = {}


def _ocr_engine(lang):
    """按 lang 缓存 PaddleOCR 实例,自动检测 2.x/3.x API。返回 (engine, api_ver) 或 (None, 错误信息)。"""
    if lang in _ocr_cache:
        return _ocr_cache[lang]
    try:
        import paddleocr
        from paddleocr import PaddleOCR
    except ImportError as e:
        return None, f"未安装 paddleocr: {e}(pip install paddleocr,首次调用需联网下载模型)"
    ver = str(getattr(paddleocr, "__version__", ""))
    if ver.startswith("3"):
        # 3.x: predict() + engine_config,use_textline_orientation 替代废弃的 use_angle_cls
        # run_mode=paddle 禁用 mkldnn/onednn,规避 oneDNN bug
        # 显式关闭文档方向分类/矫正: 保证 rec_polys 是原始图像坐标, 归一化才与截图一致
        engine = PaddleOCR(
            use_textline_orientation=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            lang=lang,
            engine_config={"paddle_static": {"run_mode": "paddle"}},
        )
        api = "3"
    else:
        engine = PaddleOCR(use_angle_cls=False, lang=lang, show_log=False)
        api = "2"
    _ocr_cache[lang] = (engine, api)
    return engine, api


def _parse_ocr_rows(result, api, W, H):
    """把 OCR 结果(2.x/3.x 两种格式)统一转成 [(ny, nx, nw, text, conf), ...]。"""
    rows = []
    if api == "3":
        for r in result:
            res = (getattr(r, 'json', None) or {}).get('res', {})
            texts = res.get('rec_texts', [])
            scores = res.get('rec_scores', [])
            polys = res.get('rec_polys', [])
            for i, text in enumerate(texts):
                conf = scores[i] if i < len(scores) else 0.0
                conf = conf if conf is not None else 0.0  # 部分版本对无置信度行返回 None
                box = polys[i] if i < len(polys) else None
                if box is None or len(box) == 0:  # 兼容 numpy 数组(真值判断会歧义)
                    continue
                x1 = min(p[0] for p in box)
                y1 = min(p[1] for p in box)
                x2 = max(p[0] for p in box)
                y2 = max(p[1] for p in box)
                rows.append((y1 / H, x1 / W, (x2 - x1) / W, text, conf))
    else:
        for block in result:
            if not block:
                continue
            for line in block:
                box = line[0]
                item = line[1]
                if item is None:
                    continue
                text, conf = item
                conf = conf if conf is not None else 0.0  # 部分 2.x 版本 conf 可能为 None
                x1 = min(p[0] for p in box)
                y1 = min(p[1] for p in box)
                x2 = max(p[0] for p in box)
                y2 = max(p[1] for p in box)
                rows.append((y1 / H, x1 / W, (x2 - x1) / W, text, conf))
    return rows


def tool_ocr(args):
    """图片 OCR 识别(基于 PaddleOCR),返回每行文本 + 置信度 + 归一化坐标。

    坐标格式 [y, x](0-1 归一化,相对截图左上角),让 agent "看见" 文字位置和布局。
    注意:截图常含多余区域(终端标题栏/任务栏/桌面),坐标相对整张截图,
    结合源码和常识过滤非目标区域。

    用法:
      run("ocr", path="screenshot.png")          识别图片中的文字(默认中英文)
      run("ocr", path="shot.png", lang="en")      仅英文

    参数:
      path   图片文件路径(必填)
      lang   语言(ch=中英, en=英文, 默认 ch)

    注意: OpenCV 限制图片宽高 < 32767px(short 上限)。超长图请先手动分段。
    """
    path = args.get("path", "")
    lang = str(args.get("lang", "ch"))
    if not path:
        return "Error: 缺少 path。用法:\n" + tool_ocr.__doc__
    if not os.path.exists(path):
        return f"Error: 文件 {path} 不存在\n\n正确用法:\n  run('ocr', path='图片路径')  # 确保文件存在"

    try:
        engine, api = _ocr_engine(lang)
        if engine is None:
            return f"Error: {api}"
    except Exception as e:
        return f"Error: PaddleOCR 初始化失败 - {e}\n\n提示: 确保已安装 paddleocr (pip install paddleocr)"

    try:
        result = engine.predict(path) if api == "3" else engine.ocr(path, cls=False)
    except Exception as e:
        return f"Error: PaddleOCR 调用失败 - {e}\n\n提示: 确保已安装 paddleocr (pip install paddleocr),首次调用需联网下载模型"
    if not result:
        return "未识别到文字"

    from PIL import Image
    try:
        img = Image.open(path)
        W, H = img.size
    except Exception:
        W, H = 1, 1

    try:
        rows = _parse_ocr_rows(result, api, W, H)
    except Exception as e:
        return f"Error: OCR 结果解析失败 - {e}\n\n提示: 可能是 PaddleOCR 版本不兼容,尝试 pip install --upgrade paddleocr"

    try:
        rows.sort(key=lambda r: (r[0], r[1]))

        out_lines = []
        for ny, nx, nw, text, conf in rows:
            indent = " " * max(0, int(nx * 50))
            short = text[:60] + "..." if len(text) > 60 else text
            out_lines.append(f"[y={ny:.2f} x={nx:.2f} w={nw:.2f}] {indent}{short}  ({conf:.0%})")

        return "\n".join(out_lines) if out_lines else "未识别到文字"
    except Exception as e:
        return f"Error: OCR 结果格式化失败 - {e}"
