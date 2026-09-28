# Changelog

## [1.0.3] — 2026-09-28

- 表情解析：同步 QFace 表情库，修正 ID 错配，统一消息、卡片和回应映射。

## [1.0.2] — 2026-09-27

- 插件 API：同时支持 `adapter.napcat.*` 和 `adapter.snowluma.*`。
- 消息过滤：新增用户黑名单，拦截指定用户的群聊和私聊消息。

## [1.0.0] — 合并版：统一 QQ 连接器

以 NapCat 适配器的模块结构为基底，合并 SnowLuma 适配器的全部特性，
形成同时支持 SnowLuma / NapCat 客户端的单一适配器插件。

### 主要功能

- 移除适配器内置的群聊/私聊黑白名单、全局用户屏蔽名单及主动私聊临时放行；入站通行统一由宿主适配器策略控制。
- client_type 三值配置（auto / napcat / snowluma）：auto 在每次连接建立后通过
  `get_version_info` 自动判定对端并应用能力画像；显式取值时做一致性校验，
  不一致打警告并按声明运行。
- 运行时热切换：WebUI 修改 client_type 或连接参数后自动断开重连并应用新画像。
- 统一 API 命名空间 `adapter.napcat.*`：171 个公开 API（NapCat 164 + SnowLuma QZone 7），
  QZone API 按画像能力位校验，napcat 下调用显式报错。
- 出站动作列表模型：SnowLuma 画像把文件段拆为独立 upload 动作并保持顺序，
  NapCat 画像保持内联 file 段；合并转发参数键按画像取 message / messages。
- 出站 token 双通道鉴权：同时附带 Bearer 头与 URL access_token 参数，兼容两类服务端。
- 富文本通知（SnowLuma 风格）：操作者真名解析（带缓存）、poke raw_info 动作文、
  invite / kick / kick_me 区分、精华增删区分、消息 ID 后缀；
  保留 NapCat 的全体禁言解除与自然解除分支、禁言状态跟踪（natural lift）与心跳监测。

### 细节（修复与特性移植）

- 移植 silk 语音转码链（pysilk 解码 24kHz PCM → ffmpeg MP3），依赖缺失时明确警告并降级。
- 移植 QQ 表情双模式解析（description / emoji，qq_face_parse_mode 配置项）。
- 移植入站媒体取数链：base64:// 引用、本地路径、get_image 动作兜底。
- 移植 Ada 原始报文调试日志与 base64 脱敏（独立 debug.py，两端通用）。
- 移植 reply 空引用过滤（入站 id=0）与合成 ID 过滤（出站 qq- 前缀），两端启用。
- 入站兼容 SnowLuma 的字符串 message 载荷与缺失 post_type 的推送（按消息路由）。
- `is_picture` 改为动态判定（任意图片段即置位），不再恒为 False。
- 聊天名单过滤默认关闭：入站通行统一交给宿主适配器策略（adapter_policy.toml / WebUI）；
  插件侧过滤保留为可选项。
- 配置迁移：旧 `[luma_client]` / `[napcat_server]` / `[connection]` 节自动迁移到 `[client]`
  （host → server、access_token → token），旧版本号自动改写。
- 旧 SnowLuma 适配器的私聊工具、通知开关、正则过滤（NapCat）等行为全部保留。

## [0.x 历史]

0.9.x 及更早版本的历史变更见上游仓库
[Mai-with-u/MaiBot-SnowLuma-Adapter](https://github.com/Mai-with-u/MaiBot-SnowLuma-Adapter)
与 [Mai-with-u/MaiBot-Napcat-Adapter](https://github.com/Mai-with-u/MaiBot-Napcat-Adapter)。
