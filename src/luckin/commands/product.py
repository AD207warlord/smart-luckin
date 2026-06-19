"""product 子命令:商品详情 + 规格切换。"""
from __future__ import annotations

import click

from ..client import LuckinClient, LuckinError
from ..config import load_profile


def _get_client() -> LuckinClient:
    profile = load_profile()
    return LuckinClient(endpoint=profile.endpoint)


@click.group(name="product")
def product_group() -> None:
    """商品详情 + 规格切换。"""


@product_group.command(name="detail")
@click.argument("product_id", type=int)
@click.option("--dept", type=int, default=None, help="门店 deptId(不填用家门店)")
def product_detail(product_id: int, dept) -> None:
    """查商品详情 + 完整规格树(选择面板)。

    \b
    示例:
      smart-luckin product detail 2507      # 加浓美式
      smart-luckin product detail 5509      # Hello苹果茉莉
    """
    profile = load_profile()
    dept_id = dept or profile.home_store.deptId
    if not dept_id:
        raise click.UsageError("未指定门店。用 --dept 或先 smart-luckin config init")

    client = _get_client()
    try:
        p = client.query_product_detail(dept_id, product_id)
    except LuckinError as e:
        raise click.ClickException(str(e))

    if not p:
        click.echo("未找到商品")
        return

    click.echo(f"🛒 {p.get('productName')} (productId={p.get('productId')})")
    click.echo(f"   skuCode: {p.get('skuCode')}")
    click.echo(f"   原价: ¥{p.get('initialPrice')} | 预估: ¥{p.get('estimatePrice')}")
    click.echo()
    click.echo("规格选项:")
    for attr in p.get("productAttrs", []):
        click.echo(f"  [{attr.get('attributeName')}] (attributeId={attr.get('attributeId')})")
        for sub in attr.get("productSubAttrs", []):
            sel = "✅" if sub.get("selected") else "  "
            price = sub.get("price", 0)
            price_str = f" +¥{price}" if price else ""
            click.echo(f"    {sel} {sub.get('attributeName')} (subId={sub.get('attributeId')}){price_str}")
        click.echo()


@product_group.command(name="switch")
@click.argument("product_id", type=int)
@click.option("--size", help="杯型(如 大杯/超大杯/特大杯)")
@click.option("--temp", help="温度(如 冰/热)")
@click.option("--bean", help="咖啡豆(如 意式拼配/深烘拼配/埃塞金烘)")
@click.option("--concentration", help="浓度(如 默认浓度/加单份浓缩)")
@click.option("--sugar", help="糖(如 不另外加糖/少甜/标准甜)")
@click.option("--milk", help="奶(如 无奶/单份奶)")
@click.option("--tea", help="茶风味(如 茉莉花香/去茶底)")
@click.option("--spec", help="自由文本规格(逗号分隔,自动归类,如 '少冰,无糖,燕麦奶')。与 --size 等可混用,显式参数优先")
@click.option("--dept", type=int, default=None, help="门店 deptId(不填用家门店)")
@click.option("--show-detail", is_flag=True, help="切换后显示完整属性树")
def product_switch(product_id: int, size, temp, bean, concentration, sugar, milk, tea, spec, dept, show_detail) -> None:
    """切换商品规格(内部自动链式调用,封装 operation=3 + skuCode 滚动)。

    \b
    示例(两种写法等价):
      smart-luckin product switch 2507 --size 超大杯 --temp 冰 --bean 意式拼配
      smart-luckin product switch 2507 --spec "超大杯,冰,意式拼配"

    \b
    自由文本 --spec 支持别名(少冰/无糖/燕麦奶 等),自动归类到属性维度:
      smart-luckin product switch 5509 --spec "少冰,无糖,燕麦奶"

    内部:queryProductDetailInfo 拿属性树 → 按 name 匹配 ID → 链式 switchProduct。
    不同商品维度不同(加浓美式 6 维,Hello苹果茉莉 4 维),自动适配。
    """
    profile = load_profile()
    dept_id = dept or profile.home_store.deptId
    if not dept_id:
        raise click.UsageError("未指定门店。用 --dept 或先 smart-luckin config init")

    # 组装 specs:先解析 --spec 自由文本,再叠加显式参数(显式优先覆盖)
    specs: dict[str, str] = {}
    if spec:
        from ..attrs import parse_spec_text
        specs.update(parse_spec_text(spec))

    name_map = {
        "杯型": size, "温度": temp, "咖啡豆": bean,
        "咖啡浓度": concentration, "糖": sugar, "奶": milk,
        "茶风味": tea,
    }
    for k, v in name_map.items():
        if v:
            specs[k] = v

    if not specs:
        raise click.UsageError("至少指定一个规格(--size/--temp/--bean 等,或 --spec '少冰,无糖')")

    client = _get_client()

    # 先拿基础商品
    try:
        detail = client.query_product_detail(dept_id, product_id)
    except LuckinError as e:
        raise click.ClickException(str(e))

    base_sku = detail.get("skuCode", "")
    base_name = detail.get("productName", str(product_id))
    click.echo(f"🛒 {base_name} (基础 skuCode: {base_sku})")
    click.echo(f"   切换规格: {specs}")
    click.echo()

    # 链式切换
    try:
        result = client.switch_specs(dept_id, product_id, base_sku, specs)
    except LuckinError as e:
        raise click.ClickException(str(e))

    final_sku = result.get("skuCode", "")
    click.echo(f"✅ 最终 skuCode: {final_sku}")
    click.echo()
    click.echo("选中状态:")
    for attr in result.get("productAttrs", []):
        sels = [s.get("attributeName", "") for s in attr.get("productSubAttrs", []) if s.get("selected")]
        click.echo(f"  [{attr.get('attributeName')}]: {' / '.join(sels)}")

    if show_detail:
        click.echo()
        click.echo("完整属性树:")
        for attr in result.get("productAttrs", []):
            click.echo(f"  [{attr.get('attributeName')}]")
            for sub in attr.get("productSubAttrs", []):
                sel = "✅" if sub.get("selected") else "  "
                click.echo(f"    {sel} {sub.get('attributeName')}")

    click.echo()
    click.echo("💡 下单用此 skuCode:")
    click.echo(f"   smart-luckin order create --product {product_id} --sku {final_sku}")
