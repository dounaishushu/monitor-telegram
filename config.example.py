# -*- coding: utf-8 -*-
"""
配置文件示例
请复制此文件为 config.py 并填入你的配置
"""

# Telegram Bot Token (从 @BotFather 获取)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# 超级管理员ID列表 (从 @userinfobot 获取你的ID)
SUPER_ADMINS = [
    123456789,  # 替换为你的用户ID
]

# ========== 监听者账号配置 (用于自动加群) ==========
# 从 https://my.telegram.org 获取
API_ID = 12345678  # 替换为你的 API ID
API_HASH = "your_api_hash_here"  # 替换为你的 API Hash

# 监听者账号手机号 (带国际区号，如 +8613812345678)
LISTENER_PHONE = "+8613812345678"

# Session 文件路径
SESSION_PATH = "data/listener.session"

# 数据库路径
DATABASE_PATH = "data/bot.db"

# 日志配置
LOG_LEVEL = "INFO"
LOG_FILE = "data/bot.log"

# 通知设置
NOTIFY_ADMINS = True  # 是否通知管理员（默认开启）
NOTIFY_SUPER_ONLY = False  # 是否只通知超级管理员（False=通知所有管理员）

# 监听设置
MAX_KEYWORDS = 100  # 最大关键词数量
MAX_GROUPS = 50     # 最大监听群组数量

# 消息模板
WELCOME_MESSAGE = """
🎉 <b>欢迎使用群监听抓取机器人！</b>

📋 <b>功能说明：</b>

🍻 <b>关键词设置</b> - 管理监听的关键词
🥬 <b>加入目标群组</b> - 让监听者加入群组
💕 <b>查看状态</b> - 查看当前监听状态
🧘 <b>管理员设置</b> - 设置普通管理员

━━━━━━━━━━━━━━━━
💡 点击下方按钮开始使用
"""
