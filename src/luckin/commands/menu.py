"""menu 子命令:菜单/商品发现。"""
from __future__ import annotations

import click

from ..client import LuckinClient, LuckinError
from ..config import load_profile
from ..utils import format_product, FALLBACK_SEARCH_DEPTS

# 四维度分类词清单(来自 menu-discovery.md 实测)
CATEGORY_QUERIES = {
    "品类": ["美式", "标准美式", "深烘美式", "拿铁", "生椰拿铁", "丝绒拿铁", "厚乳拿铁",
              "香草拿铁", "燕麦拿铁", "卡布奇诺", "澳瑞白", "耶加雪菲", "玛奇朵",
              "抹茶", "抹茶拿铁", "轻乳茶", "果茶", "瑞纳冰", "小黄油拿铁", "轻椰茉莉拿铁"],
    "口味": ["苹果", "芒果", "西柚", "柚子", "草莓", "椰子", "杨枝甘露", "芋泥",
              "巧克力", "焦糖", "榛子"],
    "系列": ["丝绒", "Hello", "弗朗明戈", "耶加雪菲", "冰吸"],
    "标签": ["新品", "经典"],
}


def _get_search_dept(preferred: int) -> int:
    """获取可用于 search 的门店(规避单店服务波动)。

    先试 preferred,失败 fallback 到已知可用门店。
    """
    client = LuckinClient()
    candidates = [preferred] + [d for d in FALLBACK_SEARCH_DEPTS if d != preferred]
    for dept_id in candidates:
        try:
            result = client.search_products(dept_id, "美式")
            if result:
                return dept_id
        except LuckinError:
            continue
    return preferred  # 全失败就返回原值(让上层报错)


@click.group(name="menu")
def menu_group() -> None:
    """菜单/商品发现。"""


@menu_group.command(name="search")
@click.argument("query")
@click.option("--dept", type=int, default=None, help="门店 deptId(不填用家门店,且自动 fallback)")
def menu_search(query: str, dept) -> None:
    """搜索商品(支持模糊匹配)。

    \b
    示例:
      smart-luckin menu search 生椰拿铁
      smart-luckin menu search Hello苹果茉莉
      smart-luckin menu search 美式
    """
    profile = load_profile()
    preferred = dept or profile.home_store.deptId or FALLBACK_SEARCH_DEPTS[0]
    search_dept = _get_search_dept(preferred)

    client = LuckinClient(endpoint=profile.endpoint)
    try:
        products = client.search_products(search_dept, query)
    except LuckinError as e:
        raise click.ClickException(str(e))

    if not products:
        click.echo(f"未找到匹配 '{query}' 的商品")
        click.echo("(提示:换更具体的品类名,如 '美式咖啡' 而非 '美式')")
        return

    click.echo(f"🔍 '{query}' 命中 {len(products)} 个商品:")
    click.echo()
    for i, p in enumerate(products, 1):
        click.echo(format_product(p, i))


@menu_group.command(name="new")
def menu_new() -> None:
    """查看新品(query='新品' 命中新品池)。"""
    profile = load_profile()
    preferred = profile.home_store.deptId or FALLBACK_SEARCH_DEPTS[0]
    search_dept = _get_search_dept(preferred)

    client = LuckinClient(endpoint=profile.endpoint)
    try:
        products = client.search_products(search_dept, "新品")
    except LuckinError as e:
        raise click.ClickException(str(e))

    if not products:
        click.echo("暂无新品信息")
        return

    click.echo("🆕 新品:")
    click.echo()
    for i, p in enumerate(products, 1):
        click.echo(format_product(p, i))


@menu_group.command(name="discover")
@click.option("--limit", type=int, default=50, help="最多显示商品数(默认 50)")
def menu_discover(limit: int) -> None:
    """发现菜单(四维度分类词批量枚举)。

    品类/口味/系列/标签四个维度系统查询,拼出尽量全的菜单。
    覆盖率约 60-70%(完整菜单需 App/小程序)。
    """
    profile = load_profile()
    preferred = profile.home_store.deptId or FALLBACK_SEARCH_DEPTS[0]
    search_dept = _get_search_dept(preferred)

    client = LuckinClient(endpoint=profile.endpoint)
    products: dict[int, dict] = {}

    with click.progressbar(CATEGORY_QUERIES.items(), label="枚举菜单") as bar:
        for dim, queries in bar:
            for q in queries:
                try:
                    result = client.search_products(search_dept, q)
                    for p in result or []:
                        pid = p.get("productId")
                        if pid and pid not in products:
                            products[pid] = p
                except LuckinError:
                    continue

    if not products:
        click.echo("菜单发现失败(可能门店搜索服务波动)")
        return

    click.echo(f"📋 发现 {len(products)} 个商品(四维度枚举,覆盖率约 60-70%):")
    click.echo()
    for i, (pid, p) in enumerate(sorted(products.items(), key=lambda x: int(x[0])), 1):
        if i > limit:
            click.echo(f"... 共 {len(products)} 个,用 --limit 查看更多")
            break
        click.echo(format_product(p, i))
