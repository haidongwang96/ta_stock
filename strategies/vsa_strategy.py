"""
VSA右侧交易策略模块

实现三种基于量价分析的右侧买入逻辑：
1. TEST_ENTRY - 缩量回调后的需求确认
2. BREAKOUT_PULLBACK - 突破-回踩
3. SELLING_CLIMAX - 恐慌抛售后的吸筹确认

策略前提条件：只在日线MARK_UP（上涨区）结构下激活
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import logging
import sys
import os

# 添加父目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from analysis.vsa_signals import VSASignalDetector
from analysis.market_structure import MarketStructureAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VSAStrategy:
    """VSA右侧交易策略"""

    def __init__(self):
        """初始化VSA策略"""
        self.structure_analyzer = MarketStructureAnalyzer()
        self.signal_detector = VSASignalDetector()
        logger.info("VSA策略初始化完成")

    def scan_entry_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        扫描入场信号

        参数:
            df: 日线数据（包含OHLCV和volume_multiple）
               至少需要30天数据以确保分析准确性

        返回:
            signals: 入场信号列表，每个信号包含：
                {
                    'type': 信号类型,
                    'date': 交易日期,
                    'price': 当前价格,
                    'strength': 信号强度,
                    'description': 信号描述,
                    'stop_loss': 建议止损价,
                    'target': 建议目标价
                }
        """
        signals = []

        if df is None or df.empty or len(df) < 30:
            logger.warning("数据不足，无法进行信号扫描（至少需要30天数据）")
            return signals

        try:
            # 1. 首先判断日线结构
            structure, confidence, details = self.structure_analyzer.analyze_structure(df)

            logger.info(f"市场结构: {structure} (置信度: {confidence:.2%}) - {details}")

            # 只在上涨区寻找入场机会
            if structure != MarketStructureAnalyzer.MARK_UP:
                logger.info(f"当前市场结构为{structure}，不是上涨区，跳过信号扫描")
                return signals

            # 2. 在日线数据上检测三种入场模式

            # 策略1：缩量回调后的需求确认
            test_entry = self._detect_test_entry(df)
            if test_entry:
                signals.append(test_entry)
                logger.info(f"发现TEST_ENTRY信号: {test_entry['description']}")

            # 策略2：突破-回踩
            breakout_entry = self._detect_breakout_pullback(df)
            if breakout_entry:
                signals.append(breakout_entry)
                logger.info(f"发现BREAKOUT_PULLBACK信号: {breakout_entry['description']}")

            # 策略3：恐慌抛售后的吸筹确认
            climax_entry = self._detect_selling_climax_entry(df)
            if climax_entry:
                signals.append(climax_entry)
                logger.info(f"发现SELLING_CLIMAX信号: {climax_entry['description']}")

            return signals

        except Exception as e:
            logger.error(f"信号扫描失败: {e}")
            return signals

    def _detect_test_entry(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        策略1：检测缩量回调后的需求确认

        逻辑：
        1. 最近5-10天有过上涨（价涨量增）
        2. 最近2-3天开始回调
        3. 回调过程中成交量持续萎缩（SUPPLY_DRY_UP信号）
        4. 今天出现第一根放量阳线（需求回归）

        参数:
            df: K线数据

        返回:
            信号字典或None
        """
        if len(df) < 10:
            return None

        recent = df.tail(10)

        # 检查前期是否有过上涨（价涨量增）
        has_prior_rally = False
        for i in range(3, 7):
            if i >= len(recent):
                continue

            prev_close = recent.iloc[i-1]['close'] if i > 0 else None
            signal, strength, _ = self.signal_detector.detect_signal(
                recent.iloc[i],
                prev_close=prev_close
            )
            if signal == VSASignalDetector.HEALTHY_UP:
                has_prior_rally = True
                break

        if not has_prior_rally:
            return None

        # 检查最近2-3天是否为缩量回调
        pullback_days = recent.tail(4).head(3)  # 倒数第2-4天
        supply_dry_count = 0

        for i in range(len(pullback_days)):
            idx = pullback_days.index[i]
            row_idx = df.index.get_loc(idx)

            if row_idx > 0:
                prev_close = df.iloc[row_idx-1]['close']
            else:
                prev_close = None

            signal, _, _ = self.signal_detector.detect_signal(
                pullback_days.iloc[i],
                prev_close=prev_close
            )
            if signal == VSASignalDetector.SUPPLY_DRY_UP:
                supply_dry_count += 1

        # 至少2天缩量回调
        if supply_dry_count < 2:
            return None

        # 检查今天是否为需求回归（放量阳线）
        today = recent.iloc[-1]
        yesterday = recent.iloc[-2]

        signal, strength, _ = self.signal_detector.detect_signal(today, yesterday['close'])

        if signal == VSASignalDetector.HEALTHY_UP:
            # 计算止损和目标价
            stop_loss = recent.tail(5)['low'].min()  # 止损设在回调低点
            target = today['close'] * 1.05  # 目标5%

            return {
                'type': 'TEST_ENTRY',
                'date': today.name if hasattr(today, 'name') else 'N/A',
                'price': today['close'],
                'strength': strength,
                'description': f'缩量回调后需求确认 (回调{supply_dry_count}天)',
                'stop_loss': round(stop_loss, 2),
                'target': round(target, 2),
                'risk_reward': round((target - today['close']) / (today['close'] - stop_loss), 2)
            }

        return None

    def _detect_breakout_pullback(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        策略2：检测突破-回踩

        逻辑：
        1. 检测到放量突破20日高点
        2. 突破后回踩（价格回到阻力位附近）
        3. 回踩时缩量（SUPPLY_DRY_UP）
        4. 出现拐头向上信号

        参数:
            df: K线数据

        返回:
            信号字典或None
        """
        if len(df) < 25:
            return None

        recent = df.tail(25)
        resistance = recent.head(20)['high'].max()  # 20日高点作为阻力位

        # 检查3-5天前是否有突破
        breakout_day_idx = None
        for i in range(-5, -2):
            if abs(i) > len(recent):
                continue

            day = recent.iloc[i]
            prev_day = recent.iloc[i-1]

            # 突破条件：收盘价突破阻力+放量
            if (day['close'] > resistance and
                prev_day['close'] <= resistance and
                'volume_multiple' in day and day['volume_multiple'] > 1.5):
                breakout_day_idx = i
                break

        if breakout_day_idx is None:
            return None

        # 检查最近是否回踩+缩量
        pullback = recent.iloc[breakout_day_idx:]
        if len(pullback) < 2:
            return None

        # 价格回到支撑位附近（原阻力变支撑）
        current_low = pullback.tail(3)['low'].min()
        if current_low > resistance * 1.03:  # 未回踩到位
            return None

        # 回踩过程缩量
        has_dry_volume = False
        for i in range(1, len(pullback)):
            idx = pullback.index[i]
            row_idx = df.index.get_loc(idx)

            if row_idx > 0:
                prev_close = df.iloc[row_idx-1]['close']
            else:
                prev_close = None

            signal, _, _ = self.signal_detector.detect_signal(
                pullback.iloc[i],
                prev_close=prev_close
            )
            if signal == VSASignalDetector.SUPPLY_DRY_UP:
                has_dry_volume = True
                break

        if not has_dry_volume:
            return None

        # 今天是否拐头向上
        today = recent.iloc[-1]
        yesterday = recent.iloc[-2]

        if today['close'] > yesterday['close'] and today['close'] > resistance:
            return {
                'type': 'BREAKOUT_PULLBACK',
                'date': today.name if hasattr(today, 'name') else 'N/A',
                'price': today['close'],
                'strength': 2,
                'description': f'突破{resistance:.2f}后回踩确认',
                'stop_loss': round(resistance * 0.98, 2),
                'target': round(today['close'] * 1.08, 2),
                'risk_reward': round((today['close'] * 1.08 - today['close']) / (today['close'] - resistance * 0.98), 2)
            }

        return None

    def _detect_selling_climax_entry(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        策略3：检测恐慌抛售后的吸筹确认

        逻辑：
        1. 最近1-3天出现过恐慌抛售（价跌量增+长下影线）
        2. 之后K线不再创出新低
        3. 成交量迅速萎缩（抛售已结束）
        4. 价格开始回升

        参数:
            df: K线数据

        返回:
            信号字典或None
        """
        if len(df) < 10:
            return None

        recent = df.tail(10)

        # 检测最近1-3天是否出现恐慌抛售
        climax_day_idx = None
        climax_low = None

        for i in range(-3, 0):
            if abs(i) > len(recent):
                continue

            day = recent.iloc[i]

            # 恐慌抛售特征：
            # 1. 价跌量增（PANIC_SELL信号）
            # 2. 长下影线（下影线长度 > K线总长度的50%）
            idx = day.name if hasattr(day, 'name') else recent.index[i]
            row_idx = df.index.get_loc(idx)

            if row_idx > 0:
                prev_close = df.iloc[row_idx-1]['close']
            else:
                prev_close = None

            signal, strength, _ = self.signal_detector.detect_signal(day, prev_close)

            # 计算下影线长度
            total_range = day['high'] - day['low']
            lower_shadow = day['close'] - day['low'] if day['close'] > day['open'] else day['open'] - day['low']

            if signal == VSASignalDetector.PANIC_SELL and total_range > 0:
                lower_shadow_ratio = lower_shadow / total_range

                # 下影线 > 50% 总长度，且放量
                if lower_shadow_ratio > 0.5 and day['volume_multiple'] > 1.8:
                    climax_day_idx = i
                    climax_low = day['low']
                    break

        if climax_day_idx is None:
            return None

        # 检查之后是否不再创新低
        after_climax = recent.iloc[climax_day_idx+1:]
        if len(after_climax) < 1:
            return None

        # 是否创新低
        new_low = after_climax['low'].min()
        if new_low < climax_low:
            return None  # 创了新低，恐慌未结束

        # 检查成交量是否萎缩
        avg_volume_after = after_climax['volume_multiple'].mean()
        if avg_volume_after > 1.0:
            return None  # 成交量未萎缩

        # 今天是否回升
        today = recent.iloc[-1]
        yesterday = recent.iloc[-2]

        if today['close'] > yesterday['close'] and today['close'] > climax_low * 1.02:
            return {
                'type': 'SELLING_CLIMAX',
                'date': today.name if hasattr(today, 'name') else 'N/A',
                'price': today['close'],
                'strength': 3,
                'description': f'恐慌抛售后吸筹确认 (低点{climax_low:.2f})',
                'stop_loss': round(climax_low * 0.98, 2),
                'target': round(today['close'] * 1.10, 2),
                'risk_reward': round((today['close'] * 1.10 - today['close']) / (today['close'] - climax_low * 0.98), 2)
            }

        return None


if __name__ == '__main__':
    # 测试代码
    print("=== VSA策略测试 ===\n")

    # 创建测试数据：模拟上涨趋势后的回调
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=40, freq='D')

    # 模拟数据：前20天上涨，21-25天回调，26-30天再次上涨
    prices = []
    for i in range(40):
        if i < 20:
            prices.append(10 + i * 0.2)  # 上涨
        elif i < 25:
            prices.append(14 - (i-20) * 0.15)  # 回调
        else:
            prices.append(13 + (i-25) * 0.25)  # 再次上涨

    test_data = pd.DataFrame({
        'open': prices,
        'high': [p + 0.3 for p in prices],
        'low': [p - 0.3 for p in prices],
        'close': [p + np.random.randn() * 0.1 for p in prices],
        'volume_multiple': [
            2.0 if i < 15 or i >= 26 else 0.6 if 20 <= i < 25 else 1.2
            for i in range(40)
        ],
    }, index=dates)

    # 初始化策略
    strategy = VSAStrategy()

    # 扫描信号
    signals = strategy.scan_entry_signals(test_data)

    if signals:
        print(f"发现 {len(signals)} 个入场信号:\n")
        for signal in signals:
            print(f"类型: {signal['type']}")
            print(f"日期: {signal['date']}")
            print(f"价格: {signal['price']:.2f}")
            print(f"强度: {signal['strength']}")
            print(f"描述: {signal['description']}")
            print(f"止损: {signal['stop_loss']:.2f}")
            print(f"目标: {signal['target']:.2f}")
            print(f"风险回报比: {signal.get('risk_reward', 'N/A')}")
            print("-" * 50)
    else:
        print("未发现入场信号")
