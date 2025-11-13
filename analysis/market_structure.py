"""
市场结构分析模块（Market Structure Analysis）

基于VSA量价信号和价格结构，判断市场处于哪个阶段：
1. ACCUMULATION - 吸筹区（底部横盘，主力悄悄买入）
2. MARK_UP - 上涨区（趋势向上，这是我们要找入场的阶段）
3. DISTRIBUTION - 派发区（顶部横盘，主力悄悄卖出）
4. MARK_DOWN - 下跌区（趋势向下）

根据Wyckoff理论，市场循环遵循：吸筹 -> 上涨 -> 派发 -> 下跌 -> 吸筹...
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict
import logging
from .vsa_signals import VSASignalDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketStructureAnalyzer:
    """市场结构分析器（日线级别）"""

    # 市场结构类型常量
    ACCUMULATION = 'ACCUMULATION'   # 吸筹区
    MARK_UP = 'MARK_UP'             # 上涨区（关键：只在此阶段寻找入场）
    DISTRIBUTION = 'DISTRIBUTION'   # 派发区
    MARK_DOWN = 'MARK_DOWN'         # 下跌区
    RANGING = 'RANGING'             # 横盘整理
    UNKNOWN = 'UNKNOWN'             # 数据不足/无法判断

    def __init__(self, lookback_period=20):
        """
        初始化市场结构分析器

        参数:
            lookback_period: 回溯周期，用于判断结构（默认20天）
        """
        self.lookback_period = lookback_period
        self.signal_detector = VSASignalDetector()
        logger.info(f"市场结构分析器初始化: lookback_period={lookback_period}")

    def analyze_structure(self, df: pd.DataFrame) -> Tuple[str, float, str]:
        """
        分析日线数据的市场结构

        参数:
            df: 包含OHLCV和volume_multiple的DataFrame（至少需要lookback_period天数据）
               必需列: open, high, low, close, volume_multiple

        返回:
            (structure, confidence, details)
            - structure: 市场结构类型（ACCUMULATION/MARK_UP/DISTRIBUTION/MARK_DOWN/RANGING/UNKNOWN）
            - confidence: 置信度 (0.0-1.0)
            - details: 结构特征描述
        """
        if df is None or df.empty:
            return self.UNKNOWN, 0.0, '数据为空'

        if len(df) < self.lookback_period:
            return self.UNKNOWN, 0.0, f'数据不足（需要至少{self.lookback_period}天）'

        try:
            # 取最近的数据进行分析
            recent = df.tail(self.lookback_period).copy()

            # 1. 统计VSA信号分布
            signal_counts = self._count_signal_types(recent)

            # 2. 判断趋势结构
            is_uptrend = self._is_making_higher_highs_higher_lows(recent)
            is_downtrend = self._is_making_lower_highs_lower_lows(recent)
            is_ranging = not is_uptrend and not is_downtrend

            # 3. 计算价格波动率（判断是否横盘）
            price_volatility = self._calculate_price_volatility(recent)

            # 4. 判断市场结构
            structure, confidence, details = self._determine_structure(
                signal_counts, is_uptrend, is_downtrend, is_ranging, price_volatility
            )

            logger.info(f"市场结构分析完成: {structure} (置信度: {confidence:.2f}) - {details}")
            return structure, confidence, details

        except Exception as e:
            logger.error(f"市场结构分析失败: {e}")
            return self.UNKNOWN, 0.0, f'分析失败: {str(e)}'

    def _count_signal_types(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        统计各类VSA信号的出现次数

        参数:
            df: 包含K线数据的DataFrame

        返回:
            信号计数字典
        """
        signal_counts = {
            VSASignalDetector.HEALTHY_UP: 0,
            VSASignalDetector.WEAK_UP: 0,
            VSASignalDetector.PANIC_SELL: 0,
            VSASignalDetector.SUPPLY_DRY_UP: 0,
            VSASignalDetector.ABSORPTION_BAR: 0,
            VSASignalDetector.NO_INTEREST: 0,
        }

        # 检测每根K线的信号
        for i in range(len(df)):
            if i > 0:
                prev_close = df.iloc[i-1]['close']
            else:
                prev_close = None

            signal, _, _ = self.signal_detector.detect_signal(df.iloc[i], prev_close)
            if signal in signal_counts:
                signal_counts[signal] += 1

        return signal_counts

    def _is_making_higher_highs_higher_lows(self, df: pd.DataFrame) -> bool:
        """
        判断是否形成更高的高点和更高的低点（上涨结构）

        参数:
            df: 包含high和low的DataFrame

        返回:
            True表示形成上涨结构
        """
        if len(df) < 10:
            return False

        # 将数据分为前半段和后半段
        mid_point = len(df) // 2

        # 前半段的最高点和最低点
        first_half_high = df.iloc[:mid_point]['high'].max()
        first_half_low = df.iloc[:mid_point]['low'].min()

        # 后半段的最高点和最低点
        second_half_high = df.iloc[mid_point:]['high'].max()
        second_half_low = df.iloc[mid_point:]['low'].min()

        # 判断：后半段的高点 > 前半段的高点 AND 后半段的低点 > 前半段的低点
        higher_high = second_half_high > first_half_high
        higher_low = second_half_low > first_half_low

        return higher_high and higher_low

    def _is_making_lower_highs_lower_lows(self, df: pd.DataFrame) -> bool:
        """
        判断是否形成更低的高点和更低的低点（下跌结构）

        参数:
            df: 包含high和low的DataFrame

        返回:
            True表示形成下跌结构
        """
        if len(df) < 10:
            return False

        mid_point = len(df) // 2

        first_half_high = df.iloc[:mid_point]['high'].max()
        first_half_low = df.iloc[:mid_point]['low'].min()

        second_half_high = df.iloc[mid_point:]['high'].max()
        second_half_low = df.iloc[mid_point:]['low'].min()

        lower_high = second_half_high < first_half_high
        lower_low = second_half_low < first_half_low

        return lower_high and lower_low

    def _calculate_price_volatility(self, df: pd.DataFrame) -> float:
        """
        计算价格波动率（用于判断是否横盘）

        参数:
            df: 包含close的DataFrame

        返回:
            波动率（标准差 / 均值）
        """
        if len(df) < 2:
            return 0.0

        close_prices = df['close'].values
        mean_price = close_prices.mean()
        std_price = close_prices.std()

        if mean_price == 0:
            return 0.0

        # 归一化波动率
        volatility = std_price / mean_price

        return volatility

    def _determine_structure(self, signal_counts: Dict[str, int], is_uptrend: bool,
                            is_downtrend: bool, is_ranging: bool,
                            price_volatility: float) -> Tuple[str, float, str]:
        """
        根据信号统计和趋势判断，确定市场结构

        参数:
            signal_counts: VSA信号统计
            is_uptrend: 是否为上涨趋势
            is_downtrend: 是否为下跌趋势
            is_ranging: 是否为横盘
            price_volatility: 价格波动率

        返回:
            (structure, confidence, details)
        """
        # 提取关键信号数量
        healthy_up_count = signal_counts[VSASignalDetector.HEALTHY_UP]
        weak_up_count = signal_counts[VSASignalDetector.WEAK_UP]
        panic_sell_count = signal_counts[VSASignalDetector.PANIC_SELL]
        supply_dry_count = signal_counts[VSASignalDetector.SUPPLY_DRY_UP]
        absorption_count = signal_counts[VSASignalDetector.ABSORPTION_BAR]

        # 判断1：上涨区（MARK_UP）
        # 特征：趋势向上 + 回调时缩量（供应枯竭）+ 上涨时放量（健康上涨）
        if is_uptrend:
            if supply_dry_count >= 3 and healthy_up_count >= 3:
                confidence = 0.85
                details = f'上涨结构：回调缩量{supply_dry_count}次+上涨放量{healthy_up_count}次'
                return self.MARK_UP, confidence, details
            elif healthy_up_count >= 2:
                confidence = 0.70
                details = f'上涨结构：上涨放量{healthy_up_count}次（但回调特征不明显）'
                return self.MARK_UP, confidence, details

        # 判断2：派发区（DISTRIBUTION）
        # 特征：横盘 + 上涨缩量（无量空涨）或 价平量增（主力出货）
        if is_ranging and price_volatility < 0.03:  # 波动率<3%表示横盘
            if weak_up_count >= 3 or absorption_count >= 2:
                confidence = 0.75
                details = f'派发结构：横盘+上涨缩量{weak_up_count}次/吸筹派发{absorption_count}次'
                return self.DISTRIBUTION, confidence, details

        # 判断3：吸筹区（ACCUMULATION）
        # 特征：底部横盘 + 价跌量缩（供应枯竭）或 价平量增（底部吸筹）
        if is_ranging and price_volatility < 0.03:
            if supply_dry_count >= 3:
                confidence = 0.75
                details = f'吸筹结构：底部横盘+缩量{supply_dry_count}次'
                return self.ACCUMULATION, confidence, details
            elif absorption_count >= 2 and panic_sell_count >= 1:
                # 出现过恐慌抛售，然后被吸收
                confidence = 0.70
                details = f'吸筹结构：恐慌抛售{panic_sell_count}次被吸收（吸筹{absorption_count}次）'
                return self.ACCUMULATION, confidence, details

        # 判断4：下跌区（MARK_DOWN）
        # 特征：趋势向下
        if is_downtrend:
            confidence = 0.80
            details = f'下跌结构：更低的高点和低点'
            return self.MARK_DOWN, confidence, details

        # 判断5：横盘整理（RANGING）
        if is_ranging:
            confidence = 0.60
            details = f'横盘整理：波动率{price_volatility:.2%}'
            return self.RANGING, confidence, details

        # 默认：无法判断
        return self.UNKNOWN, 0.50, '市场结构不明确'

    def is_in_markup_phase(self, df: pd.DataFrame) -> bool:
        """
        快速判断是否处于上涨区（MARK_UP阶段）

        这是策略入场的前置条件：只在上涨区寻找买入机会

        参数:
            df: K线数据

        返回:
            True表示处于上涨区
        """
        structure, confidence, _ = self.analyze_structure(df)
        return structure == self.MARK_UP and confidence >= 0.70


if __name__ == '__main__':
    # 测试代码
    print("=== 市场结构分析器测试 ===\n")

    # 创建测试数据：模拟上涨趋势
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=30, freq='D')

    # 上涨趋势数据
    uptrend_data = pd.DataFrame({
        'trade_date': dates,
        'open': np.linspace(10, 15, 30) + np.random.randn(30) * 0.2,
        'high': np.linspace(10.5, 15.5, 30) + np.random.randn(30) * 0.2,
        'low': np.linspace(9.8, 14.8, 30) + np.random.randn(30) * 0.2,
        'close': np.linspace(10.2, 15.2, 30) + np.random.randn(30) * 0.2,
        'volume_multiple': np.random.choice([0.5, 0.8, 1.2, 1.8, 2.0], 30),
    })

    # 初始化分析器
    analyzer = MarketStructureAnalyzer(lookback_period=20)

    # 分析结构
    structure, confidence, details = analyzer.analyze_structure(uptrend_data)

    print(f"市场结构: {structure}")
    print(f"置信度: {confidence:.2%}")
    print(f"详细描述: {details}")
    print(f"是否处于上涨区: {analyzer.is_in_markup_phase(uptrend_data)}")
