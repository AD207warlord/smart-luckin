"""commands 包:聚合所有子命令组。"""
from .config_cmd import config_group
from .shops import shops_group
from .menu import menu_group
from .product import product_group
from .order import order_group
from .locate import locate_cmd

__all__ = [
    "config_group",
    "shops_group",
    "menu_group",
    "product_group",
    "order_group",
    "locate_cmd",
]
