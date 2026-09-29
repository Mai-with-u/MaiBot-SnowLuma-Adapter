# MaiBot SnowLuma Adapter（统一 QQ 连接器）

连接 SnowLuma / NapCat 的 MaiBot 适配器插件。

1.0 版起，本插件同时支持两类客户端：连接建立后自动判断连接方为 NapCat 还是 Snowluma

## 使用方法

1.在 Maibot webui中插件市场下载或者github下载压缩包并解压到插件plugins目录

2.在napcat/snowluma中创建正向ws(ws服务器)连接，记录端口和token连接令牌

3.在适配器配置中正确填写对应的端口的token令牌

4.在 Maibot Webui中的适配器设置中的 "黑白名单规则" 配置群权限，默认全部阅读（就是所有群消息都接受），可以自行改为全部不阅读（只添加阅读的群号）

## 其他插件调用 API

通过 SDK 的 `ctx.api.call` 调用，两种前缀均使用 `version="1"`：

```python
member = await self.ctx.api.call(
    "adapter.snowluma.group.get_group_member_info",
    version="1",
    group_id=123456,
    user_id=654321,
)
# 将上面的 adapter.snowluma. 替换为 adapter.napcat.，调用行为完全相同。

data = await self.ctx.api.call(
    "adapter.snowluma.action.call_data",
    version="1",
    action_name="get_group_info",
    params={"group_id": 123456},
)
```

`await self.ctx.api.list()` 可查看已注册的两组名称。前缀不会切换客户端类型；
实际能力仍取决于当前连接的客户端，两个前缀下的 QZone API 均仅支持 SnowLuma。

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

```
