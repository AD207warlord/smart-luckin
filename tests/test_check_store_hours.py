"""_check_store_hours 集成测试(order.py 内部函数)。

验证下单前的营业时间拦截逻辑:
- closed → 抛 ClickException(拒绝)
- danger + 无 -y → 抛 ClickException(拒绝)
- danger + -y → 放行
- warn → 放行(只提醒)
- ok → 静默放行

用 Mock client 避免真实下单。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from luckin.commands.order import _check_store_hours  # noqa: E402


def _mock_client(shop: dict | None) -> MagicMock:
    """构造 mock client,query_shops 返回 [shop]。"""
    client = MagicMock()
    client.query_shops.return_value = [shop] if shop else []
    return client


def _shop(work_start: str, work_end: str, dept_id: int = 123456) -> dict:
    """构造门店响应。"""
    return {
        "deptId": dept_id,
        "deptName": "测试店",
        "workTimeStart": work_start,
        "workTimeEnd": work_end,
        "workStatus": "营业中",
    }


# ===== closed 拒绝 =====
def test_closed_store_rejected(monkeypatch):
    """门店已打烊 → 抛 ClickException。"""
    import datetime
    # 现在 18:00,门店 07:00-17:00 已关门
    fixed_now = datetime.datetime(2026, 6, 19, 18, 0)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    client = _mock_client(_shop("07:00", "17:00"))
    with pytest.raises(click.ClickException) as exc:
        _check_store_hours(client, 123456, 121.0, 31.0)
    assert "未营业" in str(exc.value) or "打烊" in str(exc.value)


def test_before_open_rejected(monkeypatch):
    """未到营业时间 → 抛 ClickException。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 6, 0)  # 06:00,07:00 才开门
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    client = _mock_client(_shop("07:00", "17:00"))
    with pytest.raises(click.ClickException):
        _check_store_hours(client, 123456, 121.0, 31.0)


# ===== danger 拦截 =====
def test_danger_without_force_rejected(monkeypatch):
    """距关门 <10min,无 -y → 抛 ClickException。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 16, 55)  # 距 17:00 关门 5min
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    client = _mock_client(_shop("07:00", "17:00"))
    with pytest.raises(click.ClickException) as exc:
        _check_store_hours(client, 123456, 121.0, 31.0, force=False)
    assert "来不及" in str(exc.value) or "制作" in str(exc.value)


def test_danger_with_force_allowed(monkeypatch):
    """距关门 <10min,带 -y(force=True)→ 二次确认后放行。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 16, 55)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))
    # mock click.confirm 返回 True(用户确认时间风险)
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: None)

    client = _mock_client(_shop("07:00", "17:00"))
    _check_store_hours(client, 123456, 121.0, 31.0, force=True)


# ===== warn 放行(需二次确认)=====
def test_warn_allowed_with_confirm(monkeypatch):
    """距关门 15min(warn 区间)→ 二次确认后放行。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 16, 45)  # 距关门 15min
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))
    # mock click.confirm 返回 None(确认,不 abort)
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: None)

    client = _mock_client(_shop("07:00", "17:00"))
    _check_store_hours(client, 123456, 121.0, 31.0)


def test_warn_aborted_if_confirm_declined(monkeypatch):
    """warn 场景用户拒绝二次确认 → 抛 ClickException(abort)。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 16, 45)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))
    # mock click.confirm 抛 Abort(用户选 N)
    def _abort(*a, **kw):
        raise click.exceptions.Abort()
    monkeypatch.setattr(click, "confirm", _abort)

    client = _mock_client(_shop("07:00", "17:00"))
    with pytest.raises(click.exceptions.Abort):
        _check_store_hours(client, 123456, 121.0, 31.0)


# ===== ok 放行 =====
def test_ok_allowed(monkeypatch):
    """营业中距关门充足 → 放行。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 10, 0)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    client = _mock_client(_shop("07:00", "17:00"))
    _check_store_hours(client, 123456, 121.0, 31.0)


# ===== 异常容错(不阻断)=====
def test_shop_not_found_does_not_block(monkeypatch):
    """门店不在查询结果 → 放行(保守不阻断)。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 10, 0)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    # 返回的门店 deptId 不匹配
    other_shop = _shop("07:00", "17:00", dept_id=999999)
    client = _mock_client(other_shop)
    _check_store_hours(client, 123456, 121.0, 31.0)  # 不抛异常


def test_no_work_hours_does_not_block(monkeypatch):
    """门店无营业时间字段 → 放行(保守不阻断)。"""
    import datetime
    fixed_now = datetime.datetime(2026, 6, 19, 10, 0)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    shop = _shop("07:00", "17:00")
    shop["workTimeStart"] = ""
    shop["workTimeEnd"] = ""
    client = _mock_client(shop)
    _check_store_hours(client, 123456, 121.0, 31.0)


def test_query_failure_does_not_block(monkeypatch):
    """query_shops 抛 LuckinError → 放行(网络问题不阻断下单)。"""
    import datetime
    from luckin.client import LuckinError
    fixed_now = datetime.datetime(2026, 6, 19, 10, 0)
    monkeypatch.setattr(datetime, "datetime", _FakeDateTime(fixed_now))

    client = MagicMock()
    client.query_shops.side_effect = LuckinError(-1, "网络错误")
    _check_store_hours(client, 123456, 121.0, 31.0)  # 不抛异常


# ===== 辅助:可控时间的 datetime 替身 =====
class _FakeDateTime:
    """模拟 datetime.datetime,让 datetime.datetime.now() 返回固定值。

    需要同时支持 datetime.datetime(2026,...) 构造调用和 .now() 类方法,
    所以做成一个工厂类。
    """
    _fixed: datetime.datetime

    def __init__(self, fixed: datetime.datetime):
        self._fixed = fixed

    def __call__(self, *args, **kwargs):
        # 模拟 datetime.datetime(2026, 6, 19, 10, 0) 构造
        return datetime.datetime(*args, **kwargs)

    def now(self, tz=None):
        return self._fixed

    def __getattr__(self, name):
        # 透传 datetime.datetime 的其他类属性(如 fromtimestamp)
        return getattr(datetime.datetime, name)
