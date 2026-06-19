"""config 子命令:profile.json 管理。"""
from __future__ import annotations

import json

import click

from ..config import load_profile, save_profile, get_profile_path, get_token, get_amap_key, Profile, HomeStore, DailyOrder


@click.group(name="config")
def config_group() -> None:
    """配置管理(家门店、日常口味、查看配置)。"""


@config_group.command(name="show")
def config_show() -> None:
    """查看当前配置。"""
    profile = load_profile()
    path = get_profile_path()

    click.echo(f"📁 配置文件: {path}")
    click.echo(f"📡 MCP endpoint: {profile.endpoint}")
    click.echo()

    # 家门店
    hs = profile.home_store
    if hs.deptId:
        click.echo(f"🏠 家门店: {hs.deptName} ({hs.number})")
        click.echo(f"   deptId: {hs.deptId}")
        click.echo(f"   地址: {hs.address}")
        click.echo(f"   坐标: {hs.longitude}, {hs.latitude}")
        if hs.work_time:
            click.echo(f"   营业: {hs.work_time}")
    else:
        click.echo("🏠 家门店: 未配置(运行 smart-luckin config init)")

    click.echo()

    # 日常口味
    do = profile.daily_order
    if do.product_id:
        click.echo(f"☕ 日常口味: {do.product_name} (productId={do.product_id})")
        if do.spec:
            click.echo(f"   规格: {do.spec}")
        if do.skuCode:
            click.echo(f"   skuCode: {do.skuCode}")
    else:
        click.echo("☕ 日常口味: 未配置")

    click.echo()

    # 环境变量(脱敏显示)
    try:
        token = get_token()
        click.echo(f"🔑 LUCKIN_MCP_ORDER_TOKEN: {token[:8]}...({len(token)}位) ✅")
    except EnvironmentError as e:
        click.echo(f"🔑 LUCKIN_MCP_ORDER_TOKEN: ❌ 未设置")

    amap = get_amap_key()
    if amap:
        click.echo(f"🗺️  AMAP_API_KEY: {amap[:8]}...({len(amap)}位) ✅")
    else:
        click.echo("🗺️  AMAP_API_KEY: 未设置(locate 命令需要)")


@config_group.command(name="init")
@click.option("--store-name", prompt="家门店名称", help="门店名")
@click.option("--dept-id", type=int, prompt="门店 deptId(从 smart-luckin shops list 获取)", help="门店数字 ID")
@click.option("--store-addr", prompt="门店地址", default="", help="门店地址")
@click.option("--store-lng", type=float, prompt="门店经度", default=0.0, help="经度")
@click.option("--store-lat", type=float, prompt="门店纬度", default=0.0, help="纬度")
@click.option("--product-id", type=int, prompt="日常口味 productId(用 smart-luckin menu search 查)", default=0, help="商品 ID")
@click.option("--product-name", prompt="商品名", default="", help="商品名")
@click.option("--sku-code", prompt="成品 skuCode(切好规格的,用 product switch 取得)", default="", help="skuCode")
def config_init(store_name, dept_id, store_addr, store_lng, store_lat, product_id, product_name, sku_code) -> None:
    """交互式配置(首次使用)。

    家门店和日常口味可先用 smart-luckin shops list / smart-luckin menu search 查到再填。
    """
    profile = load_profile()
    profile.home_store = HomeStore(
        deptId=dept_id,
        deptName=store_name,
        address=store_addr,
        longitude=store_lng,
        latitude=store_lat,
    )
    profile.daily_order = DailyOrder(
        product_id=product_id,
        product_name=product_name,
        skuCode=sku_code,
    )
    path = save_profile(profile)
    click.echo(f"✅ 配置已保存: {path}")
    click.echo("现在可以运行: smart-luckin order daily")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """设置单个配置项(如 home_store.deptId)。

    \b
    示例:
      smart-luckin config set endpoint https://gwmcp.lkcoffee.com/order/user/mcp
      smart-luckin config set daily_order.skuCode SPxxxx-xxxxx
    """
    profile = load_profile()
    d = profile.to_dict()

    # 简单的点路径解析:home_store.deptId
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})

    # 类型推断
    final = parts[-1]
    try:
        typed_val: object = json.loads(value)
    except json.JSONDecodeError:
        typed_val = value

    cur[final] = typed_val
    save_profile(Profile.from_dict(d))
    click.echo(f"✅ {key} = {value}")
