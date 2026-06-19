"""下单前时间校验测试。

测试 check_order_time 纯函数:营业时间 + 当前时间 → 可否下单 + 警告级别。

级别:
- ok:营业中,距关门 >30min,正常下单
- warn:营业中,距关门 10~30min,提醒快关门
- danger:营业中,距关门 <10min(或不足制作提前量),建议不下
- closed:未营业/已打烊
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

# 让测试能 import src/luckin
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from luckin.utils import check_order_time  # noqa: E402


def _t(hhmm: str) -> datetime.datetime:
    """'16:55' → datetime(2026,6,19,16,55) 固定日期便于测试。"""
    h, m = hhmm.split(":")
    return datetime.datetime(2026, 6, 19, int(h), int(m))


# ===== 未营业(开门前)=====
def test_before_open_hours_is_closed():
    """07:00 营业,06:30 查 → closed 未营业。"""
    level, msg = check_order_time("07:00", "17:00", _t("06:30"))
    assert level == "closed"
    assert "未营业" in msg or "未开门" in msg


def test_early_morning_way_before_open():
    """凌晨 03:00 → closed。"""
    level, _ = check_order_time("07:00", "17:00", _t("03:00"))
    assert level == "closed"


# ===== 已打烊(关门后)=====
def test_after_close_is_closed():
    """17:00 关门,18:00 查 → closed 已打烊。"""
    level, msg = check_order_time("07:00", "17:00", _t("18:00"))
    assert level == "closed"
    assert "打烊" in msg or "已关门" in msg


def test_exactly_at_close_is_closed():
    """正好 17:00 → closed(边界,到点关门)。"""
    level, _ = check_order_time("07:00", "17:00", _t("17:00"))
    assert level == "closed"


# ===== 正常下单(距关门充足)=====
def test_well_within_hours_is_ok():
    """10:00 查,距 17:00 关门还有 7 小时 → ok。"""
    level, _ = check_order_time("07:00", "17:00", _t("10:00"))
    assert level == "ok"


def test_just_opened_is_ok():
    """07:01 刚开门 → ok。"""
    level, _ = check_order_time("07:00", "17:00", _t("07:01"))
    assert level == "ok"


# ===== 快关门警告(距关门 10~30min)=====
def test_30min_before_close_is_warn():
    """16:30,距 17:00 关门 30min → warn。"""
    level, msg = check_order_time("07:00", "17:00", _t("16:30"))
    assert level == "warn"
    assert "快关门" in msg or "即将" in msg or "分钟" in msg


def test_15min_before_close_is_warn():
    """16:45,距关门 15min → warn。"""
    level, _ = check_order_time("07:00", "17:00", _t("16:45"))
    assert level == "warn"


# ===== 来不及(距关门 <10min,不足制作提前量)=====
def test_5min_before_close_is_danger():
    """16:55,距关门 5min,不足制作提前量(默认 10min)→ danger。"""
    level, msg = check_order_time("07:00", "17:00", _t("16:55"))
    assert level == "danger"
    assert "来不及" in msg or "制作" in msg or "提前量" in msg


def test_9min_before_close_is_danger():
    """16:51,距关门 9min < 10min 提前量 → danger。"""
    level, _ = check_order_time("07:00", "17:00", _t("16:51"))
    assert level == "danger"


# ===== 自定义制作提前量 =====
def test_custom_lead_time_15min():
    """制作提前量 15min,16:40(距关门 20min)→ ok,16:44(16min)→ warn 边界。"""
    # 16:40 距关门 20min > 15min 提前 + 在 30min warn 区间
    level, _ = check_order_time("07:00", "17:00", _t("16:40"), lead_minutes=15)
    assert level == "warn"  # 20min 在 warn 区间(10~30)
    # 16:44 距关门 16min > 15min 提前 → warn(还在 warn 区)
    level, _ = check_order_time("07:00", "17:00", _t("16:44"), lead_minutes=15)
    assert level == "warn"
    # 16:45 距关门 15min == 提前量 → danger(刚好不足)
    level, _ = check_order_time("07:00", "17:00", _t("16:45"), lead_minutes=15)
    assert level == "danger"


# ===== 异常输入 =====
def test_invalid_time_format_returns_closed():
    """营业时间格式错 → closed(保守拒绝)。"""
    level, _ = check_order_time("invalid", "17:00", _t("10:00"))
    assert level == "closed"


def test_empty_work_hours_returns_closed():
    """空营业时间 → closed(查不到营业信息,不下单)。"""
    level, _ = check_order_time("", "", _t("10:00"))
    assert level == "closed"


# ===== 跨午营业(如夜店 18:00-02:00)=====
def test_overnight_hours_before_midnight():
    """跨午营业 18:00-02:00,21:00 查 → ok。"""
    level, _ = check_order_time("18:00", "02:00", _t("21:00"))
    assert level == "ok"


def test_overnight_hours_after_midnight():
    """跨午营业 18:00-02:00,01:00 查(距关门 1h)→ ok。"""
    level, _ = check_order_time("18:00", "02:00", _t("01:00"))
    assert level == "ok"
