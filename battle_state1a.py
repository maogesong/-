import pyautogui
import cv2
import numpy as np
import os
import re
from glob import glob
from PIL import ImageGrab
import pygetwindow as gw
import win32gui
from time import sleep

# ---------------配置区域---------------
TEMPLATE_PREFIXES = ["atk", "hp"]  # atk=攻击力, hp=生命值
THRESHOLD = 0.65
UPPER_ROI = (300, 380, 1580, 465)
LOWER_ROI = (300, 635, 1580, 720)

# --- 新增：卡片状态检测（sleep, rush, charge） ---
STATE_THRESHOLDS = {
    'rush':   {'lower': np.array([20, 100, 100]), 'upper': np.array([60, 255, 255])},
    'charge': {'lower': np.array([60, 100, 100]), 'upper': np.array([90, 255, 255])},
}
MIN_CONFIDENCE = 20
CROP_RADIUS = 15
OFFSET_X_LEFT = 10
OFFSET_Y_UP = 10

def load_templates(folder):
    templates = []
    for prefix in TEMPLATE_PREFIXES:
        for path in glob(os.path.join(folder, f"{prefix}_*.png")):
            tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tpl is None:
                print(f"[WARNING] 无法读取模板 {path}")
                continue
            name = os.path.splitext(os.path.basename(path))[0]  # e.g. atk_6_red
            kind, raw = name.split('_', 1)
            # 提取数字部分
            m = re.search(r"(\d+)", raw)
            if m:
                num = int(m.group(1))
            else:
                print(f"[WARNING] 未能从模板名提取数值: {name}")
                continue
            templates.append({'kind': kind, 'value_str': raw, 'num': num, 'tpl': tpl})
    print(f"已加载 {len(templates)} 个模板")
    return templates

