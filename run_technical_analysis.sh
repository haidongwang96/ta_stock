#!/bin/bash
# 技术分析工具示例脚本

echo "======================================"
echo "技术指标分析工具 - 示例运行"
echo "======================================"

# 示例1: 分析平安银行（000001.SZ）最近30天
echo -e "\n示例1: 分析平安银行最近30天"
python technical_analysis.py --code 000001.SZ --days 30

# 示例2: 分析贵州茅台（600519.SH）并保存结果
# echo -e "\n\n示例2: 分析贵州茅台并保存结果"
# python technical_analysis.py --code 600519.SH --days 20 --output 茅台技术分析.csv

# 示例3: 分析比亚迪（002594.SZ）指定时间段
# echo -e "\n\n示例3: 分析比亚迪指定时间段"
# python technical_analysis.py --code 002594.SZ --start 20240601 --end 20241231 --days 15

echo -e "\n======================================"
echo "分析完成！"
echo "======================================"
