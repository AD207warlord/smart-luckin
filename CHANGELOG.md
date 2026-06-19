# Changelog

本项目的所有重要变更记录。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-06-19

首版公开发布。封装瑞幸 MCP 的踩坑经验,提供命令行点单全流程。

### 新增

**核心能力(6 命令组)**
- `config` 配置管理(profile.json:家门店 + 日常口味,init/show/set)
- `shops` 门店查询(list 周边门店,status 家门店营业状态 + 时间校验)
- `menu` 菜单发现(search 模糊搜,new 新品,discover 四维度分类词枚举)
- `product` 商品详情 + 规格切换(detail 规格树,switch 链式自动切换)
- `order` 订单管理(preview 预览不扣款,create 下单,daily 一键日常,status 查询,cancel 取消)
- `locate` 模糊地址定位(高德地理编码 + POI,三场景路由)

**踩坑封装(MCP 隐性知识固化进代码)**
- `switchProduct` 的 `operation:3`(官方 schema 未标枚举值,查文档确认)硬编码
- 链式 skuCode 滚动(switch_specs 按 attributeName 动态匹配 ID,自动链式)
- 支付二维码用 `payOrderUrl` deeplink(实测 `payOrderQrCodeUrl` 扫码失效)
- `createOrder` 前自动 `previewOrder` 取当次券码(防过期券多花钱)
- `deptName` 搜索 bug 规避(默认不带,只用坐标)
- 多店 fallback(search 失败自动换店)
- 中文编码坑规避(内部 requests 直发,不经 shell)

**安全与工程**
- token 三级优先级:环境变量 `LUCKIN_MCP_ORDER_TOKEN` > `~/.luckin/.env`(官方 CLI login 产物)> 报错引导
- 外送意图检测(`order create --locate "送到xxx"` 拦截,瑞幸 MCP 仅支持自提)
- 商品属性词表(15 类 + 别名归一,`product switch --spec "少冰,无糖"`)
- 下单前时间校验(check_order_time:ok/warn/danger/closed 四级,closed 硬拒,danger 默认拒)
- `-y` 二次确认(warn/danger 场景即使 -y 也要确认时间风险,防误下)
- client.py 优雅处理 MCP `isError:true`/Overflow 响应(20 位订单号 JS 数值溢出)

**测试**
- 25 个单元/集成测试(15 时间校验逻辑 + 10 下单拦截集成)

### 已知限制

- **外送下单暂不支持**:瑞幸后端支持(dispatchInfo 字段为证),但 createOrder 触发外送的机制未确证,CLI 暂拦截。详见 README
- **20 位订单号无法查询**:瑞幸 MCP 网关 JS 数值溢出(Number.MAX_SAFE_INTEGER),小程序/App 订单查不了,只能查 MCP 创建的 19 位订单
- **菜单发现覆盖率 ~60-70%**:无结构化分类参数,完整菜单需 App/小程序

### 与官方的关系

- 独立实现,不包含官方 my-coffee skill(CC BY-ND 4.0,禁演绎)的任何指令原文
- 商品属性词表枚举值来自官方公开文档(事实性数据)
- 瑞幸咖啡及相关商标归北京瑞幸咖啡有限公司所有,本工具为非官方第三方技术实践
