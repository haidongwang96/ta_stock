#!/bin/bash
# 技术分析工具示例脚本

code=603893.SH

python technical_analysis.py --code $code --days 120
python plot_kline.py \
  --input technical_analysis_results/technical_analysis_$code.csv \
  --code $code \
  --pool stock_pool_example.txt  \
  --type full 

