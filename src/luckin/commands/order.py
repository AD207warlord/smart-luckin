"""order 子命令:订单全流程(预览/下单/查询/取消/日常一键)。"""
from __future__ import annotations

import datetime

import click

from ..client import LuckinClient, LuckinError
from ..config import load_profile
from ..utils import (
    generate_qr_url,
    generate_qr_markdown,
    format_order_status,
    detect_delivery_intent,
    check_order_time,
)


def _get_client() -> LuckinClient:
    profile = load_profile()
    return LuckinClient(endpoint=profile.endpoint)


def _resolve_dept_and_coords(dept: int | None, locate: str | None) -> tuple[int, float, float]:
    """解析门店 + 坐标。

    优先级:--dept 显式 > --locate 定位 > 家门店配置
    """
    profile = load_profile()

    if dept:
        if not profile.home_store.deptId:
            raise click.UsageError("--dept 需要 profile 里有家门店坐标。先 smart-luckin config init")
        return dept, profile.home_store.longitude, profile.home_store.latitude

    if locate:
        # 外送意图检测(瑞幸 MCP createOrder 无 delivery/收货地址字段,协议层只支持自提)
        if detect_delivery_intent(locate):
            raise click.UsageError(
                "⚠️ 瑞幸 MCP 不支持外送(createOrder 无 delivery/收货地址字段,仅到店自取)。\n"
                "如需自提,请提供门店地址或坐标(如 'XX 路 123 号')。"
            )
        # 用高德定位
        from ..amap import AmapClient, AmapError
        try:
            amap = AmapClient()
        except EnvironmentError as e:
            raise click.UsageError(str(e))
        try:
            loc = amap.locate(locate)
        except AmapError as e:
            raise click.ClickException(str(e))

        if loc.is_fuzzy:
            click.echo(f"⚠️ 定位到路段中点({loc.district}),可能需要确认具体门店")
        click.echo(f"📍 {locate} → {loc.formatted_address} ({loc.longitude},{loc.latitude})")

        # 查最近门店
        client = _get_client()
        try:
            shops = client.query_shops(loc.longitude, loc.latitude)
        except LuckinError as e:
            raise click.ClickException(str(e))

        if not shops:
            raise click.ClickException(f"'{locate}' 附近无门店")
        nearest = shops[0]
        click.echo(f"🏠 最近门店: {nearest.get('deptName')} ({nearest.get('number')}) - {nearest.get('distance')}km")
        return nearest["deptId"], loc.longitude, loc.latitude

    # 默认家门店
    if not profile.home_store.deptId:
        raise click.UsageError("未指定门店。用 --dept / --locate,或先 smart-luckin config init")
    return profile.home_store.deptId, profile.home_store.longitude, profile.home_store.latitude


def _build_product_list(product_id: int, sku: str, amount: int = 1) -> list[dict]:
    return [{"amount": amount, "productId": product_id, "skuCode": sku}]


def _check_store_hours(client: LuckinClient, dept_id: int, lng: float, lat: float, force: bool = False) -> None:
    """下单前校验门店营业时间。

    通过 queryShopList 拿门店的 workTimeStart/End,调 check_order_time 分级:
    - closed:抛 ClickException 拒绝(门店未营业)
    - danger:打印警告;force=False 时拒绝,force=True 时**二次确认**(防 -y 误下)
    - warn:打印提醒;**无论 force 与否都二次确认**(防 -y 忽略时间警告)
    - ok:静默

    二次确认设计:warn/danger 场景即使 -y 也要用户显式确认时间风险。
    门店查不到营业时间(网络异常/字段缺失)时,保守放行(不阻断),仅打印提示。
    """
    try:
        shops = client.query_shops(lng, lat)
    except LuckinError as e:
        # 查门店失败不阻断下单(可能是临时网络问题),仅提示
        click.echo(f"⚠️ 无法校验营业时间(门店查询失败:{e}),继续下单")
        return

    shop = next((s for s in shops if s.get("deptId") == dept_id), None)
    if not shop:
        click.echo("⚠️ 无法校验营业时间(门店不在查询结果里),继续下单")
        return

    work_start = shop.get("workTimeStart", "")
    work_end = shop.get("workTimeEnd", "")
    if not work_start or not work_end:
        click.echo("⚠️ 门店未返回营业时间,无法校验,继续下单")
        return

    level, msg = check_order_time(work_start, work_end, datetime.datetime.now())
    status_emoji = {"ok": "✅", "warn": "⚠️", "danger": "🚨", "closed": "❌"}.get(level, "❓")
    click.echo(f"{status_emoji} {shop.get('deptName', '')} 营业 {work_start}-{work_end} | {msg}")

    if level == "closed":
        raise click.ClickException(f"门店未营业,无法下单。营业时间 {work_start}-{work_end}")

    if level == "danger":
        if not force:
            raise click.ClickException(
                f"{msg}\n来不及取餐。如确需下单,加 -y 强制(会再次确认)。"
            )
        # force=True(-y)也要二次确认,防误下
        click.confirm(
            f"🚨 {msg},确认仍要下单?(可能取不到餐)",
            abort=True,
        )

    if level == "warn":
        # warn 场景:即使 -y 也要二次确认时间风险(防 -y 忽略警告)
        click.confirm(
            f"⚠️ {msg},确认下单?",
            abort=True,
        )
    # ok 静默放行


