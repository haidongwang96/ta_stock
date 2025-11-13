"""
低位缩量反转策略

策略核心：在底部（ACCUMULATION）向上突破（MARK_UP）的转折时刻，
         捕捉"缩量下跌转放量上涨"的反转信号

入场逻辑：
1. 市场结构：ACCUMULATION → MARK_UP 转折
2. 低位判断：4重组合（布林带/RSI/均线/新低）满足3项
3. 缩量下跌：5-10天至少5次SUPPLY_DRY_UP信号
4. 放量上涨：HEALTHY_UP信号确认（分4个强度等级）

风险管理：
- 止损：缩量下跌期间最低点 * 0.98
- 目标：当前价 * 1.05（保守）或 1.08（强信号）
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入依赖模块
from analysis.vsa_signals import VSASignalDetector
from analysis.market_structure import MarketStructureAnalyzer
from config.low_volume_reversal_config import (
    LOW_POSITION_CONFIG,
    SUPPLY_DRY_CONFIG,
    HEALTHY_UP_CONFIG,
    MARKET_STRUCTURE_CONFIG,
    RISK_MANAGEMENT,
    validate_config
)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LowVolumeReversalStrategy:
    """低位缩量反转策略类"""

    def __init__(self):
        """初始化策略"""
        # 验证配置
        validate_config()

        # 初始化VSA信号检测器
        self.vsa_detector = VSASignalDetector()

        # 初始化市场结构分析器
        self.structure_analyzer = MarketStructureAnalyzer()

        logger.info("低位缩量反转策略初始化完成")

    def scan_entry_signals(self, df: pd.DataFrame, ts_code: str = None,
                          stock_name: str = None) -> List[Dict]:
        """
        扫描入场信号（主入口方法）

        Args:
            df: 包含OHLCV和技术指标的DataFrame，至少90天数据
            ts_code: 股票代码（可选，用于日志）
            stock_name: 股票名称（可选，用于报告）

        Returns:
            信号列表，每个信号为一个字典
        """
        if df is None or df.empty or len(df) < 30:
            logger.warning(f"{ts_code or '未知'}: 数据不足")
            return []

        # 确保必要字段存在
        required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'vol']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"{ts_code or '未知'}: 缺少必要字段")
            return []

        # 确保有volume_multiple字段（VSA核心指标）
        if 'volume_multiple' not in df.columns:
            # 临时计算
            df['volume_multiple'] = df['vol'] / df['vol'].rolling(window=20).mean()

        # 获取最新日期数据
        today = df.iloc[-1]
        today_date = today['trade_date'] if isinstance(today['trade_date'], str) else today['trade_date'].strftime('%Y%m%d')

        logger.debug(f"\n{'='*60}")
        logger.debug(f"开始扫描: {ts_code or '未知'} ({stock_name or ''}) - {today_date}")
        logger.debug(f"{'='*60}")

        signals = []

        try:
            # 第1步：检查市场结构转折
            structure_ok, structure_info = self._check_market_structure_transition(df)
            if not structure_ok:
                logger.debug(f"  ✗ 市场结构不符: {structure_info['reason']}")
                return []
            logger.debug(f"  ✓ 市场结构符合: {structure_info['structure']} (置信度{structure_info['confidence']:.2f})")

            # 第2步：检查低位
            is_low, low_info = self._check_low_position(df)
            if not is_low:
                logger.debug(f"  ✗ 低位判断不符: 仅满足{low_info['matched_count']}/{LOW_POSITION_CONFIG['low_condition_min']}个条件")
                return []
            logger.debug(f"  ✓ 低位确认: {', '.join(low_info['matched_conditions'])}")

            # 第3步：查找缩量下跌区间
            supply_dry_period = self._find_supply_dry_period(df)
            if supply_dry_period is None:
                logger.debug(f"  ✗ 未找到符合条件的缩量下跌区间")
                return []
            logger.debug(f"  ✓ 缩量下跌确认: {supply_dry_period['days']}天, "
                        f"{supply_dry_period['signal_count']}次SUPPLY_DRY_UP, "
                        f"均量倍数{supply_dry_period['avg_volume_multiple']:.2f}")

            # 第4步：检查放量上涨确认
            healthy_up_result = self._check_healthy_up_confirmation(df, supply_dry_period)
            if healthy_up_result is None:
                logger.debug(f"  ✗ 未出现放量上涨确认")
                return []

            signal_strength = healthy_up_result['strength']
            logger.debug(f"  ✓ 放量上涨确认: 强度{signal_strength}, {healthy_up_result['description']}")

            # 第5步：计算止损和目标位
            stop_loss, target, risk_reward = self._calculate_stop_and_target(
                current_price=today['close'],
                supply_dry_low=supply_dry_period['low_price'],
                signal_strength=signal_strength
            )

            # 检查风险回报比
            if risk_reward < RISK_MANAGEMENT['min_risk_reward']:
                logger.debug(f"  ✗ 风险回报比不足: {risk_reward:.2f} < {RISK_MANAGEMENT['min_risk_reward']}")
                return []
            logger.debug(f"  ✓ 风险管理: 止损{stop_loss:.2f}, 目标{target:.2f}, 风险回报比{risk_reward:.2f}")

            # 构建信号
            signal = {
                # 基础信息
                'type': 'LOW_VOLUME_REVERSAL',
                'ts_code': ts_code or 'UNKNOWN',
                'stock_name': stock_name or '',
                'date': today_date,
                'price': float(today['close']),
                'strength': signal_strength,

                # 市场结构
                'structure': structure_info['structure'],
                'structure_confidence': float(structure_info['confidence']),
                'structure_detail': structure_info.get('detail', ''),

                # 低位信息
                'low_conditions': low_info['matched_conditions'],
                'low_condition_count': low_info['matched_count'],

                # 缩量下跌信息
                'supply_dry_days': supply_dry_period['days'],
                'supply_dry_count': supply_dry_period['signal_count'],
                'supply_dry_low': float(supply_dry_period['low_price']),
                'supply_dry_avg_volume': float(supply_dry_period['avg_volume_multiple']),

                # 放量上涨信息
                'volume_confirm_type': healthy_up_result['type'],
                'volume_multiple': float(healthy_up_result['volume_multiple']),
                'healthy_up_details': healthy_up_result['details'],

                # 风险管理
                'stop_loss': float(stop_loss),
                'target': float(target),
                'risk_reward': float(risk_reward),
                'potential_gain_pct': float((target - today['close']) / today['close'] * 100),
                'potential_loss_pct': float((today['close'] - stop_loss) / today['close'] * 100),

                # 描述
                'description': self._generate_signal_description(
                    low_info, supply_dry_period, healthy_up_result, structure_info
                ),

                # 时间戳
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            signals.append(signal)
            logger.info(f"  ★ 发现信号: 强度{signal_strength}, 风险回报比{risk_reward:.2f}")

        except Exception as e:
            logger.error(f"{ts_code or '未知'}: 扫描出错 - {e}", exc_info=True)

        return signals

    def _check_market_structure_transition(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        检查市场结构转折（ACCUMULATION → MARK_UP）

        Returns:
            (是否符合, 结构信息字典)
        """
        # 分析当前市场结构
        structure, confidence, detail = self.structure_analyzer.analyze_structure(df)

        info = {
            'structure': structure,
            'confidence': confidence,
            'detail': detail,
            'reason': ''
        }

        # 检查置信度
        if confidence < MARKET_STRUCTURE_CONFIG['min_confidence']:
            info['reason'] = f"置信度不足({confidence:.2f})"
            return False, info

        # 目标结构：ACCUMULATION或ACCUMULATION→MARK_UP转折
        target_structures = MARKET_STRUCTURE_CONFIG['target_structures']

        # 情况1：当前就是ACCUMULATION（最佳，底部横盘）
        if 'ACCUMULATION' in target_structures and structure == 'ACCUMULATION':
            return True, info

        # 情况2：检查是否刚从ACCUMULATION转为MARK_UP
        if 'ACCUMULATION_TO_MARKUP' in target_structures:
            transition_window = MARKET_STRUCTURE_CONFIG['transition_window']
            transition_lookback = MARKET_STRUCTURE_CONFIG['transition_lookback']

            # 检查最近transition_window天的结构变化
            if len(df) >= transition_window + 10:
                # 分析前几天的结构
                df_before = df.iloc[:-transition_lookback]
                structure_before, _, _ = self.structure_analyzer.analyze_structure(df_before)

                # 如果之前是ACCUMULATION，现在是MARK_UP，说明刚转折
                if structure_before == 'ACCUMULATION' and structure == 'MARK_UP':
                    info['structure'] = 'ACCUMULATION_TO_MARKUP'
                    info['detail'] = f"转折{transition_lookback}天前"
                    return True, info

        # 情况3：已经是MARK_UP但时间不长（可选）
        if MARKET_STRUCTURE_CONFIG.get('allow_markup', False) and structure == 'MARK_UP':
            # 检查是否转折不久
            max_days = MARKET_STRUCTURE_CONFIG.get('markup_max_days', 5)
            if len(df) >= max_days + 10:
                df_before = df.iloc[:-(max_days + 1)]
                structure_before, _, _ = self.structure_analyzer.analyze_structure(df_before)
                if structure_before == 'ACCUMULATION':
                    info['detail'] = f"MARK_UP早期（转折{max_days}天内）"
                    return True, info

        # 情况4：RANGING横盘结构（宽松模式）
        if 'RANGING' in target_structures and structure == 'RANGING':
            info['detail'] = "横盘整理中，等待方向选择"
            return True, info

        info['reason'] = f"结构为{structure}，不在目标结构中"
        return False, info

    def _check_low_position(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        检查是否处于低位（4重组合判断）

        Returns:
            (是否低位, 详细信息字典)
        """
        today = df.iloc[-1]
        matched_conditions = []
        details = {}

        # 条件1：布林带下轨
        if 'BOLL_Lower' in df.columns or 'boll_lower' in df.columns:
            boll_col = 'BOLL_Lower' if 'BOLL_Lower' in df.columns else 'boll_lower'
            boll_lower = today[boll_col]
            threshold = boll_lower * LOW_POSITION_CONFIG['boll_threshold']

            if pd.notna(boll_lower) and today['close'] < threshold:
                matched_conditions.append('BOLL_LOWER')
                details['boll_lower'] = float(boll_lower)
                details['boll_distance_pct'] = float((today['close'] - boll_lower) / boll_lower * 100)

        # 条件2：RSI超卖
        if 'RSI' in df.columns or 'rsi' in df.columns:
            rsi_col = 'RSI' if 'RSI' in df.columns else 'rsi'
            rsi = today[rsi_col]

            if pd.notna(rsi) and rsi < LOW_POSITION_CONFIG['rsi_threshold']:
                matched_conditions.append('RSI_OVERSOLD')
                details['rsi'] = float(rsi)

        # 条件3：低于均线
        ma_periods = LOW_POSITION_CONFIG['ma_periods']
        ma_below_count = 0
        for period in ma_periods:
            ma_col = f'MA{period}' if f'MA{period}' in df.columns else f'ma{period}'
            if ma_col in df.columns:
                ma_value = today[ma_col]
                if pd.notna(ma_value) and today['close'] < ma_value:
                    ma_below_count += 1
                    details[f'ma{period}'] = float(ma_value)

        if ma_below_count > 0:
            matched_conditions.append(f'BELOW_MA{ma_periods}')

        # 条件4：近期新低
        new_low_windows = LOW_POSITION_CONFIG.get('new_low_windows', [20, 60])
        is_new_low = False
        for window in new_low_windows:
            if len(df) >= window:
                window_low = df.iloc[-window:]['low'].min()
                if today['low'] <= window_low * 1.001:  # 允许0.1%误差
                    is_new_low = True
                    details[f'new_low_{window}d'] = float(window_low)
                    break

        if is_new_low:
            matched_conditions.append('NEW_LOW')

        # 判断是否满足最低条件数
        min_conditions = LOW_POSITION_CONFIG['low_condition_min']
        is_low = len(matched_conditions) >= min_conditions

        info = {
            'matched_conditions': matched_conditions,
            'matched_count': len(matched_conditions),
            'required_count': min_conditions,
            'details': details
        }

        return is_low, info

    def _find_supply_dry_period(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        查找缩量下跌区间（5-10天，至少5次SUPPLY_DRY_UP）

        Returns:
            区间信息字典，如果未找到返回None
        """
        min_days = SUPPLY_DRY_CONFIG['min_days']
        max_days = SUPPLY_DRY_CONFIG['max_days']
        min_signals = SUPPLY_DRY_CONFIG['min_signals']
        avg_volume_threshold = SUPPLY_DRY_CONFIG['avg_volume_multiple']
        max_volume_threshold = SUPPLY_DRY_CONFIG.get('max_volume_multiple', 1.2)
        max_price_drop = SUPPLY_DRY_CONFIG.get('max_price_drop', -0.15)
        min_price_drop = SUPPLY_DRY_CONFIG.get('min_price_drop', -0.02)
        allow_panic = SUPPLY_DRY_CONFIG['allow_panic']

        # 从最近往前搜索
        for lookback_days in range(min_days, max_days + 1):
            if len(df) < lookback_days + 1:
                continue

            # 提取区间数据（不包括今天）
            period_df = df.iloc[-(lookback_days + 1):-1].copy()
            period_start_idx = len(df) - lookback_days - 1

            # 添加VSA信号
            period_df = self.vsa_detector.detect_batch(period_df)

            # 统计SUPPLY_DRY_UP信号数量
            supply_dry_count = (period_df['vsa_signal'] == 'SUPPLY_DRY_UP').sum()
            if supply_dry_count < min_signals:
                continue

            # 检查是否有PANIC_SELL（如果不允许）
            if not allow_panic:
                panic_count = (period_df['vsa_signal'] == 'PANIC_SELL').sum()
                if panic_count > 0:
                    continue

            # 检查平均成交量倍数
            avg_volume_multiple = period_df['volume_multiple'].mean()
            if pd.isna(avg_volume_multiple) or avg_volume_multiple > avg_volume_threshold:
                continue

            # 检查单日最大成交量倍数
            max_volume_multiple = period_df['volume_multiple'].max()
            if pd.notna(max_volume_multiple) and max_volume_multiple > max_volume_threshold:
                continue

            # 检查价格跌幅
            period_start_price = period_df.iloc[0]['close']
            period_end_price = period_df.iloc[-1]['close']
            price_drop = (period_end_price - period_start_price) / period_start_price

            if price_drop > min_price_drop:  # 跌幅不足
                continue
            if price_drop < max_price_drop:  # 跌幅过大
                continue

            # 找到符合条件的区间
            low_price = period_df['low'].min()

            return {
                'days': lookback_days,
                'start_idx': period_start_idx,
                'end_idx': len(df) - 1,
                'signal_count': int(supply_dry_count),
                'avg_volume_multiple': float(avg_volume_multiple),
                'low_price': float(low_price),
                'price_drop_pct': float(price_drop * 100),
                'start_date': period_df.iloc[0]['trade_date'],
                'end_date': period_df.iloc[-1]['trade_date']
            }

        return None

    def _check_healthy_up_confirmation(self, df: pd.DataFrame,
                                      supply_dry_period: Dict) -> Optional[Dict]:
        """
        检查放量上涨确认（分4个强度等级）

        Returns:
            确认信息字典，如果未确认返回None
        """
        today = df.iloc[-1]
        yesterday = df.iloc[-2] if len(df) >= 2 else None

        # 添加VSA信号（确保今天有信号）
        df_with_signals = self.vsa_detector.detect_batch(df.tail(5))
        today_signal = df_with_signals.iloc[-1]['vsa_signal'] if 'vsa_signal' in df_with_signals.columns else None

        # 基础条件：今天必须是HEALTHY_UP
        if today_signal != 'HEALTHY_UP':
            return None

        # 基础条件：价格必须上涨
        if yesterday is not None and today['close'] <= yesterday['close']:
            return None

        # 涨幅检查
        price_change_pct = (today['close'] - yesterday['close']) / yesterday['close'] if yesterday is not None else 0
        if price_change_pct < HEALTHY_UP_CONFIG.get('min_price_change', 0.01):
            return None

        # 获取今日成交量倍数
        today_volume_multiple = today['volume_multiple'] if pd.notna(today['volume_multiple']) else 0

        # 检查各项条件
        conditions = {
            'has_healthy_up': True,
            'is_high_volume': today_volume_multiple > HEALTHY_UP_CONFIG['min_volume_multiple'],
            'is_strong_volume': today_volume_multiple > HEALTHY_UP_CONFIG['strong_volume_multiple'],
            'is_extreme_volume': today_volume_multiple > HEALTHY_UP_CONFIG['extreme_volume_multiple'],
            'has_consecutive': False,
            'breaks_resistance': False
        }

        details = [f"HEALTHY_UP(量倍{today_volume_multiple:.2f})"]

        # 检查连续放量
        if len(df) >= HEALTHY_UP_CONFIG['consecutive_days'] + 1:
            consecutive_threshold = HEALTHY_UP_CONFIG['consecutive_threshold']
            recent_volumes = df.iloc[-(HEALTHY_UP_CONFIG['consecutive_days']+1):]['volume_multiple']
            if all(v > consecutive_threshold for v in recent_volumes if pd.notna(v)):
                conditions['has_consecutive'] = True
                details.append(f"连续{HEALTHY_UP_CONFIG['consecutive_days']}天放量")

        # 检查阻力位突破
        resistance_window = HEALTHY_UP_CONFIG['resistance_window']
        if len(df) >= resistance_window:
            resistance = df.iloc[-resistance_window:-1]['high'].max()
            breakout_threshold = HEALTHY_UP_CONFIG['breakout_threshold']
            if today['close'] > resistance * breakout_threshold:
                conditions['breaks_resistance'] = True
                details.append(f"突破{resistance_window}日阻力位{resistance:.2f}")

        # 计算信号强度（0-3级）
        strength = 0
        confirm_type = 'BASIC'

        if conditions['is_extreme_volume'] and conditions['has_consecutive'] and conditions['breaks_resistance']:
            strength = 3
            confirm_type = 'EXTREME_BREAKOUT'
            details.append("【强度3】极强放量+连续+突破")
        elif conditions['is_strong_volume'] and (conditions['has_consecutive'] or conditions['breaks_resistance']):
            strength = 2
            confirm_type = 'STRONG_BREAKOUT' if conditions['breaks_resistance'] else 'STRONG_CONSECUTIVE'
            details.append("【强度2】强放量+突破或连续")
        elif conditions['is_high_volume']:
            strength = 1
            confirm_type = 'HIGH_VOLUME'
            details.append("【强度1】基础放量")
        else:
            strength = 0
            confirm_type = 'MINIMAL'
            details.append("【强度0】最低确认")

        return {
            'strength': strength,
            'type': confirm_type,
            'volume_multiple': today_volume_multiple,
            'conditions': conditions,
            'details': details,
            'description': '; '.join(details)
        }

    def _calculate_stop_and_target(self, current_price: float, supply_dry_low: float,
                                  signal_strength: int) -> Tuple[float, float, float]:
        """
        计算止损和目标位

        Returns:
            (止损价, 目标价, 风险回报比)
        """
        # 止损：缩量下跌期间最低点 * 止损比例
        stop_loss = supply_dry_low * RISK_MANAGEMENT['stop_loss_ratio']

        # 目标：根据信号强度选择不同的目标比例
        if signal_strength >= 2:
            target_ratio = RISK_MANAGEMENT.get('target_ratio_strong', 1.08)
        else:
            target_ratio = RISK_MANAGEMENT['target_ratio']

        target = current_price * target_ratio

        # 计算风险回报比
        potential_gain = target - current_price
        potential_loss = current_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_gain / potential_loss
        else:
            risk_reward = 0

        return stop_loss, target, risk_reward

    def _generate_signal_description(self, low_info: Dict, supply_dry_period: Dict,
                                    healthy_up_result: Dict, structure_info: Dict) -> str:
        """生成信号描述文本"""
        parts = []

        # 市场结构
        parts.append(f"结构:{structure_info['structure']}")

        # 低位条件
        low_conds = ', '.join(low_info['matched_conditions'])
        parts.append(f"低位({low_info['matched_count']}项:{low_conds})")

        # 缩量下跌
        parts.append(f"{supply_dry_period['days']}天缩量({supply_dry_period['signal_count']}次DRY_UP)")

        # 放量上涨
        parts.append(f"放量确认:{healthy_up_result['type']}")

        return ' | '.join(parts)


# ==================== 测试代码 ====================
if __name__ == '__main__':
    # 简单测试
    print("低位缩量反转策略类已加载")
    print("使用示例：")
    print("  strategy = LowVolumeReversalStrategy()")
    print("  signals = strategy.scan_entry_signals(df, ts_code='688256.SH', stock_name='寒武纪')")
