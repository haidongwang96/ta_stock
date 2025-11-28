"""
回测执行脚本

用于运行股票回测的命令行工具
"""

import sys
import os
import argparse
import logging
import json
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtester, BacktestMetrics, BacktestVisualizer
from backtesting.strategy_base import SimpleHoldStrategy, StopLossStrategy
from config import backtest_config


def setup_logging(log_level: str = 'INFO'):
    """
    配置日志

    Args:
        log_level: 日志级别
    """
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def create_strategy(strategy_name: str, **params):
    """
    创建策略实例

    Args:
        strategy_name: 策略名称
        **params: 策略参数

    Returns:
        策略实例
    """
    if strategy_name == 'SimpleHoldStrategy':
        return SimpleHoldStrategy(**params)
    elif strategy_name == 'StopLossStrategy':
        return StopLossStrategy(**params)
    else:
        raise ValueError(f"未知的策略类型：{strategy_name}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='股票回测工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 基础回测（使用默认策略）
  python scripts/run_backtest.py --signals examples/signals.csv

  # 指定初始资金
  python scripts/run_backtest.py --signals signals.csv --capital 200000

  # 使用预定义策略配置
  python scripts/run_backtest.py --signals signals.csv --preset simple_hold_3d

  # 使用止盈止损策略
  python scripts/run_backtest.py --signals signals.csv --strategy StopLossStrategy --stop-loss -0.05 --take-profit 0.10

  # 指定输出目录和生成图表
  python scripts/run_backtest.py --signals signals.csv --output results/ --plot

  # 保存详细交易记录和指标
  python scripts/run_backtest.py --signals signals.csv --output results/ --save-trades --save-metrics
        """
    )

    # 必需参数
    parser.add_argument('--signals', required=True, help='信号文件路径（CSV格式）')

    # 资金管理参数
    parser.add_argument('--capital', type=float, default=backtest_config.INITIAL_CAPITAL,
                       help=f'初始资金（默认：{backtest_config.INITIAL_CAPITAL}）')
    parser.add_argument('--commission', type=float, default=backtest_config.COMMISSION_RATE,
                       help=f'佣金费率（默认：{backtest_config.COMMISSION_RATE}）')
    parser.add_argument('--stamp-tax', type=float, default=backtest_config.STAMP_TAX_RATE,
                       help=f'印花税率（默认：{backtest_config.STAMP_TAX_RATE}）')
    parser.add_argument('--min-commission', type=float, default=backtest_config.MIN_COMMISSION,
                       help=f'最低佣金（默认：{backtest_config.MIN_COMMISSION}）')
    parser.add_argument('--slippage', type=float, default=backtest_config.SLIPPAGE,
                       help=f'滑点（默认：{backtest_config.SLIPPAGE}）')

    # 策略参数
    parser.add_argument('--preset', type=str, choices=list(backtest_config.STRATEGY_CONFIGS.keys()),
                       help='使用预定义的策略配置')
    parser.add_argument('--strategy', type=str, default='SimpleHoldStrategy',
                       choices=['SimpleHoldStrategy', 'StopLossStrategy'],
                       help='策略类型（默认：SimpleHoldStrategy）')
    parser.add_argument('--hold-days', type=int, default=5,
                       help='持有天数（SimpleHoldStrategy，默认：5）')
    parser.add_argument('--stop-loss', type=float, default=-0.05,
                       help='止损比例（StopLossStrategy，默认：-0.05）')
    parser.add_argument('--take-profit', type=float, default=0.10,
                       help='止盈比例（StopLossStrategy，默认：0.10）')
    parser.add_argument('--max-hold-days', type=int, default=30,
                       help='最大持有天数（StopLossStrategy，默认：30）')

    # 数据参数
    parser.add_argument('--db-path', type=str, default=None,
                       help='数据库路径（默认使用项目根目录下的stock_data.db）')

    # 输出参数
    parser.add_argument('--output', type=str, default=backtest_config.OUTPUT_DIR,
                       help=f'结果输出目录（默认：{backtest_config.OUTPUT_DIR}）')
    parser.add_argument('--plot', action='store_true',
                       help='生成图表')
    parser.add_argument('--save-trades', action='store_true',
                       help='保存详细交易记录到CSV')
    parser.add_argument('--save-metrics', action='store_true',
                       help='保存指标到JSON文件')

    # 日志参数
    parser.add_argument('--log-level', type=str, default=backtest_config.LOG_LEVEL,
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help=f'日志级别（默认：{backtest_config.LOG_LEVEL}）')

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # 检查信号文件是否存在
    if not os.path.exists(args.signals):
        logger.error(f"信号文件不存在：{args.signals}")
        return 1

    # 创建策略
    if args.preset:
        # 使用预定义配置
        preset_config = backtest_config.get_strategy_config(args.preset)
        strategy_name = preset_config['strategy']
        strategy_params = preset_config['params']
        logger.info(f"使用预定义策略配置：{args.preset}")
    else:
        # 使用命令行参数
        strategy_name = args.strategy
        if strategy_name == 'SimpleHoldStrategy':
            strategy_params = {'hold_days': args.hold_days}
        elif strategy_name == 'StopLossStrategy':
            strategy_params = {
                'stop_loss': args.stop_loss,
                'take_profit': args.take_profit,
                'hold_days': args.max_hold_days
            }
        else:
            strategy_params = {}

    strategy = create_strategy(strategy_name, **strategy_params)
    logger.info(f"使用策略：{strategy}")

    # 创建回测器
    backtester = Backtester(
        signals_file=args.signals,
        strategy=strategy,
        initial_capital=args.capital,
        commission_rate=args.commission,
        stamp_tax_rate=args.stamp_tax,
        min_commission=args.min_commission,
        slippage=args.slippage,
        db_path=args.db_path
    )

    # 运行回测
    logger.info("开始回测...")
    start_time = datetime.now()

    if not backtester.run():
        logger.error("回测失败")
        return 1

    end_time = datetime.now()
    logger.info(f"回测完成，耗时：{(end_time - start_time).total_seconds():.2f}秒")

    # 获取结果
    results = backtester.get_results()

    # 计算指标
    metrics = BacktestMetrics(
        equity_curve=results['equity_curve'],
        closed_trades=results['trades'],
        initial_capital=args.capital
    )
    metrics.print_metrics()

    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)

    # 保存交易记录
    if args.save_trades and not results['trades'].empty:
        trades_file = os.path.join(args.output, 'trades.csv')
        results['trades'].to_csv(trades_file, index=False, encoding='utf-8-sig')
        logger.info(f"交易记录已保存至：{trades_file}")

    # 保存指标
    if args.save_metrics:
        metrics_file = os.path.join(args.output, 'metrics.json')
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(metrics.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"回测指标已保存至：{metrics_file}")

    # 保存净值曲线
    equity_file = os.path.join(args.output, 'equity_curve.csv')
    results['equity_curve'].to_csv(equity_file, index=False, encoding='utf-8-sig')
    logger.info(f"净值曲线已保存至：{equity_file}")

    # 生成图表
    if args.plot:
        visualizer = BacktestVisualizer(
            equity_curve=results['equity_curve'],
            trades=results['trades'],
            initial_capital=args.capital
        )
        visualizer.plot_all(output_dir=args.output)

    logger.info(f"所有结果已保存至：{args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
