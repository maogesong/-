import cv2

def iou(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    union_area = w1 * h1 + w2 * h2 - inter_area
    return inter_area / union_area if union_area else 0

def nms(detections, iou_threshold=0.2):
    detections = sorted(detections, key=lambda x: x['score'], reverse=True)
    keep = []
    while detections:
        best = detections.pop(0)
        keep.append(best)
        detections = [
            d for d in detections
            if iou(
                (best['position'][0], best['position'][1], best['shape'][0], best['shape'][1]),
                (d['position'][0], d['position'][1], d['shape'][0], d['shape'][1])
            ) < iou_threshold
        ]
    return keep

def recognize_numbers_in_region(img, templates, threshold=0.3):
    detections = []
    for cost, tpl in templates.items():
        if tpl.shape[2] != img.shape[2]:
            continue
        th, tw, _ = tpl.shape
        ih, iw, _ = img.shape
        if ih < th or iw < tw:
            continue
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        loc = zip(*((res >= threshold).nonzero()[::-1]))
        for pt in loc:
            detections.append({
                "cost": cost,
                "position": pt,
                "shape": (tw, th),
                "score": float(res[pt[1], pt[0]])
            })
    return nms(detections, iou_threshold=0.2)

def greedy_play_indices(cards, mana):
    sorted_cards = sorted([(d['cost'], idx) for idx, d in enumerate(cards)], reverse=True)
    chosen = []
    used = set()
    remain = mana
    for cost, idx in sorted_cards:
        if idx in used:
            continue
        if cost <= remain:
            chosen.append(idx)
            used.add(idx)
            remain -= cost
    return chosen
