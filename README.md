# luckin-cli

> ☕ 瑞幸咖啡点单 CLI — 封装瑞幸 MCP 的踩坑经验,装完即用的命令行点单工具。
>
> 把"调瑞幸 MCP 需要知道 operation=3、链式 skuCode、二维码用 payOrderUrl、中文编码坑、高德定位..."这些隐性知识,全部固化成 CLI 内部逻辑。对外只暴露人类友好的命令。

> **📦 包名 `luckin-cli`,命令名 `smart-luckin`**。
> 命令名刻意避开瑞幸官方 CLI(`luckin`,用于 `luckin login` 刷 token)的冲突。`pip install luckin-cli` 后用 `smart-luckin` 调用。

---

## 这是什么

一个独立的 Python CLI,通过瑞幸官方 MCP Server(`gwmcp.lkcoffee.com`)完成点单全流程:定位门店 → 查菜单 → 选规格 → 预览价格 → 下单 → 支付二维码 → 查订单/取消。

**核心价值**:瑞幸 MCP 的 8 个工具裸调时,有大量隐性坑(operation 枚举没标、skuCode 要链式更新、二维码字段用错就失效、Windows 中文编码导致搜不到商品...)。这个 CLI 把踩坑经验全部封装掉,装完直接用。

## 设计哲学:把 LLM 运行时编排,前置固化为代码

瑞幸 MCP 提供了 8 个原子工具(queryShopList / searchProductForMcp / switchProduct / ...),但要完成一次点单,需要把这 8 个工具**编排**起来:定位 → 查店 → 搜商品 → 切规格 → 预览 → 下单 → 取券 → 二维码。这个编排层,有两条路:

| 路径 | 编排者 | 代价 | 特点 |
|---|---|---|---|
| **官方 `-p` / my-coffee skill** | LLM 运行时实时编排 | 每单烧 LLM token(实测 ~7 万 token/单) | 灵活(能理解"来杯续命的"),但黑盒、不稳、贵 |
| **本 CLI** | 代码预编译编排 | 开发时设计成本(已沉没)+ Agent 理解 skill 的少量 token | 稳定、透明、可预测,但不灵活(要明确说商品) |

**这不是"零 token",是"把运行时编排成本前置固化"**:
- 开发阶段:设计这套封装所花的 token(包括和 AI 协作设计 locate/menu/order 逻辑)是**沉没成本**,摊到每次使用才划算
- 运行阶段:代码执行本身**不烧 LLM token**(纯 Python 逻辑),但 Agent 要理解"何时调 smart-luckin、调哪个子命令",这部分理解 token 仍需支付
- 我们省下的是:**每次下单时,LLM 实时推理如何编排工具的那笔大开销**(7 万 token → 接近 0)

**权衡诚实说**:我们牺牲了灵活性(遇到"给我来杯续命的"这种模糊表达,代码不会变通,得用户明确说商品名),换来稳定性与可预测性。瑞幸加新品/改 API 时,我们要改代码跟进;官方靠 LLM 读新 schema 自动适应。对于"日常那杯"这种高频固定场景,稳定性 > 灵活性。

## 裸测试基准:同一任务三种路径对比

任务:"我在上海大光明电影院,想喝冰的茶饮,给我至少 3 个商品选项"(2026-06-19 实测)

| 维度 | 纯 MCP 裸调 | 官方 CLI + GLM(`-p`) | 本 CLI (smart-luckin) |
|---|---|---|---|
| **能完成?** | ❌ 缺 7 个编排能力 | ✅ | ✅ |
| **LLM token** | 全人工编排 | 运行时烧(实测输出 72 万字符,推理流刷屏) | 开发时已沉没,运行时接近 0 |
| **耗时** | 看人工 | ~2 分钟 | <5 秒 |
| **结果质量** | — | 3 选项(其中 2 个是同款不同杯型,凑数) | 4 选项(橙C冰茶/轻轻茉莉/柠檬茶/杨枝甘露,不同风格) |
| **可控性** | 全手动 | 黑盒(GLM 内部怎么调工具看不到全貌) | 透明(每步命令可见) |
| **模糊表达** | ❌ | ✅ GLM 能理解"来杯续命的" | ❌ 要明确说商品 |

