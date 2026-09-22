# -*- coding: utf-8 -*-
"""图片视觉描述(降采样+色块分割)。由 toolbox.py 拆分,逻辑原样,见包 README。"""
import os

# ===========================================================================

def _color_name(r, g, b):
    """RGB → 人类可读颜色名(基于 HSV)。"""
    mx, mn = max(r, g, b), min(r, g, b)
    delta = mx - mn
    v = mx / 255.0
    s = delta / mx if mx > 0 else 0
    if delta == 0:
        h = 0
    elif mx == r:
        h = 60 * (((g - b) / delta) % 6)
    elif mx == g:
        h = 60 * ((b - r) / delta + 2)
    else:
        h = 60 * ((r - g) / delta + 4)

    # 明度分层
    if v < 0.12:
        return "黑"
    if v > 0.92 and s < 0.1:
        return "白"
    if s < 0.12:
        if v < 0.35:
            return "深灰"
        if v < 0.65:
            return "中灰"
        return "浅灰"

    # 色相分区
    if h < 15 or h >= 345:
        base = "红"
    elif h < 40:
        base = "橙"
    elif h < 70:
        base = "黄"
    elif h < 100:
        base = "黄绿"
    elif h < 160:
        base = "绿"
    elif h < 195:
        base = "青"
    elif h < 255:
        base = "蓝"
    elif h < 290:
        base = "紫"
    else:
        base = "粉"

    # 明度修饰
    if v < 0.3:
        return "深" + base
    if v > 0.75 and s < 0.5:
        return "浅" + base
    return base


def _rgb_hex(r, g, b):
    return f"#{r:02X}{g:02X}{b:02X}"


def _shape_desc(cells, grid_w, grid_h):
    """根据区域的格子分布描述形状。
    cells: [(col, row)] 列行坐标列表
    返回形状描述字符串。"""
    if not cells:
        return "无"
    cols = [c for c, r in cells]
    rows = [r for c, r in cells]
    w = max(cols) - min(cols) + 1
    h = max(rows) - min(rows) + 1
    area = len(cells)
    bbox_area = w * h
    fill_ratio = area / bbox_area if bbox_area > 0 else 0

    # 位置(归一化到九宫格)
    cx = (min(cols) + max(cols)) / 2 / grid_w
    cy = (min(rows) + max(rows)) / 2 / grid_h
    h_pos = "左" if cx < 0.33 else ("右" if cx > 0.66 else "中")
    v_pos = "上" if cy < 0.33 else ("下" if cy > 0.66 else "中")
    # v_pos == h_pos 仅当两者都为"中"(居中); 否则上下左右组合
    pos = v_pos + h_pos if v_pos != h_pos else "居中"

    aspect = w / h if h > 0 else 1

    if fill_ratio > 0.85:
        if 0.8 < aspect < 1.2:
            shape = "方块/圆形"
        elif aspect > 1.5:
            shape = f"横向条形({w}x{h})"
        elif aspect < 0.6:
            shape = f"纵向条形({w}x{h})"
        else:
            shape = f"矩形({w}x{h})"
    elif fill_ratio > 0.5:
        shape = f"不规则块({w}x{h}, 填充{fill_ratio:.0%})"
    else:
        shape = f"分散/碎块({w}x{h}, 填充{fill_ratio:.0%})"

    return f"{pos}, {shape}"


