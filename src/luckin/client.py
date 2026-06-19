"""瑞幸 MCP HTTP 客户端。

封装 JSON-RPC 2.0 over Streamable HTTP 调用,对外暴露 8 个工具的高层方法。
内部固化所有踩坑经验:二次 json.loads、operation=3、链式 skuCode 等。
"""
from __future__ import annotations

import json
from typing import Any, Optional

import requests

from .config import get_token


class LuckinError(Exception):
    """瑞幸 MCP 业务错误(非网络异常)"""

    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")


class LuckinClient:
    """瑞幸 MCP 客户端。

    用法:
        client = LuckinClient()  # 自动从环境变量读 token + endpoint
        shops = client.query_shops(lng, lat)
    """

    def __init__(self, endpoint: str = "https://gwmcp.lkcoffee.com/order/user/mcp", token: Optional[str] = None):
        self.endpoint = endpoint
        self.token = token or get_token()
        self._req_id = 0
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",  # Streamable HTTP 必须,否则 400
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "smart-luckin/0.1",
        })

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _call(self, tool_name: str, arguments: dict, timeout: int = 20) -> Any:
        """调用 MCP 工具(JSON-RPC tools/call)。

        响应的 result.content[0].text 是字符串化的 JSON,需二次解析。
        业务错误(code != 0)抛 LuckinError。
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = self._session.post(self.endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()

        outer = resp.json()
        # MCP 错误响应
        if "error" in outer:
            raise LuckinError(-1, f"JSON-RPC error: {outer['error']}")

        # 提取内嵌 text(JSON 字符串)
        result = outer.get("result", {})
        content = result.get("content", [])
        if not content:
            raise LuckinError(-1, "空响应")

        # MCP isError 标志(result.isError:true 表示工具执行异常)
        # 典型场景:orderId 超出 JS Number.MAX_SAFE_INTEGER(20 位订单号)→ text="Overflow"
        if result.get("isError"):
            err_text = content[0].get("text", "")
            # 针对性提示:Overflow 通常是 orderId 数值溢出(20 位订单号)
            if err_text == "Overflow":
                raise LuckinError(-1,
                    "MCP 网关返回 Overflow(orderId 数值溢出)。\n"
                    "20 位订单号(瑞幸 App/小程序下的单)超过 JS Number.MAX_SAFE_INTEGER,\n"
                    "MCP 网关解析时溢出。MCP 只能查自己创建的 19 位订单。\n"
                    "提示:App/小程序订单号普遍脱敏(如 xxxxxxxxxx675),完整号需从支付凭证/客服获取,\n"
                    "且即使拿到也因溢出查不了。建议用瑞幸 App 查历史订单。")
            raise LuckinError(-1, f"MCP 工具执行错误: {err_text}")

        text = content[0].get("text", "")
        # text 可能不是 JSON(如纯错误信息),防御性解析
        try:
            data = json.loads(text)  # 二次解析
        except json.JSONDecodeError:
            raise LuckinError(-1, f"MCP 返回非 JSON 响应: {text!r}")

        # 业务错误
        if not data.get("success", True):
            raise LuckinError(data.get("code", -1), data.get("msg", "未知错误"))

        return data.get("data")

    # ============ 8 个工具的高层封装 ============

    def query_shops(self, longitude: float, latitude: float, dept_name: str = "") -> list[dict]:
        """查询附近门店。

        注意:deptName 参数有 bug(带名字过滤常搜不到店),默认不带。
        """
        args = {"longitude": longitude, "latitude": latitude}
        # 不传 dept_name 规避 Bug 1(deptName 搜索失效)
        result = self._call("queryShopList", args)
        return result or []

    def search_products(self, dept_id: int, query: str) -> list[dict]:
        """AI 语义搜索商品。

        关键词敏感:"美式咖啡"比"美式"命中率高;"新品"命中新品池。
        部分门店此接口失效(返回空),需 fallback 到 query_product_detail + 已知 productId。
        """
        result = self._call("searchProductForMcp", {"deptId": dept_id, "query": query})
        return result or []

    def query_product_detail(self, dept_id: int, product_id: int) -> dict:
        """查商品详情(完整规格树 = 选择面板)。

        返回 productAttrs[],每个含 attributeName/attributeId/productSubAttrs[]。
        不同商品属性维度不同,不能硬编码 attributeId。
        """
        return self._call("queryProductDetailInfo", {"deptId": dept_id, "productId": product_id}) or {}

    def switch_product(
        self,
        dept_id: int,
        product_id: int,
        sku_code: str,
        attr_id: int,
        sub_attr_id: int,
        amount: int = 1,
    ) -> dict:
        """切换商品规格(链式:返回新 skuCode,下一步用新值)。

        operation 恒为 3(选中),官方 schema 没标枚举,值 3 只在文档文字里写。
        """
        return self._call("switchProduct", {
            "deptId": dept_id,
            "productId": product_id,
            "skuCode": sku_code,
            "amount": amount,
            "attrOperationParam": {
                "attributeId": attr_id,
                "subAttr": {"attributeId": sub_attr_id, "operation": 3},
            },
        }) or {}

    def switch_specs(
        self,
        dept_id: int,
        product_id: int,
        base_sku_code: str,
        specs: dict[str, str],
    ) -> dict:
        """高层:按人类规格(AttributeName→AttributeValue)链式切换。

        specs 例: {"杯型": "超大杯", "温度": "冰"}
        内部自动:query_product_detail 拿属性树 → 按 name 匹配 ID → 链式 switch。
        返回最终的商品对象(含新 skuCode + selected 状态)。
        """
        if not specs:
            # 不需要切换,直接返回基础商品
            return self.query_product_detail(dept_id, product_id)

        detail = self.query_product_detail(dept_id, product_id)
        current_sku = detail.get("skuCode", base_sku_code)
        attrs = detail.get("productAttrs", [])

        # 构建 name→id 映射
        # 注意:不同商品 attributeName 可能不同(加浓美式叫"糖",Hello苹果茉莉叫"糖度")
        for spec_name, spec_value in specs.items():
            # 找匹配的属性维度(模糊匹配 attributeName)
            attr = next(
                (a for a in attrs if spec_name in a.get("attributeName", "")),
                None,
            )
            if not attr:
                continue  # 该商品无此维度,跳过

            # 找匹配的属性值:先精确匹配,再回退到包含匹配
            # ⚠️ 不能只用包含匹配:"含轻咖" in "不含轻咖" 为 True,
            # 会误匹配到默认的"不含轻咖"(selected=True)→ 触发"已选中"跳过 → 切换丢失。
            subs = attr.get("productSubAttrs", [])
            sub = next(
                (s for s in subs if s.get("attributeName", "") == spec_value),
                None,
            )
            if sub is None:
                sub = next(
                    (s for s in subs if spec_value in s.get("attributeName", "")),
                    None,
                )
            if not sub:
                continue  # 无此选项,跳过

            # 已是默认选中就跳过
            if sub.get("selected"):
                continue

            # 链式切换
            result = self.switch_product(
                dept_id, product_id, current_sku,
                attr["attributeId"], sub["attributeId"],
            )
            current_sku = result.get("skuCode", current_sku)
            attrs = result.get("productAttrs", attrs)  # 更新属性树(冰热杯型 ID 会变)

        # 返回最终状态:重新查一次确保 skuCode 一致
        return self.query_product_detail(dept_id, product_id) if current_sku == detail.get("skuCode") else {"skuCode": current_sku, "productAttrs": attrs}

    def preview_order(self, dept_id: int, product_list: list[dict]) -> dict:
        """订单预览(拿价格 + 券码 + 预计取餐时间)。

        product_list: [{"amount": 1, "productId": <id>, "skuCode": "SPxxxx-xxxxx"}]
        返回含 discountPrice(到手价)/ couponCodeList(下单必用)/ aboutTime(取餐时间戳)。
        """
        return self._call("previewOrder", {"deptId": dept_id, "productList": product_list}) or {}

    def create_order(
        self,
        dept_id: int,
        product_list: list[dict],
        longitude: float,
        latitude: float,
        coupon_code_list: Optional[list[str]] = None,
        remark: str = "",
    ) -> dict:
        """创建订单(真实扣款)。

        ⚠️ coupon_code_list 必须用当次 previewOrder 返回的券码,不能缓存/硬编码。
        内部封装了"自动 preview 取券"逻辑的版本见 create_order_safe。
        """
        args = {
            "deptId": dept_id,
            "productList": product_list,
            "longitude": longitude,
            "latitude": latitude,
        }
        if coupon_code_list:
            args["couponCodeList"] = coupon_code_list
        if remark:
            args["remark"] = remark
        return self._call("createOrder", args) or {}

    def create_order_safe(
        self,
        dept_id: int,
        product_list: list[dict],
        longitude: float,
        latitude: float,
        remark: str = "",
    ) -> tuple[dict, dict]:
        """安全创建订单:自动先 previewOrder 取券,再 createOrder。

        返回 (order_result, preview_result)。
        确保 couponCodeList 用的是当次预览返回的(不会因缓存券码多花钱)。
        """
        preview = self.preview_order(dept_id, product_list)
        coupons = preview.get("couponCodeList", [])
        order = self.create_order(
            dept_id, product_list, longitude, latitude,
            coupon_code_list=coupons, remark=remark,
        )
        return order, preview

    def query_order(self, order_id: str) -> dict:
        """查订单详情(状态/取餐码/门店)。

        orderStatus: 20=下单成功, 100=已取消。
        takeMealCodeInfo.code = 取餐码。
        """
        return self._call("queryOrderDetailInfo", {"orderId": order_id}) or {}

    def cancel_order(self, order_id: str) -> bool:
        """取消订单(未支付状态取消最干净,不扣款)。"""
        result = self._call("cancelOrder", {"orderId": order_id})
        return bool(result)