**官方 GLM 路线的真实优势**:它理解模糊表达("我困了来杯续命的"→ 加浓美式),这是我们代码做不到的。如果你的场景高度依赖自然语言模糊理解,官方 `-p` + LLM 更合适。如果你的场景是高频固定的(每天同一杯、同一店),本 CLI 更划算。

> 本次裸测试用智谱 GLM Coding Plan(`open.bigmodel.cn/api/coding/paas/v4`),未被白名单拦截(与 Kimi Coding Plan 不同,智谱不限客户端)。这给"官方 CLI + LLM"路线打开了可用入口。

## 与官方 my-coffee skill 的关系

瑞幸官方提供三种接入方式:**MCP Server**(数据源,8 个 JSON-RPC 工具)、**CLI**(`luckin login` 刷 token)、**my-coffee skill**(对话式指令 skill,v0.8.2,CC BY-ND 4.0)。

本 CLI 与官方 my-coffee skill 是**两种不同形态的同类产品**,都基于瑞幸 MCP,能力重叠约 70%,各有侧重:

| 维度 | 官方 my-coffee skill v0.8.2 | 本 CLI (smart-luckin) |
|------|------------------------------|------------------------|
| **形态** | 对话式 instruction skill(给 Agent 读的提示词) | 命令行程序(给人和 Agent 调) |
| **定位** | 追问用户地址,或 `ipinfo.io` IP 粗定位 | 高德地理编码/POI(精度 <50m) |
| **规格切换** | 提示 Agent 查文档确定 operation | 内置 `operation:3` + 链式自动滚动 |
| **菜单发现** | 按需搜 | 四维度分类词枚举(~60-70% 覆盖) |
| **外送下单** | ❌ 拒绝(skill 决策,非 API 限制) | ⚠️ 命令框架在,暂不支持(机制待确证,见下文) |
| **token 安全** | 三级优先级(env>对话>本地文件)+ chmod 600 | 三级优先级(env>`~/.luckin/.env`>报错) |
| **商品属性** | 15 类属性词表(意图识别) | 15 类词表 + 别名归一(`--spec "少冰,无糖"`) |
| **代理/VPN** | IP 定位失效 | 不依赖 IP |

### 外送能力:有命令,暂不支持

**先澄清一个常见误解**:瑞幸 MCP **API 层面是支持外送的**——
- `queryOrderDetailInfo` 响应含 `dispatchInfo`(配送员姓名/手机号/预计送达/配送距离),自提单此字段为空,印证为外送设计
- `previewOrder` 响应含 `expressExpectTime`(配送预计送达时间)
- 第三方实测(新榜 2026-06-15):"Agent 点和瑞幸小程序下单,外送和自提价都是一致的"

> 官方 my-coffee skill v0.8.2 写"不支持 sent 外送",但这是 **skill 的产品决策**(降低对话式 Agent 下错单风险),**不是 API 限制**。而且 skill 里 `delivery="pick"` 的写法本身有误——`tools/list` 真实 schema 里 createOrder 根本没有 delivery 字段。**skill 拒绝 ≠ API 不支持。**

**本 CLI 的现状:命令框架在,外送未实现**:

| 能力 | 状态 | 说明 |
|---|---|---|
| 自提下单(`order create/daily`) | ✅ 已支持 | 主力场景,完整链路验证 |
| 外送下单 | ⚠️ **暂不支持** | `order create --locate "送到xxx"` 会被外送意图检测拦截 |

外送下单暂不开放的原因:
1. `createOrder` 入参只有 `longitude/latitude` + `deptId`,**没有收货地址字段**——如何触发外送的机制(createOrder 的经纬度是门店坐标还是送达坐标?)未在本 CLI 中确证
2. 机制不明时,拦截比误下外送单(可能送错地址/算错配送费)更安全
3. 自提是 CLI 的核心场景(日常那杯),外送不是高频需求

