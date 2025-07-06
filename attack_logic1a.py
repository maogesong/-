import time
import pyautogui
import pygetwindow as gw
import win32gui
import cv2
import numpy as np
from itertools import combinations
from PIL import ImageGrab
from battle_state1a import load_templates, detect_lower, detect_upper, LOWER_ROI, UPPER_ROI
import logging

LOG_FILENAME = 'atk_hp_mismatch.log'
logging.basicConfig(
    filename=LOG_FILENAME,
    filemode='a',  # 追加模式
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.WARNING
)

# === 配置区域 ===
TEMPLATE_FOLDER = 'battle'
TAUNT_TEMPLATE_PATH = 'battle/check_taunt.png'
CANNOTATK_TEMPLATE_PATH = 'battle/cannotatk.png'
TAUNT_THRESHOLD = 0.7
STATE_THRESHOLD = 0.7


def get_game_window():
    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    if win.isMinimized:
        win.restore()
    win.activate()
    time.sleep(1)
    ul_x, ul_y = win32gui.ClientToScreen(win._hWnd, (0, 0))
    l, t, r, b = win32gui.GetClientRect(win._hWnd)
    return ul_x, ul_y, r - l, b - t


def compute_followers(dets, atk_list, hp_list, ul_x, ul_y, region_roi, states=None):
    x0, y0 = region_roi[:2]
    followers = []
    filtered = sorted([d for d in dets if d['kind'] == 'atk'], key=lambda x: x['x'])
    for idx, d in enumerate(filtered):
        if idx >= len(atk_list) or idx >= len(hp_list):
            msg = f"atk/hp列表不足：idx={idx}, atk_list={atk_list}, hp_list={hp_list}, dets={dets}"
            print(f"[WARN] {msg}")
            logging.warning(msg)
            continue
        atk = atk_list[idx]
        hp = hp_list[idx]
        cx = ul_x + x0 + d['x'] + int(d['w']*0.9)
        cy = ul_y + y0 + d['y'] + int(d['h']*0.1)
        follower = {'position': (cx, cy), 'atk': atk, 'hp': hp}
        if states is not None and idx < len(states):
            follower['state'] = states[idx]
        followers.append(follower)
    return followers


