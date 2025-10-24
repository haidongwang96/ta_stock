# 批量技术分析工具使用说明

## 功能特点

1. **批量下载数据**：使用Tushare批量API，一次性获取多只股票数据，避免频繁调用触发限制
2. **综合技术分析**：计算MFI、OBV、均线、成交量等多项指标
3. **智能评分系统**：根据技术指标自动评分，识别买卖信号
4. **多维度排序**：支持按综合得分、MFI、涨跌幅、成交量等排序
5. **综合报告生成**：自动生成包含TOP排行榜、超买超卖股票、放量股票等的报告

## 使用方法

### 1. 基本使用

```bash
# 使用默认参数运行（分析pool.txt中的股票，最近60天数据）
python3 batch_technical_analysis.py

# 或使用运行脚本
./run_batch_analysis.sh
```

### 2. 自定义参数

```bash
# 指定股票池文件
python3 batch_technical_analysis.py --pool mystock.txt

# 指定日期范围（格式：YYYYMMDD）
python3 batch_technical_analysis.py --start 20240101 --end 20241231

# 按不同指标排序
python3 batch_technical_analysis.py --sort mfi       # 按MFI排序（超卖优先）
python3 batch_technical_analysis.py --sort pct_5d    # 按5日涨幅排序
python3 batch_technical_analysis.py --sort pct_10d   # 按10日涨幅排序
python3 batch_technical_analysis.py --sort volume_ratio  # 按成交量比率排序
```

### 3. 创建示例股票池

```bash
python3 batch_technical_analysis.py --create-sample
```

## 股票池文件格式

在`pool.txt`文件中，每行一个股票代码，格式为：`股票代码.交易所`

```
# 这是注释行，以#开头
000001.SZ  # 平安银行（深圳）
600036.SH  # 招商银行（上海）
300750.SZ  # 宁德时代
```

## 输出文件

运行后会在`batch_analysis_results/`目录生成：

1. **batch_analysis_YYYYMMDD_HHMMSS.csv** - 所有股票的详细分析数据
2. **batch_report_YYYYMMDD_HHMMSS.txt** - 综合分析报告

## 分析指标说明

### 综合得分（Score）
- 正分表示买入信号，负分表示卖出信号
- 得分≥5：强烈买入信号
- 3≤得分<5：适度买入信号
- 得分≤-3：卖出警示信号

### MFI（资金流量指标）
- MFI < 20：严重超卖
- MFI < 30：超卖
- MFI > 70：超买
- MFI > 80：严重超买

### OBV（能量潮）
- OBV > OBV_MA：上升趋势
- OBV < OBV_MA：下降趋势

### 成交量比率
- 量比 > 1.5：放量
- 量比 < 0.7：缩量

## 信号识别规则

1. **强烈买入信号**：锤子线 + 放量 + MFI超卖
2. **买入信号**：OBV上升趋势 + 价格上升
3. **买入信号**：大阳线 + 放量 + MFI未超买
4. **卖出信号**：射击之星 + 放量 + MFI超买
5. **卖出信号**：OBV下降趋势 + 价格下降

## 注意事项

1. **API限制**：Tushare有访问频率限制，脚本已做优化处理
2. **数据延迟**：股票数据可能有15分钟延迟
3. **仅供参考**：分析结果仅供参考，不构成投资建议

## 常见问题

### Q: 如何添加更多股票？
A: 编辑`pool.txt`文件，按格式添加股票代码即可

### Q: 分析失败怎么办？
A: 检查：
- 股票代码格式是否正确（需要包含.SZ或.SH后缀）
- 网络连接是否正常
- Tushare token是否有效

### Q: 如何修改分析周期？
A: 修改`--start`和`--end`参数指定日期范围

## 更新日志

- v1.0 初始版本
  - 实现批量下载和分析
  - 支持多维度排序
  - 生成综合报告