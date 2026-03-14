# -*- coding: utf-8 -*-
"""
app/shared/logic/westgard.py
(ĐÃ CẬP NHẬT GĐ 10 - Bổ sung logic 10_X và 7_T)
Logic tính toán các quy tắc Westgard.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from typing import List, Dict, Tuple, Set, Optional, Any
import math


def _to_float(v: Any) -> float:
    """Helper ép kiểu an toàn, trả về nan nếu lỗi."""
    try:
        return float(v)
    except (ValueError, TypeError, OverflowError):
        return float('nan')


def _gt(val: float, thr: float) -> bool:
    """Kiểm tra |val| > thr (an toàn với nan)."""
    if math.isnan(val):
        return False
    return abs(val) > thr


def _same_side(vals: List[float], center: float) -> bool:
    """True nếu tất cả các giá trị (không nan) cùng lớn hơn hoặc cùng nhỏ hơn center."""
    valid_vals = [v for v in vals if not math.isnan(v)]
    if not valid_vals:
        return False

    pos = [v > center for v in valid_vals]
    return all(pos) or not any(pos)


# (MỚI) HÀM TRỢ GIÚP KIỂM TRA XU HƯỚNG 7T
def _is_trending(vals: List[float], n: int) -> bool:
    """Kiểm tra n điểm liên tiếp tăng hoặc giảm (strictly monotonic)."""
    if len(vals) < n: return False
    tail = vals[-n:]

    # Kiểm tra tăng nghiêm ngặt (Strictly Increasing)
    is_increasing = all(tail[i] < tail[i + 1] for i in range(n - 1))

    # Kiểm tra giảm nghiêm ngặt (Strictly Decreasing)
    is_decreasing = all(tail[i] > tail[i + 1] for i in range(n - 1))

    return is_increasing or is_decreasing


def eval_rules(
        history: List[float],
        mean: float,
        sd: float,
        rules: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Đánh giá các quy tắc Westgard cho ĐIỂM CUỐI CÙNG trong 'history'.

    Args:
        history (List[float]): Lịch sử giá trị (thứ tự: cũ -> mới).
        mean (float): Mean mục tiêu.
        sd (float): SD mục tiêu.
        rules (Set[str], optional): Các quy tắc cần kiểm tra (ví dụ: {"1_3s", "10_x"}).

    Returns:
        Dict: {'violated': [list_of_rules], 'details': {rule: msg}, 'last_z': z_last}
    """
    if rules is None:
        rules = {"1_3s", "1_2s", "2_2s", "R_4s", "4_1s"}  # Sử dụng tên chuẩn mới

    out_v = []
    details = {}

    if not history:
        return {"violated": [], "details": {}, "last_z": float('nan')}

    m = _to_float(mean)
    s = _to_float(sd)

    if math.isnan(m) or math.isnan(s) or s <= 0:
        # Không thể đánh giá nếu không có Mean/SD
        return {"violated": [], "details": {}, "last_z": float('nan')}

    # Tính Z-scores
    zscores = [(_to_float(v) - m) / s for v in history]
    z_last = zscores[-1] if zscores else float('nan')

    if math.isnan(z_last):
        return {"violated": [], "details": {}, "last_z": z_last}

    # --- QUY TẮC CƠ BẢN ---

    # 1-3s: |z_last| > 3 (REJECT)
    if "1_3s" in rules and _gt(z_last, 3):
        out_v.append("1_3s")
        details["1_3s"] = f"Vi phạm 1_3s (Z={z_last:.2f})"

    # 1-2s: |z_last| > 2 (WARN)
    if "1_2s" in rules and _gt(z_last, 2):
        out_v.append("1_2s")
        details["1_2s"] = f"Cảnh báo 1_2s (Z={z_last:.2f})"

    # 2-2s: 2 điểm liên tiếp vượt cùng phía ±2SD (REJECT)
    if "2_2s" in rules and len(zscores) >= 2:
        z1, z2 = zscores[-2], zscores[-1]
        if _gt(z1, 2) and _gt(z2, 2) and (z1 * z2) > 0:  # Cùng dấu
            out_v.append("2_2s")
            details["2_2s"] = f"Vi phạm 2_2s (Z={z1:.2f}, {z2:.2f})"

    # R-4s: |diff 2 điểm liên tiếp| >= 4SD (REJECT)
    if "R_4s" in rules and len(zscores) >= 2:
        z1, z2 = zscores[-2], zscores[-1]
        if not math.isnan(z1) and abs(z1 - z2) >= 4:
            out_v.append("R_4s")
            details["R_4s"] = f"Vi phạm R_4s (Z={z1:.2f}, {z2:.2f})"

    # --- QUY TẮC HỆ THỐNG/NÂNG CAO ---

    # 4-1s: 4 điểm liên tiếp cùng phía vượt ±1SD (REJECT)
    if "4_1s" in rules and len(zscores) >= 4:
        tail = zscores[-4:]
        if all(_gt(z, 1) for z in tail) and _same_side(tail, 0.0):
            out_v.append("4_1s")
            details["4_1s"] = "Vi phạm 4_1s"

    # 8x (giữ lại 8x nếu người dùng dùng, mặc dù 10x là chuẩn hơn)
    if "8_x" in rules and len(zscores) >= 8:
        tail = zscores[-8:]
        if _same_side(tail, 0.0):
            out_v.append("8_x")
            details["8_x"] = "Vi phạm 8_X (Kéo dài)"

    # 10x: 10 điểm liên tiếp cùng phía mean (REJECT) - (MỚI)
    if "10_x" in rules and len(zscores) >= 10:
        tail = zscores[-10:]
        if _same_side(tail, 0.0):
            out_v.append("10_x")
            details["10_x"] = "Vi phạm 10_X (Hệ thống)"

    # 7T: 7 điểm liên tiếp có xu hướng (Trend) tăng hoặc giảm (REJECT) - (MỚI)
    if "7_t" in rules and len(zscores) >= 7:
        if _is_trending(zscores, 7):
            out_v.append("7_t")
            details["7_t"] = "Vi phạm 7_T (Xu hướng)"

    return {"violated": out_v, "details": details, "last_z": z_last}


