"""
低位缩量反转策略配置文件

策略核心思想：
在底部（ACCUMULATION）向上突破（MARK_UP）的转折时刻，捕捉"缩量下跌转放量上涨"的反转信号

配置说明：
- 所有阈值参数均可根据回测结果进行优化调整
- 建议先用默认参数运行回测，再根据结果微调
"""

# ==================== 低位判断配置 ====================
LOW_POSITION_CONFIG = {
    # 布林带判断
    'boll_threshold': 1.05,  # 价格 < 布林带下轨 * 1.05 视为低位（放宽）

    # RSI判断
    'rsi_threshold': 40,  # RSI < 40 视为超卖（放宽从30到40）

    # 均线判断
    'ma_periods': [20, 60],  # 检查的均线周期（价格低于任一均线即满足）

    # 新低判断
    'new_low_windows': [20, 60],  # 检查是否为20日/60日新低

    # 组合判断要求
    'low_condition_min': 2,  # 4个低位条件中至少满足2个（宽松模式）

    # 说明：
    # - low_condition_min=4: 最严格，信号少但质量高
    # - low_condition_min=3: 平衡，推荐使用
    # - low_condition_min=2: 宽松，信号多但假信号也多（当前设置）
}


# ==================== 缩量下跌配置 ====================
SUPPLY_DRY_CONFIG = {
    # 时间窗口
    'min_days': 3,  # 缩量下跌最少持续天数（放宽从5到3）
    'max_days': 15,  # 缩量下跌最多持续天数（放宽从10到15）

    # VSA信号要求
    'min_signals': 3,  # 最少出现的SUPPLY_DRY_UP信号数（放宽从5到3）

    # 成交量要求
    'avg_volume_multiple': 0.9,  # 期间平均volume_multiple < 0.9（放宽从0.8到0.9）
    'max_volume_multiple': 1.3,  # 单日volume_multiple不能超过1.3（放宽从1.2到1.3）

    # 价格要求
    'max_price_drop': -0.20,  # 期间最大跌幅不超过-20%（放宽从-15%到-20%）
    'min_price_drop': -0.01,  # 期间至少要有-1%的下跌（放宽从-2%到-1%）

    # 禁止条件
    'allow_panic': False,  # 是否允许期间出现PANIC_SELL信号（建议False）

    # 说明：
    # 这些参数确保缩量下跌是"供应枯竭"而非"恐慌抛售"
    # - 缩量：avg < 0.9, 单日 < 1.3（已放宽）
    # - 温和：跌幅 -1% 至 -20%（已放宽）
    # - 无恐慌：不出现PANIC_SELL
}


# ==================== 放量上涨确认配置 ====================
HEALTHY_UP_CONFIG = {
    # 成交量倍数阈值
    'min_volume_multiple': 1.2,  # 基础放量标准（放宽从1.5到1.2）
    'strong_volume_multiple': 1.6,  # 强放量标准（放宽从2.0到1.6）
    'extreme_volume_multiple': 2.2,  # 极强放量标准（放宽从2.5到2.2）

    # 连续放量要求
    'consecutive_days': 2,  # 检查连续放量的天数
    'consecutive_threshold': 1.1,  # 连续放量的阈值（放宽从1.3到1.1）

    # 阻力位突破检查
    'resistance_window': 20,  # 阻力位计算窗口（20日内的最高点）
    'breakout_threshold': 1.002,  # 突破阈值（放宽从1.005到1.002）

    # 涨幅要求
    'min_price_change': 0.005,  # 最小涨幅0.5%（放宽从1%到0.5%）

    # 说明：
    # 根据满足条件的数量，信号强度分为0-3级：
    # - 强度3：今日HEALTHY_UP + 连续2天 + 突破阻力 + 极强放量(>2.2)
    # - 强度2：今日HEALTHY_UP + (连续2天 或 突破阻力) + 强放量(>1.6)
    # - 强度1：今日HEALTHY_UP + 放量(>1.2)
    # - 强度0：仅今日HEALTHY_UP（最低标准）
}


# ==================== 市场结构配置 ====================
MARKET_STRUCTURE_CONFIG = {
    # 目标市场结构
    'target_structures': [
        'ACCUMULATION',  # 吸筹区
        'ACCUMULATION_TO_MARKUP',  # 吸筹转上涨（最佳入场时机）
        'RANGING',  # 横盘（新增，更宽松）
    ],

    # 结构转折识别
    'transition_window': 15,  # 检查最近15天内是否从ACCUMULATION转为MARK_UP（放宽从10到15）
    'transition_lookback': 5,  # 转折发生在5天内视为"刚转折"（放宽从3到5）

    # 结构置信度要求
    'min_confidence': 0.5,  # 市场结构判断的最低置信度（放宽从0.6到0.5）

    # 特殊情况
    'allow_markup': True,  # 是否允许在已确认MARK_UP阶段入场（类似TEST_ENTRY）
    'markup_max_days': 10,  # 如果允许MARK_UP，接受转折后10天内的信号（放宽从5到10）

    # 说明：
    # - ACCUMULATION: 底部横盘，正在吸筹（最安全）
    # - ACCUMULATION_TO_MARKUP: 刚刚突破（最佳时机）
    # - MARK_UP（早期）: 已确认上涨但不久（可接受）
    # - RANGING: 横盘（宽松模式新增）
}


