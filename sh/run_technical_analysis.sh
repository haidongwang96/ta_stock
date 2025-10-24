#!/bin/bash
# 技术分析工具示例脚本

code=688256.sh

python technical_analysis.py --code $code --days 60
python plot_kline.py \
  --input technical_analysis_results/technical_analysis_$code.csv \
  --code $code \
  --type full
