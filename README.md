# QQ 官方机器人 · Webhook

Python FastAPI 服务，按 [QQ 机器人 API v2](https://bot.q.qq.com/wiki/develop/api-v2/) 接入 Webhook：

1. Ed25519 签名校验
2. `op=13` 回调地址验证
3. `op=0` 事件接收后立即 `op=12` ACK
4. 群聊 @、单聊、频道消息被动回复

## 准备

1. 在 [QQ 开放平台](https://q.qq.com) 创建机器人，拿到 `AppID`、`AppSecret`
2. 沙箱里加入测试群 / 测试好友
3. 准备可公网访问的 HTTPS 域名。平台只接受端口 `80`、`443`、`8080`、`8443`

## 启动

```bash
python3 -m pip install --break-system-packages -r requirements.txt
cp .env.example .env
```

```bash
python3 app.py
```

打开控制台 `http://127.0.0.1:8080`，先登录，再在「机器人密钥」里填写 AppID、AppSecret 并保存，立刻生效。

控制台需要登录。初始账号 `admin`，初始密码 `admin`。第一次登录后必须立刻改成你自己的账号和密码，改完才能看密钥页。账号哈希保存在 `data/admin.json`，不要提交到 Git。

`/webhook` 仍然公开，QQ 开放平台回调不需要登录。

健康检查：`GET /health`

## 开放平台回调

把回调地址填成：

```text
https://你的域名/webhook
```

保存时平台会 POST 一个 `op=13` 校验包。服务用 AppSecret 计算 signature 并原样返回 `plain_token`，校验通过后即可收事件。

建议订阅：

1. `GROUP_AT_MESSAGE_CREATE` 群聊 @
2. `GROUP_MESSAGE_CREATE` 群聊全量（免 @ 指令）
3. `C2C_MESSAGE_CREATE` 单聊
4. `AT_MESSAGE_CREATE` 频道 @

免 @ 还需要群主在手机 QQ 群设置里，把机器人消息范围设为获取群内全部消息。全量群消息只响应指令，闲聊不回。

调用 OpenAPI 时，把服务器公网 IP 加进管理端白名单。

## 默认指令

1. `help` 帮助
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

控制台软妹币榜可直接改连续天数、钱包和银行。银行管理页显示存取流水。

@ 机器人或单聊里的其它文本回复一张「收到」卡片。群聊和单聊优先发 Markdown 卡片，失败时再发纯文本。业务逻辑在 `app/handlers.py`。

## 测试

```bash
python3 -m pytest -q
```

`tests/test_crypto.py` 使用官方文档里的校验样例。

## 反向代理示例

Nginx 把 443 转到本服务 8080：

```nginx
server {
    listen 443 ssl;
    server_name bot.example.com;
    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Signature-Ed25519 $http_x_signature_ed25519;
        proxy_set_header X-Signature-Timestamp $http_x_signature_timestamp;
        proxy_set_header X-Bot-Appid $http_x_bot_appid;
    }
}
```

证书必须是完整链。部分免费证书缺 CA 时，开放平台校验会失败。

## 宝塔 Python 项目

把整个项目目录上传到服务器，例如 `/www/wwwroot/qqbot`。启动后打开网站首页，先用 `admin` / `admin` 登录并改掉账号密码，再填写 AppID、AppSecret。

Python 项目管理器里这样填：

1. 项目路径：`/www/wwwroot/qqbot`
2. 启动方式 / 启动文件：`app.py`
3. 端口：`8080`
4. 在「模块」里安装 `requirements.txt`
5. 启动项目

也可以用 Gunicorn（同样端口，单进程，避免内存事件去重失效）：

```bash
gunicorn -c gunicorn.conf.py app.main:app
```

网站这边：

1. 添加站点，域名解析到这台机器
2. 申请 SSL（完整证书链）
3. 反向代理目标：`http://127.0.0.1:8080`
4. 在 Nginx 配置里补上上面三个 `X-Signature-*` / `X-Bot-Appid` 请求头，否则验签会失败

开放平台回调填：

```text
https://你的域名/webhook
```

## 目录

```text
app/
  main.py         Webhook、登录与控制台
  auth.py         控制台账号
  crypto.py       Ed25519
  api_client.py   Access Token 与发消息
  handlers.py     指令与事件分发
tests/
```
