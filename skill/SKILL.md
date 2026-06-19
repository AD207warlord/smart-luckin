---
name: luckin-coffee
description: |
  通过 luckin-cli 命令行工具下单瑞幸咖啡。当用户想点瑞幸、买咖啡、点单,提到"luckin""瑞幸""来杯咖啡""续命""日常那杯"等,或想查询门店/订单/菜单时触发。CLI 内部封装了瑞幸 MCP 的全部踩坑经验(operation=3、链式 skuCode、payOrderUrl 二维码、中文编码、高德定位等),Agent 只需调 smart-luckin 命令,无需裸调 MCP 重新踩坑。已配置用户家门店与日常口味,支持一键复刻日常订单。
---

# Luckin Coffee — 瑞幸点单(通过 luckin-cli)

通过 `smart-luckin` 命令行工具完成瑞幸点单。CLI 封装了瑞幸 MCP 的全部踩坑经验,Agent 调命令即可,不必裸调 MCP。

## 前置检查

```bash
# 确认 CLI 可用 + token 配置
smart-luckin config show
# 期望:LUCKIN_MCP_ORDER_TOKEN ✅,家门店/日常口味已配置
```

如果 token 显示 ❌ 或门店未配置,提示用户运行 `smart-luckin config init`。

## 用户存档(配置在 profile.json)

- **家门店**:见 `smart-luckin config show` 输出(deptId / 坐标 / 营业时间)
- **日常口味**:见 `smart-luckin config show`(productId / skuCode / 规格)

改门店/口味:直接编辑 `~/.luckin/profile.json`,或 `smart-luckin config set <key> <value>`。

## 日常下单(最高频)

用户说"来杯咖啡""日常那杯""续命":

```bash
smart-luckin order daily
# → 查营业 → 显示价格 → 用户确认 → 下单 → 终端二维码 → 扫码支付
```

⚠️ `order daily` / `order create` 会**真实扣款**。下单前 CLI 会显示价格并要求确认(`-y` 跳过)。支付后返回取餐码。

## 其他常用命令

```bash
# 查门店(家门店周边 或 模糊地址)
smart-luckin shops status                    # 家门店营业状态
smart-luckin locate <模糊地址>               # 高德定位 → 最近门店(如 "新华路664号")

# 查菜单
smart-luckin menu search <关键词>            # 搜商品(如 "生椰拿铁")
smart-luckin menu new                        # 看新品
smart-luckin menu discover                   # 枚举菜单(四维度分类词)

# 商品 + 规格切换
smart-luckin product detail <productId>      # 商品详情 + 规格树
smart-luckin product switch <productId> --size 超大杯 --temp 冰  # 切规格(自动链式)

# 订单
smart-luckin order preview [--product ID --sku CODE]  # 预览价格(不扣款)
smart-luckin order create [--product ID --sku CODE] [-y]  # 下单(扣款+二维码)
smart-luckin order status <orderId>          # 查订单/取餐码
smart-luckin order cancel <orderId>          # 取消
```

## 为什么用 CLI 而非裸调 MCP

裸调瑞幸 MCP 每次都要踩坑:
- `switchProduct` 的 `operation` 是几?(答:3,schema 没标)
- `skuCode` 怎么更新?(答:链式,每步用上一步返回的新值)
- 二维码用 `payOrderUrl` 还是 `payOrderQrCodeUrl`?(答:前者,后者扫码失效)
- 中文 query 为啥搜不到?(答:Windows git-bash 编码坑)
- 用户给模糊地址怎么定位?(答:高德 geocode/POI,不是 IP 定位)

CLI 内部全部封装,Agent 调一条命令即可。

## 排错

| 症状 | 原因 | 解法 |
|------|------|------|
| token ❌ | 环境变量未设/未继承 | 设 `LUCKIN_MCP_ORDER_TOKEN`,重启 Agent |
| `locate` 报无 key | AMAP_API_KEY 未配 | 申请高德 key 并设环境变量 |
| 家门店未配置 | profile.json 未生成 | `smart-luckin config init` |
| 商品搜不到 | 门店搜索服务波动 | CLI 自动 fallback 多店;或换 `menu discover` |
| 二维码扫不出 | 用了 payOrderQrCodeUrl | CLI 已用 payOrderUrl,不会出此问题 |

## 安全

- token 绑定账号能扣款,**绝不外发、不写进 git 跟踪文件**
- `profile.json` 已被 .gitignore 排除
- `order create` 扣款前必须用户确认