def detect_taunt(taunt_tpl):
    ul_x, ul_y, w, h = get_game_window()
    img = ImageGrab.grab(bbox=(ul_x, ul_y, ul_x + w, ul_y + h // 2))
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    res = cv2.matchTemplate(gray, taunt_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return max_val


def find_best_combo(followers, target_hp):
    """寻找最小过量组合击杀目标"""
    best = None
    for r in range(2, len(followers)+1):
        for combo in combinations(followers, r):
            total = sum(f['atk'] for f in combo)
            if total >= target_hp:
                over = total - target_hp
                if best is None or over < best[0]:
                    best = (over, combo)
        if best:
            return best[1]
    return None


def refresh_my_followers(templates, ul_x, ul_y):
    _, dets_l, atk_l, hp_l, states = detect_lower(templates, repeat=2)
    followers = compute_followers(dets_l, atk_l, hp_l, ul_x, ul_y, LOWER_ROI, states)
    rush_followers = [f for f in followers if f.get('state') == 'rush']
    charge_followers = [f for f in followers if f.get('state') == 'charge']
    return rush_followers, charge_followers, followers

def attack_target(attacker, target_pos):
    pyautogui.moveTo(attacker['position']); pyautogui.mouseDown()
    pyautogui.moveTo(target_pos, duration=0.3); pyautogui.mouseUp()
    time.sleep(0.3)

def attack_and_taunt_sequence():
    global ul_x, ul_y, w, h, hero_pos
    ul_x, ul_y, w, h = get_game_window()

    # 加载模板
    templates = load_templates(TEMPLATE_FOLDER)
    taunt_tpl = cv2.cvtColor(cv2.imread(TAUNT_TEMPLATE_PATH), cv2.COLOR_BGR2GRAY)
    cannotatk_tpl = cv2.cvtColor(cv2.imread(CANNOTATK_TEMPLATE_PATH), cv2.COLOR_BGR2GRAY)

    # 检测上下排随从及属性
    _, dets_u, atk_u, hp_u, states = detect_upper(templates)
    rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
    # 只保留可行动随从（rush/charge，排除sleep）
    my_followers = [f for f in my_followers if f.get('state') != 'sleep']
    enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)

    # 打印扫描结果
    print("我方随从:", [(f['atk'], f['hp'], f['position']) for f in my_followers])
    print("敌方随从:", [(e['atk'], e['hp'], e['position']) for e in enemy_followers])

    if not my_followers:
        print("未检测到我方随从，跳过")
        return

    # 我方首随从位置
    start = my_followers[0]['position']
    # 英雄位置
    hero_pos = (int(ul_x + w*0.5), int(ul_y + h*0.1))
    pyautogui.moveTo(start); pyautogui.mouseDown()
    pyautogui.moveTo(hero_pos, duration=0.2)
    # 检测英雄嘲讽
    score_hero = detect_taunt(taunt_tpl)
    print(f"英雄嘲讽得分: {score_hero:.2f}")
    pyautogui.moveTo(start, duration=0.2); pyautogui.mouseUp()
    # 无嘲讽，全体攻击英雄
    if score_hero < TAUNT_THRESHOLD:
        for f in charge_followers:
            pyautogui.moveTo(f['position']); pyautogui.mouseDown()
            pyautogui.moveTo(hero_pos, duration=0.3); pyautogui.mouseUp()
            time.sleep(0.3)
        for f in rush_followers:
            killable = [e for e in enemy_followers if f['atk'] >= e['hp']]
            if not killable:
                print(f"[Skip] Rush随从 atk={f['atk']} 无可击杀目标")
                continue
            target = max(killable, key=lambda x: x['hp'])
            print(f"[Action] rush击杀: atk={f['atk']} -> tgt_hp={target['hp']}")
            attack_target(f, target['position'])
            time.sleep(1)
            _, dets_u, atk_u, hp_u, states = detect_upper(templates)
            rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
            enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)
        return

    # 击杀循环
    if score_hero >= TAUNT_THRESHOLD:
        # 刷新双方随从，并只保留可行动单位
        rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
        _, dets_u, atk_u, hp_u, states = detect_upper(templates)
        enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)
        my_followers = [f for f in my_followers if f.get('state') != 'sleep']
        start = my_followers[0]['position']
        pyautogui.moveTo(start); pyautogui.mouseDown()
        # 收集所有taunt目标
        taunt_targets = []
        for e in enemy_followers:
            pyautogui.moveTo(e['position'], duration=0.3)
            t_score = detect_taunt(taunt_tpl)
            c_score = detect_taunt(cannotatk_tpl)
            if t_score  <= TAUNT_THRESHOLD and c_score <= TAUNT_THRESHOLD:
                taunt_targets.append(e)
        time.sleep(0.1)
        pyautogui.moveTo(start);pyautogui.mouseUp()

        for tgt in sorted(taunt_targets, key=lambda x: x['hp']):
            # 单体优先
            singles = [f for f in my_followers if f['atk'] >= tgt['hp']]
            if singles:
                attacker = min(singles, key=lambda f: f['atk'] - tgt['hp'])
                print(f"[Action] 单体击杀({attacker['state']}) atk={attacker['atk']} -> tgt_hp={tgt['hp']}")
                attack_target(attacker, tgt['position'])
                my_followers.remove(attacker)
            else:
                combo = find_best_combo(my_followers, tgt['hp'])
                if combo:
                    print(f"[Action] 组合击杀 { [f['atk'] for f in combo] } -> tgt_hp={tgt['hp']}")
                    for f in combo:
                        attack_target(f, tgt['position'])
                        my_followers.remove(f)
                else:
                    print(f"[Action] 全员攻击 -> tgt_hp={tgt['hp']}")
                    for f in my_followers:
                        attack_target(f, tgt['position'])
                    # 清空避免后续访问
                    my_followers.clear()
            _, dets_u, atk_u, hp_u, states = detect_upper(templates)
            rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
            enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)
            my_followers = [f for f in my_followers if f.get('state') != 'sleep']
        time.sleep(0.3)

    # === 尝试用剩余 rush 随从击杀敌方高血量目标 ===
    rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
    _, dets_u, atk_u, hp_u, states = detect_upper(templates)
    enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)

    for f in rush_followers:
        killable = [e for e in enemy_followers if f['atk'] >= e['hp']]
        if not killable:
            print(f"[Skip] Rush随从 atk={f['atk']} 无可击杀目标")
            continue
        target = max(killable, key=lambda x: x['hp'])
        print(f"[Action] rush击杀: atk={f['atk']} -> tgt_hp={target['hp']}")
        attack_target(f, target['position'])
        time.sleep(1)
        rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)
        _, dets_u, atk_u, hp_u, states = detect_upper(templates)
        enemy_followers = compute_followers(dets_u, atk_u, hp_u, ul_x, ul_y, UPPER_ROI)


    # === 剩余 charge 随从攻击英雄 ===
    # 刷新状态，确保位置信息准确
    rush_followers, charge_followers, my_followers = refresh_my_followers(templates, ul_x, ul_y)

    # === 剩余 charge 随从攻击英雄 ===
    for f in charge_followers:
        print(f"[Action] 攻击英雄（charge） from {f['position']} -> {hero_pos}")
        pyautogui.moveTo(f['position']); pyautogui.mouseDown()
        pyautogui.moveTo(hero_pos, duration=0.3); pyautogui.mouseUp()
        time.sleep(0.5)


if __name__ == '__main__':
    attack_and_taunt_sequence()