def iou(b1, b2):
    x1, y1, w1, h1 = b1; x2, y2, w2, h2 = b2
    xi1, yi1 = max(x1, x2), max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2); yi2 = min(y1 + h1, y2 + h2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0

def nms(dets, threshold=0.2):
    dets.sort(key=lambda d: d['score'], reverse=True)
    keep = []
    for d in dets:
        if all(iou((d['x'], d['y'], d['w'], d['h']), (k['x'], k['y'], k['w'], k['h'])) < threshold for k in keep):
            keep.append(d)
    return keep

def detect(gray, templates):
    dets = []
    for tpl in templates:
        res = cv2.matchTemplate(gray, tpl['tpl'], cv2.TM_CCOEFF_NORMED)
        w, h = tpl['tpl'].shape[::-1]
        ys, xs = np.where(res >= THRESHOLD)
        for y, x in zip(ys, xs):
            dets.append({
                'x': int(x), 'y': int(y), 'w': w, 'h': h,
                'score': float(res[y, x]),
                'kind': tpl['kind'],
                'value_str': tpl['value_str'],
                'num': tpl['num']
            })
    return nms(dets)

def detect_region(coords, templates):
    x0, y0, x1, y1 = coords
    img_pil = ImageGrab.grab(bbox=(x0, y0, x1, y1))
    color = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    dets = detect(gray, templates)
    return color, dets

def detect_upper(templates):
    """仅检测并返回上排图像和检测结果（包含数值字段 'num'）"""
    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    win.restore(); win.activate(); sleep(1)
    x0, y0 = win32gui.ClientToScreen(win._hWnd, (0, 0))
    coords = (
        x0 + UPPER_ROI[0],
        y0 + UPPER_ROI[1],
        x0 + UPPER_ROI[2],
        y0 + UPPER_ROI[3]
    )
    image, dets = detect_region(coords, templates)
    dets.sort(key=lambda d: d['x'])
    atk_values = [d['num'] for d in dets if d['kind'] == 'atk']
    hp_values = [d['num'] for d in dets if d['kind'] == 'hp']
    states = ['unknown'] * len(atk_values)
    return image, dets, atk_values, hp_values, states

def detect_lower(templates, repeat=2):
    """
    检测并返回下排图像与检测结果，所有atk卡牌的'state'字段（sleep/rush/charge）
    支持连续多次检测，取最大置信度的结果。
    """
    import pygetwindow as gw
    import win32gui
    from time import sleep
    import cv2
    import numpy as np

    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    win.restore(); win.activate(); sleep(1)
    x0, y0 = win32gui.ClientToScreen(win._hWnd, (0, 0))
    coords = (
        x0 + LOWER_ROI[0],
        y0 + LOWER_ROI[1],
        x0 + LOWER_ROI[2],
        y0 + LOWER_ROI[3]
    )

    # 首次检测获取基准随从数量与各自中心点
    image, dets = detect_region(coords, templates)
    dets.sort(key=lambda d: d['x'])
    atk_dets = [d for d in dets if d['kind'] == 'atk']
    n_atk = len(atk_dets)
    centers = [(d['x'] - OFFSET_X_LEFT, d['y'] - OFFSET_Y_UP) for d in atk_dets]
    best_states = [{'state': 'sleep', 'confidence': 0.0} for _ in range(n_atk)]

    # 连续多次检测，保留最大置信度
    for run in range(repeat):
        image, dets = detect_region(coords, templates)
        dets.sort(key=lambda d: d['x'])
        atk_dets = [d for d in dets if d['kind'] == 'atk']
        if len(atk_dets) != n_atk:
            continue  # 数量不一致，跳过本次
        hsv_full = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        for i, a in enumerate(atk_dets):
            cx, cy = centers[i]
            x0c = max(cx - CROP_RADIUS, 0)
            y0c = max(cy - CROP_RADIUS, 0)
            x1c = min(cx + CROP_RADIUS, image.shape[1])
            y1c = min(cy + CROP_RADIUS, image.shape[0])
            crop_hsv = hsv_full[y0c:y1c, x0c:x1c]

            state = 'sleep'
            conf = 0.0
            for s, th in STATE_THRESHOLDS.items():
                mask = cv2.inRange(crop_hsv, th['lower'], th['upper'])
                c = mask.sum() / mask.size
                if c > conf:
                    conf = c
                    state = s
            if conf < MIN_CONFIDENCE:
                state = 'sleep'

            # 如果本次置信度更高，则替换
            if conf > best_states[i]['confidence']:
                best_states[i] = {'state': state, 'confidence': conf}

        sleep(0.05)

    # 最终写回state到det列表
    states = [s['state'] for s in best_states]
    atk_idx = 0
    for d in dets:
        if d['kind'] == 'atk':
            state = states[atk_idx] if atk_idx < len(states) else 'sleep'
            d['state'] = states[atk_idx]
            atk_idx += 1

    atk_values = [d['num'] for d in dets if d['kind'] == 'atk']
    hp_values = [d['num'] for d in dets if d['kind'] == 'hp']

    return image, dets, atk_values, hp_values, states


def detect_all(templates):
    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    win.restore(); win.activate(); sleep(1)
    x0, y0 = win32gui.ClientToScreen(win._hWnd, (0, 0))
    regions = {
        'upper': (x0 + UPPER_ROI[0], y0 + UPPER_ROI[1], x0 + UPPER_ROI[2], y0 + UPPER_ROI[3]),
        'lower': (x0 + LOWER_ROI[0], y0 + LOWER_ROI[1], x0 + LOWER_ROI[2], y0 + LOWER_ROI[3])
    }
    results = {'upper_atk': [], 'upper_hp': [], 'lower_atk': [], 'lower_hp': []}
    images = {}
    for region, coords in regions.items():
        img, dets = detect_region(coords, templates)
        for d in dets:
            results[f"{region}_{d['kind']}"].append(d)
        for kind in ['atk', 'hp']:
            results[f"{region}_{kind}"].sort(key=lambda x: x['x'])
        annotated = img.copy()
        for d in results[f"{region}_atk"]:
            cx, cy = d['x'] + d['w']//2, d['y'] + d['h']//2
            rad = max(d['w'], d['h'])//2 + 5
            cv2.circle(annotated, (cx, cy), rad, (0, 255, 0), 2)
            cv2.putText(annotated, str(d['num']), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0),2)
        for d in results[f"{region}_hp"]:
            cx, cy = d['x'] + d['w']//2, d['y'] + d['h']//2
            rad = max(d['w'], d['h'])//2 + 5
            cv2.circle(annotated, (cx, cy), rad, (0, 0, 255), 2)
            cv2.putText(annotated, str(d['num']), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255),2)
        images[region] = img
        images[f"{region}_annotated"] = annotated
    paired = {}
    for region in ['upper', 'lower']:
        atks = results[f"{region}_atk"]
        hps = results[f"{region}_hp"]
        pairs = [(a['num'], h['num']) for a, h in zip(atks, hps)]
        paired[f"{region}_pairs"] = pairs
    return results, paired, images

