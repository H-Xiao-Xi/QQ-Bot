# QQ 官方机器人 · Webhook

Python FastAPI 服务，按 [QQ 机器人 API v2](https://bot.q.qq.com/wiki/develop/api-v2/) 接入 Webhook：

1. Ed25519 签名校验
2. `op=13` 回调地址验证
3. `op=0` 事件接收后立即 `op=12` ACK
4. 群聊、单聊、频道被动回复

## 准备

1. 在 [QQ 开放平台](https://q.qq.com) 创建机器人，拿到 `AppID`、`AppSecret`
2. 准备可公网访问的 HTTPS 域名。平台只接受端口 `80`、`443`、`8080`、`8443`

## 启动

```bash
python3 -m pip install --break-system-packages -r requirements.txt
cp .env.example .env
python3 app.py
```

程序监听 `8080`、`8443`。打开控制台登录（初始账号 `admin`，初始密码 `admin`），第一次必须改成自己的账号密码，再填写 AppID、AppSecret。

`/webhook` 对开放平台公开，不需要登录。健康检查：`GET /health`

## 开放平台回调

回调地址填：

```text
https://你的域名/webhook
```

保存时平台 POST `op=13`。服务用 AppSecret 按官方算法签名 `event_ts + plain_token`，返回：

```json
{"plain_token":"...","signature":"..."}
```

事件推送验 `X-Signature-Ed25519` / `X-Signature-Timestamp`，立刻回 `{"op":12}`。

Nginx 反代到 `http://127.0.0.1:8080`，透传上述三个请求头，关闭 HTTP/3 / QUIC。参考 `deploy/nginx-qqbot.conf`。

建议订阅：

1. `GROUP_AT_MESSAGE_CREATE` 群聊 @
2. `GROUP_MESSAGE_CREATE` 群聊全量（免 @ 指令）
3. `C2C_MESSAGE_CREATE` 单聊
4. `AT_MESSAGE_CREATE` 频道 @

免 @ 需要群主把机器人消息范围设为获取群内全部消息。全量群消息只响应指令。调用 OpenAPI 前把服务器公网 IP 加进管理端白名单。
被动回复只用事件里的消息 `id`（`msg_id`）。收发对照见 `.monkeycode/docs/qq-openapi-v2.md`。

## 默认指令

1. `帮助` 查看指令
2. `签到` 每日签到，基础 10；当日第 1/2/3 名额外 +20/+10/+5，连续天数额外 +1/天（最多 +20）
3. `搬砖` 开始搬砖，耗时 120~300 秒随机，到点提醒领取；不限次数，同时只能搬一趟
4. `领工资` 领取搬砖工资，随机 10~25 软妹币进入钱包
5. `查询` 查看钱包、银行、连续天数、今日名次和软妹币排名
6. `加软妹币 数量` / `减软妹币 数量` 增加或减少钱包，最少到 0，省略数量时为 1
7. `加天数 数量` / `减天数 数量` 增加或减少连续签到天数，最少到 0
8. `打劫` / `打劫@某人` 每天一次，成功率 60%；成功抢走对方钱包 10%~30%（最多 50），失败丢掉自己钱包 10%（最多 20）。银行里的软妹币不会被抢
9. `存款 数量` / `取款 数量` 钱包和银行互转，省略数量则全部转入；`银行` 查看余额
10. `利息` 银行存款每日领取一次，利率 5%，利息进入银行

群聊、单聊都可以不带 `/` 直接发指令，带 `/` 同样有效。

## 测试

```bash
python3 -m pytest -q
```

## 宝塔 Python 项目

1. 项目路径：例如 `/www/wwwroot/qqbot`
2. 启动文件：`app.py`
3. 端口：`8080`（同时监听 `8443`）
4. 安装 `requirements.txt` 后启动
5. 网站反代到 `http://127.0.0.1:8080`，监听 `443` / `8080` / `8443`

也可以：

```bash
gunicorn -c gunicorn.conf.py app.main:app
```

## 目录

```text
app/
  main.py         Webhook、登录与控制台
  webhook.py      官方回调协议
  crypto.py       Ed25519
  api_client.py   Access Token 与发消息
  handlers.py     指令与事件分发
tests/
```