@click.group(name="order")
def order_group() -> None:
    """订单管理(预览/下单/查询/取消)。"""


@order_group.command(name="preview")
@click.option("--product", "product_id", type=int, default=None, help="productId(不填用日常口味)")
@click.option("--sku", "sku_code", default=None, help="skuCode(不填用日常口味配置)")
@click.option("--dept", type=int, default=None, help="门店 deptId(不填用家门店)")
@click.option("--locate", default=None, help="模糊地址定位(如 'XX 区 XX 路 999 弄')")
@click.option("--amount", type=int, default=1, help="数量")
def order_preview(product_id, sku_code, dept, locate, amount) -> None:
    """预览订单(拿价格 + 券码 + 取餐时间,不扣款)。"""
    profile = load_profile()
    dept_id, lng, lat = _resolve_dept_and_coords(dept, locate)

    # 商品:优先命令行参数,否则日常口味
    pid = product_id or profile.daily_order.product_id
    sku = sku_code or profile.daily_order.skuCode
    if not pid or not sku:
        raise click.UsageError("未指定商品。用 --product/--sku,或先 smart-luckin config init 配置日常口味")

    product_list = _build_product_list(pid, sku, amount)
    client = _get_client()
    try:
        result = client.preview_order(dept_id, product_list)
    except LuckinError as e:
        raise click.ClickException(str(e))

    shop = result.get("shopInfo", {})
    products = result.get("productInfoList", [])
    click.echo(f"🏠 {shop.get('deptName', '')} ({shop.get('number', '')}) - {shop.get('workStatus', '')}")
    for p in products:
        click.echo(f"☕ {p.get('name')} × {p.get('amount')}")
        click.echo(f"   规格: {p.get('additionDesc')}")
        click.echo(f"   原价 ¥{p.get('initPrice')} → 到手 ¥{p.get('estimatePrice')}")
    click.echo()
    click.echo(f"💰 到手价: ¥{result.get('discountPrice')}")
    coupons = result.get("couponCodeList", [])
    if coupons:
        click.echo(f"🎟️ 可用券: {len(coupons)} 张")
    about_time = result.get("aboutTime")
    if about_time:
        t = datetime.datetime.fromtimestamp(about_time / 1000)
        click.echo(f"⏰ 预计取餐: {t.strftime('%H:%M')}")


