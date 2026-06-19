"""switch_specs 规格切换的单元测试。

聚焦 bug:子串包含匹配导致 "含轻咖" 误配到 "不含轻咖"。

复现场景(来自商品 5361 轻咖柠檬茶的真实属性树):
- 维度"咖啡液" attrId=105,两个 subAttr:
    - "不含轻咖" subId=643, selected=True (默认)
    - "含轻咖"   subId=644, selected=False
- 用户 spec: {"咖啡液": "含轻咖"}

期望:匹配到 "含轻咖"(subId=644),调用 switch_product,得到新 sku。
bug 行为: "含轻咖" in "不含轻咖" → True,误匹配到 "不含轻咖",
          因其 selected=True → 跳过切换,sku 不变。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from luckin.client import LuckinClient  # noqa: E402


# 构造商品 5361 的属性树(精简,只留相关维度)
def _lemon_tea_attrs():
    return [
        {
            "attributeName": "杯型", "attributeId": 64,
            "productSubAttrs": [{"attributeName": "超大杯", "attributeId": 592, "selected": True}],
        },
        {
            "attributeName": "温度", "attributeId": 17,
            "productSubAttrs": [
                {"attributeName": "冰", "attributeId": 57, "selected": True},
                {"attributeName": "少冰", "attributeId": 73, "selected": False},
            ],
        },
        {
            "attributeName": "糖度", "attributeId": 18,
            "productSubAttrs": [
                {"attributeName": "标准甜", "attributeId": 60, "selected": True},
                {"attributeName": "少甜", "attributeId": 112, "selected": False},
            ],
        },
        {
            "attributeName": "咖啡液", "attributeId": 105,
            "productSubAttrs": [
                {"attributeName": "不含轻咖", "attributeId": 643, "selected": True},
                {"attributeName": "含轻咖", "attributeId": 644, "selected": False},
            ],
        },
    ]


def _make_client(base_sku="SP3781-00035"):
    """构造一个 mock client,query_product_detail 返回带属性树的商品;
    switch_product 记录调用并返回"已切换"状态。"""
    client = MagicMock(spec=LuckinClient)

    def _detail(dept_id, product_id):
        return {
            "skuCode": base_sku,
            "productAttrs": _lemon_tea_attrs(),
        }
    client.query_product_detail.side_effect = _detail

    # switch_product:把命中的 subAttr 标记为 selected,返回新 sku + 新属性树
    call_log = []

    def _switch(dept_id, product_id, sku_code, attr_id, sub_attr_id, amount=1):
        call_log.append((sku_code, attr_id, sub_attr_id))
        # 返回一个新 sku,表示切换成功
        return {
            "skuCode": f"{sku_code}-SWITCHED-{sub_attr_id}",
            "productAttrs": _lemon_tea_attrs(),  # 简化:不细究中间树
        }
    client.switch_product.side_effect = _switch
    client._call_log = call_log
    return client


def test_switch_specs_should_match_exact_attr_value_not_substring():
    """含轻咖 不应被误匹配到 不含轻咖(子串包含陷阱)。

    spec={"咖啡液": "含轻咖"} 应触发 switch_product(attrId=105, subId=644)。
    bug 下:误匹配到"不含轻咖"(subId=643, selected=True) → 跳过 → 不调用 switch_product。
    """
    client = _make_client()
    # 直接调 switch_specs(LuckinClient.switch_specs 是未绑定的实例方法,client 是 mock)
    # 这里要调真正的 switch_specs 逻辑,所以用 unbound 方式
    result = LuckinClient.switch_specs(
        client, dept_id=326010, product_id=5361,
        base_sku_code="SP3781-00035", specs={"咖啡液": "含轻咖"},
    )

    # 必须调用了 switch_product,且 sub_attr_id 是 644(含轻咖),不是 643(不含轻咖)
    assert len(client._call_log) == 1, (
        f"应调用 switch_product 一次,实际 {len(client._call_log)} 次。"
        f"call_log={client._call_log}"
    )
    _sku, _attr, sub_attr_id = client._call_log[0]
    assert sub_attr_id == 644, (
        f"应切到含轻咖(subId=644),实际切了 subId={sub_attr_id}。"
        f"这通常意味着子串匹配把'含轻咖'误配到了'不含轻咖'。"
    )
    # 最终 sku 必须变化(原 bug 下 sku 不变)
    assert result.get("skuCode") != "SP3781-00035", "最终 sku 必须变化,原 bug 下 sku 不变"


def test_switch_specs_combined_coffee_and_sugar():
    """组合规格:含轻咖 + 少甜。两个维度都应被切换。

    bug 下:含轻咖 被跳过(误判已选中),只有糖度切了,sku 错误。
    """
    client = _make_client()
    LuckinClient.switch_specs(
        client, dept_id=326010, product_id=5361,
        base_sku_code="SP3781-00035",
        specs={"咖啡液": "含轻咖", "糖度": "少甜"},
    )

    # 应调用 switch_product 两次:一次切咖啡液(644),一次切糖度(112)
    assert len(client._call_log) == 2, (
        f"应调用 switch_product 两次(咖啡液+糖度),实际 {len(client._call_log)} 次。"
        f"call_log={client._call_log}"
    )
    sub_ids = sorted(sub_id for _sku, _attr, sub_id in client._call_log)
    assert sub_ids == [112, 644], (
        f"应切到 644(含轻咖)+112(少甜),实际切了 {sub_ids}"
    )


# ============================================================
# 全量子串陷阱覆盖(参数化)
# ============================================================
# bug 模式:spec_value 是某 subAttr 名的子串,而该长词排在前面或也是候选,
# 子串包含匹配 `spec_value in name` 会误命中长词。
# 这些 case 在真实菜单属性树里出现过(见 _attr_dump.json 扫描结果)。
# 参数:(维度, 属性树 subAttr 顺序列表[(name, subId, selected)], spec_value, 期望命中的 subId)
# 每条都构造一个独立的 mock 商品验证 switch_specs 命中正确。

TRAP_CASES = [
    # 真实触发 case:咖啡液(来自 4837 鲜萃轻轻茉莉、5361 轻咖柠檬茶)
    # "含轻咖" 是 "不含轻咖" 子串,后者在前且 selected=True
    pytest.param(
        "咖啡液",
        [("不含轻咖", 643, True), ("含轻咖", 644, False)],
        "含轻咖", 644,
        id="咖啡液_含轻咖_被不含轻咖吞",
    ),
    # 防回归:小料维度如果属性树顺序是 [不含西柚粒, 西柚粒]
    # spec="西柚粒" 应命中西柚粒,不应被前面的"不含西柚粒"吞
    pytest.param(
        "小料",
        [("不含西柚粒", 714, True), ("西柚粒", 713, False)],
        "西柚粒", 713,
        id="小料_西柚粒_反向顺序防回归",
    ),
    # 防回归:气泡维度如果 [无气泡, 气泡],spec="气泡" 应命中气泡
    pytest.param(
        "气泡",
        [("无气泡", 700, True), ("气泡", 699, False)],
        "气泡", 699,
        id="气泡_气泡_被无气泡吞(反向顺序)",
    ),
    # 防回归:酒精维度 [不含酒精, 含酒精],spec="含酒精" 应命中含酒精
    pytest.param(
        "酒精",
        [("不含酒精", 800, True), ("含酒精", 801, False)],
        "含酒精", 801,
        id="酒精_含酒精_被不含酒精吞",
    ),
    # 防回归:晶球 [不含晶球, 含晶球],spec="含晶球" 应命中含晶球
    pytest.param(
        "小料",
        [("不含晶球", 710, True), ("含晶球", 711, False)],
        "含晶球", 711,
        id="小料_含晶球_被不含晶球吞",
    ),
    # 杯型陷阱:大杯 是 超大杯/特大杯 子串。
    # 真实数据里 大杯 通常在前,这里构造反向顺序验证不会误命中
    pytest.param(
        "杯型",
        [("超大杯", 594, True), ("大杯", 365, False)],
        "大杯", 365,
        id="杯型_大杯_被超大杯吞(反向顺序)",
    ),
    # 糖度陷阱:少甜 是 少少甜 子串。真实数据少甜在前,构造反向验证
    pytest.param(
        "糖度",
        [("少少甜", 59, True), ("少甜", 112, False)],
        "少甜", 112,
        id="糖度_少甜_被少少甜吞(反向顺序)",
    ),
]


@pytest.mark.parametrize("dim, sub_attrs, spec_value, expected_sub_id", TRAP_CASES)
def test_substring_trap_all_dimensions(dim, sub_attrs, spec_value, expected_sub_id):
    """参数化:覆盖所有子串陷阱维度。

    每个 case 构造一个属性树,其中"长词(含子串)"排在前面且 selected=True,
    spec 给"短词(被子串包含)"。期望 switch_specs 命中短词(expected_sub_id),
    而非被前面的长词误吞。

    bug 下:子串包含 `spec_value in name` 会命中长词 → 因 selected=True → 跳过 → 不切换。
    """
    client = MagicMock(spec=LuckinClient)

    def _detail(dept_id, product_id):
        return {
            "skuCode": "BASE-SKU",
            "productAttrs": [{
                "attributeName": dim, "attributeId": 1000,
                "productSubAttrs": [
                    {"attributeName": name, "attributeId": sid, "selected": sel}
                    for name, sid, sel in sub_attrs
                ],
            }],
        }
    client.query_product_detail.side_effect = _detail

    call_log = []

    def _switch(dept_id, product_id, sku_code, attr_id, sub_attr_id, amount=1):
        call_log.append(sub_attr_id)
        return {"skuCode": f"NEW-{sub_attr_id}", "productAttrs": _detail(dept_id, product_id)["productAttrs"]}
    client.switch_product.side_effect = _switch

    LuckinClient.switch_specs(
        client, dept_id=326010, product_id=9999,
        base_sku_code="BASE-SKU", specs={dim: spec_value},
    )

    assert len(call_log) == 1, (
        f"[{dim}] 应调用 switch_product 一次,实际 {len(call_log)} 次。"
        f"spec={spec_value!r}, call_log={call_log}"
    )
    assert call_log[0] == expected_sub_id, (
        f"[{dim}] spec={spec_value!r} 应命中 subId={expected_sub_id},"
        f"实际命中 subId={call_log[0]}。"
        f"这通常是子串包含匹配把短词误配到了长词(含子串)。"
    )
