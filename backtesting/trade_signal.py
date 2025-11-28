"""
交易信号数据类

用于表示交易信号的数据结构
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TradeSignal:
    """
    交易信号数据类

    Attributes:
        ts_code: 股票代码（如：000001.SZ）
        trade_date: 交易日期（如：20240115）
        position_ratio: 仓位比例（0.0-1.0）
        signal_type: 信号类型（'buy', 'sell', 'hold'等）
        price: 信号触发价格（可选）
        notes: 备注信息（可选）
    """
    ts_code: str
    trade_date: str
    position_ratio: float
    signal_type: str = 'buy'
    price: Optional[float] = None
    notes: Optional[str] = None

    def __post_init__(self):
        """验证数据有效性"""
        # 验证仓位比例
        if not 0.0 <= self.position_ratio <= 1.0:
            raise ValueError(f"仓位比例必须在0-1之间，当前值：{self.position_ratio}")

        # 确保日期格式正确（YYYYMMDD）
        if not isinstance(self.trade_date, str) or len(self.trade_date) != 8:
            raise ValueError(f"日期格式错误，应为YYYYMMDD格式，当前值：{self.trade_date}")

        # 验证股票代码格式
        if not self.ts_code or '.' not in self.ts_code:
            raise ValueError(f"股票代码格式错误，应为 XXXXXX.SZ/SH，当前值：{self.ts_code}")

    def to_datetime(self) -> datetime:
        """将trade_date转换为datetime对象"""
        return datetime.strptime(self.trade_date, '%Y%m%d')

    def __repr__(self) -> str:
        return (f"TradeSignal(ts_code={self.ts_code}, "
                f"date={self.trade_date}, "
                f"position={self.position_ratio:.2%}, "
                f"type={self.signal_type})")
