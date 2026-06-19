# smart-luckin

> ☕ **基于瑞幸官方 MCP/CLI 之上的点单封装** — 把官方工具链的踩坑经验,固化成装完即用的命令行。
>
> 瑞幸官方 2026-06 上线 AI 开放平台,提供 MCP Server(8 个 JSON-RPC 工具)+ CLI(`luckin login` 刷 token)+ my-coffee skill 三件套。本 CLI **不是替代官方,是建立在官方 MCP 数据源之上**的编排封装层:复用官方 token 和 endpoint,把裸调 MCP 要踩的坑(operation 枚举/skuCode 链式/二维码字段/中文编码/定位...)预先固化进代码。

> **📦 包名/仓库名/命令名统一 `smart-luckin`**。
> 命令名刻意避开瑞幸官方 CLI(`luckin`,用于 `luckin login` 刷 token)的冲突。`pip install smart-luckin` 后用 `smart-luckin` 调用。
> **Python import 名仍是 `luckin`**(内部模块结构),用户感知不到。

---

## 这是什么

smart-luckin 是 **Agent 和瑞幸 MCP 之间的转译层**。

瑞幸官方 MCP 提供了 8 个工具,但接口很"硬":要精确的 deptId/productId/skuCode/经纬度,不收自然语言。Agent(LLM)理解力很强,但它"想说的"和瑞幸"能收的"之间有 gap。smart-luckin 做的就是把这个 gap 填上——**把 Agent 的宽泛意图,转译成瑞幸能接受的精确参数**。

```
Agent 的意图              smart-luckin 转译         瑞幸 MCP 硬接口
─────────────           ──────────────         ─────────────
"清爽果味"        →     menu search 果茶      →   searchProductForMcp(query="果茶")
"少糖"            →     --spec 糖度=少甜       →   switchProduct(subAttr=少甜, operation=3)
"续命的"          →     order daily(profile)  →   createOrder(deptId, productList, lng, lat)
"XX 广场"         →     locate → 坐标          →   queryShopList(lng, lat)
```

**不是什么**(诚实边界):
- 不替代 Agent 的语义理解(理解还是 Agent 做,我们做转译)
- 不自建后端(数据源仍是瑞幸官方 MCP,token 复用官方 CLI 登录产物)
- 不比官方"聪明"(我们是官方硬接口之上的转译层,互补关系)

## 定位:三层架构

```
┌─────────────────────────────────────────────────┐
│  语义理解层(LLM Agent)                          │
│  ZCode / Claude Code / 官方 luckin 内置 LLM      │
│  理解"来杯续命的" → 决定调什么工具               │
└─────────────────────────────────────────────────┘
                    ↓ 调用工具
┌─────────────────────────────────────────────────┐
│  转译层(smart-luckin 在这!)                    │
│  把 Agent 的意图转译成瑞幸能收的精确参数          │
│  · 语义转译(口语→品类/规格/SKU)                │
│  · 地理软化(地址→坐标)                          │
│  · 踩坑封装(operation/skuCode/二维码/编码)      │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  数据源:瑞幸官方 MCP Server(8 个原子工具)       │
└─────────────────────────────────────────────────┘
```

官方 `luckin -p` 走的是"CLI 内置 LLM 包办"(LLM 由用户 `luckin models add` 自行配置,支持任意 OpenAI 兼容模型如 GLM/DeepSeek/Kimi 等);smart-luckin 走的是"外部 Agent 理解 + 转译层执行"。两条路都能完成点单,差别在 LLM 放在哪一层。

## 核心价值 1:语义转译(口语 → 瑞幸硬接口)

Agent 理解"少糖"没问题,但瑞幸 `switchProduct` 要的是 `attributeId` + `subAttr.attributeId` + `operation=3`(schema 没标 operation 枚举)。Agent 每次裸调都要查文档、链式切 skuCode。我们把这层转译固化:

| Agent 说的 | 转译为(瑞幸硬接口) | 怎么做 |
|---|---|---|
| "少糖" | `switchProduct(糖度=少甜, operation=3)` | attrs.py 词表(15类+口语别名:少糖/微糖/低糖→少甜/微甜) |
| "清爽果味" | `searchProductForMcp(query="果茶")` | menu search(感官词→品类词) |
| "续命的" | `createOrder(日常口味)` | profile 存了日常 productId+skuCode |
| "超大杯冰燕麦奶" | 链式 switch 出最终 skuCode | `--spec` 多维归一,Agent 不用查 attributeId |

