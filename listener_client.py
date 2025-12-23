# -*- coding: utf-8 -*-
"""
监听者客户端模块
使用 Telethon 实现用户账号消息监听功能
"""
import asyncio
import re
import logging
from typing import Optional, Tuple, List, Dict, Any, Callable
from datetime import datetime
from telethon import TelegramClient, events, functions, types
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    UserAlreadyParticipantError,
    InviteHashInvalidError,
    InviteHashExpiredError,
    ChannelPrivateError,
    ChatAdminRequiredError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.types import Channel, Chat, User

logger = logging.getLogger(__name__)


class ListenerClient:
    """监听者客户端"""
    
    def __init__(self, api_id: int, api_hash: str, session_path: str, phone: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.phone = phone
        self.client: Optional[TelegramClient] = None
        self._is_connected = False
        self._pending_code = None
        self._pending_2fa = None
        self._message_handler = None
        self._on_keyword_match: Optional[Callable] = None
        self._db = None
        self._is_listening = False
        self._catch_up_task = None  # 后台任务
    
    def set_database(self, db):
        """设置数据库实例"""
        self._db = db
    
    def set_keyword_callback(self, callback: Callable):
        """设置关键词匹配回调"""
        self._on_keyword_match = callback
    
    async def connect(self) -> bool:
        """连接到 Telegram"""
        try:
            # 如果客户端已存在且已连接，检查授权状态
            if self.client and self.client.is_connected():
                if await self.client.is_user_authorized():
                    self._is_connected = True
                    return True
            
            # 创建新客户端（如果不存在）
            if self.client is None:
                self.client = TelegramClient(
                    self.session_path,
                    self.api_id,
                    self.api_hash,
                    system_version="4.16.30-vxCUSTOM"
                )
            
            # 连接
            if not self.client.is_connected():
                await self.client.connect()
            
            if await self.client.is_user_authorized():
                self._is_connected = True
                me = await self.client.get_me()
                logger.info(f"监听者账号已连接: {me.first_name} (@{me.username})")
                return True
            else:
                logger.info("监听者账号未授权，需要登录")
                return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            self._is_connected = False
            self._is_listening = False
    
    async def send_code(self) -> Tuple[bool, str]:
        """发送验证码"""
        try:
            # 确保客户端已创建并连接
            if self.client is None:
                self.client = TelegramClient(
                    self.session_path,
                    self.api_id,
                    self.api_hash,
                    system_version="4.16.30-vxCUSTOM"
                )
            
            if not self.client.is_connected():
                await self.client.connect()
            
            self._pending_code = await self.client.send_code_request(self.phone)
            return True, "验证码已发送到您的 Telegram 账号"
        except FloodWaitError as e:
            return False, f"请求过于频繁，请等待 {e.seconds} 秒后重试"
        except Exception as e:
            return False, f"发送验证码失败: {str(e)}"
    
    async def verify_code(self, code: str) -> Tuple[bool, str]:
        """验证登录码"""
        try:
            if not self._pending_code:
                return False, "请先发送验证码"
            
            await self.client.sign_in(
                self.phone,
                code,
                phone_code_hash=self._pending_code.phone_code_hash
            )
            self._is_connected = True
            me = await self.client.get_me()
            return True, f"登录成功！账号: {me.first_name}"
            
        except SessionPasswordNeededError:
            self._pending_2fa = True
            return False, "需要输入两步验证密码"
        except PhoneCodeInvalidError:
            return False, "验证码错误，请重新输入"
        except PhoneCodeExpiredError:
            return False, "验证码已过期，请重新获取"
        except Exception as e:
            return False, f"验证失败: {str(e)}"
    
    async def verify_2fa(self, password: str) -> Tuple[bool, str]:
        """验证两步验证密码"""
        try:
            await self.client.sign_in(password=password)
            self._is_connected = True
            me = await self.client.get_me()
            return True, f"登录成功！账号: {me.first_name}"
        except Exception as e:
            return False, f"密码验证失败: {str(e)}"
    
    def is_connected(self) -> bool:
        """检查是否已连接并授权"""
        return self._is_connected and self.client is not None
    
    async def get_me(self) -> Optional[dict]:
        """获取当前账号信息"""
        if not self._is_connected:
            return None
        try:
            me = await self.client.get_me()
            return {
                'id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone': me.phone
            }
        except:
            return None
    
    # ========== 获取群组/频道 ==========
    
    async def get_all_dialogs(self) -> List[Dict[str, Any]]:
        """获取所有对话（群组和频道）"""
        if not self._is_connected:
            return []
        
        dialogs = []
        try:
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity
                
                # 只获取群组和频道
                if isinstance(entity, (Channel, Chat)):
                    is_channel = isinstance(entity, Channel)
                    
                    # 获取完整的 chat_id
                    if is_channel:
                        chat_id = int(f"-100{entity.id}")
                    else:
                        chat_id = -entity.id
                    
                    dialogs.append({
                        'id': entity.id,
                        'chat_id': chat_id,
                        'title': getattr(entity, 'title', '未知'),
                        'username': getattr(entity, 'username', None),
                        'type': 'channel' if (is_channel and getattr(entity, 'broadcast', False)) else 'supergroup' if is_channel else 'group',
                        'participants_count': getattr(entity, 'participants_count', 0),
                        'is_channel': is_channel and getattr(entity, 'broadcast', False)
                    })
            
            logger.info(f"获取到 {len(dialogs)} 个群组/频道")
            return dialogs
        except Exception as e:
            logger.error(f"获取对话列表失败: {e}")
            return []
    
    async def sync_dialogs_to_db(self) -> Tuple[int, int]:
        """同步所有群组/频道到数据库"""
        if not self._db:
            return 0, 0
        
        dialogs = await self.get_all_dialogs()
        added = 0
        updated = 0
        
        for dialog in dialogs:
            try:
                exists = await self._db.is_monitored_group(dialog['chat_id'])
                await self._db.add_group(
                    chat_id=dialog['chat_id'],
                    title=dialog['title'],
                    username=dialog.get('username')
                )
                if exists:
                    updated += 1
                else:
                    added += 1
            except Exception as e:
                logger.error(f"同步群组失败: {dialog['title']} - {e}")
        
        return added, updated
    
    # ========== 消息监听 ==========
    
    async def start_listening(self) -> bool:
        """开始监听消息"""
        if not self._is_connected or not self.client:
            logger.error("监听失败: 客户端未连接")
            return False
        
        if self._is_listening:
            return True
        
        try:
            # 注册消息处理器
            @self.client.on(events.NewMessage(incoming=True))
            async def message_handler(event):
                await self._handle_message(event)
            
            self._message_handler = message_handler
            self._is_listening = True
            
            # 调用 catch_up 获取遗漏的更新
            try:
                await self.client.catch_up()
                logger.info("监听者已同步最新消息")
            except Exception as e:
                logger.warning(f"catch_up 失败: {e}")
            
            # 启动后台任务来保持客户端运行并定时检查
            async def keep_alive():
                """保持客户端运行的后台任务"""
                try:
                    while self._is_listening and self.client:
                        if not self.client.is_connected():
                            logger.warning("监听者客户端断开，尝试重连...")
                            await self.client.connect()
                        await asyncio.sleep(5)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"后台任务异常: {e}")
            
            self._catch_up_task = asyncio.create_task(keep_alive())
            
            logger.info("监听者开始监听消息")
            return True
        except Exception as e:
            logger.error(f"启动监听失败: {e}")
            return False
    
    async def stop_listening(self):
        """停止监听消息"""
        self._is_listening = False
        
        # 取消后台任务
        if self._catch_up_task:
            self._catch_up_task.cancel()
            try:
                await self._catch_up_task
            except asyncio.CancelledError:
                pass
            self._catch_up_task = None
        
        # 移除事件处理器
        if self._message_handler and self.client:
            self.client.remove_event_handler(self._message_handler)
            self._message_handler = None
        
        logger.info("监听者停止监听消息")
    
    async def _handle_message(self, event):
        """处理收到的消息"""
        try:
            message = event.message
            if not message or not message.text:
                return
            
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # 只处理群组/频道消息
            if not isinstance(chat, (Channel, Chat)):
                return
            
            # 过滤频道消息（频道发布的消息没有 sender）
            if sender is None:
                logger.debug("跳过频道发布的消息")
                return
            
            # 过滤机器人消息
            if getattr(sender, 'bot', False):
                logger.debug("跳过机器人消息")
                return
            
            # 获取 chat_id
            if isinstance(chat, Channel):
                chat_id = int(f"-100{chat.id}")
            else:
                chat_id = -chat.id
            
            chat_title = getattr(chat, 'title', '未知')
            
            # 检查发送者是否是群主/管理员，如果是则跳过
            try:
                # 尝试获取发送者在群组中的权限
                participant = await self.client.get_permissions(chat, sender)
                if participant:
                    # 检查是否是创建者或管理员
                    is_creator = getattr(participant, 'is_creator', False)
                    is_admin = getattr(participant, 'is_admin', False)
                    
                    if is_creator or is_admin:
                        logger.debug(f"跳过群主/管理员消息: {getattr(sender, 'first_name', '未知')}")
                        return
            except Exception as perm_error:
                # 获取权限失败，继续处理（可能是普通用户）
                logger.debug(f"获取用户权限失败: {perm_error}")
            
            logger.info(f"收到用户消息: {chat_title} ({chat_id}) - 用户: {getattr(sender, 'first_name', '未知')}")
            
            # 检查数据库是否设置
            if not self._db:
                logger.warning("数据库未设置，无法处理消息")
                return
            
            # 获取系统设置
            settings = await self._db.get_all_system_settings()
            
            # 检查推送是否开启
            if settings.get('push_enabled', 'true') != 'true':
                logger.debug("推送已关闭，跳过消息处理")
                return
            
            # 检查是否在监听列表中
            is_monitored = await self._db.is_monitored_group(chat_id)
            if not is_monitored:
                logger.info(f"群组不在监听列表: {chat_title} ({chat_id})")
                return
            
            # 检查用户是否被屏蔽
            sender_id = sender.id if sender else 0
            if sender and await self._db.is_blocked(sender_id):
                return
            
            # 检查黑名单
            blacklist_mode = settings.get('blacklist_match_mode', 'exact')
            if await self._db.is_blacklisted_content(message.text, blacklist_mode):
                logger.info(f"消息包含黑名单关键词，跳过")
                return
            
            # 更新消息计数
            await self._db.update_group_stats(chat_id, message_count=1)
            
            # 获取关键词
            keywords = await self._db.get_keywords()
            if not keywords:
                logger.info("没有配置关键词")
                return
            
            text = message.text.lower()
            keyword_mode = settings.get('keyword_match_mode', 'fuzzy')  # exact/fuzzy
            logger.info(f"检查关键词匹配: 关键词数={len(keywords)}, 模式={keyword_mode}")
            
            # 匹配关键词
            for kw in keywords:
                keyword = kw['keyword'].lower()
                matched = False
                
                # 根据系统设置的匹配模式
                if keyword_mode == 'exact':
                    matched = text == keyword
                else:  # fuzzy - 模糊匹配
                    matched = keyword in text
                
                if matched:
                    logger.info(f"关键词匹配成功: [{kw['keyword']}] 群组={chat_title}")
                    
                    # 检查防重复推送
                    no_repeat_duration = int(settings.get('no_repeat_duration', '0'))
                    if no_repeat_duration > 0:
                        allowed = await self._db.check_user_push_allowed(sender_id, chat_id, no_repeat_duration)
                        if not allowed:
                            logger.info(f"用户 {sender_id} 在 {no_repeat_duration} 分钟内已推送过，跳过")
                            continue
                    
                    # 记录推送
                    if no_repeat_duration > 0:
                        await self._db.record_user_push(sender_id, chat_id)
                    
                    # 更新统计
                    await self._db.increment_keyword_hit(kw['keyword'])
                    await self._db.update_group_stats(chat_id, hit_count=1)
                    
                    # 保存消息
                    await self._db.save_message(
                        chat_id=chat_id,
                        message_id=message.id,
                        user_id=sender.id if sender else 0,
                        username=getattr(sender, 'username', None),
                        content=message.text[:500],
                        matched_keyword=kw['keyword']
                    )
                    
                    # 触发回调
                    logger.info(f"回调状态: _on_keyword_match={self._on_keyword_match is not None}")
                    if self._on_keyword_match:
                        logger.info("触发关键词匹配回调...")
                        try:
                            await self._on_keyword_match(
                                chat=chat,
                                sender=sender,
                                message=message,
                                keyword=kw['keyword'],
                                chat_id=chat_id
                            )
                            logger.info("回调执行完成")
                        except Exception as cb_error:
                            logger.error(f"回调执行失败: {cb_error}", exc_info=True)
                    else:
                        logger.warning("未设置关键词匹配回调")
                    
                    break
                        
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
    
    def is_listening(self) -> bool:
        """检查是否正在监听"""
        return self._is_listening
    
    # ========== 加入群组 ==========
    
    @staticmethod
    def parse_invite_link(link: str) -> Tuple[Optional[str], Optional[str]]:
        """解析邀请链接"""
        link = link.strip()
        
        # 公开群组/频道 t.me/username
        public_match = re.match(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z][a-zA-Z0-9_]{3,31})(?:\?.*)?$', link)
        if public_match:
            return 'public', public_match.group(1)
        
        # 私有邀请链接 t.me/+xxxxx
        private_match = re.match(r'(?:https?://)?(?:t\.me|telegram\.me)/\+([a-zA-Z0-9_-]+)', link)
        if private_match:
            return 'private', private_match.group(1)
        
        joinchat_match = re.match(r'(?:https?://)?(?:t\.me|telegram\.me)/joinchat/([a-zA-Z0-9_-]+)', link)
        if joinchat_match:
            return 'joinchat', joinchat_match.group(1)
        
        return None, None
    
    async def join_chat(self, link: str) -> Tuple[bool, str, Optional[dict]]:
        """加入群组/频道"""
        if not self._is_connected:
            return False, "监听者账号未登录", None
        
        link_type, identifier = self.parse_invite_link(link)
        
        if not link_type:
            return False, "无效的群组链接格式", None
        
        try:
            if link_type == 'public':
                entity = await self.client.get_entity(identifier)
                await self.client(JoinChannelRequest(entity))
                
                chat_id = int(f"-100{entity.id}") if isinstance(entity, Channel) else -entity.id
                chat_info = {
                    'id': entity.id,
                    'chat_id': chat_id,
                    'title': getattr(entity, 'title', identifier),
                    'username': identifier,
                    'type': 'channel' if getattr(entity, 'broadcast', False) else 'supergroup'
                }
                return True, f"成功加入: {chat_info['title']}", chat_info
            
            else:
                try:
                    updates = await self.client(ImportChatInviteRequest(identifier))
                    
                    chat = updates.chats[0] if updates.chats else None
                    if chat:
                        chat_id = int(f"-100{chat.id}") if isinstance(chat, Channel) else -chat.id
                        chat_info = {
                            'id': chat.id,
                            'chat_id': chat_id,
                            'title': getattr(chat, 'title', '未知'),
                            'username': getattr(chat, 'username', None),
                            'type': 'channel' if getattr(chat, 'broadcast', False) else 'supergroup'
                        }
                        return True, f"成功加入: {chat_info['title']}", chat_info
                    
                    return True, "成功加入群组", None
                    
                except UserAlreadyParticipantError:
                    return False, "已经是该群组成员", None
        
        except UserAlreadyParticipantError:
            return False, "已经是该群组成员", None
        except InviteHashInvalidError:
            return False, "邀请链接无效", None
        except InviteHashExpiredError:
            return False, "邀请链接已过期", None
        except ChannelPrivateError:
            return False, "这是一个私有群组，无法加入", None
        except ChatAdminRequiredError:
            return False, "需要管理员权限才能加入", None
        except FloodWaitError as e:
            return False, f"操作过于频繁，请等待 {e.seconds} 秒", None
        except Exception as e:
            logger.error(f"加入群组失败: {e}")
            return False, f"加入失败: {str(e)}", None
    
    async def leave_chat(self, chat_id: int) -> Tuple[bool, str]:
        """离开群组/频道"""
        if not self._is_connected:
            return False, "监听者账号未登录"
        
        try:
            await self.client.delete_dialog(chat_id)
            return True, "成功离开群组"
        except Exception as e:
            return False, f"离开失败: {str(e)}"
    
    async def run_until_disconnected(self):
        """保持运行直到断开连接"""
        if self.client:
            await self.client.run_until_disconnected()


# 全局监听者客户端实例
_listener_client: Optional[ListenerClient] = None


async def get_listener_client() -> Optional[ListenerClient]:
    """获取监听者客户端实例"""
    global _listener_client
    
    if _listener_client is None:
        try:
            from config import API_ID, API_HASH, LISTENER_PHONE, SESSION_PATH
            _listener_client = ListenerClient(API_ID, API_HASH, SESSION_PATH, LISTENER_PHONE)
        except ImportError:
            return None
    
    return _listener_client


async def init_listener_client() -> Tuple[bool, str]:
    """初始化监听者客户端"""
    client = await get_listener_client()
    if not client:
        return False, "监听者配置不完整，请检查 config.py"
    
    success = await client.connect()
    if success:
        return True, "监听者账号已连接"
    else:
        return False, "监听者账号未登录，请先完成登录"
