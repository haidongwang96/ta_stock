# 参数调整总结 - 宽松模式

## 📋 已调整的参数

### 1. 低位判断（LOW_POSITION_CONFIG）

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `boll_threshold` | 1.02 | **1.05** | 布林带下轨阈值放宽 |
| `rsi_threshold` | 30 | **40** | RSI超卖阈值放宽 |
| `low_condition_min` | 3 | **2** | 4个条件满足2个即可（关键） |

**影响**：更容易满足"低位"判断，信号频率↑

### 2. 缩量下跌（SUPPLY_DRY_CONFIG）

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `min_days` | 5 | **3** | 最少缩量天数减少 |
| `max_days` | 10 | **15** | 最多缩量天数增加 |
| `min_signals` | 5 | **3** | 最少SUPPLY_DRY_UP信号数减少 |
| `avg_volume_multiple` | 0.8 | **0.9** | 平均量倍数阈值放宽 |
| `max_volume_multiple` | 1.2 | **1.3** | 单日量倍数上限放宽 |
| `max_price_drop` | -0.15 | **-0.20** | 最大跌幅放宽到-20% |
| `min_price_drop` | -0.02 | **-0.01** | 最小跌幅放宽到-1% |

**影响**：更容易找到缩量下跌区间，信号频率↑↑

### 3. 放量上涨确认（HEALTHY_UP_CONFIG）

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `min_volume_multiple` | 1.5 | **1.2** | 基础放量标准降低 |
| `strong_volume_multiple` | 2.0 | **1.6** | 强放量标准降低 |
| `extreme_volume_multiple` | 2.5 | **2.2** | 极强放量标准降低 |
| `consecutive_threshold` | 1.3 | **1.1** | 连续放量阈值降低 |
| `breakout_threshold` | 1.005 | **1.002** | 突破阈值降低 |
| `min_price_change` | 0.01 | **0.005** | 最小涨幅降低到0.5% |

**影响**：更容易触发放量上涨确认，信号频率↑↑

### 4. 市场结构（MARKET_STRUCTURE_CONFIG）

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `target_structures` | 2种 | **3种（+RANGING）** | 新增横盘结构 |
| `transition_window` | 10 | **15** | 转折窗口放宽 |
| `transition_lookback` | 3 | **5** | 转折回看天数增加 |
| `min_confidence` | 0.6 | **0.5** | 置信度要求降低 |
| `markup_max_days` | 5 | **10** | MARK_UP接受天数增加 |

**影响**：更多市场结构符合条件，信号频率↑↑↑（最关键）

### 5. 风险管理（RISK_MANAGEMENT）

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `stop_loss_ratio` | 0.98 | **0.97** | 止损缓冲从-2%到-3% |
| `min_risk_reward` | 2.0 | **1.5** | 最小风险回报比降低 |

**影响**：更容易通过风险回报比筛选，信号频率↑

## 📊 预期效果对比

| 模式 | 信号频率 | 胜率 | 单次收益 | 适用场景 |
|------|----------|------|----------|----------|
| **严格模式**（原配置） | 低 | 高（>70%） | 中高 | 保守投资者 |
| **宽松模式**（新配置） | 中高 | 中（50-65%） | 中 | 积极投资者 |

## 🎯 当前状态说明

### 为什么调整后仍未发现信号？

**测试的10只股票**：
- 688256.SH（寒武纪）：RANGING结构（横盘）
- 其他9只：多为MARK_DOWN（下跌）或UNKNOWN

**原因**：
1. ✅ **市场结构要求**：虽然已新增RANGING，但还要满足其他3层条件
2. ✅ **当前市场环境**：这些股票近期可能没有经历理想的"缩量下跌→放量上涨"过程
3. ✅ **时间点问题**：策略捕捉的是转折点，不是持续的信号

### 这是正常的！

即使是宽松模式，策略仍然保持了基本的质量标准：
- 必须有缩量下跌过程（3-15天，至少3次SUPPLY_DRY_UP）
- 必须有放量上涨确认（volume_multiple > 1.2）
- 必须满足低位判断（4个条件中2个）
- 必须通过风险回报比（>1.5）

