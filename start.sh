#!/bin/bash

echo "========================================"
echo "  Telegram 群监听抓取机器人"
echo "========================================"
echo

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到Python3，请先安装"
    exit 1
fi

# 检查配置文件
if [ ! -f "config.py" ]; then
    echo "[提示] 配置文件不存在，正在从示例创建..."
    cp config.example.py config.py
    echo "[重要] 请编辑 config.py 填入你的 BOT_TOKEN 和管理员ID"
    echo "nano config.py"
    exit 0
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[提示] 正在创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "[提示] 正在检查依赖..."
pip install -r requirements.txt -q

# 创建数据目录
mkdir -p data

echo
echo "[启动] 正在启动机器人..."
echo

python3 main.py
