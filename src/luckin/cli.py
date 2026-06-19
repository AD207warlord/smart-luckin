"""luckin CLI 主入口(click group)。

所有子命令在 commands/ 下,这里只做注册。
"""
from __future__ import annotations

import sys

import click

from . import __version__
from .commands import shops_group, menu_group, product_group, order_group, config_group, locate_cmd


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="smart-luckin")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """☕ smart-luckin — 瑞幸咖啡点单 CLI。

    封装瑞幸 MCP 的踩坑经验,装完即用。配置好后 `smart-luckin order daily` 一键下单。

    \b
    常用命令:
      smart-luckin config init      首次配置(家门店 + 日常口味)
      smart-luckin order daily      一键日常下单
      smart-luckin shops status     查家门店营业状态
      smart-luckin menu new         看新品
      smart-luckin locate <地址>    模糊地址找门店

    注:命令名 `smart-luckin` 避开瑞幸官方 CLI(`luckin` 登录/刷 token 用)的冲突。
    """
    # Windows GBK 控制台兼容
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, Exception):
        pass

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# 注册子命令组
cli.add_command(config_group, name="config")
cli.add_command(shops_group, name="shops")
cli.add_command(menu_group, name="menu")
cli.add_command(product_group, name="product")
cli.add_command(order_group, name="order")
cli.add_command(locate_cmd, name="locate")


if __name__ == "__main__":
    cli()
