from card_util import (load_templates, get_roi, play_card, reset_click)
from card_logic import (recognize_numbers_in_region, greedy_play_indices)
from special_state import run_special_state_detection
import pygetwindow as gw
import win32gui
from PIL import ImageGrab
import cv2
import os
import argparse
import time

def card_play_main(available_mana=1):
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

    rx0, ry0, rx1, ry1 = get_roi(client_ul_x, client_ul_y, client_w, client_h)
    os.makedirs("number", exist_ok=True)
    img_path = "number/roi.png"
    img = ImageGrab.grab(bbox=(rx0, ry0, rx1, ry1))
    img.save(img_path)

    roi = cv2.imread(img_path)
    templates = load_templates("number")
    results = recognize_numbers_in_region(roi, templates, threshold=0.5)

    drag_offset = (70, 110)
    drag_length = 200

    if results:
        idxs = greedy_play_indices(results, available_mana)
        for idx in idxs:
            if idx >= len(results):
                print(f"[WARN] idx {idx} 超界，results长度 {len(results)}，跳过")
                continue
            d = results[idx]
            play_card(d, (rx0, ry0), drag_offset=drag_offset, drag_length=drag_length)
            reset_click(client_ul_x, client_ul_y, client_w)
            available_mana -= d['cost']
            time.sleep(1)

            new_img = ImageGrab.grab(bbox=(rx0, ry0, rx1, ry1))
            new_img.save("number/roi_after_play.png")
            roi_after = cv2.imread("number/roi_after_play.png")
            current_hand = recognize_numbers_in_region(roi_after, templates, threshold=0.5)
            prev_set = {(d2['cost'], d2['position']) for d2 in results}
            curr_set = {(d2['cost'], d2['position']) for d2 in current_hand}

            if prev_set == curr_set:
                print("手牌区未变化，尝试补充出牌...")
                available_mana += d['cost']
                retry_idxs = greedy_play_indices(current_hand, available_mana)
                if retry_idxs:
                    for ridx in retry_idxs:
                        d = current_hand[ridx]
                        play_card(d, (rx0, ry0), drag_offset=drag_offset, drag_length=drag_length)
                        available_mana -= d['cost']
                        run_special_state_detection(base_dir="special", threshold=0.6)
                break
            else:
                results = current_hand

        cv2.imwrite("number/roi_detected.png", roi)
    else:
        print("未检测到数字。")

    reset_click(client_ul_x, client_ul_y, client_w)
    return available_mana

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mana', '--turn', type=int, default=1, help='本回合可用费用/回合数')
    args = parser.parse_args()
    card_play_main(available_mana=args.mana)
