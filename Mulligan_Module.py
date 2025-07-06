import os
import cv2
import numpy as np
import pyautogui
import time
from PIL import ImageGrab
import pygetwindow as gw
import win32gui

def load_templates(template_folder):
    from glob import glob
    templates = {}
    for tpl_path in glob(f"{template_folder}/mulligan/[1-9].png") + glob(f"{template_folder}/mulligan/10.png"):
        cost = int(os.path.splitext(os.path.basename(tpl_path))[0])
        tpl_img = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
        if tpl_img is not None:
            templates[cost] = tpl_img
    return templates

def get_roi(x0, y0, w, h, x_perc_start=0.10, x_perc_end=0.7, y_perc_start=0.56, y_perc_end=0.62):
    rx0 = x0 + int(w * x_perc_start)
    rx1 = x0 + int(w * x_perc_end)
    ry0 = y0 + int(h * y_perc_start)
    ry1 = y0 + int(h * y_perc_end)
    return rx0, ry0, rx1, ry1

def mulligan_hand(number_folder, client_ul_x, client_ul_y, client_w, client_h, match_threshold=0.35, drag_length=180, debug_save=True, replace_cost_threshold=5):
    templates = load_templates(number_folder)
    roi = get_roi(client_ul_x, client_ul_y, client_w, client_h)
    img = np.array(ImageGrab.grab(bbox=roi))
    if debug_save:
        os.makedirs(number_folder, exist_ok=True)
        cv2.imwrite(os.path.join(number_folder, 'mulligan_roi_raw.png'), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_vis = img.copy()
    results = []
    for cost, tpl in templates.items():
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= match_threshold:
            h, w = tpl_gray.shape
            pt = max_loc
            cx, cy = pt[0]+w//2, pt[1]+h//2
            abs_x = roi[0] + cx
            abs_y = roi[1] + cy
            # 右下角坐标
            rb_x = roi[0] + pt[0] + w
            rb_y = roi[1] + pt[1] + h
            results.append((cost, rb_x, rb_y, w, h, max_val))
            print(f"[Mulligan] 匹配: cost={cost}, 右下角=({rb_x}, {rb_y}), 匹配分数={max_val:.4f}")
            cv2.rectangle(img_vis, (abs_x-w//2, abs_y-h//2), (abs_x+w//2, abs_y+h//2), (0,255,0), 2)
            label = f"{cost}:{max_val:.2f}"
            cv2.putText(img_vis, label, (abs_x-w//2, abs_y-h//2-10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
    if debug_save:
        cv2.imwrite(os.path.join(number_folder, 'mulligan_roi_annotated.png'), img_vis)
    for cost, rb_x, rb_y, w, h, max_val in results:
        if cost >= replace_cost_threshold:  # 支持自定义换牌费用阈值
            print(f'[Mulligan] 换牌: {cost} 右下角=({rb_x}, {rb_y}), 匹配分数={max_val:.4f}')
            pyautogui.moveTo(rb_x, rb_y)
            pyautogui.dragRel(0, -drag_length, duration=0.25)
            time.sleep(0.1)
    print('[Mulligan] 完成')
    return True


if __name__ == "__main__":
    # 自动窗口定位
    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    if win.isMinimized:
        win.restore()
    win.activate()
    time.sleep(1)
    hwnd = win._hWnd
    client_ul_x, client_ul_y = win32gui.ClientToScreen(hwnd, (0, 0))
    l, t, r, b = win32gui.GetClientRect(hwnd)
    client_w, client_h = r - l, b - t

    number_folder = "number"
    mulligan_hand(number_folder, client_ul_x, client_ul_y, client_w, client_h, match_threshold=0.7, drag_length=180, debug_save=True)
