"""shops 子命令:门店查询。"""
from __future__ import annotations

import click

from ..client import LuckinClient, LuckinError
from ..config import load_profile
from ..utils import format_store


def _get_client() -> LuckinClient:
    profile = load_profile()
    return LuckinClient(endpoint=profile.endpoint)


@click.group(name="shops")
def shops_group() -> None:
    """门店查询。"""


@shops_group.command(name="list")
@click.option("--lng", type=float, help="经度(不填用家门店坐标)")
@click.option("--lat", type=float, help="纬度(不填用家门店坐标)")
@click.option("--limit", type=int, default=8, help="显示数量(默认 8)")
def shops_list(lng, lat, limit) -> None:
    """列出门店(默认家门店周边)。"""
    profile = load_profile()
    if lng is None or lat is None:
        if not profile.home_store.deptId:
            raise click.UsageError("未配置家门店。用 --lng/--lat 指定,或先 smart-luckin config init")
        lng = profile.home_store.longitude
        lat = profile.home_store.latitude
        click.echo(f"📍 家门店周边: {profile.home_store.deptName}")
        click.echo()

    client = _get_client()
    try:
        shops = client.query_shops(lng, lat)
    except LuckinError as e:
        raise click.ClickException(str(e))

    if not shops:
        click.echo("未找到门店")
        return

    for i, s in enumerate(shops[:limit], 1):
        click.echo(format_store(s, i))
        click.echo()


@shops_group.command(name="status")
def shops_status() -> None:
    """查家门店营业状态。"""
    profile = load_profile()
    if not profile.home_store.deptId:
        raise click.UsageError("未配置家门店。先 smart-luckin config init")

    client = _get_client()
    try:
        shops = client.query_shops(profile.home_store.longitude, profile.home_store.latitude)
    except LuckinError as e:
        raise click.ClickException(str(e))

    # 从结果里找家门店(按 deptId)
    home = next((s for s in shops if s.get("deptId") == profile.home_store.deptId), None)
    if not home:
        # fallback:用最近的一家提示
        click.echo("⚠️ 家门店不在周边返回里,显示最近的:")
        if shops:
            home = shops[0]
        else:
            click.echo("未找到门店")
            return

    click.echo(format_store(home))

    # 时间校验(信息性显示,不阻断)
    work_start = home.get("workTimeStart", "")
    work_end = home.get("workTimeEnd", "")
    if work_start and work_end:
        import datetime
        from ..utils import check_order_time
        level, msg = check_order_time(work_start, work_end, datetime.datetime.now())
        emoji = {"ok": "✅", "warn": "⚠️", "danger": "🚨", "closed": "❌"}.get(level, "❓")
        click.echo(f"   {emoji} {msg}")
        if level in ("danger", "closed"):
            click.echo(f"   💡 下单会被拒绝(除非 -y 强制 danger)")