如你**现在就要外送**,建议用瑞幸 App/小程序。本 CLI 的外送支持待 createOrder 触发机制确证后开放——届时只需移除外送拦截 + 验证收货坐标传参。

### 已知限制:只能查询本 CLI 创建的订单

`order status` 只能查 **MCP/CLI 创建的订单**,查不了瑞幸 App/小程序下的订单。两层原因:

1. **订单号位数差异 + 数值溢出**:MCP 创建的订单号是 19 位(如 `7652xxxxxxxxxxxxxxx`),瑞幸 App/小程序的订单号是 20 位(如 `1011xxxxxxxxxxxxxx`)。20 位超过 JavaScript `Number.MAX_SAFE_INTEGER`(2^53-1,约 16 位有效),瑞幸 MCP 网关(JS 实现)解析时溢出,返回 `Overflow`。这是瑞幸 MCP 的系统性限制。

2. **App/小程序普遍脱敏订单号**:瑞幸出于隐私保护,在 App/小程序的用户侧界面把订单号脱敏(典型如 `xxxxxxxxxx675`,只露末尾 3 位)。普通使用流程下用户**拿不到完整 20 位订单号**,只能从微信支付/支付宝账单的"商户单号"或联系客服获取。

**实际影响**:正常流程是 `smart-luckin order create` 下单时拿到 19 位 orderId → 用它查 status,这条链路完全可用。只有"用 CLI 查 App/小程序历史订单"这个场景走不通——这不是高频需求,如需查历史订单建议直接用瑞幸 App。

> 20 位订单号的 Overflow 是瑞幸 MCP 网关的 bug(应该用字符串解析 orderId 而非 Number)。本 CLI 对此给出清晰错误提示,不会崩溃。

### ⚠️ 与官方文档的一处差异:支付二维码

官方 my-coffee skill v0.8.2(SKILL.md 第 112/187/190 行)**三次强调只能用 `payOrderQrCodeUrl`,禁止 `payOrderUrl`**。

本 CLI 做了相反选择:**只用 `payOrderUrl` deeplink**。基于 2026-06-19 实测:
- `payOrderUrl`(deeplink `weixin://wxpay/bizpayurl?pr=xxx`)→ 微信扫码**一步进支付页** ✅
- `payOrderQrCodeUrl`(瑞幸中转页)→ 扫码报**"非法链接"** ❌

原因未确认(可能官方文档过时、或瑞幸后端调整、或测试环境差异)。**如果你用本 CLI 扫码失败,请提 issue 反馈**,便于复核这个判断。

### 法律说明

- 本 CLI **独立实现**,不包含官方 my-coffee skill(CC BY-ND 4.0,禁演绎)的任何指令原文
- 商品属性词表的枚举值来自官方公开文档的属性枚举(事实性数据,非创作性表达)
- 瑞幸咖啡及相关商标归北京瑞幸咖啡有限公司所有,本工具为非官方第三方技术实践

---

## 安装

### 前置条件

- Python 3.8+
- 瑞幸账号(获取 MCP token)
- 高德开放平台 key(免费,用于 `locate` 命令;可选)

### 1. 安装 CLI

```bash
pip install luckin-cli
```

或从源码:

```bash
git clone https://github.com/AD207warlord/luckin-cli.git
cd luckin-cli
pip install -e .
```

### 2. 获取瑞幸 token

用瑞幸官方 CLI 登录(只需用它拿 token):

```bash
# 安装瑞幸官方 CLI
curl -fsSL https://open.lkcoffee.com/install | bash          # macOS/Linux
irm https://open.lkcoffee.com/window/install | iex            # Windows PowerShell

# 登录(浏览器扫码授权)— 这是瑞幸官方 CLI,命令名是 luckin(非 smart-luckin)
luckin login
```

登录后 token 写入 `~/.luckin/.env`。把它设为环境变量:

```bash
# Windows (PowerShell)
[Environment]::SetEnvironmentVariable('LUCKIN_MCP_ORDER_TOKEN','<你的token>','User')

# Linux/macOS
echo 'export LUCKIN_MCP_ORDER_TOKEN=<你的token>' >> ~/.bashrc && source ~/.bashrc
```

