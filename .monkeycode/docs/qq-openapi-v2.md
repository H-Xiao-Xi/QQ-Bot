# QQ OpenAPI v2 收发要点

对照 [官方 API v2](https://bot.q.qq.com/wiki/develop/api-v2/) 整理，供本仓库 Webhook 服务排障。

## Webhook

回调地址填 `https://你的域名/webhook`。平台只接受端口 `80` / `443` / `8080` / `8443`，且必须 HTTPS。

下行 payload：

```json
{"id":"event_id","op":0,"d":{},"s":42,"t":"GATEWAY_EVENT_NAME"}
```

| op | 含义 | 本服务行为 |
| --- | --- | --- |
| 13 | 回调地址验证 | 用 AppSecret 签 `event_ts + plain_token`，只回 `{"plain_token","signature"}` |
| 0 | 事件推送 | 验 `X-Signature-Ed25519` / `X-Signature-Timestamp`，立刻回 `{"op":12}`，后台再处理 |
| 12 | HTTP ACK | 仅作为回包，不作为请求 |

Nginx 必须透传 `X-Signature-Ed25519`、`X-Signature-Timestamp`、`X-Bot-Appid`，关闭 HTTP/3 / QUIC。

## Token 与发消息主机

| 项 | 官方值 |
| --- | --- |
| Token | `POST https://api.bot.qq.com/app/getAppAccessToken`，body 为 `appId` / `clientSecret` |
| 发消息 | `https://api.bot.qq.com` |
| Header | `Authorization: QQBot {access_token}` |

Token 业务错误走 body 里的 `code`（HTTP 仍可能是 200）。发消息失败走 `err_code`。不要用 `message` 判定成败。

成功发消息返回带 `id` 的业务对象。HTTP `201` / `202` 是异步成功（可能进人工审核）。

## 被动回复

消息事件用 `d.id` 作为 `msg_id`。`event_id` 是 payload 最外层 `id`，和 `msg_id` 二选一。

| 字段 | 用于 | 支持的来源 |
| --- | --- | --- |
| `msg_id` | 回复用户消息 | `GROUP_AT_MESSAGE_CREATE`、`GROUP_MESSAGE_CREATE`、`C2C_MESSAGE_CREATE`、`AT_MESSAGE_CREATE` 的 `d.id` |
| `event_id` | 回复非消息事件 | 群：`INTERACTION_CREATE`、`GROUP_ADD_ROBOT`、`GROUP_MSG_RECEIVE`；单聊：`INTERACTION_CREATE`、`C2C_MSG_RECEIVE`、`FRIEND_ADD` |

本服务回复用户消息只带 `msg_id` + `msg_seq`。

| 场景 | 路径 | 有效期 | 次数 |
| --- | --- | --- | --- |
| 群聊 | `POST /v2/groups/{group_openid}/messages` | 5 分钟 | 每条最多 5 次 |
| 单聊 | `POST /v2/users/{user_openid}/messages` | 60 分钟 | 每条最多 4 次 |
| 频道 | `POST /channels/{channel_id}/messages` | 5 分钟 | 平台未写死次数 |

群聊文本示例：

```json
{"msg_type":0,"content":"签到成功","msg_id":"ROBOT1.0_xxx","msg_seq":1}
```

Markdown 用 `msg_type=2` 且 `markdown.content`；同时不要带 `content`。无 Markdown 权限时回落纯文本，并用 `msg_seq+1`。

## 事件订阅

Webhook 控制台勾选：

1. `GROUP_AT_MESSAGE_CREATE` 群聊 @
2. `C2C_MESSAGE_CREATE` 单聊
3. `AT_MESSAGE_CREATE` 频道 @
4. `GROUP_MESSAGE_CREATE` 群聊全量（免 @）；还需要群主把机器人消息范围设为获取群内全部消息

未开全量时，群里必须 @ 机器人。`GROUP_AT_MESSAGE_CREATE` 的 `content` 已去掉 @ 机器人前缀。

身份字段：单聊 `user_openid`，群 `group_openid`，群成员 `member_openid`。

## IP 白名单

未设置时允许所有来源 IP。设置后必须包含服务器公网 IPv4（单 IP，最多 50 个）。错误码 `11298` 表示源 IP 不在白名单。

## 控制台磁带怎么看

| 磁带 | 含义 |
| --- | --- |
| 「收到事件」不增加 | 平台没打到 `/webhook`，或签名失败 |
| `收到 group/c2c/channel` 后 `回复失败` | OpenAPI 拒绝，看错误码和 `trace=` |
| `未识别指令` | 全量群消息只响应已知指令；或订阅了全量但内容被剥空 |
| `缺少回复目标` | `d.id` 或 `group_openid` / `user_openid` / `channel_id` 为空 |

常见错误码：`11298` IP 白名单；`40034005` / `304027` / `40034028` `msg_id` 过期或超次；`40034025` `event_id` 无效；`50056` / `304036` 无 Markdown 权限。

宝塔 gunicorn 无 reload，拉代码后必须重启 Python 项目。
