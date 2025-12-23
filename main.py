# -*- coding: utf-8 -*-
"""
Telegram 群监听机器人 - 主程序
"""
import logging
import asyncio
import os
import sys

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode, ChatMemberStatus

# 导入配置
try:
    from config import *
except ImportError:
    print("❌ 配置文件不存在！请复制 config.example.py 为 config.py 并填入配置")
    sys.exit(1)

from database import Database
from handlers import keyword_handlers, group_handlers, admin_handlers
from listener_client import get_listener_client, init_listener_client, ListenerClient

# 配置日志
os.makedirs('data', exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化数据库
db = Database(DATABASE_PATH)

# 用户状态存储 (用于登录流程)
user_states = {}

# 全局 Bot Application 实例
bot_app = None


def is_super_admin(user_id: int) -> bool:
    """检查是否是超级管理员"""
    return user_id in SUPER_ADMINS


async def is_admin(user_id: int) -> bool:
    """检查是否是管理员（包括超级管理员）"""
    if is_super_admin(user_id):
        return True
    return await db.is_admin(user_id)


# ========== 主菜单 ==========

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """获取主菜单键盘"""
    keyboard = [
        [
            InlineKeyboardButton("🍻 关键词设置", callback_data="menu_keywords"),
            InlineKeyboardButton("🥬 监听群组", callback_data="menu_groups")
        ],
        [
            InlineKeyboardButton("🔗 加入群组", callback_data="menu_join_group"),
            InlineKeyboardButton("💕 查看状态", callback_data="menu_status")
        ],
        [
            InlineKeyboardButton("⚙️ 设置中心", callback_data="menu_settings"),
            InlineKeyboardButton("👤 个人信息", callback_data="menu_myinfo")
        ],
    ]
    
    # 只有管理员才能看到管理员设置
    if is_super_admin(user_id):
        keyboard.append([InlineKeyboardButton("🧘 管理员设置", callback_data="menu_admins")])
        keyboard.append([InlineKeyboardButton("👤 监听者设置", callback_data="menu_listener")])
    
    keyboard.append([InlineKeyboardButton("📊 查看统计", callback_data="menu_stats")])
    
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user = update.effective_user
    user_id = user.id
    
    # 检查权限
    if not await is_admin(user_id):
        await update.message.reply_text(
            "⚠️ 您没有权限使用此机器人。\n\n请联系管理员获取权限。"
        )
        return
    
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(user_id)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    help_text = """
📖 <b>使用帮助</b>

<b>基础命令：</b>
/start - 显示主菜单
/help - 显示帮助信息
/status - 查看当前状态

<b>关键词管理：</b>
/addkw 「关键词」 - 添加关键词
/delkw 「关键词」 - 删除关键词
/listkw - 查看所有关键词

<b>群组管理：</b>
机器人加入群组后会自动开始监听
/listgroups - 查看监听的群组
/delgroup 「群组ID」 - 停止监听某群组

<b>管理员命令：</b>
/addadmin 「用户ID」 - 添加管理员
/deladmin 「用户ID」 - 删除管理员
/listadmins - 查看管理员列表

<b>其他：</b>
/stats - 查看统计数据
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def kw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /kw 命令 - 关键词设置"""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id):
        await update.message.reply_text("⚠️ 您没有权限执行此操作")
        return
    
    keywords = await db.get_keywords(active_only=False)
    
    kw_text = """📝 <b>关键词设置</b>

━━━━━━━━━━━━━━━━
<b>当前关键词列表：</b>

"""
    
    if keywords:
        for i, kw in enumerate(keywords[:20], 1):
            status = "✅" if kw['is_active'] else "❌"
            kw_text += f"{status} {kw['keyword']} <i>({kw['hit_count']}次)</i>\n"
        if len(keywords) > 20:
            kw_text += f"\n... 还有 {len(keywords) - 20} 个关键词"
    else:
        kw_text += "暂无关键词\n"
    
    kw_text += """
━━━━━━━━━━━━━━━━
<b>使用方法：</b>
• /addkw 「关键词」 - 添加关键词
• /delkw 「关键词」 - 删除关键词
• /listkw - 查看所有关键词
"""
    
    keyboard = [
        [InlineKeyboardButton("🍻 关键词管理", callback_data="menu_keywords")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        kw_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def listen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /listen 命令 - 推送位置设置"""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id):
        await update.message.reply_text("⚠️ 您没有权限执行此操作")
        return
    
    groups = await db.get_groups()
    
    listen_text = """📡 <b>推送位置设置</b>

━━━━━━━━━━━━━━━━
<b>当前监听的群组/频道：</b>

"""
    
    if groups:
        for group in groups[:15]:
            status = "🟢" if group['is_active'] else "🔴"
            title = group['title'] or str(group['chat_id'])
            listen_text += f"{status} {title}\n"
        if len(groups) > 15:
            listen_text += f"\n... 还有 {len(groups) - 15} 个群组"
    else:
        listen_text += "暂无监听群组\n"
    
    listen_text += """
━━━━━━━━━━━━━━━━
<b>使用方法：</b>
• 通过「加入群组」添加新的监听目标
• /listgroups - 查看所有监听群组
• /delgroup 「群组ID」 - 停止监听某群组
"""
    
    keyboard = [
        [InlineKeyboardButton("🔗 加入群组", callback_data="menu_join_group")],
        [InlineKeyboardButton("🥬 群组管理", callback_data="menu_groups")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        listen_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /status 命令"""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id):
        await update.message.reply_text("⚠️ 您没有权限执行此操作")
        return
    
    stats = await db.get_stats()
    keywords = await db.get_keywords()
    groups = await db.get_groups()
    
    status_text = f"""
💕 <b>当前监听状态</b>

━━━━━━━━━━━━━━━━
📊 <b>统计概览</b>

🔑 监听关键词：<b>{stats['keyword_count']}</b> 个
📝 关键词命中：<b>{stats['keyword_hits']}</b> 次
👥 监听群组：<b>{stats['group_count']}</b> 个
💬 处理消息：<b>{stats['total_messages']}</b> 条
✅ 匹配消息：<b>{stats['matched_messages']}</b> 条
👮 管理员数：<b>{stats['admin_count']}</b> 人

━━━━━━━━━━━━━━━━
🔑 <b>关键词列表</b>（前10个）

"""
    
    if keywords:
        for i, kw in enumerate(keywords[:10]):
            status = "✅" if kw['is_active'] else "❌"
            status_text += f"{status} {kw['keyword']} ({kw['hit_count']}次)\n"
    else:
        status_text += "暂无关键词\n"
    
    status_text += f"""
━━━━━━━━━━━━━━━━
👥 <b>监听群组</b>（前5个）

"""
    
    if groups:
        for group in groups[:5]:
            status_text += f"• {group['title'] or group['chat_id']}\n"
    else:
        status_text += "暂无监听群组\n"
    
    await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /stats 命令"""
    await status_command(update, context)


# ========== 设置中心 ==========

async def show_settings_menu(query, user_id: int):
    """显示设置中心菜单"""
    settings = await db.get_all_system_settings()
    
    # 获取当前设置状态
    push_enabled = settings.get('push_enabled', 'true') == 'true'
    keyword_mode = settings.get('keyword_match_mode', 'fuzzy')  # exact/fuzzy
    blacklist_mode = settings.get('blacklist_match_mode', 'exact')
    filter_ad = settings.get('filter_ad_users', 'false') == 'true'
    attach_history = settings.get('attach_search_history', 'false') == 'true'
    no_repeat = settings.get('no_repeat_duration', '0')
    
    # 构建文本
    menu_text = """⚙️ <b>设置中心</b>

关键词设置请点 /kw
推送位置设置请使用 /listen

其他设置请点击下方按钮操作!"""
    
    # 1. 机器人推送状态
    keyboard = [
        [InlineKeyboardButton("━━━ 1. 机器人推送状态 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 开启推送" if push_enabled else "开启推送", callback_data="setting_push_on"),
            InlineKeyboardButton("关闭推送" if push_enabled else "✔ 关闭推送", callback_data="setting_push_off")
        ],
        
        # 2. 关键词匹配模式
        [InlineKeyboardButton("━━━ 2. 关键词匹配模式 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 精确匹配" if keyword_mode == 'exact' else "精确匹配", callback_data="setting_kw_exact"),
            InlineKeyboardButton("✔ 模糊匹配" if keyword_mode == 'fuzzy' else "模糊匹配", callback_data="setting_kw_fuzzy")
        ],
        
        # 3. 关键词黑名单匹配模式
        [InlineKeyboardButton("━━━ 3. 关键词黑名单匹配模式 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 精确匹配" if blacklist_mode == 'exact' else "精确匹配", callback_data="setting_bl_exact"),
            InlineKeyboardButton("✔ 模糊匹配" if blacklist_mode == 'fuzzy' else "模糊匹配", callback_data="setting_bl_fuzzy")
        ],
        
        # 4. 智能过滤广告用户
        [InlineKeyboardButton("━━━ 4. 智能过滤广告用户 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 过滤" if filter_ad else "过滤", callback_data="setting_filter_on"),
            InlineKeyboardButton("✔ 不过滤" if not filter_ad else "不过滤", callback_data="setting_filter_off")
        ],
        
        # 5. 消息推送是否附带7天内搜索记录
        [InlineKeyboardButton("━━━ 5. 消息推送是否附带7天内搜索记录 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 附带" if attach_history else "附带", callback_data="setting_history_on"),
            InlineKeyboardButton("✔ 不附带" if not attach_history else "不附带", callback_data="setting_history_off")
        ],
        
        # 6. 同一用户多久内不重复推送
        [InlineKeyboardButton("━━━ 6. 同一用户多久内不重复推送 ━━━", callback_data="ignore")],
        [
            InlineKeyboardButton("✔ 10分钟" if no_repeat == '10' else "10分钟", callback_data="setting_repeat_10"),
            InlineKeyboardButton("✔ 30分钟" if no_repeat == '30' else "30分钟", callback_data="setting_repeat_30"),
            InlineKeyboardButton("✔ 1小时" if no_repeat == '60' else "1小时", callback_data="setting_repeat_60"),
            InlineKeyboardButton("✔ 12小时" if no_repeat == '720' else "12小时", callback_data="setting_repeat_720")
        ],
        [
            InlineKeyboardButton("✔ 1天" if no_repeat == '1440' else "1天", callback_data="setting_repeat_1440"),
            InlineKeyboardButton("✔ 15天" if no_repeat == '21600' else "15天", callback_data="setting_repeat_21600"),
            InlineKeyboardButton("✔ 30天" if no_repeat == '43200' else "30天", callback_data="setting_repeat_43200"),
            InlineKeyboardButton("✔ 不限制" if no_repeat == '0' else "不限制", callback_data="setting_repeat_0")
        ],
        
        # 返回按钮
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        menu_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_setting_callback(query, data: str, user_id: int):
    """处理设置项回调"""
    setting_map = {
        # 推送状态
        'setting_push_on': ('push_enabled', 'true'),
        'setting_push_off': ('push_enabled', 'false'),
        # 关键词匹配模式
        'setting_kw_exact': ('keyword_match_mode', 'exact'),
        'setting_kw_fuzzy': ('keyword_match_mode', 'fuzzy'),
        # 黑名单匹配模式
        'setting_bl_exact': ('blacklist_match_mode', 'exact'),
        'setting_bl_fuzzy': ('blacklist_match_mode', 'fuzzy'),
        # 过滤广告用户
        'setting_filter_on': ('filter_ad_users', 'true'),
        'setting_filter_off': ('filter_ad_users', 'false'),
        # 附带搜索记录
        'setting_history_on': ('attach_search_history', 'true'),
        'setting_history_off': ('attach_search_history', 'false'),
        # 不重复推送时间
        'setting_repeat_10': ('no_repeat_duration', '10'),
        'setting_repeat_30': ('no_repeat_duration', '30'),
        'setting_repeat_60': ('no_repeat_duration', '60'),
        'setting_repeat_720': ('no_repeat_duration', '720'),
        'setting_repeat_1440': ('no_repeat_duration', '1440'),
        'setting_repeat_21600': ('no_repeat_duration', '21600'),
        'setting_repeat_43200': ('no_repeat_duration', '43200'),
        'setting_repeat_0': ('no_repeat_duration', '0'),
    }
    
    if data in setting_map:
        key, value = setting_map[data]
        await db.set_system_setting(key, value)
        await query.answer("✅ 设置已更新")
        # 刷新设置菜单
        await show_settings_menu(query, user_id)
    else:
        await query.answer("未知设置项")


# ========== 回调处理 ==========

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not await is_admin(user_id):
        await query.edit_message_text("⚠️ 您没有权限执行此操作")
        return
    
    data = query.data
    
    if data == "menu_keywords":
        await keyword_handlers.show_keywords_menu(query, db)
    
    elif data == "menu_groups":
        await group_handlers.show_groups_menu(query, db)
    
    elif data == "menu_status":
        stats = await db.get_stats()
        status_text = f"""
💕 <b>当前监听状态</b>

🔑 监听关键词：<b>{stats['keyword_count']}</b> 个
📝 关键词命中：<b>{stats['keyword_hits']}</b> 次
👥 监听群组：<b>{stats['group_count']}</b> 个
💬 处理消息：<b>{stats['total_messages']}</b> 条
✅ 匹配消息：<b>{stats['matched_messages']}</b> 条

━━━━━━━━━━━━━━━━
机器人运行正常 ✅
"""
        keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]]
        await query.edit_message_text(
            status_text, 
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_myinfo":
        # 个人信息 - 显示当前用户自己的信息
        user = query.from_user
        username = user.username or "无"
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "未知"
        
        myinfo_text = f"""👤 <b>个人信息</b>

━━━━━━━━━━━━━━━━
🆔 <b>用户ID:</b> <code>{user_id}</code>

👤 <b>昵称:</b> {full_name}

📛 <b>用户名:</b> @{username}

📎 点击复制ID: <code>{user_id}</code>
━━━━━━━━━━━━━━━━
💡 您可以将用户ID发送给管理员以获取权限"""
        
        keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]]
        await query.edit_message_text(
            myinfo_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_settings" or data == "back_settings":
        # 设置中心菜单
        await show_settings_menu(query, user_id)
    
    elif data.startswith("setting_"):
        # 处理设置项切换
        await handle_setting_callback(query, data, user_id)
    
    elif data == "menu_notify":
        # 通知设置菜单
        settings = await db.get_user_settings(user_id)
        notify_enabled = settings.get('notify_enabled', True)
        
        notify_status = "✅ 已开启" if notify_enabled else "❌ 已关闭"
        
        notify_text = f"""
🔔 <b>通知设置</b>

━━━━━━━━━━━━━━━━
<b>当前状态：</b>{notify_status}

<b>功能说明：</b>
开启后，当监听的群组中有消息匹配
关键词时，机器人会私聊通知您

━━━━━━━━━━━━━━━━
💡 点击下方按钮切换通知状态
"""
        toggle_text = "❌ 关闭通知" if notify_enabled else "✅ 开启通知"
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data="notify_toggle")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
        ]
        await query.edit_message_text(
            notify_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "notify_toggle":
        # 切换通知状态
        settings = await db.get_user_settings(user_id)
        current = settings.get('notify_enabled', True)
        await db.set_user_setting(user_id, 'notify_enabled', not current)
        
        new_status = "✅ 已开启" if not current else "❌ 已关闭"
        await query.answer(f"通知{new_status}")
        
        # 刷新菜单
        notify_text = f"""
🔔 <b>通知设置</b>

━━━━━━━━━━━━━━━━
<b>当前状态：</b>{new_status}

<b>功能说明：</b>
开启后，当监听的群组中有消息匹配
关键词时，机器人会私聊通知您

━━━━━━━━━━━━━━━━
💡 点击下方按钮切换通知状态
"""
        toggle_text = "❌ 关闭通知" if not current else "✅ 开启通知"
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data="notify_toggle")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
        ]
        await query.edit_message_text(
            notify_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_admins":
        if not is_super_admin(user_id):
            await query.edit_message_text("⚠️ 只有超级管理员才能管理管理员")
            return
        await admin_handlers.show_admins_menu(query, db)
    
    elif data == "menu_join_group":
        # 加入群组菜单
        client = await get_listener_client()
        if not client:
            await query.edit_message_text(
                "⚠️ <b>监听者未配置</b>\n\n"
                "请先在 config.py 中配置 API_ID、API_HASH 和 LISTENER_PHONE",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="back_main")]])
            )
            return
        
        if not client.is_connected():
            success = await client.connect()
            if not success:
                await query.edit_message_text(
                    "🔗 <b>加入群组</b>\n\n"
                    "⚠️ 监听者账号未登录\n\n"
                    "请先在「👤 监听者设置」中完成登录",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("👤 去登录", callback_data="menu_listener")],
                        [InlineKeyboardButton("🔙 返回", callback_data="back_main")]
                    ])
                )
                return
        
        me = await client.get_me()
        account_info = f"@{me['username']}" if me and me.get('username') else me['first_name'] if me else "未知"
        
        await query.edit_message_text(
            f"🔗 <b>加入群组</b>\n\n"
            f"当前监听者：{account_info}\n\n"
            f"请直接发送群组/频道链接给我\n"
            f"支持的格式：\n"
            f"• t.me/username\n"
            f"• t.me/+xxxxx\n"
            f"• t.me/joinchat/xxxxx\n\n"
            f"💡 发送链接后监听者会自动加入",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]])
        )
        user_states[user_id] = 'waiting_group_link'
    
    elif data == "menu_listener":
        # 监听者设置菜单
        if not is_super_admin(user_id):
            await query.edit_message_text("⚠️ 只有超级管理员才能设置监听者")
            return
        
        client = await get_listener_client()
        if not client:
            await query.edit_message_text(
                "👤 <b>监听者设置</b>\n\n"
                "⚠️ 配置不完整\n\n"
                "请在 config.py 中配置：\n"
                "• API_ID\n"
                "• API_HASH\n"
                "• LISTENER_PHONE\n\n"
                "获取方式： https://my.telegram.org",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="back_main")]])
            )
            return
        
        connected = await client.connect()
        me = await client.get_me() if connected else None
        
        if me:
            listening_status = "🔊 监听中" if client.is_listening() else "⏸️ 未监听"
            status_text = f"""
👤 <b>监听者设置</b>

━━━━━━━━━━━━━━━━
✅ <b>已登录</b>

👤 账号：{me['first_name']} {me.get('last_name', '')}
📱 手机：{me.get('phone', '未知')}
🆔 用户名：@{me.get('username', '无')}
📡 状态：{listening_status}

监听者账号已就绪，可以自动加入群组
"""
            keyboard = [
                [InlineKeyboardButton("🔄 同步群组", callback_data="listener_sync_groups")],
                [InlineKeyboardButton("🔊 开始监听" if not client.is_listening() else "⏸️ 停止监听", callback_data="listener_toggle_listen")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
            ]
        else:
            status_text = """
👤 <b>监听者设置</b>

━━━━━━━━━━━━━━━━
❌ <b>未登录</b>

请点击下方按钮开始登录流程
"""
            keyboard = [
                [InlineKeyboardButton("📲 发送验证码", callback_data="listener_send_code")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
            ]
        
        await query.edit_message_text(
            status_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "listener_send_code":
        # 发送验证码
        if not is_super_admin(user_id):
            return
        
        client = await get_listener_client()
        if not client:
            await query.answer("监听者未配置", show_alert=True)
            return
        
        await query.answer("正在发送验证码...")
        success, msg = await client.send_code()
        
        if success:
            user_states[user_id] = 'waiting_listener_code'
            await query.edit_message_text(
                f"📲 <b>验证码已发送</b>\n\n"
                f"{msg}\n\n"
                f"请直接回复验证码（纯数字）",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="menu_listener")]])
            )
        else:
            await query.edit_message_text(
                f"❌ <b>发送失败</b>\n\n{msg}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_listener")]])
            )
    
    elif data == "listener_sync_groups":
        # 同步群组
        if not is_super_admin(user_id):
            return
        
        client = await get_listener_client()
        if not client or not client.is_connected():
            await query.answer("监听者未登录", show_alert=True)
            return
        
        await query.answer("正在同步...")
        await query.edit_message_text("⏳ 正在同步群组列表...", parse_mode=ParseMode.HTML)
        
        client.set_database(db)
        added, updated = await client.sync_dialogs_to_db()
        
        await query.edit_message_text(
            f"✅ <b>同步完成</b>\n\n"
            f"📁 新增群组：{added} 个\n"
            f"🔄 更新群组：{updated} 个\n"
            f"📊 总计：{added + updated} 个",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_listener")]])
        )
    
    elif data == "listener_toggle_listen":
        # 切换监听状态
        if not is_super_admin(user_id):
            return
        
        client = await get_listener_client()
        if not client or not client.is_connected():
            await query.answer("监听者未登录", show_alert=True)
            return
        
        if client.is_listening():
            await client.stop_listening()
            await query.answer("已停止监听")
        else:
            client.set_database(db)
            client.set_keyword_callback(on_keyword_match)
            await client.start_listening()
            await query.answer("已开始监听")
        
        # 刷新监听者设置页面
        me = await client.get_me()
        listening_status = "🔊 监听中" if client.is_listening() else "⏸️ 未监听"
        status_text = f"""
👤 <b>监听者设置</b>

━━━━━━━━━━━━━━━━
✅ <b>已登录</b>

👤 账号：{me['first_name']} {me.get('last_name', '')}
📱 手机：{me.get('phone', '未知')}
🆔 用户名：@{me.get('username', '无')}
📡 状态：{listening_status}

监听者账号已就绪，可以自动加入群组
"""
        keyboard = [
            [InlineKeyboardButton("🔄 同步群组", callback_data="listener_sync_groups")],
            [InlineKeyboardButton("🔊 开始监听" if not client.is_listening() else "⏸️ 停止监听", callback_data="listener_toggle_listen")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]
        ]
        await query.edit_message_text(status_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_stats":
        stats = await db.get_stats()
        stats_text = f"""
📊 <b>详细统计数据</b>

━━━━━━━━━━━━━━━━
<b>关键词统计</b>
• 总关键词数：{stats['keyword_count']} 个
• 总命中次数：{stats['keyword_hits']} 次

<b>群组统计</b>
• 监听群组数：{stats['group_count']} 个
• 处理消息数：{stats['total_messages']} 条

<b>匹配统计</b>
• 匹配消息数：{stats['matched_messages']} 条
• 管理员数量：{stats['admin_count']} 人
━━━━━━━━━━━━━━━━
"""
        keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")]]
        await query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "back_main":
        await query.edit_message_text(
            WELCOME_MESSAGE,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    # 关键词相关回调
    elif data.startswith("kw_"):
        await keyword_handlers.handle_callback(query, data, db, user_id)
    
    # 群组相关回调
    elif data.startswith("grp_"):
        await group_handlers.handle_callback(query, data, db, user_id)
    
    # 管理员相关回调
    elif data.startswith("adm_"):
        if not is_super_admin(user_id):
            await query.edit_message_text("⚠️ 只有超级管理员才能执行此操作")
            return
        await admin_handlers.handle_callback(query, data, db, user_id)
    
    # 消息通知按钮回调
    elif data.startswith("msg_history_"):
        # 查看用户历史消息
        target_user_id = int(data[12:])
        messages = await db.get_user_messages(target_user_id, limit=10)
        
        if not messages:
            await query.answer("该用户暂无历史记录", show_alert=True)
            return
        
        history_text = f"📜 <b>用户历史记录</b> (ID: {target_user_id})\n\n"
        for i, msg in enumerate(messages, 1):
            history_text += f"{i}. [{msg['matched_keyword']}] {msg['content'][:50]}...\n"
            history_text += f"   ⏰ {msg['created_at']}\n\n"
        
        await query.answer()
        await query.message.reply_text(history_text, parse_mode=ParseMode.HTML)
    
    elif data.startswith("msg_delete_"):
        # 删除消息记录
        parts = data.split("_")
        msg_id = int(parts[2])
        chat_id = int(parts[3])
        
        # 从数据库删除记录
        await db.delete_message_by_id(msg_id, chat_id)
        await query.answer("✅ 已删除该消息记录")
        
        # 删除通知消息
        try:
            await query.message.delete()
        except:
            pass
    
    elif data.startswith("msg_block_"):
        # 屏蔽用户
        target_user_id = int(data[10:])
        success = await db.block_user(target_user_id)
        
        if success:
            await query.answer("✅ 已屏蔽该用户，将不再接收其消息通知", show_alert=True)
        else:
            await query.answer("该用户已在屏蔽列表中", show_alert=True)
    
    elif data.startswith("msg_userinfo_"):
        # 获取用户个人信息
        target_user_id = int(data[13:])
        
        # 构建用户信息文本
        userinfo_text = f"""👤 <b>用户个人信息</b>

━━━━━━━━━━━━━━━━
🆔 <b>用户ID:</b> <code>{target_user_id}</code>

📎 点击复制ID: <code>{target_user_id}</code>

🔗 用户链接: <a href="tg://user?id={target_user_id}">点击查看用户</a>
━━━━━━━━━━━━━━━━"""
        
        await query.answer()
        await query.message.reply_text(userinfo_text, parse_mode=ParseMode.HTML)


# ========== 自动监听群组 ==========

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """追踪机器人加入/离开群组"""
    result = update.my_chat_member
    if not result:
        return
    
    chat = result.chat
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    
    # 只处理群组
    if chat.type not in ['group', 'supergroup']:
        return
    
    # 机器人被添加到群组
    if new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        if old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, None]:
            # 自动添加群组到监听列表
            await db.add_group(
                chat_id=chat.id,
                title=chat.title,
                username=chat.username
            )
            logger.info(f"自动添加监听群组: {chat.title} ({chat.id})")
            
            # 通知超级管理员
            for admin_id in SUPER_ADMINS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"✅ 已自动加入并开始监听群组：\n\n"
                             f"群组名称：{chat.title}\n"
                             f"群组ID：<code>{chat.id}</code>",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
    
    # 机器人被移出群组
    elif new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
        if old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
            # 从监听列表移除
            await db.remove_group(chat.id)
            logger.info(f"已从监听列表移除群组: {chat.title} ({chat.id})")


# ========== 私聊消息处理 ==========

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理私聊消息（群组链接、验证码等）"""
    message = update.message
    if not message or not message.text:
        return
    
    chat = message.chat
    user = message.from_user
    text = message.text.strip()
    
    # 只处理私聊消息
    if chat.type != 'private':
        return
    
    # 检查权限
    if not await is_admin(user.id):
        return
    
    user_state = user_states.get(user.id)
    
    # 处理监听者验证码
    if user_state == 'waiting_listener_code':
        if text.isdigit():
            client = await get_listener_client()
            if client:
                success, msg = await client.verify_code(text)
                
                if success:
                    user_states.pop(user.id, None)
                    
                    # 登录成功后自动同步群组并启动监听
                    client.set_database(db)
                    client.set_keyword_callback(on_keyword_match)
                    
                    sync_msg = await message.reply_text("⏳ 正在同步群组列表...")
                    added, updated = await client.sync_dialogs_to_db()
                    await client.start_listening()
                    
                    await sync_msg.edit_text(
                        f"✅ <b>登录成功</b>\n\n{msg}\n\n"
                        f"📁 已同步 {added + updated} 个群组/频道\n"
                        f"🔊 已开始监听消息\n\n"
                        f"现在可以使用「🔗 加入群组」功能了",
                        parse_mode=ParseMode.HTML
                    )
                elif '两步验证' in msg:
                    user_states[user.id] = 'waiting_listener_2fa'
                    await message.reply_text(
                        f"🔐 <b>需要两步验证</b>\n\n请输入您的两步验证密码",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(f"❌ {msg}\n\n请重新输入验证码")
        else:
            await message.reply_text("请输入纯数字验证码")
        return
    
    # 处理两步验证密码
    if user_state == 'waiting_listener_2fa':
        client = await get_listener_client()
        if client:
            success, msg = await client.verify_2fa(text)
            
            if success:
                user_states.pop(user.id, None)
                
                # 登录成功后自动同步群组并启动监听
                client.set_database(db)
                client.set_keyword_callback(on_keyword_match)
                
                sync_msg = await message.reply_text("⏳ 正在同步群组列表...")
                added, updated = await client.sync_dialogs_to_db()
                await client.start_listening()
                
                await sync_msg.edit_text(
                    f"✅ <b>登录成功</b>\n\n{msg}\n\n"
                    f"📁 已同步 {added + updated} 个群组/频道\n"
                    f"🔊 已开始监听消息\n\n"
                    f"现在可以使用「🔗 加入群组」功能了",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(f"❌ {msg}\n\n请重新输入密码")
        return
    
    # 处理群组链接
    if user_state == 'waiting_group_link' or 't.me/' in text.lower():
        # 检查是否是群组链接
        if 't.me/' in text.lower():
            client = await get_listener_client()
            
            if not client:
                await message.reply_text("⚠️ 监听者未配置，无法自动加群")
                return
            
            if not client.is_connected():
                success = await client.connect()
                if not success:
                    await message.reply_text(
                        "⚠️ 监听者未登录\n\n"
                        "请先在「👤 监听者设置」中完成登录"
                    )
                    return
            
            await message.reply_text("✅ 正在加入群组，请稍候...")
            
            success, msg, chat_info = await client.join_chat(text)
            
            if success:
                # 添加到数据库
                if chat_info:
                    # 转换为完整的 chat_id 格式
                    full_chat_id = -1000000000000 - chat_info['id'] if chat_info['id'] > 0 else chat_info['id']
                    if not str(full_chat_id).startswith('-100'):
                        full_chat_id = int(f"-100{abs(chat_info['id'])}")
                    
                    await db.add_group(
                        chat_id=full_chat_id,
                        title=chat_info.get('title', '未知'),
                        username=chat_info.get('username')
                    )
                
                await message.reply_text(
                    f"✅ <b>加入成功</b>\n\n{msg}\n\n"
                    f"已自动添加到监听列表",
                    parse_mode=ParseMode.HTML
                )
                user_states.pop(user.id, None)
            else:
                await message.reply_text(
                    f"❌ <b>加入失败</b>\n\n{msg}",
                    parse_mode=ParseMode.HTML
                )
        return


# ========== 消息监听 ==========

async def monitor_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """监听群消息"""
    message = update.message
    if not message or not message.text:
        return
    
    chat = message.chat
    user = message.from_user
    
    # 只监听群组消息
    if chat.type not in ['group', 'supergroup']:
        return
    
    # 检查是否是监听的群组
    if not await db.is_monitored_group(chat.id):
        # 自动添加新群组（备用逻辑）
        await db.add_group(
            chat_id=chat.id,
            title=chat.title,
            username=chat.username
        )
    
    # 检查发送者是否被屏蔽
    if user and await db.is_blocked(user.id):
        return
    
    # 更新群组消息计数
    await db.update_group_stats(chat.id, message_count=1)
    
    # 获取关键词列表
    keywords = await db.get_keywords()
    if not keywords:
        return
    
    text = message.text.lower()
    
    # 检查关键词匹配
    for kw in keywords:
        keyword = kw['keyword']
        matched = False
        
        if kw['match_type'] == 'exact':
            matched = text == keyword
        elif kw['match_type'] == 'startswith':
            matched = text.startswith(keyword)
        else:  # contains
            matched = keyword in text
        
        if matched:
            # 更新统计
            await db.increment_keyword_hit(keyword)
            await db.update_group_stats(chat.id, hit_count=1)
            
            # 保存消息
            await db.save_message(
                chat_id=chat.id,
                message_id=message.message_id,
                user_id=user.id if user else 0,
                username=user.username if user else None,
                content=message.text[:500],
                matched_keyword=keyword
            )
            
            # 转发消息到目标
            logger.info(f"Bot API 关键词匹配: [{keyword}] 群组={chat.title}")
            await forward_matched_message(context, message, keyword)
            
            logger.info(f"关键词匹配: [{keyword}] 群组: {chat.title} 用户: {user.username if user else 'Unknown'}")
            break


async def forward_matched_message(context: ContextTypes.DEFAULT_TYPE, message, keyword: str):
    """转发匹配的消息给管理员"""
    
    def clean_text(text: str) -> str:
        """清理无效的 Unicode 字符"""
        if not text:
            return ''
        try:
            cleaned = text.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
            cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8')
            return cleaned
        except:
            return ''.join(c for c in text if ord(c) < 0x10000)
    
    # 获取所有管理员
    all_admin_ids = set(SUPER_ADMINS)
    
    admins = await db.get_admins()
    for admin in admins:
        all_admin_ids.add(admin['user_id'])
    
    if not all_admin_ids:
        return
    
    user = message.from_user
    chat = message.chat
    
    # 构建通知消息
    username_display = f"@{user.username}" if user and user.username else "无用户名"
    user_name = clean_text(user.first_name) if user and user.first_name else "未知"
    if user and user.last_name:
        user_name += f" {clean_text(user.last_name)}"
    
    # 构建群组链接
    chat_title = clean_text(chat.title) if chat.title else str(chat.id)
    if chat.username:
        group_link = f"https://t.me/{chat.username}"
        group_display = f"<a href='{group_link}'>{chat_title}</a>"
    else:
        group_link = f"https://t.me/c/{str(chat.id)[4:]}/1" if str(chat.id).startswith('-100') else None
        if group_link:
            group_display = f"<a href='{group_link}'>{chat_title}</a>"
        else:
            group_display = chat_title
    
    # 用户链接
    if user and user.username:
        user_link = f"<a href='https://t.me/{user.username}'>{user_name}</a> ({username_display})"
    else:
        user_link = f"{user_name} ({username_display})"
    
    forward_text = f"""👤 用户：{user_link}
🔥 来源：{group_display}
📝 内容：{keyword}
🕐 时间：{message.date.strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━
🔥 历史记录：{clean_text(message.text[:200])}"""
    
    # 构建功能按钮
    user_id_for_btn = user.id if user else 0
    keyboard = [
        [
            InlineKeyboardButton("📜 历史", callback_data=f"msg_history_{user_id_for_btn}"),
            InlineKeyboardButton("🗑️ 删除", callback_data=f"msg_delete_{message.message_id}_{chat.id}"),
            InlineKeyboardButton("🚫 屏蔽", callback_data=f"msg_block_{user_id_for_btn}"),
        ],
        [
            InlineKeyboardButton("👤 个人信息", callback_data=f"msg_userinfo_{user_id_for_btn}"),
            InlineKeyboardButton("💬 私聊", url=f"https://t.me/{user.username}" if user and user.username else f"tg://user?id={user_id_for_btn}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 发送给开启通知的管理员
    for admin_id in all_admin_ids:
        try:
            settings = await db.get_user_settings(admin_id)
            if not settings.get('notify_enabled', True):
                continue
            
            # 清理整个消息文本
            safe_text = forward_text.encode('utf-8', errors='ignore').decode('utf-8')
            
            await context.bot.send_message(
                chat_id=admin_id,
                text=safe_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            logger.info(f"Bot API 通知发送成功: user_id={admin_id}")
        except Exception as e:
            logger.error(f"发送通知失败 (user_id={admin_id}): {e}")


# ========== 启动机器人 ==========

async def on_keyword_match(chat, sender, message, keyword: str, chat_id: int):
    """监听者客户端关键词匹配回调 - 发送通知"""
    global bot_app
    logger.info(f"回调被调用: 关键词={keyword}, bot_app={bot_app is not None}")
    
    if not bot_app:
        logger.error("回调失败: bot_app 未设置")
        return
    
    def clean_text(text: str) -> str:
        """清理无效的 Unicode 字符"""
        if not text:
            return ''
        # 先处理 surrogate 字符
        try:
            # 尝试编码为 utf-8，失败则替换
            cleaned = text.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
            # 移除无法编码的字符
            cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8')
            return cleaned
        except:
            # 最后的备用方案：只保留 ASCII 和常见字符
            return ''.join(c for c in text if ord(c) < 0x10000)
    
    try:
        # 获取用户信息
        user_id = sender.id if sender else 0
        username = getattr(sender, 'username', None)
        first_name = clean_text(getattr(sender, 'first_name', '') or '')
        last_name = clean_text(getattr(sender, 'last_name', '') or '')
        full_name = f"{first_name} {last_name}".strip() or '未知用户'
        
        # 用户链接
        if username:
            user_link = f'<a href="https://t.me/{username}">{full_name}</a>'
        else:
            user_link = f'<a href="tg://user?id={user_id}">{full_name}</a>'
        
        # 群组链接
        chat_title = clean_text(getattr(chat, 'title', '未知群组'))
        chat_username = getattr(chat, 'username', None)
        if chat_username:
            group_display = f'<a href="https://t.me/{chat_username}">{chat_title}</a>'
        else:
            group_display = f'{chat_title}'
        
        # 构建通知内容
        time_str = message.date.strftime('%Y-%m-%d %H:%M:%S') if message.date else ''
        msg_text = clean_text(message.text or '')
        content_preview = (msg_text[:200] + '...') if len(msg_text) > 200 else msg_text
        
        forward_text = f"""\ud83d\udc64 用户：{user_link}
\ud83d\udd25 来源：{group_display}
\ud83d\udcdd 内容：{keyword}
\ud83d\udd50 时间：{time_str}
━━━━━━━━━━━━━━━━━━
\ud83d\udd25 历史记录：{content_preview}"""
        
        # 功能按钮
        keyboard = []
        if username:
            keyboard.append([
                InlineKeyboardButton("\ud83d\udcdc 历史", callback_data=f"msg_history_{user_id}"),
                InlineKeyboardButton("\ud83d\uddd1\ufe0f 删除", callback_data=f"msg_delete_{message.id}_{chat_id}"),
                InlineKeyboardButton("\ud83d\udeab 屏蔽", callback_data=f"msg_block_{user_id}"),
            ])
            keyboard.append([
                InlineKeyboardButton("\ud83d\udc64 个人信息", callback_data=f"msg_userinfo_{user_id}"),
                InlineKeyboardButton("\ud83d\udcac 私聊", url=f"https://t.me/{username}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("\ud83d\udcdc 历史", callback_data=f"msg_history_{user_id}"),
                InlineKeyboardButton("\ud83d\uddd1\ufe0f 删除", callback_data=f"msg_delete_{message.id}_{chat_id}"),
                InlineKeyboardButton("\ud83d\udeab 屏蔽", callback_data=f"msg_block_{user_id}")
            ])
            keyboard.append([
                InlineKeyboardButton("\ud83d\udc64 个人信息", callback_data=f"msg_userinfo_{user_id}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 发送给所有管理员
        admins = await db.get_admins()
        for admin in admins:
            admin_id = admin['user_id']
            try:
                settings = await db.get_user_settings(admin_id)
                if not settings.get('notify_enabled', True):
                    continue
                
                # 清理整个消息文本
                safe_text = forward_text.encode('utf-8', errors='ignore').decode('utf-8')
                
                await bot_app.bot.send_message(
                    chat_id=admin_id,
                    text=safe_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                logger.info(f"通知发送成功: user_id={admin_id}")
            except Exception as e:
                logger.error(f"发送通知失败 (user_id={admin_id}): {e}")
        
        logger.info(f"监听者通知已发送: 关键词=[{keyword}] 群组={chat_title}")
        
    except Exception as e:
        logger.error(f"处理监听者通知失败: {e}")


async def post_init(application: Application):
    """初始化后执行"""
    global bot_app
    bot_app = application
    
    await db.init()
    
    for admin_id in SUPER_ADMINS:
        await db.add_admin(admin_id, role='super_admin')
    
    commands = [
        BotCommand("start", "显示主菜单"),
        BotCommand("help", "显示帮助信息"),
        BotCommand("status", "查看当前状态"),
        BotCommand("kw", "关键词设置"),
        BotCommand("listen", "推送位置设置"),
        BotCommand("addkw", "添加关键词"),
        BotCommand("delkw", "删除关键词"),
        BotCommand("listkw", "查看关键词列表"),
        BotCommand("listgroups", "查看监听的群组"),
        BotCommand("stats", "查看统计数据"),
    ]
    await application.bot.set_my_commands(commands)
    
    # 初始化监听者客户端
    try:
        listener = await get_listener_client()
        if listener:
            listener.set_database(db)
            listener.set_keyword_callback(on_keyword_match)
            
            success = await listener.connect()
            if success:
                # 自动同步群组并启动监听
                added, updated = await listener.sync_dialogs_to_db()
                logger.info(f"监听者同步群组: 新增 {added} 个，更新 {updated} 个")
                
                await listener.start_listening()
                logger.info("监听者客户端已启动")
            else:
                logger.info("监听者账号未登录，请通过机器人进行登录")
    except Exception as e:
        logger.error(f"初始化监听者失败: {e}")
    
    logger.info("机器人初始化完成")


def main():
    """主函数"""
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # 注册命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("kw", kw_command))
    application.add_handler(CommandHandler("listen", listen_command))
    
    # 关键词命令
    application.add_handler(CommandHandler("addkw", keyword_handlers.add_keyword_command))
    application.add_handler(CommandHandler("delkw", keyword_handlers.del_keyword_command))
    application.add_handler(CommandHandler("listkw", keyword_handlers.list_keywords_command))
    
    # 群组命令
    application.add_handler(CommandHandler("addgroup", group_handlers.add_group_command))
    application.add_handler(CommandHandler("delgroup", group_handlers.del_group_command))
    application.add_handler(CommandHandler("listgroups", group_handlers.list_groups_command))
    
    # 管理员命令
    application.add_handler(CommandHandler("addadmin", admin_handlers.add_admin_command))
    application.add_handler(CommandHandler("deladmin", admin_handlers.del_admin_command))
    application.add_handler(CommandHandler("listadmins", admin_handlers.list_admins_command))
    
    # 回调处理器
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # 监听机器人加入/离开群组（自动监听）
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # 私聊消息处理（群组链接、验证码等）
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_private_message
    ))
    
    # 群消息监听（放在最后，优先级最低）
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        monitor_message
    ))
    
    logger.info("🚀 机器人启动中...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
