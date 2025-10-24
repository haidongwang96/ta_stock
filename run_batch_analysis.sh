#!/bin/bash
# 批量技术分析示例脚本

echo "======================================"
echo "批量技术分析工具 - 示例运行"
echo "======================================"

# 检查示例股票池文件是否存在
if [ ! -f "stock_pool_example.txt" ]; then
    echo "错误: 找不到 stock_pool_example.txt 文件"
    exit 1
fi

# 显示股票池内容
echo -e "\n股票池内容:"
cat stock_pool_example.txt | grep -v "^#" | grep -v "^$"

# 运行批量分析
echo -e "\n开始批量分析..."
python batch_technical_analysis.py --pool stock_pool_example.txt --days 60

echo -e "\n======================================"
echo "分析完成！"
echo "======================================"