# ==================== 风险管理配置 ====================
RISK_MANAGEMENT = {
    # 止损设置
    'stop_loss_type': 'supply_dry_low',  # 止损类型：supply_dry_low | boll_lower | atr
    'stop_loss_ratio': 0.97,  # 止损缓冲比例（放宽从0.98到0.97，-3%缓冲）

    # 目标位设置
    'target_type': 'fixed_ratio',  # 目标类型：fixed_ratio | resistance | atr
    'target_ratio': 1.05,  # 固定目标比例（+5%）
    'target_ratio_strong': 1.08,  # 强信号目标比例（+8%，强度>=2时使用）

    # 风险回报比
    'min_risk_reward': 1.5,  # 最小风险回报比（放宽从2.0到1.5）

    # 仓位管理（可选，用于自动化交易）
    'max_position_per_stock': 0.20,  # 单只股票最大仓位20%
    'max_total_position': 0.60,  # 同时持仓总比例60%

    # 说明：
    # - 止损：缩量下跌期间最低点-3%（给予更多波动空间）
    # - 目标：当前价+5%（保守）或+8%（强信号）
    # - 风险回报比：通常在1.5-3.0之间（已放宽）
}


# ==================== 扫描器配置 ====================
SCANNER_CONFIG = {
    # 数据要求
    'min_data_days': 90,  # 至少需要90天历史数据
    'data_source': 'local_db',  # 数据源：local_db | tushare

    # 输出设置
    'output_dir': 'low_volume_reports',  # 输出目录
    'report_format': 'txt',  # 报告格式：txt | html | json
    'generate_charts': True,  # 是否生成K线标注图
    'chart_top_n': 10,  # 为前N个信号生成图表

    # 过滤设置
    'min_price': 5.0,  # 最低股价过滤（元）
    'max_price': 10000.0,  # 最高股价过滤（元）- 放宽限制以支持高价股
    'min_volume': 100000,  # 最小成交量（手，过滤流动性差的股票）- 降低门槛

    # 并发设置
    'max_workers': 4,  # 并发扫描线程数（建议2-4）

    # 说明：
    # - min_data_days: 需要足够数据计算指标
    # - chart_top_n: 只为高质量信号生成图表，节省时间
}


# ==================== 回测配置 ====================
BACKTEST_CONFIG = {
    # 回测周期
    'default_lookback_days': 365,  # 默认回测1年

    # 交易模拟
    'entry_method': 'next_open',  # 入场方式：next_open | signal_close | limit
    'exit_method': 'stop_or_target',  # 出场方式：stop_or_target | trailing_stop | time_exit
    'max_holding_days': 30,  # 最大持仓天数（强制出场）

    # 费用设置
    'commission_rate': 0.0003,  # 佣金费率0.03%
    'slippage_rate': 0.001,  # 滑点0.1%

    # 统计设置
    'calculate_benchmark': True,  # 是否计算相对基准收益（如沪深300）
    'benchmark_code': '000300.SH',  # 基准指数代码

    # 说明：
    # - entry_method: next_open最保守（第二天开盘价）
    # - exit_method: stop_or_target为标准止损/止盈
    # - max_holding_days: 防止长期套牢
}


# ==================== 调试配置 ====================
DEBUG_CONFIG = {
    'verbose': False,  # 是否输出详细日志
    'save_intermediate': False,  # 是否保存中间结果（用于调试）
    'test_mode': False,  # 测试模式（只扫描前10只股票）
}


# ==================== 配置验证函数 ====================
def validate_config():
    """验证配置参数的合理性"""
    errors = []

    # 检查缩量下跌时间窗口
    if SUPPLY_DRY_CONFIG['min_days'] > SUPPLY_DRY_CONFIG['max_days']:
        errors.append("缩量下跌min_days不能大于max_days")

    # 检查风险回报比
    if RISK_MANAGEMENT['min_risk_reward'] < 1.0:
        errors.append("最小风险回报比应>=1.0")

    # 检查目标比例
    if RISK_MANAGEMENT['target_ratio'] <= RISK_MANAGEMENT['stop_loss_ratio']:
        errors.append("目标比例应大于止损比例")

    # 检查低位条件数量
    if not (2 <= LOW_POSITION_CONFIG['low_condition_min'] <= 4):
        errors.append("low_condition_min应在2-4之间")

    if errors:
        raise ValueError("配置参数错误:\n" + "\n".join(errors))

    return True


# 自动验证配置
if __name__ == '__main__':
    try:
        validate_config()
        print("✓ 配置验证通过")
        print("\n当前配置摘要:")
        print(f"  低位判断: 4个条件满足{LOW_POSITION_CONFIG['low_condition_min']}个")
        print(f"  缩量下跌: {SUPPLY_DRY_CONFIG['min_days']}-{SUPPLY_DRY_CONFIG['max_days']}天, "
              f"至少{SUPPLY_DRY_CONFIG['min_signals']}次SUPPLY_DRY_UP")
        print(f"  放量确认: volume_multiple > {HEALTHY_UP_CONFIG['min_volume_multiple']}")
        print(f"  风险管理: 止损{(1-RISK_MANAGEMENT['stop_loss_ratio'])*100:.0f}%, "
              f"目标+{(RISK_MANAGEMENT['target_ratio']-1)*100:.0f}%")
        print(f"  最小风险回报比: {RISK_MANAGEMENT['min_risk_reward']}")
    except ValueError as e:
        print(f"✗ {e}")
