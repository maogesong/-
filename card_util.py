import os
import cv2
import pyautogui
import time

def load_templates(template_folder):
    from glob import glob
    templates = {}
    for tpl_path in glob(f"{template_folder}/[1-9].png") + glob(f"{template_folder}/10.png"):
        cost = int(os.path.splitext(os.path.basename(tpl_path))[0])
        tpl_img = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
        if tpl_img is not None:
            templates[cost] = tpl_img
    return templates

def get_roi(x0, y0, w, h, x_perc_start=0.6, x_perc_end=1.0, y_perc_start=0.86, y_perc_end=0.895):
    rx0 = x0 + int(w * x_perc_start)
    rx1 = x0 + int(w * x_perc_end)
    ry0 = y0 + int(h * y_perc_start)
    ry1 = y0 + int(h * y_perc_end)
    return rx0, ry0, rx1, ry1

def play_card(card_info, roi_lefttop, drag_offset=(70, 110), drag_length=200, delay=0.3):
    x, y = card_info['position']
    w, h = card_info['shape']
    start_x = roi_lefttop[0] + x + int(w * 0.7) + drag_offset[0]
    start_y = roi_lefttop[1] + y + int(h * 0.7) + drag_offset[1]
    end_x = start_x
    end_y = start_y - drag_length
    print(f"滑动出牌: 从({start_x}, {start_y})到({end_x}, {end_y})")
    pyautogui.moveTo(start_x, start_y)
    pyautogui.mouseDown()
    pyautogui.moveTo(end_x, end_y, duration=0.3)
    pyautogui.mouseUp()
    time.sleep(delay)

def reset_click(client_ul_x, client_ul_y, client_w):
    right_top_x = client_ul_x + client_w - 350
    right_top_y = client_ul_y + 500
    print(f"复位点击({right_top_x}, {right_top_y})")
    pyautogui.moveTo(right_top_x, right_top_y, duration=0.3)
    pyautogui.mouseDown()
    time.sleep(0.3)
    pyautogui.mouseUp()
