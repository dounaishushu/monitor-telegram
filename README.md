# Telegram 群监听机器人

## 功能说明

🍻 **关键词设置** - 管理监听的关键词
🥬 **加入目标群组** - 让监听者加入群组  
💕 **查看状态** - 查看当前监听状态
🧘 **管理员设置** - 设置普通管理员

## 环境要求

- Python 3.8+
- SQLite3

## 安装步骤

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置机器人：
   - 复制 `config.example.py` 为 `config.py`
   - 填入你的 Bot Token 和管理员 ID

3. 运行机器人：
```bash
python main.py
```

## 获取 Bot Token

1. 在 Telegram 中找到 @BotFather
2. 发送 `/newbot` 创建新机器人
3. 按提示设置机器人名称和用户名
4. 获取 API Token

## 获取用户 ID

1. 在 Telegram 中找到 @userinfobot
2. 发送任意消息即可获取你的用户 ID
