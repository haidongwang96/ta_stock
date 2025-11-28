"""
回测配置文件

包含回测的默认参数设置
"""

# ==================== 资金管理配置 ====================

# 初始资金
INITIAL_CAPITAL = 100000.0

# 佣金费率（万分之三）
COMMISSION_RATE = 0.0003

# 印花税率（千分之一，仅卖出时收取）
STAMP_TAX_RATE = 0.001

# 最低佣金（元）
MIN_COMMISSION = 5.0

# 滑点（百分比）
SLIPPAGE = 0.0


# ==================== 策略配置 ====================

# 默认策略类型
DEFAULT_STRATEGY = 'SimpleHoldStrategy'

# 简单持有策略参数
SIMPLE_HOLD_PARAMS = {
    'hold_days': 5  # 持有天数
}

# 止盈止损策略参数
STOP_LOSS_PARAMS = {
    'stop_loss': -0.05,      # 止损比例（-5%）
    'take_profit': 0.10,     # 止盈比例（10%）
    'hold_days': 30          # 最大持有天数
}


# ==================== 数据配置 ====================

# 数据库路径（None表示使用默认路径）
DB_PATH = None

# 回测时获取历史数据的天数（用于技术指标计算）
HISTORY_DAYS = 60


# ==================== 输出配置 ====================

# 结果输出目录
OUTPUT_DIR = './backtest_results'

# 是否生成图表
GENERATE_PLOTS = True

# 是否保存详细交易记录
SAVE_TRADES = True

# 是否打印详细日志
VERBOSE = True

# 日志级别（DEBUG, INFO, WARNING, ERROR）
LOG_LEVEL = 'INFO'


# ==================== 风险管理配置 ====================

# 单只股票最大仓位比例
MAX_POSITION_RATIO = 0.3

# 最大同时持仓数量
MAX_POSITIONS = 10

# 无风险利率（用于计算夏普比率，年化）
RISK_FREE_RATE = 0.03


# ==================== 高级配置 ====================

# 是否使用开盘价买入（False则使用收盘价）
USE_OPEN_PRICE = True

# 是否使用收盘价卖出（False则使用开盘价）
USE_CLOSE_PRICE = True

# 是否跳过停牌日
SKIP_SUSPENDED_DAYS = True

# 回测模式（'signal' 表示按信号回测，'strategy' 表示完整策略回测）
BACKTEST_MODE = 'signal'


# ==================== 预定义策略配置集合 ====================

STRATEGY_CONFIGS = {
    'simple_hold_3d': {
        'strategy': 'SimpleHoldStrategy',
        'params': {'hold_days': 3}
    },
    'simple_hold_5d': {
        'strategy': 'SimpleHoldStrategy',
        'params': {'hold_days': 5}
    },
    'simple_hold_10d': {
        'strategy': 'SimpleHoldStrategy',
        'params': {'hold_days': 10}
    },
    'stop_loss_conservative': {
        'strategy': 'StopLossStrategy',
        'params': {
            'stop_loss': -0.03,
            'take_profit': 0.06,
            'hold_days': 20
        }
    },
    'stop_loss_aggressive': {
        'strategy': 'StopLossStrategy',
        'params': {
            'stop_loss': -0.08,
            'take_profit': 0.15,
            'hold_days': 40
        }
    }
}


# ==================== 辅助函数 ====================

def get_strategy_config(strategy_name: str) -> dict:
    """
    获取预定义的策略配置

    Args:
        strategy_name: 策略名称

    Returns:
        策略配置字典
    """
    if strategy_name in STRATEGY_CONFIGS:
        return STRATEGY_CONFIGS[strategy_name]
    else:
        raise ValueError(f"未找到策略配置：{strategy_name}")


def print_config():
    """打印当前配置"""
    print("\n" + "=" * 60)
    print("回测配置")
    print("=" * 60)
    print(f"初始资金：{INITIAL_CAPITAL:,.2f}")
    print(f"佣金费率：{COMMISSION_RATE:.4%}")
    print(f"印花税率：{STAMP_TAX_RATE:.4%}")
    print(f"最低佣金：{MIN_COMMISSION:.2f}")
    print(f"滑点：{SLIPPAGE:.4%}")
    print(f"默认策略：{DEFAULT_STRATEGY}")
    print(f"输出目录：{OUTPUT_DIR}")
    print(f"生成图表：{GENERATE_PLOTS}")
    print(f"日志级别：{LOG_LEVEL}")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    # 测试配置
    print_config()

    # 打印所有预定义策略
    print("预定义策略配置：")
    for name, config in STRATEGY_CONFIGS.items():
        print(f"  - {name}: {config}")
