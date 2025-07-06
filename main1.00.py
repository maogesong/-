import os
import cv2
import numpy as np
import mss
import pygetwindow as gw
import pyautogui
import win32gui
from time import sleep
from card_play import card_play_main
from battle_state1a import evolve_lower_module, load_templates 
from card_util import reset_click

# --------------全局状态----------------
battle_number = 0
win_count = 0
loss_count = 0

# --------------窗口与客户区定位----------------
wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
if not wins:
    raise RuntimeError("未找到 ShadowverseWB 窗口")
win = wins[0]
if win.isMinimized:
    win.restore()
win.activate()
sleep(1)
hwnd = win._hWnd

client_ul_x, client_ul_y = win32gui.ClientToScreen(hwnd, (0, 0))
l, t, r, b = win32gui.GetClientRect(hwnd)
client_w, client_h = r - l, b - t
region = (client_ul_x, client_ul_y, client_w, client_h)

def check_end_conditions(region_gray):
    """
    返回 (victory_detected, defeat_detected)
    """
    # 胜利检测
    win_tpl = cv2.imread('win.png', 0)
    res_w = cv2.matchTemplate(region_gray, win_tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv_w, _, _ = cv2.minMaxLoc(res_w)
    victory = maxv_w >= 0.8

    # 失败检测
    def_tpl = cv2.imread('gameset.png', 0)
    res_d = cv2.matchTemplate(region_gray, def_tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv_d, _, _ = cv2.minMaxLoc(res_d)
    defeat = maxv_d >= 0.8

    return victory, defeat

# --------------截屏函数----------------
def take_screenshot(region, to_gray=True):
    with mss.mss() as sct:
        mon = {
            "top": region[1], "left": region[0],
            "width": region[2], "height": region[3]
        }
        img = sct.grab(mon)
    frame = np.array(img)[:, :, :3]
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if to_gray else frame

# --------------鼠标点击----------------
def do_click(x, y, name):
    print(f"[{name}] 点击 -> 屏幕坐标 ({x}, {y})")
    pyautogui.click(x, y)

# --------------按钮模板加载----------------
tpls = {
    '决定':     'decision.png',
    '结束回合':  'end_round.png',
    '结束':     'end.png',
    '重试':     'retry.png',
    '阶位积分':   'rank.png',
    '决斗':     'war.png',
    'ok':      'ok.png',
    'click':    'click.png',
    'rankup':   'rankup.png'
}
for name, p in tpls.items():
    img = cv2.imread(p, 0)
    if img is None:
        raise FileNotFoundError(f"找不到模板 {p}")
    h, w = img.shape
    tpls[name] = (img, w, h)
button_thr = 0.8

# ------------主循环：按钮检测 + 回合管理 + 换牌与出牌-------------
clicked = {name: False for name in tpls}
round_cnt = 1
mulligan_done = False

print("脚本已启动，按 Ctrl+C 停止")
try:
    while True:
        gray = take_screenshot(region)
        detected_button = None

        for name, (tpl, w, h) in tpls.items():
            res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, maxl = cv2.minMaxLoc(res)
            if maxv >= button_thr and not clicked[name]:
                lx, ly = maxl
                sx = client_ul_x + lx + w//2
                sy = client_ul_y + ly + h//2
                print(f"[{name}] 按钮被检测到，坐标({sx},{sy})")
                clicked[name] = True
                detected_button = (name, sx, sy)
                break
            elif maxv < button_thr and clicked[name]:
                clicked[name] = False

        # ----"决定" 出现时处理换牌 + 重置回合数----
        if detected_button and detected_button[0] == '决定':
            if not mulligan_done:
                print("检测到 '决定'，开始执行换牌逻辑")
                os.system("python Mulligan_Module.py")
                mulligan_done = True
                sleep(1.0)
            print("点击 '决定' 按钮以开始对局")
            do_click(detected_button[1], detected_button[2], detected_button[0])
            round_cnt = 1
            reset_click(client_ul_x, client_ul_y, client_w)
            sleep(1.0)
            continue

        # ----"结束回合"：自动出牌、攻击、点击结束----
        if detected_button and detected_button[0] == '结束回合':
            print(f"--- 第 {battle_number} 场战斗，当前回合 {round_cnt} ---")
            print(f"检测到 '结束回合'，本回合费用为 {round_cnt}，开始自动出牌与攻击…")
            # 第一次出牌
            remaining_mana = card_play_main(available_mana=round_cnt)
            if  round_cnt>=4:  
                print("尝试进化随从…")
                templates = load_templates('battle')
                img, dets, atk_vals, hp_vals, states = evolve_lower_module(templates, repeat=2)
            os.system("python attack_logic1a.py")
            sleep(1.0)
            do_click(detected_button[1], detected_button[2], detected_button[0])
            round_cnt += 1
            sleep(1.0)
            reset_click(client_ul_x, client_ul_y, client_w)
            continue

        # ----处理其他按钮（重试、决斗等）----
        if detected_button:
            if detected_button[0] in ('重试', '决斗', 'ok', 'click', 'rankup', '阶位积分'):
                print("检测到 '重试' 或 '决斗'，点击继续")
            do_click(detected_button[1], detected_button[2], detected_button[0])
            reset_click(client_ul_x, client_ul_y, client_w)
            region_gray = take_screenshot(region, to_gray=True)
            victory, defeat = check_end_conditions(region_gray)
            win_count += victory
            loss_count += defeat
            print(f"*** 当前胜利次数: {win_count} 次, 失败次数: {loss_count} 次 ***")
            # 战数与回合数显示
            battle_number += 1
            sleep(1.0)
        sleep(1.2)
except KeyboardInterrupt:
    print("检测到 Ctrl+C，脚本已停止运行，感谢使用 ShadowverseBot！")
