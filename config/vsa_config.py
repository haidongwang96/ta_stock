"""
VSA策略参数配置文件

集中管理所有VSA相关参数，便于调优和回测
"""

# ===== 信号检测参数 =====
VSA_SIGNAL_PARAMS = {
    # 成交量倍数阈值
    'volume_high_threshold': 1.5,       # 放量标准：成交量 > 1.5倍VMA20
    'volume_low_threshold': 1.0,        # 缩量标准：成交量 < 1.0倍VMA20
    'volume_extreme_threshold': 2.0,    # 极端放量：成交量 > 2.0倍VMA20（天量）
    'volume_dry_threshold': 0.7,        # 供应枯竭：成交量 < 0.7倍VMA20

    # K线形态参数
    'narrow_range_pct': 0.02,           # 窄幅K线：涨跌幅 < 2%
    'close_position_high': 0.7,         # 收盘位置高位：> 0.7（强势）
    'close_position_low': 0.3,          # 收盘位置低位：< 0.3（弱势）

    # VMA计算周期
    'vma_period': 20,                   # 成交量均线周期（日）
}

# ===== 市场结构分析参数 =====
STRUCTURE_PARAMS = {
    # 结构分析回溯期
    'lookback_period': 20,              # 分析最近20天数据判断结构

    # 趋势判断参数
    'uptrend_min_healthy_up': 3,        # 上涨区最少需要3次价涨量增
    'uptrend_min_supply_dry': 3,        # 上涨区最少需要3次缩量回调

    # 派发区判断参数
    'distribution_min_weak_up': 3,      # 派发区最少需要3次无量空涨
    'distribution_min_absorption': 2,   # 派发区最少需要2次价平量增

    # 吸筹区判断参数
    'accumulation_min_supply_dry': 3,   # 吸筹区最少需要3次缩量
    'accumulation_min_absorption': 2,   # 吸筹区最少需要2次吸筹信号

    # 横盘波动率阈值
    'ranging_volatility': 0.03,         # 波动率 < 3% 判定为横盘

    # 结构置信度阈值
    'min_confidence': 0.70,             # 最低置信度要求
}

# ===== 交易策略参数 =====
STRATEGY_PARAMS = {
    # 策略1：缩量回调后需求确认（TEST_ENTRY）
    'test_entry': {
        'lookback_days': 10,            # 回溯天数
        'rally_check_range': (3, 7),    # 检查前期上涨的天数区间
        'pullback_days': 3,             # 回调天数
        'min_supply_dry_count': 2,      # 最少缩量回调天数
        'stop_loss_lookback': 5,        # 止损参考最近N天低点
        'profit_target_pct': 0.05,      # 目标涨幅5%
    },

    # 策略2：突破-回踩（BREAKOUT_PULLBACK）
    'breakout_pullback': {
        'lookback_days': 25,            # 回溯天数
        'resistance_period': 20,        # 阻力位参考周期（20日高点）
        'breakout_check_range': (3, 5), # 检查突破的天数区间
        'breakout_volume_threshold': 1.5,  # 突破时需要的成交量倍数
        'pullback_tolerance': 0.03,     # 回踩容差3%（价格可高于支撑位3%）
        'stop_loss_pct': 0.98,          # 止损设在支撑位下方2%
        'profit_target_pct': 0.08,      # 目标涨幅8%
    },

    # 策略3：恐慌抛售后吸筹确认（SELLING_CLIMAX）
    'selling_climax': {
        'lookback_days': 10,            # 回溯天数
        'climax_check_range': (1, 3),   # 检查恐慌抛售的天数区间
        'lower_shadow_ratio': 0.5,      # 下影线占比 > 50%
        'climax_volume_threshold': 1.8, # 恐慌抛售时成交量倍数
        'volume_dry_threshold': 1.0,    # 之后成交量需萎缩至 < 1.0倍VMA
        'recovery_threshold': 1.02,     # 价格需回升至低点以上2%
        'stop_loss_pct': 0.98,          # 止损设在恐慌低点下方2%
        'profit_target_pct': 0.10,      # 目标涨幅10%
    },

    # 通用参数
    'min_data_days': 30,                # 扫描信号至少需要30天数据
    'only_markup_phase': True,          # 只在MARK_UP阶段寻找信号
}

# ===== 风控参数 =====
RISK_PARAMS = {
    # 止损止盈
    'max_loss_pct': 0.05,               # 最大亏损5%
    'min_profit_pct': 0.05,             # 最小盈利5%
    'trailing_stop_pct': 0.03,          # 移动止损3%

    # 风险回报比
    'min_risk_reward': 1.5,             # 最低风险回报比1.5:1

    # 仓位管理
    'max_position_pct': 0.20,           # 单只股票最大仓位20%
    'max_positions': 5,                 # 最多持仓5只

    # 信号过滤
    'min_signal_strength': 2,           # 最低信号强度
}

# ===== 数据参数 =====
DATA_PARAMS = {
    # 数据获取
    'default_start_days': 60,           # 默认获取60天数据
    'min_price': 5.0,                   # 最低价格过滤（元）
    'max_price': 500.0,                 # 最高价格过滤（元）
    'min_volume': 1000000,              # 最小成交量过滤（股）

    # 数据质量
    'max_missing_ratio': 0.1,           # 最大缺失数据比例10%
}

# ===== 输出参数 =====
OUTPUT_PARAMS = {
    # 报告格式
    'date_format': '%Y-%m-%d',          # 日期格式
    'price_decimals': 2,                # 价格小数位
    'pct_decimals': 2,                  # 百分比小数位

    # 输出列
    'signal_columns': [
        'type',                         # 信号类型
        'date',                         # 日期
        'price',                        # 价格
        'strength',                     # 强度
        'description',                  # 描述
        'stop_loss',                    # 止损
        'target',                       # 目标
        'risk_reward',                  # 风险回报比
    ],
}


def get_all_params():
    """获取所有参数的字典"""
    return {
        'signal': VSA_SIGNAL_PARAMS,
        'structure': STRUCTURE_PARAMS,
        'strategy': STRATEGY_PARAMS,
        'risk': RISK_PARAMS,
        'data': DATA_PARAMS,
        'output': OUTPUT_PARAMS,
    }


def print_params():
    """打印所有参数"""
    all_params = get_all_params()

    print("=" * 60)
    print("VSA策略参数配置")
    print("=" * 60)

    for category, params in all_params.items():
        print(f"\n【{category.upper()}】")
        print("-" * 60)

        if isinstance(params, dict):
            for key, value in params.items():
                if isinstance(value, dict):
                    print(f"\n  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    {sub_key}: {sub_value}")
                else:
                    print(f"  {key}: {value}")


if __name__ == '__main__':
    print_params()