**关键**:我们做的是**收敛转译**,不是发散思考。Agent 的理解力不变(该发散该收敛由 Agent 决定),我们只负责把 Agent 已经想好的意图,"翻译"成瑞幸的硬接口语言。属性词表就是这本字典。

> 实测(2026-06-19):`menu search 果茶` 命中 3 款;`parse_spec_text("少糖,冰")` → `{糖度:少甜, 温度:冰}` 转译正确。

## 核心价值 2:地理软化(人类地址 → 瑞幸硬坐标)

瑞幸 MCP 的 `queryShopList` / `createOrder` 都**强制要经纬度**(number 类型,必填)。但普通人不会报经纬度,Agent 拿到的也是"XX 商场""XX 路 123 号"这种人类地址。我们接高德 API 做软化:

| 用户/Agent 说的 | 转译为(瑞幸硬坐标) | 高德 API |
|---|---|---|
| "XX 广场"(地标) | `lng=121.474, lat=31.232`(示例) | POI 搜索(`/place/text`) |
| "XX 路 123 号"(门牌) | `lng=121.420, lat=31.205`(示例) | 地理编码(`/geocode/geo`) |
| "XX 路"(模糊路段) | 路段中点坐标 + 候选门店列表 | 地理编码 + 跨区检测 |
| "日常那杯"(无地址) | profile 家门店坐标(配置一次复用) | 无需定位 |

