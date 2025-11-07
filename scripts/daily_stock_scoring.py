#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票当日技术面打分排名系统
基于 advanced_technical_analysis.py 的完整打分规则
支持批量分析和多进程加速
"""

import os
import sys
import logging
import argparse
import tushare as ts
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
import warnings

warnings.filterwarnings('ignore')

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False

# ==================== 全局配置 ====================

# 输出目录
OUTPUT_DIR = 'daily_scoring_results'

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 创建输出目录
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logger.info(f"创建输出目录: {OUTPUT_DIR}")


# ==================== StockScoringAnalyzer 类 ====================

class StockScoringAnalyzer:
    """
    股票技术面打分分析器
    整合 advanced_technical_analysis.py 的完整打分系统
    """

    def __init__(self, ts_token=None, use_local_db=False):
        """
        初始化分析器

        Args:
            ts_token: Tushare token，如果为None则从token.txt读取
            use_local_db: 是否使用本地数据库，默认False（使用在线Tushare）
        """
        self.use_local_db = use_local_db and LOCAL_DB_AVAILABLE
        self.local_query = None

        if self.use_local_db:
            # 使用本地数据库
            self.local_query = StockDataQuery()
            logger.info("使用本地数据库作为数据源")
        else:
            # 读取 Tushare token
            if ts_token is None:
                token_file = os.path.join(os.path.dirname(__file__), 'token.txt')
                try:
                    with open(token_file, 'r', encoding='utf-8') as f:
                        ts_token = f.read().strip()
                    if not ts_token:
                        raise ValueError("token.txt 文件为空")
                except FileNotFoundError:
                    logger.error(f"找不到 token.txt 文件: {token_file}")
                    logger.error("请在脚本目录下创建 token.txt 文件并填入您的 tushare token")
                    sys.exit(1)
                except Exception as e:
                    logger.error(f"读取 token 文件失败: {e}")
                    sys.exit(1)

            # 初始化 Tushare
            ts.set_token(ts_token)
            self.pro = ts.pro_api()
            logger.info("使用在线Tushare作为数据源")

        # 技术指标参数配置
        self.params = {
            'ma_periods': [5, 10, 20, 60],
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'rsi_period': 14,
            'kdj_period': 9,
            'cci_period': 14,
            'boll_period': 20,
            'boll_std': 2,
            'atr_period': 14,
            'obv_ma_period': 20,
            'mfi_period': 14,
            'sar_acceleration': 0.02,
            'sar_maximum': 0.2
        }

    def fetch_data(self, stock_code, start_date, end_date):
        """获取股票数据"""
        try:
            if self.use_local_db:
                # 从本地数据库获取数据
                df = self.local_query.daily(stock_code, start_date, end_date)
            else:
                # 从在线Tushare获取数据
                df = self.pro.daily(
                    ts_code=stock_code,
                    start_date=start_date,
                    end_date=end_date
                )

            if df is None or df.empty:
                logger.warning(f"未获取到 {stock_code} 的数据")
                return None

            # 数据预处理
            df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
            df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'vol': 'Volume'
            }, inplace=True)

            return df

        except Exception as e:
            logger.error(f"获取 {stock_code} 数据失败: {e}")
            return None

    def calculate_trend_indicators(self, df):
        """计算趋势类指标"""
        if df is None or df.empty:
            return df

        # 移动平均线
        for period in self.params['ma_periods']:
            df[f'MA{period}'] = ta.sma(df['Close'], length=period)

        # MACD
        if len(df) >= self.params['macd_slow'] + self.params['macd_signal']:
            macd = ta.macd(
                df['Close'],
                fast=self.params['macd_fast'],
                slow=self.params['macd_slow'],
                signal=self.params['macd_signal']
            )
            df['MACD_DIF'] = macd.iloc[:, 0]
            df['MACD_DEA'] = macd.iloc[:, 1]
            df['MACD_Histogram'] = macd.iloc[:, 2]

        # SAR
        sar = ta.psar(
            df['High'],
            df['Low'],
            df['Close'],
            af=self.params['sar_acceleration'],
            max_af=self.params['sar_maximum']
        )
        if sar is not None and not sar.empty:
            df['SAR'] = sar.iloc[:, 1]  # SAR values

        return df

    def calculate_momentum_indicators(self, df):
        """计算动量类指标"""
        if df is None or df.empty:
            return df

        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=self.params['rsi_period'])

        # KDJ
        stoch = ta.stoch(
            df['High'],
            df['Low'],
            df['Close'],
            k=self.params['kdj_period'],
            d=3,
            smooth_k=3
        )
        if stoch is not None and not stoch.empty:
            df['K'] = stoch.iloc[:, 0]
            df['D'] = stoch.iloc[:, 1]
            df['J'] = 3 * df['K'] - 2 * df['D']

        # CCI
        df['CCI'] = ta.cci(
            df['High'],
            df['Low'],
            df['Close'],
            length=self.params['cci_period']
        )

        return df

    def calculate_volatility_indicators(self, df):
        """计算波动类指标"""
        if df is None or df.empty:
            return df

        # 布林带
        if len(df) >= self.params['boll_period']:
            bbands = ta.bbands(
                df['Close'],
                length=self.params['boll_period'],
                std=self.params['boll_std']
            )
            if bbands is not None and not bbands.empty:
                cols = bbands.columns.tolist()
                df['BOLL_Lower'] = bbands.iloc[:, 0]
                df['BOLL_Middle'] = bbands.iloc[:, 1]
                df['BOLL_Upper'] = bbands.iloc[:, 2]
                df['BOLL_Bandwidth'] = bbands.iloc[:, 3]

        # ATR
        df['ATR'] = ta.atr(
            df['High'],
            df['Low'],
            df['Close'],
            length=self.params['atr_period']
        )

        return df

    def calculate_volume_indicators(self, df):
        """计算成交量类指标"""
        if df is None or df.empty:
            return df

        # 成交量均线和量比
        df['Volume_MA'] = ta.sma(df['Volume'], length=20)
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']

        # OBV
        df['OBV'] = ta.obv(df['Close'], df['Volume'])
        df['OBV_MA'] = ta.sma(df['OBV'], length=self.params['obv_ma_period'])

        # MFI
        df['MFI'] = ta.mfi(
            df['High'],
            df['Low'],
            df['Close'],
            df['Volume'],
            length=self.params['mfi_period']
        )

        # VWAP
        df['VWAP'] = ta.vwap(
            df['High'],
            df['Low'],
            df['Close'],
            df['Volume']
        )

        return df

    def calculate_support_resistance(self, df, window=20):
        """计算支撑位和阻力位"""
        if df is None or df.empty or len(df) < window:
            return df

        df['Support'] = df['Low'].rolling(window=window, min_periods=1).min()
        df['Resistance'] = df['High'].rolling(window=window, min_periods=1).max()

        return df

    def identify_candle_patterns(self, df):
        """识别K线形态"""
        if df is None or df.empty:
            return df

        # 计算K线结构
        df['body'] = abs(df['Close'] - df['Open'])
        df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['total_range'] = df['High'] - df['Low']

        # 避免除零
        df['body_ratio'] = df['body'] / df['total_range'].replace(0, np.nan)
        df['body_ratio'] = df['body_ratio'].fillna(0)

        # 锤子线
        df['is_hammer'] = (
            (df['lower_shadow'] > df['body'] * 2) &
            (df['upper_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)
        )

        # 射击之星
        df['is_shooting_star'] = (
            (df['upper_shadow'] > df['body'] * 2) &
            (df['lower_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)
        )

        # 十字星
        df['is_doji'] = (
            (df['body_ratio'] < 0.05) &
            (df['upper_shadow'] > 0) &
            (df['lower_shadow'] > 0)
        )

        # 大阳线
        df['is_big_bullish'] = (
            (df['Close'] > df['Open']) &
            (df['body_ratio'] > 0.7)
        )

        # 大阴线
        df['is_big_bearish'] = (
            (df['Close'] < df['Open']) &
            (df['body_ratio'] > 0.7)
        )

        return df

    def identify_divergence(self, df, lookback=5):
        """识别背离信号"""
        if df is None or df.empty or len(df) < lookback * 2:
            return df

        # 重置索引以确保使用连续的整数索引
        df = df.reset_index(drop=True)

        df['RSI_Divergence'] = ''
        df['MACD_Divergence'] = ''

        for i in range(lookback * 2, len(df)):
            # RSI背离
            if 'RSI' in df.columns and pd.notna(df.loc[i, 'RSI']):
                recent_price = df.loc[i-lookback:i, 'Close']
                recent_rsi = df.loc[i-lookback:i, 'RSI']

                # 顶背离
                if (df.loc[i, 'Close'] > recent_price.max() and
                    df.loc[i, 'RSI'] < recent_rsi.max()):
                    df.loc[i, 'RSI_Divergence'] = '顶背离'

                # 底背离
                if (df.loc[i, 'Close'] < recent_price.min() and
                    df.loc[i, 'RSI'] > recent_rsi.min()):
                    df.loc[i, 'RSI_Divergence'] = '底背离'

            # MACD背离
            if 'MACD_Histogram' in df.columns and pd.notna(df.loc[i, 'MACD_Histogram']):
                recent_price = df.loc[i-lookback:i, 'Close']
                recent_macd = df.loc[i-lookback:i, 'MACD_Histogram']

                # 顶背离
                if (df.loc[i, 'Close'] > recent_price.max() and
                    df.loc[i, 'MACD_Histogram'] < recent_macd.max()):
                    df.loc[i, 'MACD_Divergence'] = '顶背离'

                # 底背离
                if (df.loc[i, 'Close'] < recent_price.min() and
                    df.loc[i, 'MACD_Histogram'] > recent_macd.min()):
                    df.loc[i, 'MACD_Divergence'] = '底背离'

        return df

    def calculate_detailed_scores(self, df):
        """
        计算详细的技术面打分
        完全复用 advanced_technical_analysis.py 的打分规则
        """
        if df is None or df.empty:
            return df

        # 重置索引以确保使用连续的整数索引
        df = df.reset_index(drop=True)

        # 初始化打分列
        df['Trend_Score'] = 0
        df['Momentum_Score'] = 0
        df['Volatility_Score'] = 0
        df['Volume_Score'] = 0
        df['Pattern_Score'] = 0
        df['Total_Score'] = 0
        df['Score_Details'] = ''

        # 逐行计算打分
        for i in range(len(df)):
            trend_score = 0
            momentum_score = 0
            volatility_score = 0
            volume_score = 0
            pattern_score = 0
            score_details = []

            # ==================== 趋势类打分 ====================

            # 1. MACD打分
            if pd.notna(df.loc[i, 'MACD_DIF']) and pd.notna(df.loc[i, 'MACD_DEA']):
                if i > 0:
                    # 金叉死叉
                    if df.loc[i-1, 'MACD_DIF'] <= df.loc[i-1, 'MACD_DEA'] and df.loc[i, 'MACD_DIF'] > df.loc[i, 'MACD_DEA']:
                        if df.loc[i, 'MACD_DIF'] < 0:
                            trend_score += 3
                            score_details.append('MACD低位金叉(+3)')
                        else:
                            trend_score += 2
                            score_details.append('MACD金叉(+2)')

                    elif df.loc[i-1, 'MACD_DIF'] >= df.loc[i-1, 'MACD_DEA'] and df.loc[i, 'MACD_DIF'] < df.loc[i, 'MACD_DEA']:
                        if df.loc[i, 'MACD_DIF'] > 0:
                            trend_score -= 3
                            score_details.append('MACD高位死叉(-3)')
                        else:
                            trend_score -= 2
                            score_details.append('MACD死叉(-2)')

                # MACD柱状图
                if pd.notna(df.loc[i, 'MACD_Histogram']) and i > 0 and pd.notna(df.loc[i-1, 'MACD_Histogram']):
                    if df.loc[i, 'MACD_Histogram'] > 0 and df.loc[i, 'MACD_Histogram'] > df.loc[i-1, 'MACD_Histogram']:
                        trend_score += 1
                        score_details.append('MACD红柱增长(+1)')
                    elif df.loc[i, 'MACD_Histogram'] < 0 and df.loc[i, 'MACD_Histogram'] < df.loc[i-1, 'MACD_Histogram']:
                        trend_score -= 1
                        score_details.append('MACD绿柱增长(-1)')

            # 2. SAR打分
            if pd.notna(df.loc[i, 'SAR']) and i > 0 and pd.notna(df.loc[i-1, 'SAR']):
                current_sar_bullish = df.loc[i, 'Close'] > df.loc[i, 'SAR']
                prev_sar_bullish = df.loc[i-1, 'Close'] > df.loc[i-1, 'SAR']

                if current_sar_bullish and not prev_sar_bullish:
                    trend_score += 3
                    score_details.append('SAR空转多(+3)')
                elif not current_sar_bullish and prev_sar_bullish:
                    trend_score -= 3
                    score_details.append('SAR多转空(-3)')
                elif current_sar_bullish:
                    trend_score += 2
                    score_details.append('SAR多头持续(+2)')
                else:
                    trend_score -= 2
                    score_details.append('SAR空头持续(-2)')

            # 3. 均线排列
            if all(pd.notna(df.loc[i, col]) for col in ['MA5', 'MA10', 'MA20']):
                if (df.loc[i, 'Close'] > df.loc[i, 'MA5'] >
                    df.loc[i, 'MA10'] > df.loc[i, 'MA20']):
                    trend_score += 3
                    score_details.append('均线多头排列(+3)')
                elif (df.loc[i, 'Close'] < df.loc[i, 'MA5'] <
                      df.loc[i, 'MA10'] < df.loc[i, 'MA20']):
                    trend_score -= 3
                    score_details.append('均线空头排列(-3)')

            # ==================== 动量类打分 ====================

            # 1. RSI打分
            if pd.notna(df.loc[i, 'RSI']):
                if df.loc[i, 'RSI'] < 20:
                    momentum_score += 3
                    score_details.append('RSI严重超卖(+3)')
                elif df.loc[i, 'RSI'] < 30:
                    momentum_score += 2
                    score_details.append('RSI超卖(+2)')
                elif df.loc[i, 'RSI'] > 80:
                    momentum_score -= 3
                    score_details.append('RSI严重超买(-3)')
                elif df.loc[i, 'RSI'] > 70:
                    momentum_score -= 2
                    score_details.append('RSI超买(-2)')

                # RSI中轴突破
                if i > 0 and pd.notna(df.loc[i-1, 'RSI']):
                    if df.loc[i-1, 'RSI'] <= 50 and df.loc[i, 'RSI'] > 50:
                        momentum_score += 1
                        score_details.append('RSI突破中轴(+1)')
                    elif df.loc[i-1, 'RSI'] >= 50 and df.loc[i, 'RSI'] < 50:
                        momentum_score -= 1
                        score_details.append('RSI跌破中轴(-1)')

            # 2. KDJ打分
            if all(pd.notna(df.loc[i, col]) for col in ['K', 'D', 'J']):
                if i > 0 and pd.notna(df.loc[i-1, 'K']) and pd.notna(df.loc[i-1, 'D']):
                    # KDJ金叉死叉
                    if df.loc[i-1, 'K'] <= df.loc[i-1, 'D'] and df.loc[i, 'K'] > df.loc[i, 'D']:
                        if df.loc[i, 'D'] < 20:
                            momentum_score += 3
                            score_details.append('KDJ低位金叉(+3)')
                    elif df.loc[i-1, 'K'] >= df.loc[i-1, 'D'] and df.loc[i, 'K'] < df.loc[i, 'D']:
                        if df.loc[i, 'D'] > 80:
                            momentum_score -= 3
                            score_details.append('KDJ高位死叉(-3)')

                # J值极值
                if df.loc[i, 'J'] < 0:
                    momentum_score += 2
                    score_details.append('J值极度超卖(+2)')
                elif df.loc[i, 'J'] > 100:
                    momentum_score -= 2
                    score_details.append('J值极度超买(-2)')

            # 3. CCI打分
            if pd.notna(df.loc[i, 'CCI']):
                if i > 0 and pd.notna(df.loc[i-1, 'CCI']):
                    # CCI突破
                    if df.loc[i-1, 'CCI'] <= -100 and df.loc[i, 'CCI'] > -100:
                        momentum_score += 2
                        score_details.append('CCI脱离超卖区(+2)')
                    elif df.loc[i-1, 'CCI'] >= 100 and df.loc[i, 'CCI'] < 100:
                        momentum_score -= 2
                        score_details.append('CCI脱离超买区(-2)')

                # CCI区间
                if df.loc[i, 'CCI'] > 100:
                    momentum_score += 1
                    score_details.append('CCI强势(+1)')
                elif df.loc[i, 'CCI'] < -100:
                    momentum_score -= 1
                    score_details.append('CCI弱势(-1)')

            # ==================== 波动类打分 ====================

            # 1. 布林带打分
            if all(pd.notna(df.loc[i, col]) for col in ['BOLL_Upper', 'BOLL_Lower', 'BOLL_Middle']):
                # 突破上下轨
                if df.loc[i, 'Close'] > df.loc[i, 'BOLL_Upper']:
                    volatility_score -= 2
                    score_details.append('突破布林上轨(-2)')
                elif df.loc[i, 'Close'] < df.loc[i, 'BOLL_Lower']:
                    volatility_score += 2
                    score_details.append('突破布林下轨(+2)')
                # 触及上下轨
                elif df.loc[i, 'Close'] >= df.loc[i, 'BOLL_Upper'] * 0.98:
                    volatility_score -= 1
                    score_details.append('触及布林上轨(-1)')
                elif df.loc[i, 'Close'] <= df.loc[i, 'BOLL_Lower'] * 1.02:
                    volatility_score += 1
                    score_details.append('触及布林下轨(+1)')

                # 布林带开口
                if i > 0 and pd.notna(df.loc[i-1, 'BOLL_Bandwidth']):
                    if df.loc[i, 'BOLL_Bandwidth'] > df.loc[i-1, 'BOLL_Bandwidth']:
                        if df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                            volatility_score += 1
                            score_details.append('布林带开口上涨(+1)')
                        else:
                            volatility_score -= 1
                            score_details.append('布林带开口下跌(-1)')

            # 2. ATR打分
            if pd.notna(df.loc[i, 'ATR']) and i >= 20:
                atr_mean = df.loc[i-20:i, 'ATR'].mean()
                if df.loc[i, 'ATR'] > atr_mean * 1.5:
                    if i > 0 and df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                        volatility_score += 1
                        score_details.append('ATR波动加大上涨(+1)')
                    elif i > 0 and df.loc[i, 'Close'] < df.loc[i-1, 'Close']:
                        volatility_score -= 2
                        score_details.append('ATR波动加大下跌(-2)')

            # ==================== 成交量类打分 ====================

            # 1. VWAP打分
            if pd.notna(df.loc[i, 'VWAP']):
                if df.loc[i, 'Close'] > df.loc[i, 'VWAP'] * 1.02:
                    volume_score += 2
                    score_details.append('价格远高于VWAP(+2)')
                elif df.loc[i, 'Close'] > df.loc[i, 'VWAP']:
                    volume_score += 1
                    score_details.append('价格高于VWAP(+1)')
                elif df.loc[i, 'Close'] < df.loc[i, 'VWAP'] * 0.98:
                    volume_score -= 2
                    score_details.append('价格远低于VWAP(-2)')
                elif df.loc[i, 'Close'] < df.loc[i, 'VWAP']:
                    volume_score -= 1
                    score_details.append('价格低于VWAP(-1)')

            # 2. MFI打分
            if pd.notna(df.loc[i, 'MFI']):
                if df.loc[i, 'MFI'] < 10:
                    volume_score += 3
                    score_details.append('MFI严重超卖(+3)')
                elif df.loc[i, 'MFI'] < 20:
                    volume_score += 2
                    score_details.append('MFI超卖(+2)')
                elif df.loc[i, 'MFI'] > 90:
                    volume_score -= 3
                    score_details.append('MFI严重超买(-3)')
                elif df.loc[i, 'MFI'] > 80:
                    volume_score -= 2
                    score_details.append('MFI超买(-2)')

            # 3. OBV打分
            if pd.notna(df.loc[i, 'OBV']) and pd.notna(df.loc[i, 'OBV_MA']):
                if df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA']:
                    volume_score += 2
                    score_details.append('OBV上升趋势(+2)')
                else:
                    volume_score -= 2
                    score_details.append('OBV下降趋势(-2)')

            # 4. 成交量打分
            if pd.notna(df.loc[i, 'Volume_Ratio']) and i > 0:
                if df.loc[i, 'Volume_Ratio'] > 1.5:
                    if df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                        volume_score += 2
                        score_details.append('放量上涨(+2)')
                    else:
                        volume_score -= 2
                        score_details.append('放量下跌(-2)')

            # 5. MFI/OBV组合信号
            if pd.notna(df.loc[i, 'MFI']) and pd.notna(df.loc[i, 'OBV']) and pd.notna(df.loc[i, 'OBV_MA']):
                if df.loc[i, 'MFI'] < 20 and df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA']:
                    volume_score += 2
                    score_details.append('MFI超卖+OBV上升(+2)')
                elif df.loc[i, 'MFI'] > 80 and df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA']:
                    volume_score -= 2
                    score_details.append('MFI超买+OBV下降(-2)')
                elif df.loc[i, 'MFI'] < 20 and df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA']:
                    volume_score -= 1
                    score_details.append('MFI超卖但OBV下降(-1)')
                elif df.loc[i, 'MFI'] > 80 and df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA']:
                    volume_score += 1
                    score_details.append('MFI超买但OBV上升(+1)')

            # ==================== 形态类打分 ====================

            # 1. 背离打分
            if 'RSI_Divergence' in df.columns and df.loc[i, 'RSI_Divergence']:
                if df.loc[i, 'RSI_Divergence'] == '顶背离':
                    pattern_score -= 3
                    score_details.append('RSI顶背离(-3)')
                elif df.loc[i, 'RSI_Divergence'] == '底背离':
                    pattern_score += 3
                    score_details.append('RSI底背离(+3)')

            if 'MACD_Divergence' in df.columns and df.loc[i, 'MACD_Divergence']:
                if df.loc[i, 'MACD_Divergence'] == '顶背离':
                    pattern_score -= 3
                    score_details.append('MACD顶背离(-3)')
                elif df.loc[i, 'MACD_Divergence'] == '底背离':
                    pattern_score += 3
                    score_details.append('MACD底背离(+3)')

            # 2. 支撑阻力突破
            if pd.notna(df.loc[i, 'Support']) and pd.notna(df.loc[i, 'Resistance']):
                if i > 0:
                    if df.loc[i, 'Close'] > df.loc[i, 'Resistance'] and df.loc[i-1, 'Close'] <= df.loc[i, 'Resistance']:
                        pattern_score += 3
                        score_details.append('突破阻力位(+3)')
                    elif df.loc[i, 'Close'] < df.loc[i, 'Support'] and df.loc[i-1, 'Close'] >= df.loc[i, 'Support']:
                        pattern_score -= 3
                        score_details.append('跌破支撑位(-3)')
                    elif df.loc[i, 'Low'] <= df.loc[i, 'Support'] * 1.02 and df.loc[i, 'Close'] > df.loc[i, 'Support']:
                        pattern_score += 2
                        score_details.append('获得支撑(+2)')
                    elif df.loc[i, 'High'] >= df.loc[i, 'Resistance'] * 0.98 and df.loc[i, 'Close'] < df.loc[i, 'Resistance']:
                        pattern_score -= 2
                        score_details.append('遇到阻力(-2)')

            # 3. K线形态打分
            if 'is_hammer' in df.columns:
                if df.loc[i, 'is_hammer'] and i >= 5:
                    prev_trend = df.loc[i-5:i-1, 'Close'].diff().mean()
                    if prev_trend < 0:
                        pattern_score += 3
                        score_details.append('锤子线(+3)')
                    else:
                        pattern_score += 1
                        score_details.append('锤子线(+1)')

            if 'is_shooting_star' in df.columns:
                if df.loc[i, 'is_shooting_star'] and i >= 5:
                    prev_trend = df.loc[i-5:i-1, 'Close'].diff().mean()
                    if prev_trend > 0:
                        pattern_score -= 3
                        score_details.append('射击之星(-3)')
                    else:
                        pattern_score -= 1
                        score_details.append('射击之星(-1)')

            if 'is_doji' in df.columns:
                if df.loc[i, 'is_doji']:
                    score_details.append('十字星(观望)')

            if 'is_big_bullish' in df.columns:
                if df.loc[i, 'is_big_bullish']:
                    pattern_score += 2
                    score_details.append('大阳线(+2)')

            if 'is_big_bearish' in df.columns:
                if df.loc[i, 'is_big_bearish']:
                    pattern_score -= 2
                    score_details.append('大阴线(-2)')

            # 保存分项得分和总分
            df.loc[i, 'Trend_Score'] = trend_score
            df.loc[i, 'Momentum_Score'] = momentum_score
            df.loc[i, 'Volatility_Score'] = volatility_score
            df.loc[i, 'Volume_Score'] = volume_score
            df.loc[i, 'Pattern_Score'] = pattern_score
            df.loc[i, 'Total_Score'] = trend_score + momentum_score + volatility_score + volume_score + pattern_score
            df.loc[i, 'Score_Details'] = '; '.join(score_details)

        return df


# ==================== 辅助函数 ====================

def get_latest_date_and_filter_stocks(stock_codes, use_local_db=False):
    """
    获取股票池中的最新日期，并筛选出有该日期数据的股票

    Args:
        stock_codes: 股票代码列表
        use_local_db: 是否使用本地数据库

    Returns:
        (最新日期, 有该日期数据的股票代码列表) 元组
        如果无法确定则返回 (None, [])
    """
    if not use_local_db or not LOCAL_DB_AVAILABLE:
        # 不使用本地数据库，返回今天和所有股票
        return datetime.now().strftime('%Y%m%d'), stock_codes

    try:
        from database.db_manager import StockDatabase

        db = StockDatabase()
        stock_date_map = {}  # 记录每个股票的最新日期

        logger.info("正在查询股票池中所有股票的最新日期...")

        for code in stock_codes:
            latest_date = db.get_latest_date(code)
            if latest_date:
                stock_date_map[code] = latest_date
                logger.debug(f"  {code}: {latest_date}")
            else:
                logger.warning(f"  {code}: 数据库中无数据")

        db.close()

        if not stock_date_map:
            logger.error("股票池中所有股票在数据库中都没有数据")
            return None, []

        # 找出最新的日期（所有股票中最晚的日期）
        all_dates = list(stock_date_map.values())
        latest_date = max(all_dates)

        # 筛选出有最新日期数据的股票
        stocks_with_latest_date = [code for code, date in stock_date_map.items() if date == latest_date]
        stocks_without_latest_date = [code for code, date in stock_date_map.items() if date < latest_date]

        logger.info(f"✓ 数据库最新日期: {latest_date}")
        logger.info(f"  日期范围: {min(all_dates)} 至 {latest_date}")
        logger.info(f"  有最新日期数据的股票: {len(stocks_with_latest_date)}/{len(stock_codes)} 只")

        if stocks_without_latest_date:
            logger.warning(f"  {len(stocks_without_latest_date)} 只股票数据未更新到最新日期，将被排除:")
            # 显示前10只未更新的股票
            excluded_display = ', '.join(stocks_without_latest_date[:10])
            if len(stocks_without_latest_date) > 10:
                excluded_display += f" 等{len(stocks_without_latest_date)}只"
            logger.warning(f"    排除股票: {excluded_display}")

        return latest_date, stocks_with_latest_date

    except Exception as e:
        logger.error(f"查询最新日期失败: {e}")
        return None, []


# ==================== 多进程工作函数 ====================

def analyze_single_stock(args):
    """
    分析单只股票的多进程工作函数
    """
    stock_code, stock_name, start_date, end_date, use_local_db = args

    try:
        # 创建分析器实例
        analyzer = StockScoringAnalyzer(use_local_db=use_local_db)

        # 获取数据
        df = analyzer.fetch_data(stock_code, start_date, end_date)
        if df is None or df.empty:
            return None

        # 计算所有指标
        df = analyzer.calculate_trend_indicators(df)
        df = analyzer.calculate_momentum_indicators(df)
        df = analyzer.calculate_volatility_indicators(df)
        df = analyzer.calculate_volume_indicators(df)
        df = analyzer.calculate_support_resistance(df)
        df = analyzer.identify_candle_patterns(df)
        df = analyzer.identify_divergence(df)

        # 计算打分
        df = analyzer.calculate_detailed_scores(df)

        # 获取最新一日的数据
        if df.empty:
            return None

        latest = df.iloc[-1]

        # 计算涨跌幅
        if len(df) > 1:
            change_pct = ((latest['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100
        else:
            change_pct = 0

        # 返回结果字典
        result = {
            'code': stock_code,
            'name': stock_name,
            'date': latest['trade_date'].strftime('%Y%m%d'),
            'close': latest['Close'],
            'change_pct': change_pct,
            'total_score': latest['Total_Score'] if pd.notna(latest['Total_Score']) else 0,
            'trend_score': latest['Trend_Score'] if pd.notna(latest['Trend_Score']) else 0,
            'momentum_score': latest['Momentum_Score'] if pd.notna(latest['Momentum_Score']) else 0,
            'volatility_score': latest['Volatility_Score'] if pd.notna(latest['Volatility_Score']) else 0,
            'volume_score': latest['Volume_Score'] if pd.notna(latest['Volume_Score']) else 0,
            'pattern_score': latest['Pattern_Score'] if pd.notna(latest['Pattern_Score']) else 0,
            'score_details': latest['Score_Details'] if pd.notna(latest['Score_Details']) else '',
            'mfi': latest['MFI'] if pd.notna(latest['MFI']) else 0,
            'rsi': latest['RSI'] if pd.notna(latest['RSI']) else 0,
            'volume_ratio': latest['Volume_Ratio'] if pd.notna(latest['Volume_Ratio']) else 0,
            'obv_trend': 'up' if (pd.notna(latest['OBV']) and pd.notna(latest['OBV_MA']) and
                                 latest['OBV'] > latest['OBV_MA']) else 'down'
        }

        return result

    except Exception as e:
        logger.error(f"分析 {stock_code} 时出错: {e}")
        return None


# ==================== 报告生成函数 ====================

def read_stock_pool(pool_file):
    """读取股票池文件，返回包含代码和名称的列表"""
    stocks = []

    if not os.path.exists(pool_file):
        logger.error(f"股票池文件不存在: {pool_file}")
        return stocks

    with open(pool_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释行
            if not line or line.startswith('#'):
                continue

            # 解析代码和名称
            code = ''
            name = ''
            if '#' in line:
                parts = line.split('#')
                code = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ''
            else:
                code = line.strip()

            if code:
                stocks.append({'code': code, 'name': name})

    logger.info(f"从 {pool_file} 读取了 {len(stocks)} 只股票")
    return stocks


def get_score_level(score):
    """根据总分返回打分等级"""
    if score >= 8:
        return "强烈看多"
    elif score >= 5:
        return "看多"
    elif score >= 2:
        return "偏多"
    elif score >= -1:
        return "中性"
    elif score >= -4:
        return "偏空"
    elif score >= -7:
        return "看空"
    else:
        return "强烈看空"


def extract_category_signals(score_details, category):
    """
    从得分明细中提取特定分类的信号

    Args:
        score_details: 得分明细字符串（用分号分隔）
        category: 分类类型 ('trend', 'momentum', 'volatility', 'volume', 'pattern')

    Returns:
        该分类的信号列表字符串
    """
    if not score_details or pd.isna(score_details):
        return ""

    # 定义各分类的关键词
    category_keywords = {
        'trend': ['MACD', 'SAR', '均线', '多头排列', '空头排列', '红柱', '绿柱', '金叉', '死叉', '空转多', '多转空'],
        'momentum': ['RSI', 'KDJ', 'CCI', '超买', '超卖', 'J值', 'K值', 'D值', '中轴'],
        'volatility': ['布林', '上轨', '下轨', 'ATR', '波动', '开口'],
        'volume': ['VWAP', 'MFI', 'OBV', '成交量', '量比', '放量', '缩量', '资金'],
        'pattern': ['背离', '支撑', '阻力', '锤子', '射击', '十字星', '大阳', '大阴', '突破', '跌破']
    }

    if category not in category_keywords:
        return ""

    keywords = category_keywords[category]
    signals = []

    # 分割得分明细
    details_list = score_details.split('; ')

    # 筛选包含关键词的信号
    for detail in details_list:
        for keyword in keywords:
            if keyword in detail:
                signals.append(detail)
                break

    return '; '.join(signals) if signals else "-"


def generate_comprehensive_report(results, output_file, analysis_date=None):
    """
    生成详细版综合报告

    Args:
        results: 分析结果列表
        output_file: 输出文件路径
        analysis_date: 分析基准日期（YYYYMMDD格式），如果为None则使用当前时间
    """
    if not results:
        logger.warning("没有分析结果，无法生成报告")
        return

    # 按总分排序
    results_sorted = sorted(results, key=lambda x: x['total_score'], reverse=True)

    # 按各分类得分排序
    results_by_trend = sorted(results, key=lambda x: x['trend_score'], reverse=True)
    results_by_momentum = sorted(results, key=lambda x: x['momentum_score'], reverse=True)
    results_by_volatility = sorted(results, key=lambda x: x['volatility_score'], reverse=True)
    results_by_volume = sorted(results, key=lambda x: x['volume_score'], reverse=True)
    results_by_pattern = sorted(results, key=lambda x: x['pattern_score'], reverse=True)

    # 统计数据
    total_count = len(results)
    avg_score = np.mean([r['total_score'] for r in results])
    max_score = max([r['total_score'] for r in results])
    min_score = min([r['total_score'] for r in results])

    # 各分类得分统计
    trend_scores = [r['trend_score'] for r in results]
    momentum_scores = [r['momentum_score'] for r in results]
    volatility_scores = [r['volatility_score'] for r in results]
    volume_scores = [r['volume_score'] for r in results]
    pattern_scores = [r['pattern_score'] for r in results]

    category_stats = {
        '趋势类': {'avg': np.mean(trend_scores), 'max': max(trend_scores), 'min': min(trend_scores)},
        '动量类': {'avg': np.mean(momentum_scores), 'max': max(momentum_scores), 'min': min(momentum_scores)},
        '波动类': {'avg': np.mean(volatility_scores), 'max': max(volatility_scores), 'min': min(volatility_scores)},
        '成交量类': {'avg': np.mean(volume_scores), 'max': max(volume_scores), 'min': min(volume_scores)},
        '形态类': {'avg': np.mean(pattern_scores), 'max': max(pattern_scores), 'min': min(pattern_scores)}
    }

    # 分类统计
    strong_bullish = [r for r in results if r['total_score'] >= 8]
    bullish = [r for r in results if 5 <= r['total_score'] < 8]
    neutral = [r for r in results if -1 <= r['total_score'] < 2]
    bearish = [r for r in results if -7 <= r['total_score'] < -4]
    strong_bearish = [r for r in results if r['total_score'] < -7]

    # 超买超卖统计
    oversold_rsi = [r for r in results if r['rsi'] < 30]
    overbought_rsi = [r for r in results if r['rsi'] > 70]
    oversold_mfi = [r for r in results if r['mfi'] < 30]
    overbought_mfi = [r for r in results if r['mfi'] > 70]

    # 放量股票
    high_volume = [r for r in results if r['volume_ratio'] > 1.5]

    # OBV趋势
    obv_up = [r for r in results if r['obv_trend'] == 'up']
    obv_down = [r for r in results if r['obv_trend'] == 'down']

    # 写入报告
    with open(output_file, 'w', encoding='utf-8') as f:
        # 标题
        f.write("=" * 100 + "\n")
        f.write("股票当日技术面打分排名报告\n")
        f.write("=" * 100 + "\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if analysis_date:
            # 格式化日期显示
            formatted_date = f"{analysis_date[:4]}-{analysis_date[4:6]}-{analysis_date[6:]}"
            f.write(f"分析基准日期: {formatted_date} (数据库最新日期)\n")
        f.write(f"分析股票数量: {total_count}\n")
        f.write(f"平均总分: {avg_score:.2f}\n")
        f.write(f"最高分: {max_score:.0f} | 最低分: {min_score:.0f}\n")
        # 添加分类得分统计
        f.write(f"\n分类得分概览:\n")
        for category_name, stats in category_stats.items():
            f.write(f"  {category_name}: 平均 {stats['avg']:+.2f} | "
                   f"最高 {stats['max']:+.0f} | 最低 {stats['min']:+.0f}\n")
        f.write("\n")

        # 综合得分排行榜
        f.write("-" * 100 + "\n")
        f.write("【综合得分排行榜 】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'MFI':<8}{'关键信号'}\n")
        f.write("-" * 100 + "\n")

        for idx, r in enumerate(results_sorted, 1):
            # 提取前3个得分明细
            details_list = r['score_details'].split('; ')
            details_str = '; '.join(details_list)
            # if len(details_list) < len(r['score_details'].split('; ')):
            #     details_str += '...'

            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['total_score']:>+6.0f}  "
                   f"{r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{r['mfi']:>6.1f}  {details_str}\n")

        f.write("\n\n")

        # 趋势类打分排行榜
        f.write("-" * 100 + "\n")
        f.write("【趋势类打分排行榜 TOP 30】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'趋势分':<8}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'趋势类信号'}\n")
        f.write("-" * 100 + "\n")
        for idx, r in enumerate(results_by_trend[:30], 1):
            trend_signals = extract_category_signals(r['score_details'], 'trend')
            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['trend_score']:>+6.0f}  "
                   f"{r['total_score']:>+6.0f}  {r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{trend_signals}\n")
        f.write("\n\n")

        # 动量类打分排行榜
        f.write("-" * 100 + "\n")
        f.write("【动量类打分排行榜 TOP 30】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'动量分':<8}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'动量类信号'}\n")
        f.write("-" * 100 + "\n")
        for idx, r in enumerate(results_by_momentum[:30], 1):
            momentum_signals = extract_category_signals(r['score_details'], 'momentum')
            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['momentum_score']:>+6.0f}  "
                   f"{r['total_score']:>+6.0f}  {r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{momentum_signals}\n")
        f.write("\n\n")

        # 波动类打分排行榜
        f.write("-" * 100 + "\n")
        f.write("【波动类打分排行榜 TOP 30】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'波动分':<8}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'波动类信号'}\n")
        f.write("-" * 100 + "\n")
        for idx, r in enumerate(results_by_volatility[:30], 1):
            volatility_signals = extract_category_signals(r['score_details'], 'volatility')
            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['volatility_score']:>+6.0f}  "
                   f"{r['total_score']:>+6.0f}  {r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{volatility_signals}\n")
        f.write("\n\n")

        # 成交量类打分排行榜
        f.write("-" * 100 + "\n")
        f.write("【成交量类打分排行榜 TOP 30】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'成交量分':<10}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'成交量类信号'}\n")
        f.write("-" * 100 + "\n")
        for idx, r in enumerate(results_by_volume[:30], 1):
            volume_signals = extract_category_signals(r['score_details'], 'volume')
            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['volume_score']:>+8.0f}  "
                   f"{r['total_score']:>+6.0f}  {r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{volume_signals}\n")
        f.write("\n\n")

        # 形态类打分排行榜
        f.write("-" * 100 + "\n")
        f.write("【形态类打分排行榜 TOP 30】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'排名':<6}{'股票代码':<12}{'名称':<10}{'形态分':<8}{'总分':<8}{'收盘价':<10}{'涨跌幅':<10}{'形态类信号'}\n")
        f.write("-" * 100 + "\n")
        for idx, r in enumerate(results_by_pattern[:30], 1):
            pattern_signals = extract_category_signals(r['score_details'], 'pattern')
            f.write(f"{idx:<6}{r['code']:<12}{r['name']:<10}{r['pattern_score']:>+6.0f}  "
                   f"{r['total_score']:>+6.0f}  {r['close']:>8.2f}  {r['change_pct']:>+7.2f}%  "
                   f"{pattern_signals}\n")
        f.write("\n\n")

        # 分项得分统计
        f.write("-" * 100 + "\n")
        f.write("【分项得分统计】\n")
        f.write("-" * 100 + "\n")

        for score_type, name in [('trend_score', '趋势类'), ('momentum_score', '动量类'),
                                 ('volatility_score', '波动类'), ('volume_score', '成交量类'),
                                 ('pattern_score', '形态类')]:
            scores = [r[score_type] for r in results]
            avg = np.mean(scores)
            max_val = max(scores)
            min_val = min(scores)
            max_stock = [r for r in results if r[score_type] == max_val][0]
            min_stock = [r for r in results if r[score_type] == min_val][0]

            f.write(f"\n{name}得分:\n")
            f.write(f"  平均分: {avg:+.2f}\n")
            f.write(f"  最高分: {max_val:+.0f} ({max_stock['code']})\n")
            f.write(f"  最低分: {min_val:+.0f} ({min_stock['code']})\n")

        f.write("\n\n")

        # 强烈看多/看空股票
        if strong_bullish:
            f.write("-" * 100 + "\n")
            f.write(f"【强烈看多股票】(总分 ≥ 8, 共 {len(strong_bullish)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(strong_bullish, key=lambda x: x['total_score'], reverse=True):
                f.write(f"{r['code']:<12} {r['name']:<10} | 总分: {r['total_score']:>+3.0f} | "
                       f"收盘: {r['close']:>7.2f} | 涨跌: {r['change_pct']:>+6.2f}%\n")
                f.write(f"             分项: 趋势{r['trend_score']:+.0f} 动量{r['momentum_score']:+.0f} "
                       f"波动{r['volatility_score']:+.0f} 成交量{r['volume_score']:+.0f} "
                       f"形态{r['pattern_score']:+.0f}\n")
                f.write(f"             明细: {r['score_details']}\n")
                f.write("\n")

        if strong_bearish:
            f.write("-" * 100 + "\n")
            f.write(f"【强烈看空股票】(总分 < -7, 共 {len(strong_bearish)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(strong_bearish, key=lambda x: x['total_score']):
                f.write(f"{r['code']:<12} {r['name']:<10} | 总分: {r['total_score']:>+3.0f} | "
                       f"收盘: {r['close']:>7.2f} | 涨跌: {r['change_pct']:>+6.2f}%\n")
                f.write(f"             分项: 趋势{r['trend_score']:+.0f} 动量{r['momentum_score']:+.0f} "
                       f"波动{r['volatility_score']:+.0f} 成交量{r['volume_score']:+.0f} "
                       f"形态{r['pattern_score']:+.0f}\n")
                f.write("\n")

        f.write("\n")

        # 趋势类高分股票
        trend_high = sorted([r for r in results if r['trend_score'] >= 5],
                          key=lambda x: x['trend_score'], reverse=True)[:10]
        if trend_high:
            f.write("-" * 100 + "\n")
            f.write(f"【趋势类高分股票 TOP 10】(趋势得分 ≥ 5)\n")
            f.write("-" * 100 + "\n")
            for r in trend_high:
                f.write(f"{r['code']:<12} {r['name']:<10} | 趋势分: {r['trend_score']:>+3.0f} | "
                       f"总分: {r['total_score']:>+3.0f} | 涨跌: {r['change_pct']:>+6.2f}%\n")
            f.write("\n\n")

        # RSI超卖/超买
        if oversold_rsi:
            f.write("-" * 100 + "\n")
            f.write(f"【RSI超卖股票】(RSI < 30, 共 {len(oversold_rsi)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(oversold_rsi, key=lambda x: x['rsi'])[:10]:
                f.write(f"{r['code']:<12} {r['name']:<10} | RSI: {r['rsi']:>5.1f} | "
                       f"总分: {r['total_score']:>+3.0f} | 收盘: {r['close']:>7.2f}\n")
            f.write("\n\n")

        if overbought_rsi:
            f.write("-" * 100 + "\n")
            f.write(f"【RSI超买股票】(RSI > 70, 共 {len(overbought_rsi)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(overbought_rsi, key=lambda x: x['rsi'], reverse=True)[:10]:
                f.write(f"{r['code']:<12} {r['name']:<10} | RSI: {r['rsi']:>5.1f} | "
                       f"总分: {r['total_score']:>+3.0f} | 收盘: {r['close']:>7.2f}\n")
            f.write("\n\n")

        # MFI超卖/超买
        if oversold_mfi:
            f.write("-" * 100 + "\n")
            f.write(f"【MFI超卖股票】(MFI < 30, 共 {len(oversold_mfi)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(oversold_mfi, key=lambda x: x['mfi'])[:10]:
                f.write(f"{r['code']:<12} {r['name']:<10} | MFI: {r['mfi']:>5.1f} | "
                       f"总分: {r['total_score']:>+3.0f} | OBV: {r['obv_trend']}\n")
            f.write("\n\n")

        if overbought_mfi:
            f.write("-" * 100 + "\n")
            f.write(f"【MFI超买股票】(MFI > 70, 共 {len(overbought_mfi)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(overbought_mfi, key=lambda x: x['mfi'], reverse=True)[:10]:
                f.write(f"{r['code']:<12} {r['name']:<10} | MFI: {r['mfi']:>5.1f} | "
                       f"总分: {r['total_score']:>+3.0f} | OBV: {r['obv_trend']}\n")
            f.write("\n\n")

        # 放量股票
        if high_volume:
            f.write("-" * 100 + "\n")
            f.write(f"【放量股票】(量比 > 1.5, 共 {len(high_volume)} 只)\n")
            f.write("-" * 100 + "\n")
            for r in sorted(high_volume, key=lambda x: x['volume_ratio'], reverse=True)[:15]:
                f.write(f"{r['code']:<12} {r['name']:<10} | 量比: {r['volume_ratio']:>5.2f}x | "
                       f"涨跌: {r['change_pct']:>+6.2f}% | 总分: {r['total_score']:>+3.0f}\n")
            f.write("\n\n")

        # OBV趋势统计
        f.write("-" * 100 + "\n")
        f.write("【OBV趋势统计】\n")
        f.write("-" * 100 + "\n")
        f.write(f"上升趋势: {len(obv_up)} 只 ({len(obv_up)/total_count*100:.1f}%)\n")
        f.write(f"下降趋势: {len(obv_down)} 只 ({len(obv_down)/total_count*100:.1f}%)\n")
        f.write("\n\n")

        # 综合建议
        f.write("-" * 100 + "\n")
        f.write("【综合建议】\n")
        f.write("-" * 100 + "\n")

        if strong_bullish:
            codes = ', '.join([r['code'] for r in strong_bullish[:10]])
            f.write(f"强烈关注 (得分≥8): {codes}\n")
        if bullish:
            codes = ', '.join([r['code'] for r in bullish[:10]])
            f.write(f"适度关注 (5≤得分<8): {codes}\n")
        if strong_bearish:
            codes = ', '.join([r['code'] for r in strong_bearish[:10]])
            f.write(f"风险警示 (得分<-7): {codes}\n")

        f.write("\n")
        f.write("=" * 100 + "\n")
        f.write("报告生成完成\n")
        f.write("=" * 100 + "\n")

    logger.info(f"详细报告已保存到: {output_file}")


def save_csv_summary(results, output_file):
    """保存CSV汇总文件"""
    if not results:
        return

    # 转换为DataFrame
    df = pd.DataFrame(results)

    # 按总分排序
    df = df.sort_values('total_score', ascending=False).reset_index(drop=True)

    # 添加综合排名和等级
    df.insert(0, 'rank', range(1, len(df) + 1))
    df['score_level'] = df['total_score'].apply(get_score_level)

    # 添加各分类排名
    # 趋势类排名
    df_trend = df[['code', 'trend_score']].copy()
    df_trend = df_trend.sort_values('trend_score', ascending=False).reset_index(drop=True)
    df_trend['trend_rank'] = range(1, len(df_trend) + 1)
    df = df.merge(df_trend[['code', 'trend_rank']], on='code', how='left')

    # 动量类排名
    df_momentum = df[['code', 'momentum_score']].copy()
    df_momentum = df_momentum.sort_values('momentum_score', ascending=False).reset_index(drop=True)
    df_momentum['momentum_rank'] = range(1, len(df_momentum) + 1)
    df = df.merge(df_momentum[['code', 'momentum_rank']], on='code', how='left')

    # 波动类排名
    df_volatility = df[['code', 'volatility_score']].copy()
    df_volatility = df_volatility.sort_values('volatility_score', ascending=False).reset_index(drop=True)
    df_volatility['volatility_rank'] = range(1, len(df_volatility) + 1)
    df = df.merge(df_volatility[['code', 'volatility_rank']], on='code', how='left')

    # 成交量类排名
    df_volume = df[['code', 'volume_score']].copy()
    df_volume = df_volume.sort_values('volume_score', ascending=False).reset_index(drop=True)
    df_volume['volume_rank'] = range(1, len(df_volume) + 1)
    df = df.merge(df_volume[['code', 'volume_rank']], on='code', how='left')

    # 形态类排名
    df_pattern = df[['code', 'pattern_score']].copy()
    df_pattern = df_pattern.sort_values('pattern_score', ascending=False).reset_index(drop=True)
    df_pattern['pattern_rank'] = range(1, len(df_pattern) + 1)
    df = df.merge(df_pattern[['code', 'pattern_rank']], on='code', how='left')

    # 保存
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    logger.info(f"CSV汇总已保存到: {output_file}")


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description='股票当日技术面打分排名系统')
    parser.add_argument('--pool', type=str, required=True, help='股票池文件路径')
    parser.add_argument('--days', type=int, default=60, help='获取历史数据天数，默认60天')
    parser.add_argument('--workers', type=int, default=4, help='并发进程数，默认4')
    parser.add_argument('--output_dir', type=str, default=None, help='输出目录，默认 daily_scoring_results')
    parser.add_argument('--use-local-db', action='store_true', help='使用本地数据库而非在线Tushare（需要先初始化数据库）')

    args = parser.parse_args()

    # 设置输出目录
    output_dir = args.output_dir if args.output_dir else OUTPUT_DIR
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 读取股票池
    stocks = read_stock_pool(args.pool)
    if not stocks:
        logger.error("股票池为空，退出")
        sys.exit(1)

    # 提取股票代码列表
    stock_codes = [s['code'] for s in stocks]

    # 计算日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y%m%d')

    # 如果使用本地数据库，查询最新日期并筛选股票
    filtered_stocks = stocks  # 默认使用所有股票
    if args.use_local_db:
        latest_date, stocks_with_latest = get_latest_date_and_filter_stocks(stock_codes, use_local_db=True)
        if latest_date is None:
            logger.error("无法确定最新日期，退出")
            sys.exit(1)
        # 使用最新日期作为结束日期
        end_date = latest_date
        # 筛选出有最新日期数据的股票
        filtered_stocks = [s for s in stocks if s['code'] in stocks_with_latest]
        logger.info(f"使用本地数据库最新日期: {end_date}")

    logger.info(f"开始批量分析 {len(filtered_stocks)} 只股票")
    if args.use_local_db and len(filtered_stocks) < len(stocks):
        logger.warning(f"  (原股票池 {len(stocks)} 只，{len(stocks) - len(filtered_stocks)} 只因数据未更新被排除)")
    logger.info(f"日期范围: {start_date} 至 {end_date}")
    logger.info(f"并发进程数: {args.workers}")
    logger.info(f"数据源: {'本地数据库' if args.use_local_db else '在线Tushare'}")

    # 准备任务参数（只处理筛选后的股票）
    tasks = [(s['code'], s['name'], start_date, end_date, args.use_local_db) for s in filtered_stocks]

    # 多进程批量处理
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(analyze_single_stock, task): task[0] for task in tasks}

        for future in as_completed(futures):
            stock_code = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    logger.info(f"✓ {stock_code} {result['name']} | 总分: {result['total_score']:+.0f}")
                else:
                    logger.warning(f"✗ {stock_code} | 分析失败")
            except Exception as e:
                logger.error(f"✗ {stock_code} | 异常: {e}")

    # 生成报告
    if results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # TXT详细报告
        txt_file = os.path.join(output_dir, f'daily_scoring_report_{timestamp}.txt')
        # 如果使用本地数据库，传入分析基准日期
        generate_comprehensive_report(results, txt_file,
                                     analysis_date=end_date if args.use_local_db else None)

        # CSV汇总
        csv_file = os.path.join(output_dir, f'daily_scoring_summary_{timestamp}.csv')
        save_csv_summary(results, csv_file)

        logger.info(f"\n{'='*50}")
        logger.info(f"批量分析完成！")
        logger.info(f"成功分析: {len(results)}/{len(filtered_stocks)} 只股票")
        if args.use_local_db:
            logger.info(f"分析基准日期: {end_date}")
            if len(filtered_stocks) < len(stocks):
                logger.info(f"排除股票: {len(stocks) - len(filtered_stocks)} 只（数据未更新到最新日期）")
        logger.info(f"详细报告: {txt_file}")
        logger.info(f"CSV汇总: {csv_file}")
        logger.info(f"{'='*50}")
    else:
        logger.error("没有成功分析的股票，无法生成报告")


if __name__ == '__main__':
    main()
