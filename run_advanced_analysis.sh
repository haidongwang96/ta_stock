#!/bin/bash
# 高级技术分析脚本
# 使用 pandas_ta 和 tushare 进行全面的技术指标分析

# 设置脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活Python环境（如果需要）
# source /path/to/your/venv/bin/activate

# 使用方法函数
usage() {
    echo "使用方法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -c CODE       股票代码（如 000001.SZ）"
    echo "  -p POOL       股票池文件路径"
    echo "  -b            批量分析模式（分析股票池中所有股票）"
    echo "  -d DAYS       分析最近N天的数据（默认120天）"
    echo "  -r DAYS       报告中显示最近N天的信号（默认20天）"
    echo "  -s START      开始日期 YYYYMMDD"
    echo "  -e END        结束日期 YYYYMMDD"
    echo "  -o OUTPUT     输出文件名"
    echo "  -h            显示帮助信息"
    echo ""
    echo "示例:"
    echo "  # 分析单个股票"
    echo "  $0 -c 000001.SZ"
    echo ""
    echo "  # 分析股票池中的第一个股票"
    echo "  $0 -p stock_pool.txt"
    echo ""
    echo "  # 批量分析股票池中的所有股票"
    echo "  $0 -p stock_pool.txt -b"
    echo ""
    echo "  # 分析最近30天的数据"
    echo "  $0 -c 000001.SZ -d 30"
    echo ""
    echo "  # 指定日期范围"
    echo "  $0 -c 000001.SZ -s 20250101 -e 20251028"
    exit 1
}

# 默认参数
CODE=""
POOL=""
BATCH=""
DAYS="120"
REPORT_DAYS="20"
START=""
END=""
OUTPUT=""

# 解析命令行参数
while getopts "c:p:bd:r:s:e:o:h" opt; do
    case $opt in
        c) CODE="$OPTARG";;
        p) POOL="$OPTARG";;
        b) BATCH="--batch";;
        d) DAYS="$OPTARG";;
        r) REPORT_DAYS="$OPTARG";;
        s) START="$OPTARG";;
        e) END="$OPTARG";;
        o) OUTPUT="$OPTARG";;
        h) usage;;
        *) usage;;
    esac
done

# 检查参数
if [[ -z "$CODE" && -z "$POOL" ]]; then
    echo "错误：必须指定股票代码(-c)或股票池文件(-p)"
    echo ""
    usage
fi

# 构建Python命令
CMD="python advanced_technical_analysis.py"

# 添加参数
if [[ -n "$CODE" ]]; then
    CMD="$CMD --code $CODE"
fi

if [[ -n "$POOL" ]]; then
    CMD="$CMD --pool $POOL"
fi

if [[ -n "$BATCH" ]]; then
    CMD="$CMD $BATCH"
fi

CMD="$CMD --days $DAYS --report_days $REPORT_DAYS"

if [[ -n "$START" ]]; then
    CMD="$CMD --start $START"
fi

if [[ -n "$END" ]]; then
    CMD="$CMD --end $END"
fi

if [[ -n "$OUTPUT" ]]; then
    CMD="$CMD --output $OUTPUT"
fi

# 显示将要执行的命令
echo "执行命令: $CMD"
echo "=========================================="
echo ""

# 执行Python脚本
eval $CMD

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "分析完成！"
    echo "结果保存在 advanced_analysis_results/ 文件夹"
else
    echo ""
    echo "=========================================="
    echo "分析失败，请检查错误信息"
    exit 1
fi