@order_group.command(name="create")
@click.option("--product", "product_id", type=int, default=None, help="productId(不填用日常口味)")
@click.option("--sku", "sku_code", default=None, help="skuCode(不填用日常口味配置)")
@click.option("--dept", type=int, default=None, help="门店 deptId(不填用家门店)")
@click.option("--locate", default=None, help="模糊地址定位")
@click.option("--amount", type=int, default=1, help="数量")
@click.option("--yes", "-y", is_flag=True, help="跳过确认(危险:直接扣款)")
@click.option("--no-qr", is_flag=True, help="不显示二维码(只输出 URL)")
def order_create(product_id, sku_code, dept, locate, amount, yes, no_qr) -> None:
    """创建订单(⚠️ 真实扣款,自动取券 + 生成支付二维码)。

    内部:createOrder 前自动 previewOrder 取当次券码,避免用过期券多花钱。
    二维码用 payOrderUrl(deeplink)直出,扫码一步进支付。
    """
    profile = load_profile()
    dept_id, lng, lat = _resolve_dept_and_coords(dept, locate)

    pid = product_id or profile.daily_order.product_id
    sku = sku_code or profile.daily_order.skuCode
    if not pid or not sku:
        raise click.UsageError("未指定商品。用 --product/--sku,或配置日常口味")

    product_list = _build_product_list(pid, sku, amount)

    # 先校验门店营业时间(closed 拒绝 / danger 默认拒除非 -y / warn 提醒)
    client = _get_client()
    _check_store_hours(client, dept_id, lng, lat, force=yes)

    # 再预览确认价格
    try:
        preview = client.preview_order(dept_id, product_list)
    except LuckinError as e:
        raise click.ClickException(str(e))

    price = preview.get("discountPrice")
    shop = preview.get("shopInfo", {}).get("deptName", "")
    click.echo(f"💰 {shop} | 到手价 ¥{price}")

    if not yes:
        click.confirm("确认下单?(会真实扣款)", abort=True)

    # 安全下单(自动取券)
    try:
        order, _ = client.create_order_safe(dept_id, product_list, lng, lat)
    except LuckinError as e:
        raise click.ClickException(str(e))

    order_id = order.get("orderId", "")
    pay_url = order.get("payOrderUrl", "")  # deeplink,用这个
    # payOrderQrCodeUrl 是中转页,实测扫码报"非法链接",不用

    click.echo(f"✅ 订单已创建: {order_id}")
    click.echo(f"   应付: ¥{order.get('discountPrice', price)}")

    if pay_url:
        qr_url = generate_qr_url(pay_url)
        click.echo()
        if no_qr:
            click.echo(f"📱 支付链接: {pay_url}")
            click.echo(f"   二维码图片: {qr_url}")
        else:
            click.echo("📱 扫码支付(微信扫下方二维码):")
            click.echo()
            click.echo(generate_qr_markdown(pay_url))
            click.echo()
            click.echo(f"(图片打不开?复制此链接到浏览器: {qr_url})")
        click.echo()
        click.echo(f"支付完成后:smart-luckin order status {order_id}")


@order_group.command(name="status")
@click.argument("order_id")
def order_status(order_id: str) -> None:
    """查订单状态 + 取餐码。"""
    client = _get_client()
    try:
        order = client.query_order(order_id)
    except LuckinError as e:
        raise click.ClickException(str(e))

    click.echo(format_order_status(order))


@order_group.command(name="cancel")
@click.argument("order_id")
@click.option("--yes", "-y", is_flag=True, help="跳过确认")
def order_cancel(order_id: str, yes) -> None:
    """取消订单(未支付时取消最干净,不扣款)。"""
    if not yes:
        click.confirm(f"确认取消订单 {order_id}?", abort=True)

    client = _get_client()
    try:
        ok = client.cancel_order(order_id)
    except LuckinError as e:
        raise click.ClickException(str(e))

    if ok:
        click.echo(f"✅ 订单 {order_id} 已取消")
    else:
        click.echo(f"❌ 取消失败")


@order_group.command(name="daily")
@click.option("--yes", "-y", is_flag=True, help="跳过确认")
def order_daily(yes) -> None:
    """一键日常下单(用配置的家门店 + 日常口味)。

    最高频命令。内部:查营业 → 预览 → 确认 → 下单 → 二维码。
    """
    profile = load_profile()
    if not profile.home_store.deptId or not profile.daily_order.product_id:
        raise click.UsageError("未配置家门店或日常口味。先 smart-luckin config init")

    click.echo(f"🏠 {profile.home_store.deptName}")
    click.echo(f"☕ {profile.daily_order.product_name}")

    # 走 create 流程(复用,create 内部会做营业时间校验)
    ctx = click.get_current_context()
    ctx.invoke(order_create,
               product_id=profile.daily_order.product_id,
               sku_code=profile.daily_order.skuCode,
               dept=profile.home_store.deptId,
               locate=None, amount=1, yes=yes, no_qr=False)