def evolve_lower_module(templates, repeat=2):
    """
    在 detect_lower 基础上检测进化并执行：
    1. 调用 detect_lower 获取随从位置
    2. 截取下排区域，匹配紫/黄进化点
    3. 优先紫色，拖动进化点至 detect_lower 提供的随从攻击区域
       仅使用检测到的相对坐标，避免全局坐标偏移
    """
    # 1. 获取随从检测结果（相对区域坐标）
    image, dets, atk_vals, hp_vals, states = detect_lower(templates, repeat)

    # 2. 定义截屏区域（全局坐标，仅用于截图）
    coords = (0, 540, 1920, 1080)
    img_pil = ImageGrab.grab(bbox=coords)
    region = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    # 3. 加载进化模板
    EVO_DEFS = [
        ("purple", ["battle/purple1.png", "battle/purple2.png"]),
        ("yellow", ["battle/yellow1.png", "battle/yellow2.png"])
    ]
    evo_tpls = []
    for color, paths in EVO_DEFS:
        for p in paths:
            tpl = cv2.imread(p, cv2.IMREAD_COLOR)
            if tpl is not None:
                evo_tpls.append({'color': color, 'tpl': tpl})

    # 4. 匹配进化点，相对区域坐标
    pts = []
    rh, rw = region.shape[:2]
    for tpl in evo_tpls:
        ph, pw = tpl['tpl'].shape[:2]
        if ph > rh or pw > rw:
            continue
        res = cv2.matchTemplate(region, tpl['tpl'], cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= 0.9)
        for y, x in zip(ys, xs):
            print(f"匹配到进化点 颜色={tpl['color']} 位置=({x},{y}) 分数={res[y, x]:.3f}")
            pts.append({'x': x, 'y': y, 'w': pw, 'h': ph, 'score': float(res[y, x]), 'color': tpl['color']})
    pts = nms(pts)
    if not pts:
        print("未检测到进化点")
        return image, dets, atk_vals, hp_vals, states

    # 5. 优先紫色
    pts.sort(key=lambda d: d['color'] != 'purple')
    pt = pts[0]
    # 进化点相对坐标
    evo_rel_x = pt['x'] + pt['w']//2
    evo_rel_y = pt['y'] + pt['h']//2

    # 6. 遍历 detect_lower 的 dets，使用相对坐标拖动
    # 将 dets 中的 atk 随从按状态排序
    priority_order = {'sleep': 0, 'charge': 1, 'rush': 2}
    atk_dets = [d for d in dets if d['kind'] == 'atk']
    for d in atk_dets:
        # 保证每个 d 包含 state 字段
        d.setdefault('state', 'sleep')
    # 排序: 先状态, 再数值大的先
    atk_dets.sort(key=lambda d: (priority_order.get(d.get('state','sleep'),1), -d['num']))

    # DEBUG: 打印排序后列表
    print("排序后随从顺序：", [(d['num'], d['state']) for d in atk_dets])
    for d in  atk_dets:
        corrected_rel_x = d['x'] + 400
        corrected_rel_y = d['y'] + 150
        # 转换为屏幕坐标，添加截图区域偏移
        start_x = coords[0] + evo_rel_x
        start_y = coords[1] + evo_rel_y
        end_x = coords[0] + corrected_rel_x
        end_y = coords[1] + corrected_rel_y
        print(f"从 ({start_x},{start_y}) 拖动至 ({end_x},{end_y})")
        pyautogui.moveTo(start_x, start_y)
        pyautogui.mouseDown()
        pyautogui.moveTo(end_x, end_y, duration=0.3)
        pyautogui.mouseUp()
        sleep(0.1)
    print(f"已使用{pt['color']}完成进化")
    return image, dets, atk_vals, hp_vals, states

if __name__ == '__main__':
    templates = load_templates('battle')
    # 单独测试 detect_lower 功能
    image, dets, atk_values, hp_values, states = detect_lower(templates, repeat=2)
    print(f"检测到下排随从atk值: {atk_values}")
    print(f"检测到下排随从hp值: {hp_values}")
    print(f"检测到下排随从状态: {states}")
    image_u, dets_u, atk_values_u, hp_values_u, states_u = detect_upper(templates)
    print(f"检测到上排随从atk值: {atk_values_u}")
    print(f"检测到上排随从hp值: {hp_values_u}")
    print(f"检测到上排随从状态: {states_u}")