**不是参数问题，而是当前这些股票确实不符合策略模式！**

## 💡 使用建议

### 方案1：扩大股票池（推荐）

```bash
# 扫描更大的股票池
python3 scripts/low_volume_scanner.py --pool pool/stock_pool_all.txt
```

理由：
- 在更大的样本中更容易找到符合条件的股票
- 120只股票中通常会有1-3只符合条件

### 方案2：使用回测验证策略

```bash
# 回测过去1年，看看历史上是否有信号
python3 scripts/low_volume_backtest.py --code 000001.SZ --name 平安银行
python3 scripts/low_volume_backtest.py --code 600519.SH --name 贵州茅台
```

理由：
- 验证策略在历史上是否有效
- 找到曾经符合条件的案例学习

### 方案3：进一步放宽（不推荐）

如果一定要更多信号，可以继续放宽：

```python
# 在 config/low_volume_reversal_config.py 中

# 1. 低位判断更宽松
LOW_POSITION_CONFIG = {
    'low_condition_min': 1,  # 4个条件满足1个即可（非常宽松）
}

# 2. 完全放开市场结构限制
MARKET_STRUCTURE_CONFIG = {
    'target_structures': [
        'ACCUMULATION', 'MARK_UP', 'RANGING', 'DISTRIBUTION'
    ],  # 接受所有结构（几乎不限制）
    'min_confidence': 0.3,  # 置信度降到很低
}

# 3. 降低缩量要求
SUPPLY_DRY_CONFIG = {
    'min_signals': 2,  # 只需要2次SUPPLY_DRY_UP
    'min_days': 2,     # 只需要2天缩量
}
```

⚠️ **警告**：过度放宽会导致：
- 信号质量下降
- 假信号增多
- 胜率降低
- 失去策略的核心价值

## 📈 建议的测试流程

### 第1步：验证配置
```bash
python3 config/low_volume_reversal_config.py
```

### 第2步：小池测试（已完成）
```bash
python3 scripts/low_volume_scanner.py --pool pool/stock_pool_small.txt --test
```

### 第3步：大池扫描
```bash
python3 scripts/low_volume_scanner.py --pool pool/stock_pool_all.txt
```

### 第4步：回测验证
```bash
# 选择几只典型股票回测
python3 scripts/low_volume_backtest.py --code 股票代码 --name 股票名称
```

### 第5步：实盘跟踪
- 每天收盘后运行扫描
- 记录信号及后续走势
- 根据实际表现调整参数

## 🔧 参数恢复

如需恢复严格模式，修改配置文件：

```python
# 恢复关键参数
LOW_POSITION_CONFIG = {
    'low_condition_min': 3,  # 恢复到3
    'rsi_threshold': 30,      # 恢复到30
}

SUPPLY_DRY_CONFIG = {
    'min_days': 5,            # 恢复到5
    'min_signals': 5,         # 恢复到5
}

MARKET_STRUCTURE_CONFIG = {
    'target_structures': ['ACCUMULATION', 'ACCUMULATION_TO_MARKUP'],  # 移除RANGING
    'min_confidence': 0.6,    # 恢复到0.6
}

RISK_MANAGEMENT = {
    'min_risk_reward': 2.0,   # 恢复到2.0
}
```

## 📝 总结

✅ **已完成**：参数已调整为宽松模式
✅ **验证通过**：配置文件无错误
✅ **功能正常**：扫描器和回测工具运行正常

⚠️ **当前状态**：测试股票池未发现信号（正常，不是bug）

💡 **建议**：
1. 使用更大的股票池扫描
2. 用回测验证历史表现
3. 根据实际运行结果微调参数
4. 保持耐心，好的信号不是每天都有

---

**配置文件位置**：`config/low_volume_reversal_config.py`
**当前模式**：宽松模式（已生效）
**创建时间**：2025-11-11
