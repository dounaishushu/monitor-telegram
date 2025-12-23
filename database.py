# -*- coding: utf-8 -*-
"""
数据库操作模块
"""
import aiosqlite
import os
from datetime import datetime
from typing import List, Optional, Dict, Any


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保数据库目录存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    async def init(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 管理员表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    role TEXT DEFAULT 'admin',
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 关键词表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL UNIQUE,
                    match_type TEXT DEFAULT 'contains',
                    is_active INTEGER DEFAULT 1,
                    hit_count INTEGER DEFAULT 0,
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 监听群组表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    username TEXT,
                    is_active INTEGER DEFAULT 1,
                    message_count INTEGER DEFAULT 0,
                    hit_count INTEGER DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 消息记录表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    content TEXT,
                    matched_keyword TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 转发目标表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS forward_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    title TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 用户设置表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, setting_key)
                )
            ''')
            
            # 屏蔽用户表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    reason TEXT,
                    blocked_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 系统设置表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 关键词黑名单表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS keyword_blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL UNIQUE,
                    match_type TEXT DEFAULT 'contains',
                    is_active INTEGER DEFAULT 1,
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 用户推送记录表（用于防重复推送）
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_push_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER,
                    last_push_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, chat_id)
                )
            ''')
            
            # 初始化默认系统设置
            default_settings = [
                ('push_enabled', 'true'),
                ('keyword_match_mode', 'fuzzy'),  # exact/fuzzy
                ('blacklist_match_mode', 'exact'),  # exact/fuzzy
                ('filter_ad_users', 'false'),
                ('attach_search_history', 'false'),
                ('no_repeat_duration', '0'),  # 0=不限制, 10/30/60/720/1440/21600/43200分钟
            ]
            for key, value in default_settings:
                await db.execute(
                    'INSERT OR IGNORE INTO system_settings (setting_key, setting_value) VALUES (?, ?)',
                    (key, value)
                )
            
            await db.commit()
    
    # ========== 管理员操作 ==========
    
    async def add_admin(self, user_id: int, username: str = None, role: str = 'admin', added_by: int = None) -> bool:
        """添加管理员"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT OR REPLACE INTO admins (user_id, username, role, added_by) VALUES (?, ?, ?, ?)',
                    (user_id, username, role, added_by)
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"添加管理员失败: {e}")
                return False
    
    async def remove_admin(self, user_id: int) -> bool:
        """移除管理员"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            await db.commit()
            return True
    
    async def get_admins(self) -> List[Dict]:
        """获取所有管理员"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM admins ORDER BY created_at DESC') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def is_admin(self, user_id: int) -> bool:
        """检查是否是管理员"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)) as cursor:
                return await cursor.fetchone() is not None
    
    # ========== 关键词操作 ==========
    
    async def add_keyword(self, keyword: str, match_type: str = 'contains', added_by: int = None) -> bool:
        """添加关键词"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT INTO keywords (keyword, match_type, added_by) VALUES (?, ?, ?)',
                    (keyword.lower().strip(), match_type, added_by)
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False  # 关键词已存在
    
    async def remove_keyword(self, keyword: str) -> bool:
        """删除关键词"""
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute('DELETE FROM keywords WHERE keyword = ?', (keyword.lower().strip(),))
            await db.commit()
            return result.rowcount > 0
    
    async def get_keywords(self, active_only: bool = True) -> List[Dict]:
        """获取关键词列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if active_only:
                query = 'SELECT * FROM keywords WHERE is_active = 1 ORDER BY hit_count DESC'
            else:
                query = 'SELECT * FROM keywords ORDER BY hit_count DESC'
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def increment_keyword_hit(self, keyword: str):
        """增加关键词命中次数"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE keywords SET hit_count = hit_count + 1 WHERE keyword = ?',
                (keyword,)
            )
            await db.commit()
    
    async def toggle_keyword(self, keyword: str) -> Optional[bool]:
        """切换关键词状态"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT is_active FROM keywords WHERE keyword = ?', (keyword,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                new_status = 0 if row['is_active'] else 1
                await db.execute('UPDATE keywords SET is_active = ? WHERE keyword = ?', (new_status, keyword))
                await db.commit()
                return bool(new_status)
    
    # ========== 群组操作 ==========
    
    async def add_group(self, chat_id: int, title: str = None, username: str = None) -> bool:
        """添加监听群组"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT OR REPLACE INTO groups (chat_id, title, username) VALUES (?, ?, ?)',
                    (chat_id, title, username)
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"添加群组失败: {e}")
                return False
    
    async def remove_group(self, chat_id: int) -> bool:
        """移除群组"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM groups WHERE chat_id = ?', (chat_id,))
            await db.commit()
            return True
    
    async def get_groups(self, active_only: bool = True) -> List[Dict]:
        """获取群组列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if active_only:
                query = 'SELECT * FROM groups WHERE is_active = 1 ORDER BY hit_count DESC'
            else:
                query = 'SELECT * FROM groups ORDER BY hit_count DESC'
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def is_monitored_group(self, chat_id: int) -> bool:
        """检查是否是监听的群组"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT 1 FROM groups WHERE chat_id = ? AND is_active = 1', (chat_id,)) as cursor:
                return await cursor.fetchone() is not None
    
    async def update_group_stats(self, chat_id: int, message_count: int = 0, hit_count: int = 0):
        """更新群组统计"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE groups SET 
                    message_count = message_count + ?,
                    hit_count = hit_count + ?
                WHERE chat_id = ?
            ''', (message_count, hit_count, chat_id))
            await db.commit()
    
    # ========== 消息记录 ==========
    
    async def save_message(self, chat_id: int, message_id: int, user_id: int, 
                          username: str, content: str, matched_keyword: str):
        """保存匹配的消息"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO messages (chat_id, message_id, user_id, username, content, matched_keyword)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, message_id, user_id, username, content, matched_keyword))
            await db.commit()
    
    async def get_recent_messages(self, limit: int = 50) -> List[Dict]:
        """获取最近的匹配消息"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM messages ORDER BY created_at DESC LIMIT ?', 
                (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ========== 转发目标 ==========
    
    async def add_forward_target(self, chat_id: int, title: str = None) -> bool:
        """添加转发目标"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT OR REPLACE INTO forward_targets (chat_id, title) VALUES (?, ?)',
                    (chat_id, title)
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"添加转发目标失败: {e}")
                return False
    
    async def get_forward_targets(self) -> List[Dict]:
        """获取转发目标列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM forward_targets WHERE is_active = 1') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ========== 统计 ==========
    
    async def get_stats(self) -> Dict:
        """获取统计数据"""
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            
            # 关键词统计
            async with db.execute('SELECT COUNT(*) FROM keywords WHERE is_active = 1') as cursor:
                stats['keyword_count'] = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT SUM(hit_count) FROM keywords') as cursor:
                stats['keyword_hits'] = (await cursor.fetchone())[0] or 0
            
            # 群组统计
            async with db.execute('SELECT COUNT(*) FROM groups WHERE is_active = 1') as cursor:
                stats['group_count'] = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT SUM(message_count) FROM groups') as cursor:
                stats['total_messages'] = (await cursor.fetchone())[0] or 0
            
            # 匹配消息统计
            async with db.execute('SELECT COUNT(*) FROM messages') as cursor:
                stats['matched_messages'] = (await cursor.fetchone())[0]
            
            # 管理员数量
            async with db.execute('SELECT COUNT(*) FROM admins') as cursor:
                stats['admin_count'] = (await cursor.fetchone())[0]
            
            return stats
    
    # ========== 用户设置操作 ==========
    
    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """获取用户所有设置"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT setting_key, setting_value FROM user_settings WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
            
            settings = {}
            for row in rows:
                key = row['setting_key']
                value = row['setting_value']
                # 转换布尔值
                if value == 'True':
                    settings[key] = True
                elif value == 'False':
                    settings[key] = False
                else:
                    settings[key] = value
            
            # 默认值
            if 'notify_enabled' not in settings:
                settings['notify_enabled'] = True
            
            return settings
    
    async def set_user_setting(self, user_id: int, key: str, value: Any) -> bool:
        """设置用户设置"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    '''INSERT OR REPLACE INTO user_settings 
                       (user_id, setting_key, setting_value, updated_at) 
                       VALUES (?, ?, ?, ?)''',
                    (user_id, key, str(value), datetime.now())
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"设置失败: {e}")
                return False
    
    async def get_notify_enabled_admins(self) -> List[int]:
        """获取开启通知的管理员ID列表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 获取所有管理员
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT user_id FROM admins') as cursor:
                admin_rows = await cursor.fetchall()
            
            admin_ids = [row['user_id'] for row in admin_rows]
            
            # 获取关闭通知的用户
            async with db.execute(
                "SELECT user_id FROM user_settings WHERE setting_key = 'notify_enabled' AND setting_value = 'False'"
            ) as cursor:
                disabled_rows = await cursor.fetchall()
            
            disabled_ids = [row['user_id'] for row in disabled_rows]
            
            # 返回开启通知的管理员
            return [aid for aid in admin_ids if aid not in disabled_ids]
    
    # ========== 屏蔽用户操作 ==========
    
    async def block_user(self, user_id: int, username: str = None, reason: str = None, blocked_by: int = None) -> bool:
        """屏蔽用户"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT OR IGNORE INTO blocked_users (user_id, username, reason, blocked_by) VALUES (?, ?, ?, ?)',
                    (user_id, username, reason, blocked_by)
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"屏蔽用户失败: {e}")
                return False
    
    async def unblock_user(self, user_id: int) -> bool:
        """取消屏蔽用户"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
                await db.commit()
                return True
            except:
                return False
    
    async def is_blocked(self, user_id: int) -> bool:
        """检查用户是否被屏蔽"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,)
            ) as cursor:
                return await cursor.fetchone() is not None
    
    async def get_blocked_users(self) -> List[Dict[str, Any]]:
        """获取屏蔽用户列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM blocked_users ORDER BY created_at DESC') as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== 消息记录操作 ==========
    
    async def get_user_messages(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户的历史消息"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def delete_message_by_id(self, message_id: int, chat_id: int) -> bool:
        """删除消息记录"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'DELETE FROM messages WHERE message_id = ? AND chat_id = ?',
                    (message_id, chat_id)
                )
                await db.commit()
                return True
            except:
                return False
    
    # ========== 系统设置操作 ==========
    
    async def get_system_setting(self, key: str, default: str = None) -> str:
        """获取系统设置"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT setting_value FROM system_settings WHERE setting_key = ?', (key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default
    
    async def set_system_setting(self, key: str, value: str) -> bool:
        """设置系统设置"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    '''INSERT OR REPLACE INTO system_settings (setting_key, setting_value, updated_at) 
                       VALUES (?, ?, ?)''',
                    (key, value, datetime.now())
                )
                await db.commit()
                return True
            except Exception as e:
                print(f"设置失败: {e}")
                return False
    
    async def get_all_system_settings(self) -> Dict[str, str]:
        """获取所有系统设置"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT setting_key, setting_value FROM system_settings') as cursor:
                rows = await cursor.fetchall()
            return {row['setting_key']: row['setting_value'] for row in rows}
    
    # ========== 关键词黑名单操作 ==========
    
    async def add_blacklist_keyword(self, keyword: str, match_type: str = 'contains', added_by: int = None) -> bool:
        """添加黑名单关键词"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    'INSERT INTO keyword_blacklist (keyword, match_type, added_by) VALUES (?, ?, ?)',
                    (keyword.lower().strip(), match_type, added_by)
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def remove_blacklist_keyword(self, keyword: str) -> bool:
        """删除黑名单关键词"""
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute('DELETE FROM keyword_blacklist WHERE keyword = ?', (keyword.lower().strip(),))
            await db.commit()
            return result.rowcount > 0
    
    async def get_blacklist_keywords(self, active_only: bool = True) -> List[Dict]:
        """获取黑名单关键词列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if active_only:
                query = 'SELECT * FROM keyword_blacklist WHERE is_active = 1'
            else:
                query = 'SELECT * FROM keyword_blacklist'
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def is_blacklisted_content(self, text: str, match_mode: str = 'exact') -> bool:
        """检查内容是否包含黑名单关键词"""
        blacklist = await self.get_blacklist_keywords()
        text_lower = text.lower()
        
        for item in blacklist:
            keyword = item['keyword'].lower()
            if match_mode == 'exact':
                if keyword == text_lower:
                    return True
            else:  # fuzzy
                if keyword in text_lower:
                    return True
        return False
    
    # ========== 用户推送记录操作 ==========
    
    async def check_user_push_allowed(self, user_id: int, chat_id: int, duration_minutes: int) -> bool:
        """检查用户是否允许推送（防重复）"""
        if duration_minutes <= 0:
            return True  # 不限制
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                '''SELECT last_push_at FROM user_push_records 
                   WHERE user_id = ? AND chat_id = ?''',
                (user_id, chat_id)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return True
                
                last_push = datetime.fromisoformat(row[0])
                now = datetime.now()
                diff_minutes = (now - last_push).total_seconds() / 60
                return diff_minutes >= duration_minutes
    
    async def record_user_push(self, user_id: int, chat_id: int):
        """记录用户推送"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''INSERT OR REPLACE INTO user_push_records (user_id, chat_id, last_push_at)
                   VALUES (?, ?, ?)''',
                (user_id, chat_id, datetime.now().isoformat())
            )
            await db.commit()
    
    async def clean_old_push_records(self, days: int = 30):
        """清理过旧的推送记录"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''DELETE FROM user_push_records 
                   WHERE datetime(last_push_at) < datetime('now', ?)''',
                (f'-{days} days',)
            )
            await db.commit()