def get_rule_priority(rule_code: str) -> int:
    """Gán mức độ ưu tiên (thấp hơn là nghiêm trọng hơn)."""
    if rule_code == "1_3s": return 1
    if rule_code == "R_4s": return 2
    if rule_code == "2_2s": return 3
    if rule_code in ("4_1s", "8_x", "10_x", "7_t"): return 4  # Tất cả lỗi hệ thống là ưu tiên 4
    if rule_code == "1_2s": return 6  # Cảnh báo (Warn)
    return 99


def get_highest_priority_violation(violated: List[str]) -> Optional[str]:
    """Tìm vi phạm nghiêm trọng nhất từ danh sách."""
    if not violated:
        return None
    return min(violated, key=get_rule_priority)

def check_westgard_multilevel(
        current_z_scores: Dict[str, float],  # VD: {'L1': 2.5, 'L2': -2.1}
        history_z_scores: Dict[str, List[float]],  # VD: {'L1': [1.0, 0.5...], 'L2': [...]} (Điểm gần nhất ở index 0)
        rules_config: Optional[List[str]] = None
) -> Dict[str, str]:
    """
    Kiểm tra quy tắc Westgard đa mức (Multi-level).
    Bao gồm:
    1. Within-Run: R-4s, 2-2s (giữa các mức trong cùng lần chạy).
    2. Across-Run: 2-2s (so với lịch sử của chính mức đó).
    3. Single-Rule: 1-3s, 1-2s.

    Output: Dict mapping { 'L1': '1_3s', 'L2': 'R_4s' ... }
    """
    if rules_config is None:
        rules_config = ["1_3s", "2_2s", "R_4s", "1_2s"]  # Mặc định

    violations = {}
    levels = list(current_z_scores.keys())

    # --- GIAI ĐOẠN 1: KIỂM TRA ĐƠN LẺ & ACROSS-RUN ---
    for lvl, z in current_z_scores.items():
        # 1. Quy tắc 1-3s (Random/Systematic - Từ chối)
        if "1_3s" in rules_config and abs(z) > 3:
            violations[lvl] = "1_3s"
            continue  # Lỗi nặng nhất, không cần check tiếp

        # 2. Quy tắc 2-2s (Across-Run - Từ chối)
        # (Mức này > 2SD VÀ Lần chạy trước của chính nó > 2SD cùng chiều)
        if "2_2s" in rules_config:
            hist = history_z_scores.get(lvl, [])
            prev_z = hist[0] if hist else 0.0
            if (z > 2 and prev_z > 2) or (z < -2 and prev_z < -2):
                violations[lvl] = "2_2s"
                continue

    # --- GIAI ĐOẠN 2: KIỂM TRA WITHIN-RUN (GIỮA CÁC MỨC) ---
    # Chỉ thực hiện nếu có từ 2 mức trở lên (L1, L2...)
    if len(levels) >= 2:
        z_values = [current_z_scores[l] for l in levels]

        # 3. Quy tắc R-4s (Random - Từ chối)
        # (Chênh lệch giữa Max Z và Min Z trong cùng đợt > 4SD)
        if "R_4s" in rules_config:
            z_max = max(z_values)
            z_min = min(z_values)
            if (z_max - z_min) > 4:
                # Đánh dấu lỗi cho cả 2 level gây ra (Max và Min)
                for lvl in levels:
                    z = current_z_scores[lvl]
                    if z == z_max or z == z_min:
                        # Chỉ ghi đè nếu chưa có lỗi nặng hơn (1-3s)
                        if violations.get(lvl) != "1_3s":
                            violations[lvl] = "R_4s"

        # 4. Quy tắc 2-2s (Systematic - Within-Run - Từ chối)
        # (Hai mức trong cùng đợt đều > 2SD hoặc đều < -2SD)
        if "2_2s" in rules_config:
            count_pos = sum(1 for z in z_values if z > 2)
            count_neg = sum(1 for z in z_values if z < -2)

            if count_pos >= 2 or count_neg >= 2:
                for lvl in levels:
                    if abs(current_z_scores[lvl]) > 2:
                        if violations.get(lvl) != "1_3s":
                            violations[lvl] = "2_2s"

    # --- GIAI ĐOẠN 3: CẢNH BÁO ---
    for lvl, z in current_z_scores.items():
        if lvl not in violations:
            # 5. Quy tắc 1-2s (Warning)
            if "1_2s" in rules_config and abs(z) > 2:
                violations[lvl] = "1_2s"
            else:
                violations[lvl] = "OK"

    return violations