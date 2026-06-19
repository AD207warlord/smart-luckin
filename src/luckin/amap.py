"""高德地理编码客户端:模糊地址 → 精确坐标。

解决瑞幸官方 skill 的 IP 定位缺陷(代理/VPN 环境下 ipinfo.io 失效)。
三场景路由:精确门牌 / 纯地标 / 模糊路段。
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests

from .config import get_amap_key


@dataclass
class Location:
    """地理定位结果"""
    longitude: float
    latitude: float
    formatted_address: str = ""
    district: str = ""  # 行政区(用于跨区检测)
    source: str = ""  # geocode / poi
    is_fuzzy: bool = False  # 是否模糊定位(路段中点,需列候选)


class AmapError(Exception):
    pass


class AmapClient:
    """高德开放平台客户端"""

    GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
    POI_URL = "https://restapi.amap.com/v3/place/text"

    def __init__(self, key: Optional[str] = None):
        self.key = key or get_amap_key()
        if not self.key:
            raise EnvironmentError(
                "未设置 AMAP_API_KEY 环境变量(高德开放平台 key)。\n"
                "免费申请:https://lbs.amap.com/ \n"
                "然后设为环境变量:export AMAP_API_KEY=<key>"
            )

    def geocode(self, address: str, city: str = "") -> Optional[Location]:
        """地理编码:地址 → 坐标。

        适合精确门牌("XX 路 123 号")或模糊路段("XX 路")。
        模糊路段返回的是中点坐标(is_fuzzy=True)。
        """
        params = {"address": address, "key": self.key}
        if city:
            params["city"] = city
        resp = requests.get(self.GEOCODE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            raise AmapError(f"高德 geocode 失败: {data.get('info', data)}")

        geocodes = data.get("geocodes") or []
        if not geocodes:
            return None

        g = geocodes[0]
        loc = g.get("location", "")
        if not loc:
            return None
        lng, lat = loc.split(",")

        # 判断是否模糊(无门牌号 → 可能是路段中点)
        is_fuzzy = not any(c.isdigit() for c in address)

        return Location(
            longitude=float(lng),
            latitude=float(lat),
            formatted_address=g.get("formatted_address", ""),
            district=g.get("district", ""),
            source="geocode",
            is_fuzzy=is_fuzzy,
        )

    def poi_search(self, keyword: str, city: str = "") -> Optional[Location]:
        """POI 搜索:地标名 → 坐标 + 完整地址。

        适合建筑物/大厦/广场名("XX 国际商务中心")。精度比 geocode 更高。
        """
        params = {"keywords": keyword, "key": self.key}
        if city:
            params["city"] = city
        resp = requests.get(self.POI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            raise AmapError(f"高德 POI 失败: {data.get('info', data)}")

        pois = data.get("pois") or []
        if not pois:
            return None

        p = pois[0]
        loc = p.get("location", "")
        if not loc:
            return None
        lng, lat = loc.split(",")

        return Location(
            longitude=float(lng),
            latitude=float(lat),
            formatted_address=f"{p.get('name', '')} - {p.get('address', '')}",
            district=p.get("adname", ""),
            source="poi",
            is_fuzzy=False,
        )

    def locate(self, address: str, city: str = "") -> Location:
        """智能定位:三场景路由。

        自动判断输入特征:
        - 精确门牌(含数字)→ geocode
        - 地标名(含大厦/广场/中心等)→ POI 优先
        - 模糊路段 → geocode(返回中点,is_fuzzy=True,调用方应列候选)

        返回 Location。找不到抛 AmapError。
        """
        address = address.strip()

        # 建筑物关键词 → 优先 POI
        building_keywords = ["大厦", "广场", "中心", "大楼", "商务区", "mall", "Mall", "写字楼", "公寓", "小区"]
        has_building = any(k in address for k in building_keywords)
        has_number = any(c.isdigit() for c in address)

        # 优先级:POI(地标)> geocode(门牌)> geocode(模糊)
        if has_building:
            loc = self.poi_search(address, city)
            if loc:
                return loc
            # POI 没中,fallback geocode
            loc = self.geocode(address, city)
            if loc:
                return loc
        elif has_number:
            # 精确门牌,geocode
            loc = self.geocode(address, city)
            if loc:
                return loc
        else:
            # 模糊路段,geocode 返回中点
            loc = self.geocode(address, city)
            if loc:
                return loc

        raise AmapError(f"高德查不到 '{address}',请提供更具体信息(区+路+号,或附近地标)")
