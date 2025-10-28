# 技术分析工具项目总结

## 项目结构

```
ta_stock/
├── technical_analysis.py           # 原有的基础技术分析脚本
├── advanced_technical_analysis.py  # 新的高级技术分析脚本
├── run_advanced_analysis.sh       # 便利运行脚本
├── stock_pool.txt                 # 股票池示例文件
├── new_requirement.md             # 需求文档
├── ADVANCED_ANALYSIS_README.md   # 高级分析工具使用说明
├── SUMMARY.md                     # 本总结文档
├── technical_analysis_results/   # 原脚本输出目录
└── advanced_analysis_results/    # 新脚本输出目录

```

## 新脚本特点

### advanced_technical_analysis.py

根据 `new_requirement.md` 的需求，使用 `pandas_ta` 和 `tushare` 重新开发了一个功能更全面的技术分析工具。

#### 主要改进

1. **指标覆盖更全面**
   - 趋势类：MA、MACD、SAR
   - 动量类：RSI、KDJ、CCI
   - 波动类：布林带、ATR
   - 成交量类：VOL、OBV、MFI、VWAP

2. **信号识别更智能**
   - 多指标综合判断
   - 信号强度评级系统
   - 背离信号检测

3. **批量分析功能**
   - 支持股票池文件
   - 批量分析汇总报告
   - 灵活的参数配置

4. **报告输出更详细**
   - 综合分析建议
   - 支撑阻力位计算
   - 清晰的买卖信号提示

## 快速使用指南

### 1. 分析单个股票

```bash
# 使用Python直接运行
python advanced_technical_analysis.py --code 000001.SZ

# 使用Shell脚本
./run_advanced_analysis.sh -c 000001.SZ
```

### 2. 批量分析

```bash
# 分析股票池中的所有股票
python advanced_technical_analysis.py --pool stock_pool.txt --batch

# 使用Shell脚本
./run_advanced_analysis.sh -p stock_pool.txt -b
```

### 3. 自定义参数

```bash
# 分析最近60天，报告显示最近10天的信号
python advanced_technical_analysis.py --code 000001.SZ --days 60 --report_days 10

# 指定日期范围
python advanced_technical_analysis.py --code 000001.SZ --start 20250901 --end 20251028
```

## 输出文件说明

### CSV文件内容

- **基础数据**：日期、OHLCV
- **趋势指标**：MA5/10/20/60、MACD、SAR
- **动量指标**：RSI、KDJ、CCI
- **波动指标**：布林带上中下轨、ATR
- **成交量指标**：量比、OBV、MFI、VWAP
- **分析结果**：买入信号、卖出信号、信号强度
- **支撑阻力**：支撑位、阻力位、枢轴点

### 报告解读

#### 信号强度说明
- **强度 >= 5**：强烈买入信号
- **强度 >= 3**：买入信号
- **强度 >= 1**：偏多信号
- **强度 <= -5**：强烈卖出信号
- **强度 <= -3**：卖出信号
- **强度 <= -1**：偏空信号
- **强度 = 0**：中性信号

#### 常见买入信号
- MA金叉（短期均线上穿长期均线）
- MACD低位金叉
- RSI进入超卖区（<30）
- KDJ低位金叉（D<20）
- 触及布林下轨
- 放量上涨

#### 常见卖出信号
- MA死叉（短期均线下穿长期均线）
- MACD高位死叉
- RSI进入超买区（>70）
- KDJ高位死叉（D>80）
- 触及布林上轨
- 放量下跌

## 注意事项

1. **数据要求**
   - MACD至少需要35天数据（26+9）
   - 其他指标建议至少60天数据
   - 背离检测需要更长的历史数据

2. **使用建议**
   - 技术分析仅供参考，不构成投资建议
   - 建议结合基本面分析
   - 注意市场整体环境
   - 设置止损止盈

3. **性能优化**
   - 批量分析时建议控制股票数量
   - 长时间周期分析可能需要较长时间
   - 输出文件会自动覆盖旧文件

## 后续改进方向

1. 添加更多技术指标（如威廉指标、ROC等）
2. 实现图表可视化功能
3. 添加回测功能
4. 集成实时数据更新
5. 添加预警通知功能
6. 优化背离检测算法

## 联系方式

如有问题或建议，请查看代码注释或联系开发者。

---

*最后更新：2025-10-28*