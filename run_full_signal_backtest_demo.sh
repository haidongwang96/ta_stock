#!/bin/bash
# 完整的技术信号回测演示
# 从生成技术分析数据到回测和查看结果

set -e  # 遇到错误立即退出

echo "========================================"
echo "技术信号回测 - 完整流程演示"
echo "========================================"
echo ""

# 设置默认参数
STOCK_CODE=${1:-"002050.SZ"}
START_DATE=${2:-"20230101"}
END_DATE=${3:-"20241231"}
CAPITAL=${4:-"100000"}

echo "配置参数:"
echo "  股票代码: $STOCK_CODE"
echo "  开始日期: $START_DATE"
echo "  结束日期: $END_DATE"
echo "  初始资金: ¥$CAPITAL"
echo ""

# 步骤1: 生成技术分析数据
echo "步骤1: 生成技术分析数据..."
echo "----------------------------------------"
python technical_analysis.py \
    --code "$STOCK_CODE" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --days 10

if [ $? -ne 0 ]; then
    echo "错误: 技术分析失败"
    exit 1
fi

echo ""
echo "✓ 技术分析完成"
echo ""

# 找到生成的CSV文件
ANALYSIS_FILE=$(ls -t technical_analysis_results/technical_analysis_*.csv | head -1)

if [ ! -f "$ANALYSIS_FILE" ]; then
    echo "错误: 找不到技术分析文件"
    exit 1
fi

echo "使用数据文件: $ANALYSIS_FILE"
echo ""

# 步骤2: 运行策略对比
echo "步骤2: 运行策略对比..."
echo "----------------------------------------"
python backtest_strategies_comparison.py \
    --input "$ANALYSIS_FILE" \
    --capital "$CAPITAL"

if [ $? -ne 0 ]; then
    echo "错误: 策略对比失败"
    exit 1
fi

echo ""
echo "✓ 策略对比完成"
echo ""

# 步骤3: 使用最优策略单独回测（这里用高频交易策略作为示例）
echo "步骤3: 运行单独回测（高频交易策略）..."
echo "----------------------------------------"
python backtest_technical_signals.py \
    --input "$ANALYSIS_FILE" \
    --capital "$CAPITAL" \
    --buy-threshold 1 \
    --sell-threshold -1 \
    --position-size 0.25 \
    --max-positions 4 \
    --stop-loss -0.05 \
    --stop-profit 0.1

if [ $? -ne 0 ]; then
    echo "错误: 回测失败"
    exit 1
fi

echo ""
echo "✓ 回测完成"
echo ""

# 步骤4: 查看结果
echo "步骤4: 查看结果..."
echo "----------------------------------------"
echo ""

# 查看策略对比
echo "【策略对比结果】"
echo ""
python view_signal_backtest.py --comparison

echo ""
echo "【最新回测详情】"
echo ""
python view_signal_backtest.py --latest

echo ""
echo "========================================"
echo "演示完成！"
echo "========================================"
echo ""
echo "结果文件保存在 backtest_results/ 目录"
echo ""
echo "下一步建议:"
echo "  1. 查看策略对比，选择夏普比率最高的策略"
echo "  2. 根据自己的风险偏好调整参数"
echo "  3. 在多只股票上测试策略的稳定性"
echo "  4. 使用模拟盘验证策略"
echo ""
