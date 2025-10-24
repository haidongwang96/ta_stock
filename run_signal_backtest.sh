#!/bin/bash
# 技术分析信号回测示例脚本

echo "================================"
echo "技术分析信号回测工具"
echo "================================"
echo ""

# 检查是否提供了CSV文件
if [ -z "$1" ]; then
    echo "请提供技术分析CSV文件路径"
    echo "用法: $0 <csv_file_path> [options]"
    echo ""
    echo "示例:"
    echo "  $0 technical_analysis_results/technical_analysis_002050.sz_20251023.csv"
    echo "  $0 technical_analysis_results/technical_analysis_002050.sz_20251023.csv --capital 200000 --position-size 0.5"
    echo ""
    exit 1
fi

CSV_FILE="$1"
shift  # 移除第一个参数，剩余的作为额外选项

# 检查文件是否存在
if [ ! -f "$CSV_FILE" ]; then
    echo "错误: 文件不存在: $CSV_FILE"
    exit 1
fi

echo "正在回测文件: $CSV_FILE"
echo ""

# 运行回测（使用默认参数 + 用户提供的额外参数）
python backtest_technical_signals.py \
    --input "$CSV_FILE" \
    --capital 100000 \
    --buy-threshold 2 \
    --sell-threshold -2 \
    --position-size 0.3 \
    --max-positions 3 \
    --stop-loss -0.1 \
    --stop-profit 0.2 \
    "$@"

echo ""
echo "回测完成！结果已保存到 backtest_results 目录"