⚠️ **改完环境变量需重启终端/Agent 进程才能生效。**

### 3.(可选)配置高德 key

用于 `smart-luckin locate` 模糊地址定位。免费申请:[lbs.amap.com](https://lbs.amap.com/)

```bash
# Windows
[Environment]::SetEnvironmentVariable('AMAP_API_KEY','<你的key>','User')
# Linux/macOS
echo 'export AMAP_API_KEY=<你的key>' >> ~/.bashrc && source ~/.bashrc
```

### 4. 首次配置

```bash
smart-luckin config init
# 交互式填入:家门店名称/deptId/坐标/日常口味 productId/skuCode
```

---

## 快速开始

```bash
# 查看配置
smart-luckin config show

# 一键日常下单(最高频)
smart-luckin order daily
# → 查营业 → 显示价格 → 确认 → 下单 → 终端二维码 → 微信扫码支付

# 找附近门店(模糊地址)
smart-luckin locate 新华路664号
smart-luckin locate 万宝国际商务中心

# 看新品
smart-luckin menu new

# 临时换门店换商品下单
smart-luckin order create --locate "宝山区新二路999弄" --product 5509 --sku SP3929-00009
```

---

## 命令手册

### `smart-luckin config` — 配置管理

```bash
smart-luckin config init                    # 交互式首次配置
smart-luckin config show                    # 查看当前配置(含 token/高德 key 脱敏显示)
smart-luckin config set <key> <value>       # 设置单项(如 daily_order.skuCode SPxxxx-xxxxx)
```

配置文件:`~/.luckin/profile.json`(不进 git),含家门店 + 日常口味。

### `smart-luckin order` — 订单管理(核心)

```bash
smart-luckin order daily                    # 一键日常下单(家门店 + 日常口味)
smart-luckin order preview [--product ID] [--sku CODE] [--dept ID] [--locate ADDR]
                                      # 预览价格(不扣款)
smart-luckin order create [--product ID] [--sku CODE] [--dept ID] [--locate ADDR] [-y]
                                      # 下单(真实扣款,自动取券 + 生成二维码)
smart-luckin order status <orderId>         # 查订单状态 + 取餐码
smart-luckin order cancel <orderId> [-y]    # 取消订单(未支付时最干净)
```

`order create` 内部自动:`previewOrder 取当次券码 → createOrder → 用 payOrderUrl(deeplink)生成二维码`。

#### ⏰ 下单前时间校验(防取不到餐)

`order create` / `order daily` 下单前会查门店营业时间,按距关门时间分级处理:

| 级别 | 条件 | 行为 |
|---|---|---|
| ✅ ok | 萝关门 >30min | 静默放行 |
| ⚠️ warn | 距关门 10~30min | 提醒 + **二次确认**(即使 `-y` 也要确认) |
| 🚨 danger | 距关门 <10min 或不足制作提前量(默认 10min) | 默认拒绝;`-y` 强制时**二次确认** |
| ❌ closed | 未营业/已打烊 | 硬拒绝(无法下单) |

**为什么 warn/danger 即使 `-y` 也要二次确认**:防止用户用 `-y` 跳过价格确认时,忽略时间警告误下单(快关门的单可能取不到餐)。`-y` 只跳价格确认,不跳时间风险确认。

`shops status` 也会显示时间校验结果(信息性,不阻断)。

### `smart-luckin shops` — 门店查询

```bash
smart-luckin shops list [--lng LNG --lat LAT] [--limit N]   # 列门店(默认家门店周边)
smart-luckin shops status                                    # 家门店营业状态
```

### `smart-luckin menu` — 菜单发现

```bash
smart-luckin menu search <关键词>           # 搜商品(模糊匹配,如 "生椰拿铁")
smart-luckin menu new                       # 查新品
smart-luckin menu discover [--limit N]      # 四维度枚举菜单(品类/口味/系列/标签)
```

`menu discover` 用 ~50 个分类词系统查询,覆盖率约 60-70%(完整菜单需 App/小程序)。

### `smart-luckin product` — 商品详情 + 规格切换

```bash
smart-luckin product detail <productId>     # 商品详情 + 完整规格树
smart-luckin product switch <productId> \
    --size 超大杯 --temp 冰 \
    [--bean 意式拼配] [--concentration 默认浓度] \
    [--sugar 不另外加糖] [--milk 无奶] [--tea 茉莉花香]
                                      # 切换规格(内部自动链式 + operation=3)
```

`product switch` 内部:`queryProductDetailInfo 拿属性树 → 按 name 匹配 ID → 链式 switchProduct`。不同商品维度不同(加浓美式 6 维,Hello苹果茉莉 4 维),自动适配,无需手动查 ID。

### `smart-luckin locate` — 模糊地址定位

```bash
smart-luckin locate <地址> [--city 城市] [--limit N]
```

三场景自动路由:
- 精确门牌(含数字)→ 地理编码,精度 <50m
- 地标名(含大厦/广场/中心)→ POI 搜索,精度最高
- 模糊路段(无门牌)→ 地理编码中点,列候选 + 跨区检测

---

## 配置文件

`~/.luckin/profile.json`:

```json
{
  "home_store": {
    "deptId": <你的门店 deptId>,
    "deptName": "<你的家门店名>",
    "number": "<如 No.xxxx,仅展示用>",
    "address": "<门店地址>",
    "longitude": <门店经度>,
    "latitude": <门店纬度>
  },
  "daily_order": {
    "product_id": <productId,如 2507=加浓美式>,
    "product_name": "<商品名>",
    "skuCode": "<切好规格的成品 skuCode,用 smart-luckin product switch 取得>"
  },
  "endpoint": "https://gwmcp.lkcoffee.com/order/user/mcp"
}
```

环境变量(不进 profile.json):
- `LUCKIN_MCP_ORDER_TOKEN`(必填,49 位,绑定账号能扣款)
- `AMAP_API_KEY`(可选,locate 命令用)
- `LUCKIN_PROFILE`(可选,自定义 profile.json 路径)

---

## 内部封装的踩坑经验(对外透明)

| 坑 | CLI 如何处理 |
|----|-------------|
| `operation=3`(官方 schema 没标枚举) | switchProduct 内部硬编码 |
| 链式 skuCode 更新 | `product switch` 自动链式,用户只给规格名 |
| 冰热杯型 ID 不同(热 650 / 冰 594) | 自动读属性树动态匹配 |
| `payOrderQrCodeUrl` 扫码失效 | 只用 `payOrderUrl` deeplink 生成二维码 |
| Windows git-bash 中文编码 | 内部 requests 直发,绕开 shell |
| couponCodeList 不能缓存 | `create_order_safe` 自动先 preview 取券 |
| `deptName` 搜索 bug | 永远不带 deptName |
| `deptId ≠ No.xxx` | 只用 queryShopList 返回的数字 ID |
| 门店搜索服务波动 | 多店 fallback |
| IP 定位在代理下失效 | locate 用高德 geocode/POI |

---

## 作为 skill 给 Agent 用

本 CLI 同时提供 skill 形态(`skill/SKILL.md`),Agent 可直接调用 `luckin` 命令而非裸调 MCP。

价值:Agent 调裸 MCP 每次都要重新踩坑(operation 几?skuCode 怎么更新?二维码哪个字段?)。调 CLI 只需一条命令,踩坑经验在 CLI 内部固化。

安装 skill:
```bash
cp -r skill/luckin-coffee ~/.agents/skills/
```

---

## ⚠️ 重要说明

### 涉及真实扣款

- `smart-luckin order create` / `smart-luckin order daily` 会**真实下单扣款**
- token(`LUCKIN_MCP_ORDER_TOKEN`)绑定你的瑞幸账号,**泄露 = 别人能花你账号的钱**
- 本仓库**全面脱敏**,不含任何真实 token / 门店 ID / 订单号。使用前自行填入

---

## License

MIT — 见 [LICENSE](LICENSE)
