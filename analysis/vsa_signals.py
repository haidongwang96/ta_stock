"""
VSA (Volume Spread Analysis) 量价原子信号检测模块

基于Price和Volume的原始数据，检测6种核心的量价关系信号：
1. HEALTHY_UP - 价涨量增（健康上涨）
2. WEAK_UP - 价涨量缩（无量空涨，警告信号）
3. PANIC_SELL - 价跌量增（恐慌抛售）
4. SUPPLY_DRY_UP - 价跌量缩（供应枯竭，关键买入信号）
5. ABSORPTION_BAR - 价平量增（吸筹/派发信号）
6. NO_INTEREST - 价平量缩（市场观望）
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VSASignalDetector:
    """VSA量价原子信号检测器"""

    # 信号类型常量
    HEALTHY_UP = 'HEALTHY_UP'           # 价涨量增
    WEAK_UP = 'WEAK_UP'                 # 价涨量缩
    PANIC_SELL = 'PANIC_SELL'           # 价跌量增
    SUPPLY_DRY_UP = 'SUPPLY_DRY_UP'     # 价跌量缩（关键信号）
    ABSORPTION_BAR = 'ABSORPTION_BAR'   # 价平量增
    NO_INTEREST = 'NO_INTEREST'         # 价平量缩
    NEUTRAL = 'NEUTRAL'                 # 无明确信号

    def __init__(self, volume_threshold=1.5, narrow_threshold=0.02):
        """
        初始化VSA信号检测器

        参数:
            volume_threshold: 成交量倍数阈值（默认1.5倍VMA表示放量）
            narrow_threshold: 窄幅K线阈值（默认2%涨跌幅以内为窄幅）
        """
        self.volume_threshold = volume_threshold
        self.narrow_threshold = narrow_threshold
        #logger.info(f"VSA信号检测器初始化: volume_threshold={volume_threshold}, narrow_threshold={narrow_threshold}")

    def detect_signal(self, row: pd.Series, prev_close: Optional[float] = None) -> Tuple[str, int, str]:
        """
        检测单根K线的VSA信号

        参数:
            row: 包含OHLCV和volume_multiple的Series
                必需字段: open, high, low, close, volume_multiple
            prev_close: 前一日收盘价（用于判断涨跌）

        返回:
            (signal_type, strength, description)
            - signal_type: 信号类型字符串
            - strength: 信号强度 (0-3)
            - description: 信号描述
        """
        try:
            # 检查必需字段
            required_fields = ['open', 'high', 'low', 'close']
            for field in required_fields:
                if field not in row or pd.isna(row[field]):
                    return self.NEUTRAL, 0, '数据不完整'

            # 如果没有volume_multiple，返回中性
            if 'volume_multiple' not in row or pd.isna(row['volume_multiple']):
                return self.NEUTRAL, 0, '缺少成交量数据'

            # 判断价格方向
            is_up = self._is_price_up(row, prev_close)
            is_down = self._is_price_down(row, prev_close)

            # 判断成交量状态
            is_high_vol = self._is_high_volume(row)
            is_low_vol = self._is_low_volume(row)

            # 判断是否为窄幅K线
            is_narrow = self._is_narrow_range(row)

            # 计算收盘位置（用于判断K线强度）
            close_pos = self._calculate_close_position(row)

            # 信号检测逻辑

            # 1. 价涨+量增（健康上涨）
            if is_up and is_high_vol and not is_narrow:
                # 收盘价接近最高价（收盘位置>0.7）表示强势
                if close_pos > 0.7:
                    strength = 3 if row['volume_multiple'] > 2.0 else 2
                    return self.HEALTHY_UP, strength, f'价涨量增-健康上涨(量倍:{row["volume_multiple"]:.2f})'
                else:
                    return self.HEALTHY_UP, 1, f'价涨量增-温和上涨(收盘位:{close_pos:.2f})'

            # 2. 价涨+量缩（无量空涨）
            if is_up and is_low_vol:
                return self.WEAK_UP, 1, f'价涨量缩-警告信号(量倍:{row["volume_multiple"]:.2f})'

            # 3. 价跌+量增（恐慌抛售）
            if is_down and is_high_vol and not is_narrow:
                # 收盘价接近最低价（收盘位置<0.3）表示恐慌
                if close_pos < 0.3:
                    strength = 3 if row['volume_multiple'] > 2.0 else 2
                    return self.PANIC_SELL, strength, f'价跌量增-恐慌抛售(量倍:{row["volume_multiple"]:.2f})'
                else:
                    return self.PANIC_SELL, 1, f'价跌量增-温和抛售(收盘位:{close_pos:.2f})'

            # 4. 价跌+量缩（缩量惜售）- 关键买入信号
            if is_down and is_low_vol:
                # 成交量越小，信号越强
                if row['volume_multiple'] < 0.5:
                    strength = 3
                elif row['volume_multiple'] < 0.7:
                    strength = 2
                else:
                    strength = 1
                return self.SUPPLY_DRY_UP, strength, f'价跌量缩-供应枯竭(量倍:{row["volume_multiple"]:.2f})'

            # 5. 价平+量增（吸筹/派发）
            if is_narrow and is_high_vol:
                strength = 3 if row['volume_multiple'] > 2.0 else 2
                return self.ABSORPTION_BAR, strength, f'价平量增-吸筹派发(量倍:{row["volume_multiple"]:.2f})'

            # 6. 价平+量缩（失去兴趣）
            if is_narrow and is_low_vol:
                return self.NO_INTEREST, 0, f'价平量缩-市场观望(量倍:{row["volume_multiple"]:.2f})'

            # 默认：无明确信号
            return self.NEUTRAL, 0, '无明确信号'

        except Exception as e:
            logger.error(f"VSA信号检测失败: {e}")
            return self.NEUTRAL, 0, f'检测失败: {str(e)}'

    def _is_price_up(self, row: pd.Series, prev_close: Optional[float] = None) -> bool:
        """
        判断是否为上涨

        参数:
            row: K线数据
            prev_close: 前一日收盘价

        返回:
            True表示上涨
        """
        if prev_close is not None:
            # 如果有前一日收盘价，用当日收盘价对比
            return row['close'] > prev_close
        else:
            # 否则用当日开盘价对比收盘价
            return row['close'] > row['open']

    def _is_price_down(self, row: pd.Series, prev_close: Optional[float] = None) -> bool:
        """判断是否为下跌"""
        if prev_close is not None:
            return row['close'] < prev_close
        else:
            return row['close'] < row['open']

    def _is_high_volume(self, row: pd.Series) -> bool:
        """
        判断是否为放量（成交量 > 1.5倍VMA）

        参数:
            row: 必须包含volume_multiple字段

        返回:
            True表示放量
        """
        return row['volume_multiple'] > self.volume_threshold

    def _is_low_volume(self, row: pd.Series) -> bool:
        """
        判断是否为缩量（成交量 < VMA）

        参数:
            row: 必须包含volume_multiple字段

        返回:
            True表示缩量
        """
        return row['volume_multiple'] < 1.0

    def _is_narrow_range(self, row: pd.Series) -> bool:
        """
        判断是否为窄幅K线（振幅 < 2%）

        参数:
            row: 包含open, high, low的Series

        返回:
            True表示窄幅
        """
        # 计算K线实体大小
        body_pct = abs(row['close'] - row['open']) / row['open']
        return body_pct < self.narrow_threshold

    def _calculate_close_position(self, row: pd.Series) -> float:
        """
        计算收盘位置（0-1之间，1表示收在最高点，0表示收在最低点）

        参数:
            row: 包含high, low, close的Series

        返回:
            收盘位置 (0.0 - 1.0)
        """
        range_val = row['high'] - row['low']
        if range_val == 0:
            return 0.5  # 一字板，返回中间位置
        return (row['close'] - row['low']) / range_val

    def detect_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        批量检测DataFrame中所有K线的VSA信号

        参数:
            df: 包含OHLCV和volume_multiple的DataFrame

        返回:
            添加了VSA信号列的DataFrame（原地修改）
            新增列: vsa_signal, vsa_strength, vsa_description
        """
        if df is None or df.empty:
            logger.warning("数据为空，无法进行VSA信号检测")
            return df

        # 初始化结果列
        df['vsa_signal'] = self.NEUTRAL
        df['vsa_strength'] = 0
        df['vsa_description'] = ''

        # 逐行检测信号
        for i in range(len(df)):
            if i > 0:
                prev_close = df.iloc[i-1]['close']
            else:
                prev_close = None

            signal, strength, desc = self.detect_signal(df.iloc[i], prev_close)
            df.loc[df.index[i], 'vsa_signal'] = signal
            df.loc[df.index[i], 'vsa_strength'] = strength
            df.loc[df.index[i], 'vsa_description'] = desc

        logger.info(f"完成VSA信号批量检测，共{len(df)}根K线")
        return df

    def get_signal_summary(self, df: pd.DataFrame) -> dict:
        """
        统计DataFrame中各类VSA信号的数量

        参数:
            df: 已经过detect_batch处理的DataFrame

        返回:
            信号统计字典
        """
        if 'vsa_signal' not in df.columns:
            logger.warning("数据中没有vsa_signal列，请先运行detect_batch")
            return {}

        summary = df['vsa_signal'].value_counts().to_dict()

        # 计算各类信号的平均强度
        for signal_type in summary.keys():
            mask = df['vsa_signal'] == signal_type
            avg_strength = df.loc[mask, 'vsa_strength'].mean()
            summary[f"{signal_type}_avg_strength"] = round(avg_strength, 2)

        return summary


if __name__ == '__main__':
    # 测试代码
    print("=== VSA信号检测器测试 ===\n")

    # 创建测试数据
    test_data = pd.DataFrame({
        'open': [10.0, 10.5, 10.3, 10.8, 10.6],
        'high': [10.6, 10.8, 10.5, 11.0, 10.7],
        'low': [9.9, 10.4, 10.0, 10.7, 10.3],
        'close': [10.5, 10.7, 10.1, 10.9, 10.4],
        'volume_multiple': [2.0, 1.8, 0.6, 2.5, 0.8],
    })

    # 初始化检测器
    detector = VSASignalDetector()

    # 批量检测
    result = detector.detect_batch(test_data)

    print("检测结果:")
    print(result[['close', 'volume_multiple', 'vsa_signal', 'vsa_strength', 'vsa_description']])

    print("\n信号统计:")
    summary = detector.get_signal_summary(result)
    for key, value in summary.items():
        print(f"{key}: {value}")