高德 key 免费申请([lbs.amap.com](https://lbs.amap.com/))。这是对比官方 my-coffee skill 的一个差异点——官方用 `ipinfo.io` IP 粗定位(代理/VPN 下失效,且只到城市级),我们用高德精准定位(精度 <50m)。

## 核心价值 3:支付二维码的 UI 适配

瑞幸 `createOrder` 返回两个 URL,选哪个取决于**调用方的 UI 环境**:

| 字段 | 类型 | 适合的场景 |
|---|---|---|
| `payOrderUrl` | `weixin://wxpay/bizpayurl?pr=xxx`(deeplink) | **Agent 开发环境**(ZCode/Claude Code 等 UI 能直接渲染图片) |
| `payOrderQrCodeUrl` | 瑞幸中转页 URL | 纯终端(无图片渲染) |

我们选 `payOrderUrl`:套一层二维码生成服务,渲染成 Markdown 图片(`![](api.qrserver.com?data=...)`),在 ZCode 这类 Agent 的 UI 预览区**直接显示可扫的二维码**。

**为什么这么选**(开发态体验):在 Agent 开发环境里,扫码路径是 `UI 显示二维码 → 手机微信扫 → 进支付页`,**一步**。如果用中转页或纯链接,路径变成 `复制链接 → 转发到手机 → 手机浏览器打开 → 长按图片识别 → 再扫`,繁琐。`payOrderQrCodeUrl` 实测还会报"非法链接"(2026-06-19),所以弃用。

> 这个选择是为 **Agent 开发态 UI** 优化的。如果你的环境是纯终端(无图片渲染),`payOrderUrl` 的 deeplink 可能不如中转页方便——届时可以加 `--no-qr` 只输出 URL。

## 实测对比:同任务三种路径(2026-06-19)

任务:"我在上海某商圈,想喝冰的茶饮,给我至少 3 个商品选项"

| 维度 | 纯 MCP 裸调 | 官方 CLI(`-p`,内置可配 LLM) | **Agent + smart-luckin** |
|---|---|---|---|
| **定位** | 工具层(原子) | 工具层 + 内置 LLM 一体化 | 转译层 + 外部 Agent |
| **能完成?** | 要外部补转译/定位/踩坑 | ✅ | ✅ |
| **LLM token** | 外部 Agent 自行转译 | 运行时烧(实测输出 72 万字符) | Agent 理解意图(单轮)+ 转译层零 LLM token |
| **耗时** | 看 Agent | **~2 分钟** | **<5 秒** |
| **结果** | — | 3 选项(2 个同款凑数) | 4 选项(不同风格) |

**不夸大也不过谦**:
- 官方 `-p` 的优势:**一体化**(内置 LLM,配个模型 key 就能用,不依赖外部 Agent)。LLM 可配任意 OpenAI 兼容模型,不绑定厂商。适合没有 Agent 的纯终端环境。
- smart-luckin 的优势:**在已有 Agent 的环境下**,转译固化让 Agent 调用更直接(72 万字符 → 1 秒命令)。不重复造 LLM 的轮子,复用你已有的 Agent。
- 共同基础:都建立在瑞幸官方 MCP 之上,token 都来自官方 CLI 登录。

> 本次裸测试官方 `-p` 用智谱 GLM Coding Plan 配置,未被白名单拦截。官方 `models add` 支持任意 OpenAI 兼容模型,不限于 GLM。

## 独有能力:菜单发现(menu discover)

这是 smart-luckin **官方三件套(MCP/CLI/skill)都没有的能力**。

**背景**:瑞幸 MCP 只提供 `searchProductForMcp`,每次只能搜**一个关键词**。官方 CLI `luckin menu <deptId> <词>` 和 skill 都靠这个工具单次搜。想知道"这家店到底有什么",得手动想几十个词逐个搜。

**我们做的**:`menu discover` 用 4 个维度 38 个分类词批量枚举,去重聚合:

| 维度 | 词数 | 示例 |
|---|---|---|
| 品类 | 20 | 美式/拿铁/生椰拿铁/卡布奇诺/澳瑞白/抹茶/果茶/瑞纳冰... |
| 口味 | 11 | 苹果/芒果/西柚/草莓/椰子/芋泥/焦糖/榛子... |
| 系列 | 5 | 丝绒/Hello/弗朗明戈/耶加雪菲/冰吸 |
| 标签 | 2 | 新品/经典 |

**实测**(2026-06-19):一次 `menu discover` 调 38 次 searchProductForMcp,去重后**命中 40 款商品**(含新品/经典/各品类),覆盖率约 60-70%(完整菜单需 App/小程序,瑞幸无全量列表 API)。

```bash
smart-luckin menu discover --limit 100
# → 枚举 4 维度 38 词 → 去重聚合 → 按 productId 排序展示
```

**边界诚实说**:这不是"完整菜单",瑞幸没有公开的全量商品列表 API,我们靠分类词枚举逼近,覆盖率约 60-70%(实测 40 款)。冷门商品可能漏。但比官方"只能单次搜一个词"强——Agent 想"看看这家店有什么"时,一条命令出 40 款,不用想 38 个词。

> 注:`menu new`(新品)和 `menu search`(关键词)**不是我们独有**——MCP 的 searchProductForMcp 原生支持,官方 CLI `luckin menu <id> 新品` 也能查新品(实测返回带 `tags:["新品"]` 的商品)。我们只是封装成命令。**menu discover 的批量枚举聚合,才是我们独有的。**

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

### 前置条件(环境要求)

**必需环境**:

| 项 | 要求 | 说明 |
|---|---|---|
| **Python** | 3.8+ | 推荐 3.10+,用 `python --version` 确认 |
| **pip** | 任意可用版本 | 装依赖用 |
| **瑞幸官方 CLI** | 已安装 | **必须先用它登录拿 token**(本 CLI 复用官方 token,不独立实现登录) |
| **瑞幸账号** | 有效 | 通过官方 CLI `luckin login` 扫码授权 |

**可选环境**:

| 项 | 用途 | 缺失影响 |
|---|---|---|
| **高德开放平台 key** | `locate` 命令(模糊地址→门店) | `locate` 不可用,但 `order daily`/`shops` 等用已配置坐标,不受影响 |
| **PATH 中的 Python Scripts 目录** | 直接打 `smart-luckin` 命令 | 需用 `python -m luckin` 或全路径调用 |

**关键依赖说明**:本 CLI **建立在瑞幸官方工具链之上**,不替代官方:
- **token 来源**:复用瑞幸官方 CLI(`luckin login`)写入的 `~/.luckin/.env`,不独立实现登录鉴权
- **数据源**:直接调瑞幸官方 MCP Server(`gwmcp.lkcoffee.com`),不自建后端
- **定位**:用高德(替代官方 skill 的 IP 粗定位,精度更高)

### 1. 安装 CLI

```bash
pip install smart-luckin
```

或从源码:

```bash
git clone https://github.com/AD207warlord/smart-luckin.git
cd smart-luckin
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
smart-luckin locate "XX 路 123 号"
smart-luckin locate "XX 国际商务中心"

# 看新品
smart-luckin menu new

# 临时换门店换商品下单
smart-luckin order create --locate "XX 区 XX 路 999 弄" --product 5509 --sku SP3929-00009
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
