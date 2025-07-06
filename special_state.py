import os
import cv2
from PIL import ImageGrab
import argparse
import pygetwindow as gw
import win32gui
import glob

def detect_and_save(template_path, capture_path, result_path, threshold=0.5):
    screen_img = cv2.imread(capture_path)
    ref_img = cv2.imread(template_path)
    if ref_img is None or screen_img is None:
        print(f"错误：读取图像失败 {template_path} 或 {capture_path}")
        return False, 0.0

    if screen_img.shape[0] < ref_img.shape[0] or screen_img.shape[1] < ref_img.shape[1]:
        print(f"模板尺寸大于截图，跳过 {template_path}")
        return False, 0.0

    res = cv2.matchTemplate(screen_img, ref_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        top_left = max_loc
        h_, w_, _ = ref_img.shape
        bottom_right = (top_left[0] + w_, top_left[1] + h_)
        cv2.rectangle(screen_img, top_left, bottom_right, (0, 0, 255), 2)
        cv2.putText(screen_img, f"Matched (score={max_val:.2f})", (top_left[0], top_left[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imwrite(result_path, screen_img)
        return True, max_val
    else:
        return False, max_val

def screenshot_shadowverse(save_path):
    wins = [w for w in gw.getAllWindows() if "ShadowverseWB" in w.title]
    if not wins:
        raise RuntimeError("未找到 ShadowverseWB 窗口")
    win = wins[0]
    if win.isMinimized:
        win.restore()
    win.activate()
    hwnd = win._hWnd
    x0, y0 = win32gui.ClientToScreen(hwnd, (0, 0))
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    img = ImageGrab.grab(bbox=(x0, y0, x0 + w, y0 + h))
    img.save(save_path)
    print(f"截图已保存：{save_path}")
    return True

def run_special_state_detection(base_dir='special', threshold=0.5):
    os.makedirs(base_dir, exist_ok=True)
    capture_path = os.path.join(base_dir, "batch_capture.png")

    try:
        screenshot_shadowverse(capture_path)
    except Exception as e:
        print(str(e))
        return

    templates = sorted(glob.glob(os.path.join(base_dir, '[0-9][0-9][0-9].png')))
    if not templates:
        print("未找到任何模板文件（格式为 001.png、002.png 等）")
        return

    print(f"\n开始批量检测（总共 {len(templates)} 个模板）\n")
    for tpl_path in templates:
        base_name = os.path.splitext(os.path.basename(tpl_path))[0]
        result_path = os.path.join(base_dir, f"{base_name}_match.png")

        ok, score = detect_and_save(
            template_path=tpl_path,
            capture_path=capture_path,
            result_path=result_path,
            threshold=threshold
        )

        status = "✅ 匹配成功" if ok else "❌ 未匹配"
        print(f"{base_name}: {status}（score = {score:.2f}）")

    print("\n检测完毕。")

# CLI 调用支持
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量检测 ShadowverseWB 窗口中的特殊状态")
    parser.add_argument('--base_dir', type=str, default='special', help='模板和保存目录')
    parser.add_argument('--threshold', type=float, default=0.5, help='匹配阈值')
    args = parser.parse_args()
    run_special_state_detection(base_dir=args.base_dir, threshold=args.threshold)
