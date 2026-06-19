"""locate 子命令:模糊地址 → 精确坐标 → 附近门店。"""
from __future__ import annotations

import click

from ..amap import AmapClient, AmapError
from ..client import LuckinClient, LuckinError
from ..config import load_profile
from ..utils import format_store


@click.command(name="locate")
@click.argument("address")
@click.option("--city", default="", help="城市限定(如 上海/北京)")
@click.option("--limit", type=int, default=5, help="显示门店数")
def locate_cmd(address: str, city: str, limit: int) -> None:
    """模糊地址 → 高德定位 → 附近门店。

    \b
    三场景自动路由:
      - 精确门牌(含数字)→ 地理编码,精度 <50m
      - 地标名(含大厦/广场/中心)→ POI 搜索,精度最高
      - 模糊路段(无门牌)→ 地理编码中点,列候选让用户选

    \b
    示例:
      smart-luckin locate 新华路664号
      smart-luckin locate 万宝国际商务中心
      smart-luckin locate 延安西路 --city 上海
    """
    profile = load_profile()

    try:
        amap = AmapClient()
    except EnvironmentError as e:
        raise click.UsageError(str(e))

    try:
        loc = amap.locate(address, city)
    except AmapError as e:
        raise click.ClickException(str(e))

    click.echo(f"📍 {address}")
    click.echo(f"   {loc.formatted_address} ({loc.district})")
    click.echo(f"   坐标: {loc.longitude},{loc.latitude} [{loc.source}]")
    if loc.is_fuzzy:
        click.echo(f"   ⚠️ 模糊定位(路段中点),如不在 {loc.district} 请说明具体位置")
    click.echo()

    # 查附近门店
    client = LuckinClient(endpoint=profile.endpoint)
    try:
        shops = client.query_shops(loc.longitude, loc.latitude)
    except LuckinError as e:
        raise click.ClickException(str(e))

    if not shops:
        click.echo("附近无瑞幸门店")
        return

    click.echo(f"🏠 附近 {len(shops)} 家门店:")
    click.echo()
    for i, s in enumerate(shops[:limit], 1):
        click.echo(format_store(s, i))
        click.echo()
