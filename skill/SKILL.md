---
name: luckin-coffee
description: |
  通过 smart-luckin 命令行工具下单瑞幸咖啡。当用户想点瑞幸、买咖啡、点单,提到"luckin""瑞幸""来杯咖啡""续命""日常那杯"等,或想查询门店/订单/菜单时触发。smart-luckin 是 Agent 和瑞幸 MCP 之间的转译层:把 Agent 的宽泛意图(口语/感官词/地名)转译成瑞幸硬接口能收的精确参数(deptId/productId/skuCode/经纬度)。Agent 负责语义理解,smart-luckin 负责转译执行。
---

# Luckin Coffee — 瑞幸点单(通过 smart-luckin 转译层)

## 这个 skill 的定位

smart-luckin **不是替代 Agent 的语义理解**,是 **Agent 和瑞幸 MCP 之间的转译层**:

```
Agent 的意图              smart-luckin 转译         瑞幸 MCP 硬接口
"清爽果味"        →     menu search 果茶      →   searchProductForMcp
"少糖"            →     --spec 糖度=少甜       →   switchProduct(operation=3)
"续命的"          →     order daily(profile)  →   createOrder
"XX 广场"         →     locate → 坐标          →   queryShopList(lng, lat)
```

**Agent 负责理解用户意图,smart-luckin 负责把意图转译成瑞幸能收的参数**。你(ZCode/Claude 等 Agent)不需要查 operation 枚举、链式切 skuCode、背 attributeId、找经纬度——这些转译在 CLI 内部固化了。

## 前置检查

```bash
# 确认 CLI 可用 + token 配置
smart-luckin config show
# 期望:LUCKIN_MCP_ORDER_TOKEN ✅,家门店/日常口味已配置
```

token 缺失或门店未配置时,提示用户运行 `smart-luckin config init`(需先用瑞幸官方 `luckin login` 拿 token)。

## 日常下单(最高频)

用户说"来杯咖啡""日常那杯""续命"——这类靠 profile 日常口味,直接:

```bash
smart-luckin order daily
# → 时间校验 → 预览价格 → 确认 → 下单 → UI 直接显示二维码 → 扫码支付
```

⚠️ `order daily` / `order create` 会**真实扣款**。CLI 内置时间校验(关门/快关门会拦截或二次确认),`-y` 只跳价格确认不跳时间风险确认。支付二维码用 `payOrderUrl` 渲染成 Markdown 图片,在 Agent UI 直接可扫。

## 品类/规格转译(Agent 理解 + CLI 转译)

用户说宽泛表达时,Agent 负责理解,CLI 负责转译:

| 用户说的 | Agent 理解 | 调用命令(转译) |
|---|---|---|
| "清爽果味""酸甜" | → 果茶/柠檬茶类 | `smart-luckin menu search 果茶` |
| "看新品" | → 新品池 | `smart-luckin menu new` |
| "少糖""微糖""低糖" | → 糖度调整 | `smart-luckin product switch <id> --spec "少糖"` |
| "大杯冰燕麦" | → 多维规格 | `smart-luckin product switch <id> --spec "大杯,冰,燕麦奶"` |
| "XX 商场/地标" | → 地名 | `smart-luckin locate "XX 商场"`(高德→坐标→门店) |

`--spec` 支持 15 类属性词 + 口语别名(少糖/微糖/低糖/半糖/无糖/全糖 等),自动归一到瑞幸维度。

## 其他常用命令

```bash
# 门店(家门店状态 或 模糊地址定位)
smart-luckin shops status                    # 家门店营业状态 + 时间校验
smart-luckin locate <模糊地址>               # 高德定位 → 最近门店

# 菜单
smart-luckin menu search <关键词>            # 搜商品
smart-luckin menu discover                   # 四维度枚举菜单

# 订单
smart-luckin order preview [--product ID --sku CODE]  # 预览(不扣款)
smart-luckin order create [--product ID --sku CODE] [-y]  # 下单
smart-luckin order status <orderId>          # 查订单/取餐码
smart-luckin order cancel <orderId>          # 取消
```

## 为什么用转译层而非裸调 MCP

裸调瑞幸 MCP 每次 Agent 都要踩坑:
- `switchProduct` 的 `operation` 是几?(答:3,schema 没标)
- `skuCode` 怎么更新?(答:链式,每步用上一步新值)
- 二维码用哪个字段?(答:`payOrderUrl`,`payOrderQrCodeUrl` 实测失效)
- 中文 query 为啥搜不到?(答:Windows 编码坑)
- 用户给模糊地址怎么定位?(答:高德 geocode/POI,不是 IP 定位)

转译层把这些固化进 CLI,Agent 调一条命令即可,不用每次重新踩。

## 排错

| 症状 | 原因 | 解法 |
|------|------|------|
| token ❌ | 环境变量未设/未继承 | 先 `luckin login`(官方 CLI),再设 `LUCKIN_MCP_ORDER_TOKEN` |
| `locate` 报无 key | AMAP_API_KEY 未配 | 申请高德 key(免费)并设环境变量 |
| 家门店未配置 | profile.json 未生成 | `smart-luckin config init` |
| 下单被拒"未营业" | 时间校验 closed/danger | 换营业中的店,或 `-y` 强制(danger 场景会二次确认) |
| 二维码扫不出 | 用了 payOrderQrCodeUrl | CLI 已用 payOrderUrl,不会出此问题 |

## 安全

- token 绑定账号能扣款,**绝不外发、不写进 git 跟踪文件**
- `profile.json` 已被 .gitignore 排除
- `order create` 扣款前必须用户确认(`-y` 跳价格确认,但 warn/danger 场景仍会二次确认时间风险)
