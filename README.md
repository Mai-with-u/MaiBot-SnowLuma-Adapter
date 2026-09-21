# MaiBot SnowLuma Adapter（统一 QQ 连接器）

连接 SnowLuma / NapCat（OneBot v11 正向 WebSocket）的 MaiBot 适配器插件。
1.0 版起，本插件同时支持两类客户端：连接建立后通过标准动作 `get_version_info`
自动判定对端实现并应用对应能力画像；也可以在配置中固定 `client_type`，
或配置为 `auto` 由适配器每次重连时重新判定。

## 核心特性

- **双客户端画像**：`client.client_type` 支持 `auto` / `napcat` / `snowluma` 三值。
  - `auto`：每次连接建立后探测 `get_version_info`，按对端 `app_name` 判定
    （SnowLuma 自报 "SnowLuma"，NapCat 自报 "NapCat"），判定失败会让网关保持未就绪并报错，
    不静默猜测。
  - 显式取值：探测仍会执行，但仅做一致性校验；配置与对端不一致时打警告并按配置声明运行。
- **运行时热切换**：在 WebUI 修改 `client_type` 或连接参数后，插件会自动断开重连并应用新画像。
- **统一 API 命名空间**：`adapter.napcat.*` 共 171 个公开 API（含 SnowLuma 专属 QZone 组），
  QZone API 在 `client_type=napcat` 下调用会得到明确的「不支持」错误。
- **名单默认交给宿主**：适配器侧群聊/私聊黑白名单默认关闭，
  请在 WebUI 聊天页的「适配器策略」（`config/adapter_policy.toml`）中配置通行规则。
- **SnowLuma 特性移植**：silk 语音转码（依赖 `silk-python` + ffmpeg）、QQ 表情双模式解析
  （description / emoji）、入站媒体 base64:// 与本地路径取数、Ada 原始报文调试日志、
  QZone API、富文本通知（真名解析、poke 动作文、invite/kick 区分）。
- **NapCat 能力保留**：群管理 / 文件 / 相册 / 账号全套 API、正则过滤、
  禁言状态跟踪与自然解除、官方机器人屏蔽、心跳监测。

## 从旧 SnowLuma 适配器（0.9.x）升级

配置自动迁移：旧 `[luma_client]` 节会被读取并迁移到 `[client]`，旧版本号会自动改写。
建议直接使用新的 `[client]` 节名。两处行为变化需要留意：

1. **名单过滤默认关闭**：旧版的群聊/私聊白名单不再由插件执行，
   请把名单迁到宿主适配器策略（WebUI 聊天页 → 适配器策略，按本插件维度配置
   `default_action = "block"` + `allow_ids` 即可复刻白名单语义）。
2. **`open_private_chat` 工具的 15 分钟放行**只作用于插件侧过滤；
   名单过滤交给宿主后，还需在宿主策略中放行对应私聊。

## 从旧 NapCat 适配器迁移

| 旧配置（NapCat 适配器） | 新配置（本插件） |
| --- | --- |
| `plugin.*` | `plugin.*`（字段一致，新增表情模式与调试开关） |
| `[napcat_server]` 节 | `[client]` 节（`host` → `server`，其余字段一致） |
| `[chat]` / `[notice]` / `[filters]` | 同名节，字段一致；`enable_chat_list_filter` 默认 false |
| API 前缀 `adapter.napcat.*` | 保持不变 |
| `regex_filter_*` | 一致 |

NapCat 用户迁移后获得的新能力：silk 语音兜底转码、表情双模式解析、
入站媒体 base64/本地路径取数、富文本通知、Ada 调试日志（连接 SnowLuma 时另有 QZone API）。

## 能力差异参考

| 维度 | napcat 画像 | snowluma 画像 |
| --- | --- | --- |
| 发送动作 | `send_group_msg` / `send_private_msg` | 通用 `send_msg` + `message_type` |
| 出站文件 | 内联 `file` 段 | 拆独立 `upload_group_file` / `upload_private_file` |
| 合并转发参数键 | `message` | `messages` |
| 语音 `get_record` 格式 | `wav` | `mp3`（silk 自动转码兜底） |
| QZone API | 不支持（显式报错） | 支持 |

token 鉴权不区分画像：连接时同时附带 `Authorization: Bearer` 头与 URL
`access_token` 参数（OneBot v11 两种标准方式），两类服务端各取所需。

## 依赖

- `silk-python >= 0.2.8`（宿主启动时自动安装；仅 SnowLuma 语音转码需要）
- `ffmpeg`（可选，silk 转 MP3 时需要；缺失时语音降级为占位文本并有警告日志）

## 运行测试

```bash
cd plugins/MaiBot-SnowLuma-Adapter
pytest tests -q
```
