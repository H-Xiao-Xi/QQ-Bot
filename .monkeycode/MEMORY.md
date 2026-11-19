# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Project Knowledge Summary]
- Date: 2026-11-17
- Context: Discovered by Agent while performing QQ official bot webhook service setup
- Category: Build Methods
- Instructions:
  - Install dependencies: `python3 -m pip install --break-system-packages -r requirements.txt`
  - Start webhook server: `python3 app.py` (binds `127.0.0.1:8080` and `127.0.0.1:8443`)
  - Baota reverse proxy `443`/`8080`/`8443` -> `http://127.0.0.1:8080`
  - Health check: `GET /health`
  - Webhook callback path: `POST /webhook`
  - Tests: `python3 -m pytest -q`

[User Instruction Summary]
- Date: 2026-11-17
- Context: QQ 官方机器人部署方式
- Instructions:
  - 开放平台回调地址后缀固定为 `/webhook`
  - 生产环境按宝塔「Python 项目管理器」部署，启动文件用 `app.py`，程序端口 `8080`
  - 回调地址 `https://qqbot.anzixi.cn/webhook`
  - GitHub 仓库只要 `main`

[User Instruction Summary]
- Date: 2026-11-19
- Context: 清理回调接入与指令文案
- Instructions:
  - 回调接入只保留 QQ 官方 Webhook 协议，不要加预览端口、密钥诊断或写死的回调地址

[Project Knowledge Summary]
- Date: 2026-11-19
- Context: Discovered by Agent while comparing QQ OpenAPI v2 send/receive docs
- Category: Troubleshooting & Debugging
- Instructions:
  - Message replies send only `msg_id` from event `d.id`. `event_id` is the outer payload `id` and is mutually exclusive; only INTERACTION_CREATE / GROUP_ADD_ROBOT / GROUP_MSG_RECEIVE / C2C_MSG_RECEIVE / FRIEND_ADD may use `event_id`
  - Token URL is `POST https://api.bot.qq.com/app/getAppAccessToken`; send host is `https://api.bot.qq.com`
  - Console tape: received not increasing means webhook miss; `回复失败` plus `err_code`/`trace=` is OpenAPI reject; `11298` is IP whitelist
  - Protocol notes live in `.monkeycode/docs/qq-openapi-v2.md`
