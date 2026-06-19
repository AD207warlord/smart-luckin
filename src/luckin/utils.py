"""工具函数:二维码生成、价格格式化、输出辅助、时间校验。"""
from __future__ import annotations

import datetime
import urllib.parse


# 外送意图关键词
# 根本原因:瑞幸 MCP 后端(createOrder 等 8 工具)协议层就没有 delivery/收货地址/配送字段,
# 是到店自提专用 API。用户表达配送/外送/外卖/送到/送达等意图时物理上无法满足,需拒绝。
# (官方 my-coffee skill v0.8.2 也有外送拒绝约束,但其文档写 delivery="pick" 有误导——
#  实际 MCP schema 根本没 delivery 字段,2026-06-19 查 tools/list 确认)
DELIVERY_KEYWORDS = [
    "配送", "外送", "外卖", "送到", "送达", "送货", "邮寄", "快递",
    "送过来", "送上门", "同城送", "跑腿",
]


def detect_delivery_intent(text: str) -> bool:
    """检测文本是否含外送意图。

    用于 order create/daily 的 --locate / --remark 参数校验。
    瑞幸 MCP 协议层(createOrder schema)无 delivery/收货地址字段,只支持到店自取,
    外送意图物理上无法实现,应拒绝并提示自提。
    """
    if not text:
        return False
    return any(kw in text for kw in DELIVERY_KEYWORDS)


def format_price(price: float | int | None) -> str:
    """格式化价格:9.9 → '¥9.9'"""
    if price is None:
        return "¥-"
    return f"¥{price}"


def generate_qr_url(pay_url: str, size: int = 300) -> str:
    """生成支付二维码图片 URL。

    用 payOrderUrl(deeplink,如 weixin://wxpay/bizpayurl?pr=xxx),
    NOT payOrderQrCodeUrl(中转页,实测扫码报"非法链接")。

    套 api.qrserver.com 生成 PNG,手机微信扫码一步进支付。
    """
    encoded = urllib.parse.quote(pay_url, safe="")
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}"


def generate_qr_markdown(pay_url: str, size: int = 300) -> str:
    """生成 Markdown 图片语法(在支持 MD 预览的终端/IDE 直接显示二维码)。"""
    return f"![支付二维码]({generate_qr_url(pay_url, size)})"


def format_store(store: dict, index: int | None = None) -> str:
    """格式化门店信息为可读字符串。"""
    prefix = f"{index}. " if index else ""
    name = store.get("deptName", "")
    number = store.get("number", "")
    addr = store.get("address", "")
    dist = store.get("distance", 0)
    status = store.get("workStatus", "")
    ws = store.get("workTimeStart", "")
    we = store.get("workTimeEnd", "")
    return (
        f"{prefix}{name} ({number})\n"
        f"   {addr}\n"
        f"   距离 {dist}km | 营业 {ws}-{we} | {status}"
    )


def format_product(p: dict, index: int | None = None) -> str:
    """格式化商品信息为可读字符串。"""
    prefix = f"{index}. " if index else ""
    pid = p.get("productId", "")
    name = p.get("productName", "")
    price = p.get("estimatePrice")
    init = p.get("initialPrice")
    price_str = format_price(price) if price else ""
    init_str = f"(原{format_price(init)})" if init and init != price else ""
    return f"{prefix}{pid} | {name} | {price_str}{init_str}"


def format_order_status(order: dict) -> str:
    """格式化订单状态为可读字符串。"""
    status_code = order.get("orderStatus")
    status_name = order.get("orderStatusName", "")
    shop = order.get("shopInfo", {})
    take_meal = order.get("takeMealCodeInfo", {}) or {}
    code = take_meal.get("code", "")
    pay_amount = order.get("orderPayAmount", 0)

    lines = [f"状态: {status_name} (code={status_code})"]
    if shop:
        lines.append(f"门店: {shop.get('deptName', '')} ({shop.get('number', '')})")
    if code:
        lines.append(f"🎯 取餐码: {code}")
    if pay_amount:
        lines.append(f"实付: {format_price(pay_amount)}")
    return "\n".join(lines)


# 门店搜索服务波动时的 fallback 门店(已知可用,商品全国通用)
FALLBACK_SEARCH_DEPTS = [16401, 380664, 390280]  # 占位 deptId(实际使用时用你账号能查到的门店)


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    """'07:00' → (7, 0);非法 → None。"""
    if not s or ":" not in s:
        return None
    try:
        h, m = s.split(":", 1)
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, TypeError):
        pass
    return None


def check_order_time(
    work_start: str,
    work_end: str,
    now: datetime.datetime,
    lead_minutes: int = 10,
) -> tuple[str, str]:
    """下单前时间校验:营业时间内 + 距关门时间是否充足。

    参数:
        work_start: 营业开始 "HH:MM"(来自 queryShopList 的 workTimeStart)
        work_end: 营业结束 "HH:MM"(workTimeEnd)
        now: 当前时间
        lead_minutes: 制作提前量(分钟),距关门不足此值则建议不下单

    返回 (level, message):
        level ∈ {"ok", "warn", "danger", "closed"}
        - ok: 营业中,距关门 >30min
        - warn: 营业中,距关门 10~30min(或 lead~30 区间)
        - danger: 营业中,距关门 <10min 或不足 lead_minutes(来不及取餐)
        - closed: 未营业/已打烊/营业时间无法解析

    message: 人类可读提示(含剩余分钟数)。
    """
    start = _parse_hhmm(work_start)
    end = _parse_hhmm(work_end)
    if not start or not end:
        return "closed", "营业时间无法解析,不下单(保守)"

    # 当前时间的分钟数(0-1439)
    now_min = now.hour * 60 + now.minute
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]

    # 计算距关门的剩余分钟(支持跨午营业,如 18:00-02:00)
    if end_min > start_min:
        # 正常营业(如 07:00-17:00)
        if now_min < start_min:
            return "closed", f"未营业(营业时间 {work_start}-{work_end})"
        if now_min >= end_min:
            return "closed", f"已打烊(营业时间 {work_start}-{work_end})"
        remaining = end_min - now_min
        in_hours = True
    else:
        # 跨午营业(如 18:00-02:00)
        if start_min <= now_min:
            # 当天营业中(如 18:00-23:59)
            remaining = (end_min + 24 * 60) - now_min
            in_hours = True
        elif now_min <= end_min:
            # 跨到次日凌晨(如 00:01-02:00)
            remaining = end_min - now_min
            in_hours = True
        else:
            # 非营业时段(如 10:00 查 18:00-02:00 的店)
            return "closed", f"未营业(营业时间 {work_start}-{work_end})"

    # 营业中,按剩余时间分级
    # 边界规则:
    #   remaining <= lead_minutes → danger(不足或刚好等于提前量,没余量)
    #   lead_minutes < remaining < 10 → danger(<10min 根本来不及)
    #     (注:默认 lead=10 时这俩合并成 remaining <= 10 → danger)
    #   10 <= remaining <= 30 → warn(快关门)
    #   remaining > 30 → ok
    if remaining <= lead_minutes or remaining < 10:
        return "danger", f"距关门仅 {remaining} 分钟,不足制作提前量({lead_minutes}min),可能来不及取餐"
    if remaining <= 30:
        return "warn", f"营业中,距关门 {remaining} 分钟,快关门了建议尽快下单"
    return "ok", f"营业中,距关门 {remaining} 分钟"

