@echo off
chcp 65001 >nul
title Telegram 群监听机器人

echo ========================================
echo   Telegram 群监听抓取机器人
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 检查配置文件
if not exist "config.py" (
    echo [提示] 配置文件不存在，正在从示例创建...
    copy config.example.py config.py >nul
    echo [重要] 请编辑 config.py 填入你的 BOT_TOKEN 和管理员ID
    echo.
    notepad config.py
    pause
    exit /b 0
)

REM 检查虚拟环境
if not exist "venv" (
    echo [提示] 正在创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo [提示] 正在检查依赖...
pip install -r requirements.txt -q

REM 创建数据目录
if not exist "data" mkdir data

echo.
echo [启动] 正在启动机器人...
echo.

python main.py

pause