def tool_image_describe(args):
    """图片视觉描述 — 降采样 + 色块聚类, 输出结构化文本让 agent "认出" 图像内容。
    不是 OCR(不认文字), 是把图像转为色块区域描述(位置+颜色+形状+占比)。
    agent 结合先验知识(苹果是红色圆形等)从描述中推断图像内容。
    path: 图片路径(必填)
    grid: 采样网格大小, 默认 32(宽), 高度按比例算
    merge: 颜色合并阈值(0-255), 默认 30, 越大合并越多区域越少"""
    path = args.get("path", "")
    if not path:
        return "Error: 缺少 path"
    if not os.path.exists(path):
        return f"Error: 文件 {path} 不存在"

    try:
        grid_w = int(args.get("grid", 32))
        merge_thresh = int(args.get("merge", 30))
    except (ValueError, TypeError):
        return "Error: grid/merge 参数必须是数字"
    grid_w = max(8, min(grid_w, 64))
    merge_thresh = max(0, min(merge_thresh, 255))

    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        orig_w, orig_h = img.size
    except Exception as e:
        return f"Error: 打开图片失败 - {e}"

    # 降采样:网格高度按宽高比算, 限制在 6-32
    grid_h = max(6, min(32, int(grid_w * orig_h / orig_w) if orig_w > 0 else grid_w))
    small = img.resize((grid_w, grid_h), Image.BOX)

    # 取每个格子的平均颜色(保留原始值用于距离计算)
    raw_pixels = list(small.getdata())

    # 颜色量化:用 merge_thresh 做粗量化(减少颜色种类)
    # 但 flood fill 用颜色距离而非精确匹配, 更鲁棒
    def quantize(rgb):
        r, g, b = rgb
        step = max(merge_thresh, 20)  # 量化步长至少 20
        return (r // step * step, g // step * step, b // step * step)

    # 建网格:每个格子的量化颜色
    grid = []
    for row in range(grid_h):
        line = []
        for col in range(grid_w):
            idx = row * grid_w + col
            line.append(quantize(raw_pixels[idx]))
        grid.append(line)

    # 区域生长(flood fill):相邻格子颜色距离在阈值内就合并
    # 用量化后的颜色做距离判断, 比精确匹配更鲁棒
    color_dist_thresh = max(merge_thresh, 25)  # 颜色距离阈值
    visited = [[False] * grid_w for _ in range(grid_h)]
    regions = []  # [(color_key, [(col, row), ...])]

    for sr in range(grid_h):
        for sc in range(grid_w):
            if visited[sr][sc]:
                continue
            target = grid[sr][sc]
            stack = [(sc, sr)]
            cells = []
            while stack:
                cx, cy = stack.pop()
                if cx < 0 or cx >= grid_w or cy < 0 or cy >= grid_h:
                    continue
                if visited[cy][cx]:
                    continue
                cur = grid[cy][cx]
                # 颜色距离(曼哈顿)
                dist = abs(cur[0]-target[0]) + abs(cur[1]-target[1]) + abs(cur[2]-target[2])
                if dist > color_dist_thresh * 3:  # 曼哈顿距离阈值
                    continue
                visited[cy][cx] = True
                cells.append((cx, cy))
                stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])
            if cells:
                regions.append((target, cells))

    # 按面积排序, 小区域(噪声)过滤
    total = grid_w * grid_h
    min_area = max(2, total // 40)  # 至少占 2.5% 才报告
    regions = [(ck, cells) for ck, cells in regions if len(cells) >= min_area]
    regions.sort(key=lambda x: len(x[1]), reverse=True)

    # 限制最多 15 个区域
    regions = regions[:15]

    if not regions:
        return f"图片 {path} ({orig_w}x{orig_h}) 降采样 {grid_w}x{grid_h}, 未检测到明显色块区域"

    out_lines = [
        f"图片视觉描述: {path}",
        f"原始尺寸: {orig_w}x{orig_h}, 降采样: {grid_w}x{grid_h}, 颜色合并阈值: {merge_thresh}",
        f"共 {len(regions)} 个色块区域(按面积排序):\n",
    ]

    for i, (ck, cells) in enumerate(regions):
        area = len(cells)
        pct = area / total
        r, g, b = ck
        cname = _color_name(r, g, b)
        hex_color = _rgb_hex(r, g, b)
        shape = _shape_desc(cells, grid_w, grid_h)
        out_lines.append(
            f"  区域{i+1}: {cname}({hex_color}) 占比{pct:.0%} | {shape}"
        )

    # 补充全局统计
    out_lines.append(f"\n全局: {grid_w}x{grid_h}={total} 格, 最小区域阈值 {min_area} 格({min_area/total:.0%})")

    return "\n".join(out_lines)
