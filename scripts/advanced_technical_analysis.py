#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级技术指标分析工具
根据new_requirement.md的需求，实现完整的技术指标体系
包含：趋势类、动量类、波动类、成交量类指标
"""

import pandas as pd
import pandas_ta as ta
import tushare as ts
from datetime import datetime, timedelta
import logging
import argparse
import os
import sys
import numpy as np

# ==================== 路径配置 ====================
# 将项目根目录添加到 Python 路径，以便导入 database 模块
# 这样无论从哪个目录运行脚本都能正常工作
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False

# 创建输出文件夹
OUTPUT_DIR = 'advanced_analysis_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class TeeOutput:
    """同时输出到控制台和文件的类"""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


class AdvancedTechnicalAnalyzer:
    """高级技术分析器"""

    def __init__(self, use_local_db=False):
        """
        初始化

        Args:
            use_local_db: 是否使用本地数据库，默认False（使用在线Tushare）
        """
        self.use_local_db = use_local_db and LOCAL_DB_AVAILABLE
        self.local_query = None

        if self.use_local_db:
            # 使用本地数据库
            self.local_query = StockDataQuery()
            logger.info("使用本地数据库作为数据源")
        else:
            # 使用在线Tushare
            # 从 token.txt 读取 Tushare token
            token_file = os.path.join(os.path.dirname(__file__), '../token.txt')
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    ts_token = f.read().strip()
                if not ts_token:
                    raise ValueError("token.txt 文件为空")
            except FileNotFoundError:
                logger.error(f"未找到 token.txt 文件，请在 {token_file} 中添加您的 tushare token")
                raise
            except Exception as e:
                logger.error(f"读取 token.txt 文件失败: {e}")
                raise

            ts.set_token(ts_token)
            self.pro = ts.pro_api()
            logger.info("使用在线Tushare作为数据源")

        # 指标参数配置
        self.params = {
            'ma_periods': [5, 10, 20, 60],  # 移动平均线周期
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'rsi_period': 14,
            'kdj_period': 9,
            'cci_period': 14,
            'boll_period': 20,
            'boll_std': 2,
        }

    def fetch_data(self, ts_code, start_date, end_date):
        """
        获取股票数据
        :param ts_code: 股票代码，如 '000001.SZ'
        :param start_date: 开始日期 'YYYYMMDD'
        :param end_date: 结束日期 'YYYYMMDD'
        :return: DataFrame
        """
        logger.info(f"获取 {ts_code} 从 {start_date} 到 {end_date} 的数据")

        if self.use_local_db:
            # 从本地数据库获取数据
            df = self.local_query.daily(ts_code, start_date, end_date)
        else:
            # 从在线Tushare获取数据
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

        if df is None or df.empty:
            logger.warning(f"未获取到 {ts_code} 的数据")
            return None

        # 按日期升序排列
        df = df.sort_values('trade_date').reset_index(drop=True)

        # 重命名列以符合 pandas-ta 的要求
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'vol': 'Volume'
        })

        logger.info(f"成功获取 {len(df)} 条数据")
        return df

    def calculate_trend_indicators(self, df):
        """
        计算趋势类指标
        包括：移动平均线(MA)、MACD、SAR
        """
        if df is None or df.empty:
            return None

        logger.info("计算趋势类指标")

        # 1. 移动平均线 (MA)
        for period in self.params['ma_periods']:
            df[f'MA{period}'] = ta.sma(df['Close'], length=period)
            logger.info(f"  - 计算MA{period}")

        # 2. MACD
        if len(df) >= self.params['macd_slow'] + self.params['macd_signal']:
            macd = ta.macd(df['Close'],
                          fast=self.params['macd_fast'],
                          slow=self.params['macd_slow'],
                          signal=self.params['macd_signal'])

            if macd is not None and not macd.empty:
                df['MACD_DIF'] = macd[f'MACD_{self.params["macd_fast"]}_{self.params["macd_slow"]}_{self.params["macd_signal"]}']
                df['MACD_DEA'] = macd[f'MACDs_{self.params["macd_fast"]}_{self.params["macd_slow"]}_{self.params["macd_signal"]}']
                df['MACD_Histogram'] = macd[f'MACDh_{self.params["macd_fast"]}_{self.params["macd_slow"]}_{self.params["macd_signal"]}']
                logger.info("  - 计算MACD")
            else:
                logger.warning("  - MACD计算失败：数据不足")
                df['MACD_DIF'] = np.nan
                df['MACD_DEA'] = np.nan
                df['MACD_Histogram'] = np.nan
        else:
            logger.warning(f"  - MACD需要至少{self.params['macd_slow'] + self.params['macd_signal']}天数据，当前只有{len(df)}天")
            df['MACD_DIF'] = np.nan
            df['MACD_DEA'] = np.nan
            df['MACD_Histogram'] = np.nan

        # 3. SAR (抛物线指标)
        sar = ta.psar(df['High'], df['Low'], df['Close'])
        df['SAR_Long'] = sar['PSARl_0.02_0.2']
        df['SAR_Short'] = sar['PSARs_0.02_0.2']
        df['SAR_Indicator'] = sar['PSARaf_0.02_0.2']
        df['SAR_Reversal'] = sar['PSARr_0.02_0.2']
        logger.info("  - 计算SAR")

        return df

    def calculate_momentum_indicators(self, df):
        """
        计算动量/摆荡类指标
        包括：RSI、KDJ、CCI
        """
        if df is None or df.empty:
            return None

        logger.info("计算动量/摆荡类指标")

        # 1. RSI (相对强弱指数)
        df['RSI'] = ta.rsi(df['Close'], length=self.params['rsi_period'])
        logger.info(f"  - 计算RSI({self.params['rsi_period']})")

        # 2. KDJ (随机指标)
        # pandas_ta中的stoch对应KDJ
        stoch = ta.stoch(df['High'], df['Low'], df['Close'],
                        k=self.params['kdj_period'],
                        d=3, smooth_k=3)

        df['K'] = stoch[f'STOCHk_{self.params["kdj_period"]}_3_3']
        df['D'] = stoch[f'STOCHd_{self.params["kdj_period"]}_3_3']
        # J = 3K - 2D
        df['J'] = 3 * df['K'] - 2 * df['D']
        logger.info("  - 计算KDJ")

        # 3. CCI (商品通道指数)
        df['CCI'] = ta.cci(df['High'], df['Low'], df['Close'],
                          length=self.params['cci_period'])
        logger.info(f"  - 计算CCI({self.params['cci_period']})")

        return df

    def calculate_volatility_indicators(self, df):
        """
        计算波动类指标
        包括：布林带(BOLL)、ATR
        """
        if df is None or df.empty:
            return None

        logger.info("计算波动类指标")

        # 1. 布林带 (Bollinger Bands)
        if len(df) >= self.params['boll_period']:
            bbands = ta.bbands(df['Close'],
                              length=self.params['boll_period'],
                              std=self.params['boll_std'])

            if bbands is not None and not bbands.empty:
                # 动态获取列名（pandas_ta版本可能有差异）
                bbands_cols = bbands.columns.tolist()
                df['BOLL_Upper'] = bbands[bbands_cols[2]]  # BBU
                df['BOLL_Middle'] = bbands[bbands_cols[1]]  # BBM
                df['BOLL_Lower'] = bbands[bbands_cols[0]]  # BBL
                df['BOLL_Bandwidth'] = bbands[bbands_cols[3]]  # BBB
                df['BOLL_Percent'] = bbands[bbands_cols[4]]  # BBP
                logger.info("  - 计算布林带")
            else:
                logger.warning("  - 布林带计算失败：数据不足")
                df['BOLL_Upper'] = np.nan
                df['BOLL_Middle'] = np.nan
                df['BOLL_Lower'] = np.nan
                df['BOLL_Bandwidth'] = np.nan
                df['BOLL_Percent'] = np.nan
        else:
            logger.warning(f"  - 布林带需要至少{self.params['boll_period']}天数据，当前只有{len(df)}天")
            df['BOLL_Upper'] = np.nan
            df['BOLL_Middle'] = np.nan
            df['BOLL_Lower'] = np.nan
            df['BOLL_Bandwidth'] = np.nan
            df['BOLL_Percent'] = np.nan

        # 2. ATR (平均真实波幅)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        logger.info("  - 计算ATR")

        return df

    def calculate_volume_indicators(self, df):
        """
        计算成交量类指标
        包括：成交量分析、OBV、MFI、VWAP
        """
        if df is None or df.empty:
            return None

        logger.info("计算成交量类指标")

        # 1. 成交量移动平均
        df['VOL_MA5'] = ta.sma(df['Volume'], length=5)
        df['VOL_MA10'] = ta.sma(df['Volume'], length=10)

        # 量比
        df['Volume_Ratio'] = df['Volume'] / df['VOL_MA5']
        logger.info("  - 计算成交量均线和量比")

        # 2. OBV (能量潮)
        df['OBV'] = ta.obv(df['Close'], df['Volume'])
        df['OBV_MA'] = ta.sma(df['OBV'], length=10)
        logger.info("  - 计算OBV")

        # 3. MFI (资金流量指数)
        df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
        logger.info("  - 计算MFI")

        # 4. VWAP (成交量加权平均价格)
        df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        logger.info("  - 计算VWAP")

        return df

    def calculate_detailed_scores(self, df):
        """
        基于new_requirement.md的打分规则计算详细的技术面打分
        返回包含分项得分和总分的DataFrame
        """
        if df is None or df.empty:
            return None

        logger.info("计算详细技术面打分")

        # 初始化打分列
        df['Trend_Score'] = 0      # 趋势类得分
        df['Momentum_Score'] = 0   # 动量类得分
        df['Volatility_Score'] = 0 # 波动类得分
        df['Volume_Score'] = 0     # 成交量类得分
        df['Pattern_Score'] = 0    # 形态类得分
        df['Total_Score'] = 0      # 总分
        df['Score_Details'] = ''   # 得分明细

        for i in range(20, len(df)):  # 从第20行开始，确保有足够的历史数据
            trend_score = 0
            momentum_score = 0
            volatility_score = 0
            volume_score = 0
            pattern_score = 0
            score_details = []

            # ==================== 趋势类打分 ====================

            # 1. MACD打分
            if pd.notna(df.loc[i, 'MACD_DIF']) and pd.notna(df.loc[i, 'MACD_DEA']):
                # MACD金叉/死叉
                if i > 0 and pd.notna(df.loc[i-1, 'MACD_DIF']) and pd.notna(df.loc[i-1, 'MACD_DEA']):
                    # 金叉
                    if df.loc[i, 'MACD_DIF'] > df.loc[i, 'MACD_DEA'] and df.loc[i-1, 'MACD_DIF'] <= df.loc[i-1, 'MACD_DEA']:
                        if df.loc[i, 'MACD_DIF'] < 0:  # 0轴下金叉
                            trend_score += 3
                            score_details.append('MACD低位金叉(+3)')
                        else:  # 0轴上金叉
                            trend_score += 2
                            score_details.append('MACD金叉(+2)')
                    # 死叉
                    elif df.loc[i, 'MACD_DIF'] < df.loc[i, 'MACD_DEA'] and df.loc[i-1, 'MACD_DIF'] >= df.loc[i-1, 'MACD_DEA']:
                        if df.loc[i, 'MACD_DIF'] > 0:  # 0轴上死叉
                            trend_score -= 3
                            score_details.append('MACD高位死叉(-3)')
                        else:  # 0轴下死叉
                            trend_score -= 2
                            score_details.append('MACD死叉(-2)')

                # MACD动能（柱状图）
                if pd.notna(df.loc[i, 'MACD_Histogram']) and i > 0 and pd.notna(df.loc[i-1, 'MACD_Histogram']):
                    if df.loc[i, 'MACD_Histogram'] > df.loc[i-1, 'MACD_Histogram'] and df.loc[i, 'MACD_Histogram'] > 0:
                        trend_score += 1
                        score_details.append('MACD红柱增长(+1)')
                    elif df.loc[i, 'MACD_Histogram'] < df.loc[i-1, 'MACD_Histogram'] and df.loc[i, 'MACD_Histogram'] < 0:
                        trend_score -= 1
                        score_details.append('MACD绿柱增长(-1)')

            # 2. SAR打分
            if 'SAR_Long' in df.columns and 'SAR_Short' in df.columns:
                if i > 0:
                    # SAR转向
                    if pd.notna(df.loc[i, 'SAR_Long']) and pd.isna(df.loc[i-1, 'SAR_Long']):
                        trend_score += 3
                        score_details.append('SAR空转多(+3)')
                    elif pd.notna(df.loc[i, 'SAR_Short']) and pd.isna(df.loc[i-1, 'SAR_Short']):
                        trend_score -= 3
                        score_details.append('SAR多转空(-3)')
                    # SAR持续
                    elif pd.notna(df.loc[i, 'SAR_Long']) and pd.notna(df.loc[i-1, 'SAR_Long']):
                        trend_score += 2
                        score_details.append('SAR多头持续(+2)')
                    elif pd.notna(df.loc[i, 'SAR_Short']) and pd.notna(df.loc[i-1, 'SAR_Short']):
                        trend_score -= 2
                        score_details.append('SAR空头持续(-2)')

            # 3. 均线排列打分
            if pd.notna(df.loc[i, 'MA5']) and pd.notna(df.loc[i, 'MA10']) and pd.notna(df.loc[i, 'MA20']):
                # 多头排列
                if df.loc[i, 'Close'] > df.loc[i, 'MA5'] > df.loc[i, 'MA10'] > df.loc[i, 'MA20']:
                    trend_score += 3
                    score_details.append('均线多头排列(+3)')
                # 空头排列
                elif df.loc[i, 'Close'] < df.loc[i, 'MA5'] < df.loc[i, 'MA10'] < df.loc[i, 'MA20']:
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

                # RSI突破50中轴
                if i > 0 and pd.notna(df.loc[i-1, 'RSI']):
                    if df.loc[i, 'RSI'] > 50 and df.loc[i-1, 'RSI'] <= 50:
                        momentum_score += 1
                        score_details.append('RSI突破中轴(+1)')
                    elif df.loc[i, 'RSI'] < 50 and df.loc[i-1, 'RSI'] >= 50:
                        momentum_score -= 1
                        score_details.append('RSI跌破中轴(-1)')

            # 2. KDJ打分
            if pd.notna(df.loc[i, 'K']) and pd.notna(df.loc[i, 'D']):
                # KDJ金叉/死叉
                if i > 0 and pd.notna(df.loc[i-1, 'K']) and pd.notna(df.loc[i-1, 'D']):
                    # 低位金叉
                    if df.loc[i, 'K'] > df.loc[i, 'D'] and df.loc[i-1, 'K'] <= df.loc[i-1, 'D'] and df.loc[i, 'D'] < 20:
                        momentum_score += 3
                        score_details.append('KDJ低位金叉(+3)')
                    # 高位死叉
                    elif df.loc[i, 'K'] < df.loc[i, 'D'] and df.loc[i-1, 'K'] >= df.loc[i-1, 'D'] and df.loc[i, 'D'] > 80:
                        momentum_score -= 3
                        score_details.append('KDJ高位死叉(-3)')

                # J值极值
                if pd.notna(df.loc[i, 'J']):
                    if df.loc[i, 'J'] < 0:
                        momentum_score += 2
                        score_details.append('J值极度超卖(+2)')
                    elif df.loc[i, 'J'] > 100:
                        momentum_score -= 2
                        score_details.append('J值极度超买(-2)')

            # 3. CCI打分
            if pd.notna(df.loc[i, 'CCI']):
                if i > 0 and pd.notna(df.loc[i-1, 'CCI']):
                    # 从超卖区突破
                    if df.loc[i, 'CCI'] > -100 and df.loc[i-1, 'CCI'] <= -100:
                        momentum_score += 2
                        score_details.append('CCI脱离超卖区(+2)')
                    # 从超买区跌落
                    elif df.loc[i, 'CCI'] < 100 and df.loc[i-1, 'CCI'] >= 100:
                        momentum_score -= 2
                        score_details.append('CCI脱离超买区(-2)')

                # 持续强弱
                if df.loc[i, 'CCI'] > 100:
                    momentum_score += 1
                    score_details.append('CCI强势(+1)')
                elif df.loc[i, 'CCI'] < -100:
                    momentum_score -= 1
                    score_details.append('CCI弱势(-1)')

            # ==================== 波动类打分 ====================

            # 1. 布林带打分
            if pd.notna(df.loc[i, 'BOLL_Upper']) and pd.notna(df.loc[i, 'BOLL_Lower']):
                # 突破布林带
                if df.loc[i, 'Close'] > df.loc[i, 'BOLL_Upper']:
                    volatility_score -= 2
                    score_details.append('突破布林上轨(-2)')
                elif df.loc[i, 'Close'] < df.loc[i, 'BOLL_Lower']:
                    volatility_score += 2
                    score_details.append('突破布林下轨(+2)')
                # 触及布林带
                elif df.loc[i, 'Close'] >= df.loc[i, 'BOLL_Upper'] * 0.98:
                    volatility_score -= 1
                    score_details.append('触及布林上轨(-1)')
                elif df.loc[i, 'Close'] <= df.loc[i, 'BOLL_Lower'] * 1.02:
                    volatility_score += 1
                    score_details.append('触及布林下轨(+1)')

                # 布林带开口
                if pd.notna(df.loc[i, 'BOLL_Bandwidth']) and i > 5:
                    bandwidth_ma = df.loc[i-5:i, 'BOLL_Bandwidth'].mean()
                    if df.loc[i, 'BOLL_Bandwidth'] > bandwidth_ma * 1.2:
                        if df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                            volatility_score += 1
                            score_details.append('布林带开口上涨(+1)')
                        else:
                            volatility_score -= 1
                            score_details.append('布林带开口下跌(-1)')

            # 2. ATR打分
            if pd.notna(df.loc[i, 'ATR']) and i > 5:
                atr_ma = df.loc[i-5:i, 'ATR'].mean()
                if df.loc[i, 'ATR'] > atr_ma * 1.5:
                    # 大幅波动
                    if df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                        volatility_score += 1
                        score_details.append('ATR波动加大上涨(+1)')
                    else:
                        volatility_score -= 2
                        score_details.append('ATR波动加大下跌(-2)')

            # ==================== 成交量类打分 ====================

            # 1. VWAP打分
            if pd.notna(df.loc[i, 'VWAP']):
                # 价格与VWAP关系
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
                # 放量
                if df.loc[i, 'Volume_Ratio'] > 1.5:
                    if df.loc[i, 'Close'] > df.loc[i-1, 'Close']:
                        volume_score += 2
                        score_details.append('放量上涨(+2)')
                    else:
                        volume_score -= 2
                        score_details.append('放量下跌(-2)')

            # 5. MFI/OBV组合信号
            if pd.notna(df.loc[i, 'MFI']) and pd.notna(df.loc[i, 'OBV']) and pd.notna(df.loc[i, 'OBV_MA']):
                # 强烈看涨组合：MFI超卖 + OBV上升
                if df.loc[i, 'MFI'] < 20 and df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA']:
                    volume_score += 2
                    score_details.append('MFI超卖+OBV上升(+2)')
                # 强烈看跌组合：MFI超买 + OBV下降
                elif df.loc[i, 'MFI'] > 80 and df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA']:
                    volume_score -= 2
                    score_details.append('MFI超买+OBV下降(-2)')
                # 矛盾信号：MFI超卖但OBV下降（警惕）
                elif df.loc[i, 'MFI'] < 20 and df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA']:
                    volume_score -= 1
                    score_details.append('MFI超卖但OBV下降(-1)')
                # 矛盾信号：MFI超买但OBV上升（警惕）
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
                # 突破阻力
                if i > 0 and df.loc[i, 'Close'] > df.loc[i, 'Resistance'] and df.loc[i-1, 'Close'] <= df.loc[i, 'Resistance']:
                    pattern_score += 3
                    score_details.append('突破阻力位(+3)')
                # 跌破支撑
                elif i > 0 and df.loc[i, 'Close'] < df.loc[i, 'Support'] and df.loc[i-1, 'Close'] >= df.loc[i, 'Support']:
                    pattern_score -= 3
                    score_details.append('跌破支撑位(-3)')
                # 获得支撑
                elif df.loc[i, 'Low'] <= df.loc[i, 'Support'] * 1.02 and df.loc[i, 'Close'] > df.loc[i, 'Support']:
                    pattern_score += 2
                    score_details.append('获得支撑(+2)')
                # 遇到阻力
                elif df.loc[i, 'High'] >= df.loc[i, 'Resistance'] * 0.98 and df.loc[i, 'Close'] < df.loc[i, 'Resistance']:
                    pattern_score -= 2
                    score_details.append('遇到阻力(-2)')

            # 3. K线形态打分
            if 'is_hammer' in df.columns:
                # 锤子线（在下跌后出现）
                if df.loc[i, 'is_hammer'] and i >= 5:
                    # 检查前5天是否有下跌趋势
                    prev_trend = df.loc[i-5:i-1, 'Close'].diff().mean()
                    if prev_trend < 0:
                        pattern_score += 3
                        score_details.append('锤子线(+3)')
                    else:
                        pattern_score += 1
                        score_details.append('锤子线(+1)')

            if 'is_shooting_star' in df.columns:
                # 射击之星（在上涨后出现）
                if df.loc[i, 'is_shooting_star'] and i >= 5:
                    # 检查前5天是否有上涨趋势
                    prev_trend = df.loc[i-5:i-1, 'Close'].diff().mean()
                    if prev_trend > 0:
                        pattern_score -= 3
                        score_details.append('射击之星(-3)')
                    else:
                        pattern_score -= 1
                        score_details.append('射击之星(-1)')

            if 'is_doji' in df.columns:
                # 十字星（不确定性信号，轻微减分）
                if df.loc[i, 'is_doji']:
                    score_details.append('十字星(观望)')

            if 'is_big_bullish' in df.columns:
                # 大阳线
                if df.loc[i, 'is_big_bullish']:
                    pattern_score += 2
                    score_details.append('大阳线(+2)')

            if 'is_big_bearish' in df.columns:
                # 大阴线
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
            df.loc[i, 'Score_Details'] = '; '.join(score_details) if score_details else ''

        return df

    def identify_signals(self, df):
        """
        识别交易信号
        综合多个指标生成买卖信号
        使用详细打分系统
        """
        if df is None or df.empty:
            return None

        logger.info("识别交易信号和计算打分")

        # 先计算详细打分
        df = self.calculate_detailed_scores(df)

        # 初始化信号列（保留原有的信号识别逻辑）
        df['Buy_Signals'] = ''
        df['Sell_Signals'] = ''
        df['Signal_Strength'] = 0

        for i in range(60, len(df)):  # 从第60行开始，确保有足够的历史数据
            buy_signals = []
            sell_signals = []
            strength = 0

            # 趋势类信号
            # 1. MA金叉/死叉
            if pd.notna(df.loc[i, 'MA5']) and pd.notna(df.loc[i, 'MA20']):
                if df.loc[i, 'MA5'] > df.loc[i, 'MA20'] and df.loc[i-1, 'MA5'] <= df.loc[i-1, 'MA20']:
                    buy_signals.append('MA金叉(5/20)')
                    strength += 2
                elif df.loc[i, 'MA5'] < df.loc[i, 'MA20'] and df.loc[i-1, 'MA5'] >= df.loc[i-1, 'MA20']:
                    sell_signals.append('MA死叉(5/20)')
                    strength -= 2

            # 2. MACD信号
            if pd.notna(df.loc[i, 'MACD_DIF']) and pd.notna(df.loc[i, 'MACD_DEA']):
                # MACD金叉/死叉
                if df.loc[i, 'MACD_DIF'] > df.loc[i, 'MACD_DEA'] and df.loc[i-1, 'MACD_DIF'] <= df.loc[i-1, 'MACD_DEA']:
                    if df.loc[i, 'MACD_DIF'] < 0:
                        buy_signals.append('MACD低位金叉')
                        strength += 3
                    else:
                        buy_signals.append('MACD金叉')
                        strength += 2
                elif df.loc[i, 'MACD_DIF'] < df.loc[i, 'MACD_DEA'] and df.loc[i-1, 'MACD_DIF'] >= df.loc[i-1, 'MACD_DEA']:
                    if df.loc[i, 'MACD_DIF'] > 0:
                        sell_signals.append('MACD高位死叉')
                        strength -= 3
                    else:
                        sell_signals.append('MACD死叉')
                        strength -= 2

            # 动量类信号
            # 3. RSI超买超卖
            if pd.notna(df.loc[i, 'RSI']):
                if df.loc[i, 'RSI'] < 30 and df.loc[i-1, 'RSI'] >= 30:
                    buy_signals.append('RSI进入超卖区')
                    strength += 2
                elif df.loc[i, 'RSI'] > 70 and df.loc[i-1, 'RSI'] <= 70:
                    sell_signals.append('RSI进入超买区')
                    strength -= 2

            # 4. KDJ信号
            if pd.notna(df.loc[i, 'K']) and pd.notna(df.loc[i, 'D']):
                # KDJ金叉/死叉
                if df.loc[i, 'K'] > df.loc[i, 'D'] and df.loc[i-1, 'K'] <= df.loc[i-1, 'D']:
                    if df.loc[i, 'D'] < 20:
                        buy_signals.append('KDJ低位金叉')
                        strength += 3
                    else:
                        buy_signals.append('KDJ金叉')
                        strength += 1
                elif df.loc[i, 'K'] < df.loc[i, 'D'] and df.loc[i-1, 'K'] >= df.loc[i-1, 'D']:
                    if df.loc[i, 'D'] > 80:
                        sell_signals.append('KDJ高位死叉')
                        strength -= 3
                    else:
                        sell_signals.append('KDJ死叉')
                        strength -= 1

                # J值极端情况
                if pd.notna(df.loc[i, 'J']):
                    if df.loc[i, 'J'] < 0:
                        buy_signals.append('J值超卖')
                        strength += 1
                    elif df.loc[i, 'J'] > 100:
                        sell_signals.append('J值超买')
                        strength -= 1

            # 5. CCI信号
            if pd.notna(df.loc[i, 'CCI']):
                if df.loc[i, 'CCI'] > 100 and df.loc[i-1, 'CCI'] <= 100:
                    buy_signals.append('CCI突破100')
                    strength += 1
                elif df.loc[i, 'CCI'] < -100 and df.loc[i-1, 'CCI'] >= -100:
                    sell_signals.append('CCI跌破-100')
                    strength -= 1

            # 波动类信号
            # 6. 布林带信号
            if pd.notna(df.loc[i, 'BOLL_Upper']) and pd.notna(df.loc[i, 'BOLL_Lower']):
                # 触及布林带上下轨
                if df.loc[i, 'Close'] <= df.loc[i, 'BOLL_Lower']:
                    buy_signals.append('触及布林下轨')
                    strength += 2
                elif df.loc[i, 'Close'] >= df.loc[i, 'BOLL_Upper']:
                    sell_signals.append('触及布林上轨')
                    strength -= 2

                # 布林带收口/张口
                if pd.notna(df.loc[i, 'BOLL_Bandwidth']) and i > 5:
                    bandwidth_ma = df.loc[i-5:i, 'BOLL_Bandwidth'].mean()
                    if df.loc[i, 'BOLL_Bandwidth'] < bandwidth_ma * 0.8:
                        buy_signals.append('布林带收口')
                        strength += 1

            # 成交量类信号
            # 7. 量价配合
            if pd.notna(df.loc[i, 'Volume_Ratio']):
                # 放量上涨
                if df.loc[i, 'Close'] > df.loc[i-1, 'Close'] and df.loc[i, 'Volume_Ratio'] > 1.5:
                    buy_signals.append('放量上涨')
                    strength += 2
                # 放量下跌
                elif df.loc[i, 'Close'] < df.loc[i-1, 'Close'] and df.loc[i, 'Volume_Ratio'] > 1.5:
                    sell_signals.append('放量下跌')
                    strength -= 2

            # 8. OBV信号
            if pd.notna(df.loc[i, 'OBV']) and pd.notna(df.loc[i, 'OBV_MA']):
                if df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA'] and df.loc[i-1, 'OBV'] <= df.loc[i-1, 'OBV_MA']:
                    buy_signals.append('OBV上穿均线')
                    strength += 1
                elif df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA'] and df.loc[i-1, 'OBV'] >= df.loc[i-1, 'OBV_MA']:
                    sell_signals.append('OBV下穿均线')
                    strength -= 1

            # 9. MFI信号
            if pd.notna(df.loc[i, 'MFI']):
                if df.loc[i, 'MFI'] < 20:
                    buy_signals.append('MFI极度超卖')
                    strength += 2
                elif df.loc[i, 'MFI'] > 80:
                    sell_signals.append('MFI极度超买')
                    strength -= 2

            # 记录信号
            if buy_signals:
                df.loc[i, 'Buy_Signals'] = '; '.join(buy_signals)
            if sell_signals:
                df.loc[i, 'Sell_Signals'] = '; '.join(sell_signals)

            # 使用Total_Score作为Signal_Strength（如果已经计算了打分）
            if 'Total_Score' in df.columns and pd.notna(df.loc[i, 'Total_Score']):
                df.loc[i, 'Signal_Strength'] = df.loc[i, 'Total_Score']
            else:
                df.loc[i, 'Signal_Strength'] = strength

        return df

    def identify_divergence(self, df):
        """
        识别背离信号
        价格与技术指标的背离是重要的反转信号
        """
        if df is None or df.empty:
            return None

        logger.info("识别背离信号")

        df['RSI_Divergence'] = ''
        df['MACD_Divergence'] = ''
        df['OBV_Divergence'] = ''

        # 使用滚动窗口寻找局部高低点
        window = 20
        for i in range(window, len(df) - window):
            # 价格局部高点
            if df.loc[i, 'High'] == df.loc[i-window:i+window, 'High'].max():
                # RSI顶背离
                if pd.notna(df.loc[i, 'RSI']):
                    prev_high_idx = df.loc[i-window*2:i-1, 'High'].idxmax()
                    if prev_high_idx and df.loc[i, 'High'] > df.loc[prev_high_idx, 'High']:
                        if df.loc[i, 'RSI'] < df.loc[prev_high_idx, 'RSI']:
                            df.loc[i, 'RSI_Divergence'] = '顶背离'

                # MACD顶背离
                if pd.notna(df.loc[i, 'MACD_DIF']):
                    prev_high_idx = df.loc[i-window*2:i-1, 'High'].idxmax()
                    if prev_high_idx and df.loc[i, 'High'] > df.loc[prev_high_idx, 'High']:
                        if df.loc[i, 'MACD_DIF'] < df.loc[prev_high_idx, 'MACD_DIF']:
                            df.loc[i, 'MACD_Divergence'] = '顶背离'

            # 价格局部低点
            if df.loc[i, 'Low'] == df.loc[i-window:i+window, 'Low'].min():
                # RSI底背离
                if pd.notna(df.loc[i, 'RSI']):
                    prev_low_idx = df.loc[i-window*2:i-1, 'Low'].idxmin()
                    if prev_low_idx and df.loc[i, 'Low'] < df.loc[prev_low_idx, 'Low']:
                        if df.loc[i, 'RSI'] > df.loc[prev_low_idx, 'RSI']:
                            df.loc[i, 'RSI_Divergence'] = '底背离'

                # MACD底背离
                if pd.notna(df.loc[i, 'MACD_DIF']):
                    prev_low_idx = df.loc[i-window*2:i-1, 'Low'].idxmin()
                    if prev_low_idx and df.loc[i, 'Low'] < df.loc[prev_low_idx, 'Low']:
                        if df.loc[i, 'MACD_DIF'] > df.loc[prev_low_idx, 'MACD_DIF']:
                            df.loc[i, 'MACD_Divergence'] = '底背离'

        return df

    def calculate_support_resistance(self, df, window=20):
        """
        计算支撑位和阻力位
        """
        if df is None or df.empty:
            return None

        logger.info("计算支撑位和阻力位")

        df['Support'] = df['Low'].rolling(window=window).min()
        df['Resistance'] = df['High'].rolling(window=window).max()

        # 计算枢轴点 (Pivot Points)
        df['Pivot'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['R1'] = 2 * df['Pivot'] - df['Low']  # 第一阻力位
        df['S1'] = 2 * df['Pivot'] - df['High']  # 第一支撑位
        df['R2'] = df['Pivot'] + (df['High'] - df['Low'])  # 第二阻力位
        df['S2'] = df['Pivot'] - (df['High'] - df['Low'])  # 第二支撑位

        return df

    def identify_candle_patterns(self, df):
        """
        识别K线形态
        从 technical_analysis.py 迁移
        包括：锤子线、射击之星、十字星、大阳线、大阴线
        """
        if df is None or df.empty:
            return None

        logger.info("识别K线形态")

        # 计算实体和影线长度
        df['body'] = abs(df['Close'] - df['Open'])
        df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['total_range'] = df['High'] - df['Low']

        # 避免除以零
        df['body_ratio'] = df['body'] / (df['total_range'] + 0.0001)
        df['lower_shadow_ratio'] = df['lower_shadow'] / (df['total_range'] + 0.0001)
        df['upper_shadow_ratio'] = df['upper_shadow'] / (df['total_range'] + 0.0001)

        # 识别长下影线（锤子线）
        # 条件：下影线长度 > 实体的2倍，且上影线很短
        df['is_hammer'] = (
            (df['lower_shadow'] > df['body'] * 2) &
            (df['upper_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)  # 实体不能太小
        )

        # 识别长上影线（射击之星）
        df['is_shooting_star'] = (
            (df['upper_shadow'] > df['body'] * 2) &
            (df['lower_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)
        )

        # 识别十字星（实体很小）
        df['is_doji'] = df['body_ratio'] < 0.1

        # 计算日涨跌幅（相对前一日收盘价）
        df['pct_change'] = df['Close'].pct_change() * 100

        # 识别大阳线（涨幅大且实体大）
        df['is_big_bullish'] = (
            (df['Close'] > df['Open']) &
            (df['body_ratio'] > 0.7) &
            (df['pct_change'] > 3)
        )

        # 识别大阴线
        df['is_big_bearish'] = (
            (df['Close'] < df['Open']) &
            (df['body_ratio'] > 0.7) &
            (df['pct_change'] < -3)
        )

        return df

    def print_comprehensive_report(self, df, ts_code, recent_days=10):
        """
        打印综合分析报告
        """
        if df is None or df.empty:
            logger.warning("无数据可分析")
            return

        print("\n" + "="*100)
        print(f"高级技术分析报告 - {ts_code}")
        print("="*100)

        # 获取最新数据
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. 当前价格和趋势
        print("\n【价格概况】")
        print("-"*50)
        print(f"最新收盘价: {latest['Close']:.2f}")
        print(f"日涨跌幅: {((latest['Close'] - prev['Close']) / prev['Close'] * 100):.2f}%")

        if pd.notna(latest['MA5']) and pd.notna(latest['MA20']):
            trend = "上涨" if latest['MA5'] > latest['MA20'] else "下跌"
            print(f"短期趋势: {trend} (MA5={latest['MA5']:.2f}, MA20={latest['MA20']:.2f})")

        if pd.notna(latest['MA20']) and pd.notna(latest['MA60']):
            trend = "上涨" if latest['MA20'] > latest['MA60'] else "下跌"
            print(f"中期趋势: {trend} (MA20={latest['MA20']:.2f}, MA60={latest['MA60']:.2f})")

        # 2. 动量指标状态
        print("\n【动量指标】")
        print("-"*50)

        if pd.notna(latest['RSI']):
            rsi_status = "超买" if latest['RSI'] > 70 else ("超卖" if latest['RSI'] < 30 else "正常")
            print(f"RSI(14): {latest['RSI']:.2f} - {rsi_status}")

        if pd.notna(latest['K']) and pd.notna(latest['D']) and pd.notna(latest['J']):
            kdj_status = "超买" if latest['D'] > 80 else ("超卖" if latest['D'] < 20 else "正常")
            print(f"KDJ: K={latest['K']:.2f}, D={latest['D']:.2f}, J={latest['J']:.2f} - {kdj_status}")

        if pd.notna(latest['CCI']):
            cci_status = "超买" if latest['CCI'] > 100 else ("超卖" if latest['CCI'] < -100 else "正常")
            print(f"CCI(14): {latest['CCI']:.2f} - {cci_status}")

        # 3. MACD状态
        print("\n【MACD指标】")
        print("-"*50)

        if pd.notna(latest['MACD_DIF']) and pd.notna(latest['MACD_DEA']):
            macd_position = "多头" if latest['MACD_DIF'] > latest['MACD_DEA'] else "空头"
            macd_trend = "零轴上方" if latest['MACD_DIF'] > 0 else "零轴下方"
            print(f"DIF: {latest['MACD_DIF']:.4f}, DEA: {latest['MACD_DEA']:.4f}")
            print(f"MACD柱: {latest['MACD_Histogram']:.4f}")
            print(f"状态: {macd_position}, {macd_trend}")

        # 4. 布林带状态
        print("\n【布林带指标】")
        print("-"*50)

        if pd.notna(latest['BOLL_Upper']) and pd.notna(latest['BOLL_Lower']):
            print(f"上轨: {latest['BOLL_Upper']:.2f}")
            print(f"中轨: {latest['BOLL_Middle']:.2f}")
            print(f"下轨: {latest['BOLL_Lower']:.2f}")
            print(f"带宽: {latest['BOLL_Bandwidth']:.4f}")

            position = "上轨附近" if latest['Close'] > latest['BOLL_Middle'] else "下轨附近"
            print(f"价格位置: {position}")

        # 5. 成交量分析
        print("\n【成交量分析】")
        print("-"*50)

        if pd.notna(latest['Volume_Ratio']):
            vol_status = "放量" if latest['Volume_Ratio'] > 1.5 else ("缩量" if latest['Volume_Ratio'] < 0.7 else "正常")
            print(f"成交量: {latest['Volume']:.0f}")
            print(f"量比: {latest['Volume_Ratio']:.2f} - {vol_status}")

        if pd.notna(latest['OBV']):
            obv_trend = "上升" if latest['OBV'] > latest['OBV_MA'] else "下降"
            print(f"OBV趋势: {obv_trend}")

        if pd.notna(latest['MFI']):
            mfi_status = "超买" if latest['MFI'] > 80 else ("超卖" if latest['MFI'] < 20 else "正常")
            print(f"MFI(14): {latest['MFI']:.2f} - {mfi_status}")

        # 6. 支撑阻力位
        print("\n【支撑阻力位】")
        print("-"*50)

        if pd.notna(latest['Support']) and pd.notna(latest['Resistance']):
            print(f"20日支撑位: {latest['Support']:.2f}")
            print(f"20日阻力位: {latest['Resistance']:.2f}")

        if pd.notna(latest['S1']) and pd.notna(latest['R1']):
            print(f"枢轴点: {latest['Pivot']:.2f}")
            print(f"第一支撑: {latest['S1']:.2f}, 第二支撑: {latest['S2']:.2f}")
            print(f"第一阻力: {latest['R1']:.2f}, 第二阻力: {latest['R2']:.2f}")

        # 7. 最近的交易信号
        print("\n【最近交易信号】")
        print("-"*50)

        recent_df = df.tail(recent_days)

        # 买入信号
        buy_signals = recent_df[recent_df['Buy_Signals'] != '']
        if not buy_signals.empty:
            print("\n买入信号:")
            for idx, row in buy_signals.tail(5).iterrows():
                strength = "强" if row['Signal_Strength'] >= 3 else ("中" if row['Signal_Strength'] >= 2 else "弱")
                print(f"  {row['trade_date']}: [{strength}] {row['Buy_Signals']}")

        # 卖出信号
        sell_signals = recent_df[recent_df['Sell_Signals'] != '']
        if not sell_signals.empty:
            print("\n卖出信号:")
            for idx, row in sell_signals.tail(5).iterrows():
                strength = "强" if abs(row['Signal_Strength']) >= 3 else ("中" if abs(row['Signal_Strength']) >= 2 else "弱")
                print(f"  {row['trade_date']}: [{strength}] {row['Sell_Signals']}")

        # 8. 背离信号
        print("\n【背离信号】")
        print("-"*50)

        divergence_df = recent_df[(recent_df['RSI_Divergence'] != '') |
                                  (recent_df['MACD_Divergence'] != '') |
                                  (recent_df['OBV_Divergence'] != '')]

        if not divergence_df.empty:
            for idx, row in divergence_df.tail(3).iterrows():
                divergences = []
                if row['RSI_Divergence']:
                    divergences.append(f"RSI{row['RSI_Divergence']}")
                if row['MACD_Divergence']:
                    divergences.append(f"MACD{row['MACD_Divergence']}")
                if row['OBV_Divergence']:
                    divergences.append(f"OBV{row['OBV_Divergence']}")

                if divergences:
                    print(f"  {row['trade_date']}: {', '.join(divergences)}")
        else:
            print("  无背离信号")

        # 9. 技术面打分统计
        if 'Total_Score' in df.columns:
            print("\n【技术面打分统计】")
            print("-"*50)

            # 最近N天的打分趋势
            recent_scores = recent_df['Total_Score'].dropna()
            if not recent_scores.empty:
                avg_score = recent_scores.mean()
                max_score = recent_scores.max()
                min_score = recent_scores.min()
                latest_score = latest['Total_Score'] if pd.notna(latest['Total_Score']) else 0

                print(f"最新打分: {latest_score:+d}")
                print(f"平均打分: {avg_score:+.1f}")
                print(f"最高打分: {max_score:+d} (日期: {recent_df[recent_df['Total_Score'] == max_score]['trade_date'].iloc[0]})")
                print(f"最低打分: {min_score:+d} (日期: {recent_df[recent_df['Total_Score'] == min_score]['trade_date'].iloc[0]})")

                # 打分趋势判断
                if len(recent_scores) >= 3:
                    trend_last3 = recent_scores.tail(3).mean()
                    trend_prev3 = recent_scores.tail(6).head(3).mean() if len(recent_scores) >= 6 else trend_last3
                    if trend_last3 > trend_prev3 + 1:
                        trend = "上升"
                    elif trend_last3 < trend_prev3 - 1:
                        trend = "下降"
                    else:
                        trend = "横盘"
                    print(f"打分趋势: {trend}")

                # 分项得分统计
                if 'Trend_Score' in latest and pd.notna(latest['Trend_Score']):
                    print(f"\n最新分项得分:")
                    print(f"  趋势类: {latest['Trend_Score']:+d}")
                    print(f"  动量类: {latest.get('Momentum_Score', 0):+d}")
                    print(f"  波动类: {latest.get('Volatility_Score', 0):+d}")
                    print(f"  成交量类: {latest.get('Volume_Score', 0):+d}")
                    print(f"  形态类: {latest.get('Pattern_Score', 0):+d}")

        # 10. 综合分析建议
        print("\n【综合分析建议】")
        print("-"*50)

        # 使用Total_Score或Signal_Strength判断
        if 'Total_Score' in latest and pd.notna(latest['Total_Score']):
            score = latest['Total_Score']
            score_type = "技术面综合打分"
        else:
            score = latest.get('Signal_Strength', 0)
            score_type = "信号强度"

        if score >= 8:
            suggestion = "强烈看多"
            action = "技术面强烈看多，可以考虑积极建仓"
        elif score >= 5:
            suggestion = "看多"
            action = "技术面看多，可以适当买入"
        elif score >= 2:
            suggestion = "偏多"
            action = "技术面偏多，可以持股观望"
        elif score >= -1:
            suggestion = "中性"
            action = "技术面中性，观望为主"
        elif score >= -4:
            suggestion = "偏空"
            action = "技术面偏空，谨慎持股"
        elif score >= -7:
            suggestion = "看空"
            action = "技术面看空，建议减仓"
        else:
            suggestion = "强烈看空"
            action = "技术面强烈看空，建议清仓观望"

        print(f"{score_type}: {score:+d}")
        print(f"综合判断: {suggestion}")
        print(f"操作建议: {action}")

        print("\n" + "="*100)

    def print_daily_indicators(self, df, ts_code, recent_days=None):
        """
        打印每日详细指标数据
        类似于 technical_analysis.py 的逐日输出格式
        """
        if df is None or df.empty:
            logger.warning("无数据可分析")
            return

        # 确定要显示的天数
        if recent_days is None:
            recent_days = len(df)

        display_df = df.tail(recent_days).copy()

        print("\n" + "="*100)
        print(f"每日技术指标详细数据 - {ts_code}")
        print(f"日期范围: {display_df.iloc[0]['trade_date']} 至 {display_df.iloc[-1]['trade_date']}")
        print(f"共 {len(display_df)} 个交易日")
        print("="*100)

        for idx, row in display_df.iterrows():
            print("\n" + "="*80)
            print(f"【日期: {row['trade_date']}】")
            print( "="*80+"\n")
            print("-"*80)

            # 价格数据
            print("价格数据:")
            print(f"  开盘: {row['Open']:.2f}   最高: {row['High']:.2f}   最低: {row['Low']:.2f}   收盘: {row['Close']:.2f}")

            # 计算日涨跌幅
            if idx > 0:
                prev_close = df.loc[idx-1, 'Close']
                pct_change = ((row['Close'] - prev_close) / prev_close * 100)
                print(f"  日涨跌幅: {pct_change:+.2f}%")

            # 成交量
            print(f"\n成交量指标:")
            print(f"  成交量: {row['Volume']:.0f}")
            if pd.notna(row.get('Volume_Ratio')):
                vol_status = "放量" if row['Volume_Ratio'] > 1.5 else ("缩量" if row['Volume_Ratio'] < 0.7 else "正常")
                print(f"  量比: {row['Volume_Ratio']:.2f} ({vol_status})")

            # 趋势指标 - 均线
            print(f"\n趋势指标:")
            ma_values = []
            for ma in ['MA5', 'MA10', 'MA20', 'MA60']:
                if ma in row and pd.notna(row[ma]):
                    ma_values.append(f"{ma}={row[ma]:.2f}")
            if ma_values:
                print(f"  均线: {', '.join(ma_values)}")

            # MACD
            if 'MACD_DIF' in row and pd.notna(row['MACD_DIF']):
                macd_position = "多头" if row['MACD_DIF'] > row.get('MACD_DEA', 0) else "空头"
                macd_trend = "零轴上" if row['MACD_DIF'] > 0 else "零轴下"
                print(f"  MACD: DIF={row['MACD_DIF']:.4f}, DEA={row.get('MACD_DEA', 0):.4f}, 柱={row.get('MACD_Histogram', 0):.4f}")
                print(f"        状态: {macd_position}, {macd_trend}")

            # SAR
            if 'SAR_Long' in row and pd.notna(row['SAR_Long']):
                sar_signal = "多头" if pd.notna(row['SAR_Long']) else "空头"
                sar_value = row['SAR_Long'] if pd.notna(row['SAR_Long']) else row.get('SAR_Short', '')
                if pd.notna(sar_value):
                    print(f"  SAR: {sar_value:.2f} ({sar_signal})")

            # 动量指标
            print(f"\n动量指标:")
            if 'RSI' in row and pd.notna(row['RSI']):
                rsi_status = "超买" if row['RSI'] > 70 else ("超卖" if row['RSI'] < 30 else "正常")
                print(f"  RSI(14): {row['RSI']:.2f} ({rsi_status})")

            if 'K' in row and pd.notna(row['K']):
                kdj_status = "超买" if row.get('D', 0) > 80 else ("超卖" if row.get('D', 0) < 20 else "正常")
                print(f"  KDJ: K={row['K']:.2f}, D={row.get('D', 0):.2f}, J={row.get('J', 0):.2f} ({kdj_status})")

            if 'CCI' in row and pd.notna(row['CCI']):
                cci_status = "超买" if row['CCI'] > 100 else ("超卖" if row['CCI'] < -100 else "正常")
                print(f"  CCI(14): {row['CCI']:.2f} ({cci_status})")

            # 波动指标
            print(f"\n波动指标:")
            if 'BOLL_Upper' in row and pd.notna(row['BOLL_Upper']):
                boll_position = "上轨附近" if row['Close'] > row.get('BOLL_Middle', 0) else "下轨附近"
                print(f"  布林带: 上轨={row['BOLL_Upper']:.2f}, 中轨={row.get('BOLL_Middle', 0):.2f}, 下轨={row.get('BOLL_Lower', 0):.2f}")
                print(f"         带宽={row.get('BOLL_Bandwidth', 0):.4f}, 价格位置: {boll_position}")

            if 'ATR' in row and pd.notna(row['ATR']):
                print(f"  ATR(14): {row['ATR']:.2f}")

            # 成交量类指标
            print(f"\n资金流指标:")
            if 'OBV' in row and pd.notna(row['OBV']):
                obv_trend = "上升" if row['OBV'] > row.get('OBV_MA', row['OBV']) else "下降"
                print(f"  OBV: {row['OBV']:.0f} (趋势: {obv_trend})")

            if 'MFI' in row and pd.notna(row['MFI']):
                mfi_status = "超买" if row['MFI'] > 80 else ("超卖" if row['MFI'] < 20 else "正常")
                print(f"  MFI(14): {row['MFI']:.2f} ({mfi_status})")

            if 'VWAP' in row and pd.notna(row['VWAP']):
                vwap_position = "上方" if row['Close'] > row['VWAP'] else "下方"
                print(f"  VWAP: {row['VWAP']:.2f} (价格在VWAP{vwap_position})")

            # 支撑阻力
            if 'Support' in row and pd.notna(row['Support']):
                print(f"\n支撑阻力:")
                print(f"  20日支撑: {row['Support']:.2f}, 20日阻力: {row.get('Resistance', 0):.2f}")
                if 'Pivot' in row and pd.notna(row['Pivot']):
                    print(f"  枢轴点: {row['Pivot']:.2f}")
                    print(f"  S1={row.get('S1', 0):.2f}, S2={row.get('S2', 0):.2f}, R1={row.get('R1', 0):.2f}, R2={row.get('R2', 0):.2f}")

            # 交易信号
            if 'Buy_Signals' in row and row['Buy_Signals']:
                print(f"\n★ 买入信号: {row['Buy_Signals']}")
            if 'Sell_Signals' in row and row['Sell_Signals']:
                print(f"\n☆ 卖出信号: {row['Sell_Signals']}")
            if 'Signal_Strength' in row and row['Signal_Strength'] != 0:
                strength_desc = "强" if abs(row['Signal_Strength']) >= 3 else ("中" if abs(row['Signal_Strength']) >= 2 else "弱")
                signal_type = "看多" if row['Signal_Strength'] > 0 else "看空"
                print(f"  信号强度: {row['Signal_Strength']} ({strength_desc}{signal_type})")

            # 背离信号
            divergences = []
            if 'RSI_Divergence' in row and row['RSI_Divergence']:
                divergences.append(f"RSI{row['RSI_Divergence']}")
            if 'MACD_Divergence' in row and row['MACD_Divergence']:
                divergences.append(f"MACD{row['MACD_Divergence']}")
            if 'OBV_Divergence' in row and row['OBV_Divergence']:
                divergences.append(f"OBV{row['OBV_Divergence']}")

            if divergences:
                print(f"\n◆ 背离信号: {', '.join(divergences)}")

            # 技术面综合打分
            if 'Total_Score' in row and pd.notna(row['Total_Score']) and row['Total_Score'] != 0:
                print(f"\n【技术面综合打分】")
                print("-"*50)

                # 判断打分等级
                total_score = row['Total_Score']
                if total_score >= 8:
                    score_level = "强烈看多"
                elif total_score >= 5:
                    score_level = "看多"
                elif total_score >= 2:
                    score_level = "偏多"
                elif total_score >= -1:
                    score_level = "中性"
                elif total_score >= -4:
                    score_level = "偏空"
                elif total_score >= -7:
                    score_level = "看空"
                else:
                    score_level = "强烈看空"

                print(f"总分: {total_score:+d} ({score_level})")
                print(f"\n分项得分:")

                # 趋势类
                if 'Trend_Score' in row and pd.notna(row['Trend_Score']) and row['Trend_Score'] != 0:
                    print(f"  趋势类: {row['Trend_Score']:+d}")

                # 动量类
                if 'Momentum_Score' in row and pd.notna(row['Momentum_Score']) and row['Momentum_Score'] != 0:
                    print(f"  动量类: {row['Momentum_Score']:+d}")

                # 波动类
                if 'Volatility_Score' in row and pd.notna(row['Volatility_Score']) and row['Volatility_Score'] != 0:
                    print(f"  波动类: {row['Volatility_Score']:+d}")

                # 成交量类
                if 'Volume_Score' in row and pd.notna(row['Volume_Score']) and row['Volume_Score'] != 0:
                    print(f"  成交量类: {row['Volume_Score']:+d}")

                # 形态类
                if 'Pattern_Score' in row and pd.notna(row['Pattern_Score']) and row['Pattern_Score'] != 0:
                    print(f"  形态类: {row['Pattern_Score']:+d}")

                # 得分明细
                if 'Score_Details' in row and row['Score_Details']:
                    print(f"\n得分明细:")
                    # 将明细按分号分割并格式化输出
                    details = row['Score_Details'].split('; ')
                    for detail in details[:10]:  # 最多显示10个明细
                        print(f"  • {detail}")
                    if len(details) > 10:
                        print(f"  ... 还有{len(details)-10}项")

        print("\n" + "="*100)
        print("每日指标数据输出完成")
        print("="*100)

    def save_to_csv(self, df, filename):
        """
        保存分析结果到CSV
        """
        if df is None or df.empty:
            return

        # 选择要保存的列
        save_columns = [
            'trade_date', 'Open', 'High', 'Low', 'Close', 'Volume',
            'MA5', 'MA10', 'MA20', 'MA60',
            'MACD_DIF', 'MACD_DEA', 'MACD_Histogram',
            'RSI', 'K', 'D', 'J', 'CCI',
            'BOLL_Upper', 'BOLL_Middle', 'BOLL_Lower',
            'Volume_Ratio', 'OBV', 'MFI', 'VWAP',
            'Support', 'Resistance',
            'is_hammer', 'is_shooting_star', 'is_doji', 'is_big_bullish', 'is_big_bearish',
            'Buy_Signals', 'Sell_Signals', 'Signal_Strength',
            'Trend_Score', 'Momentum_Score', 'Volatility_Score',
            'Volume_Score', 'Pattern_Score', 'Total_Score', 'Score_Details'
        ]

        # 仅保留存在的列
        save_columns = [col for col in save_columns if col in df.columns]

        df[save_columns].to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"分析结果已保存到 {filename}")


def main():
    parser = argparse.ArgumentParser(description='高级股票技术指标分析工具')
    parser.add_argument('--code', type=str, help='股票代码，如 000001.SZ 或 000001.SZ#平安银行')
    parser.add_argument('--start', type=str, help='开始日期 YYYYMMDD')
    parser.add_argument('--end', type=str, help='结束日期 YYYYMMDD，默认今天')
    parser.add_argument('--days', type=int, default=120, help='分析最近N天的数据，默认120天')
    parser.add_argument('--output', type=str, help='保存结果到CSV文件')
    parser.add_argument('--report_days', type=int, default=20, help='报告中显示最近N天的信号，默认20天')
    parser.add_argument('--pool', type=str, help='从股票池文件读取股票代码进行批量分析')
    parser.add_argument('--batch', action='store_true', help='批量分析模式，分析股票池中的所有股票')
    parser.add_argument('--use-local-db', action='store_true', help='使用本地数据库而非在线Tushare（需要先初始化数据库）')

    args = parser.parse_args()

    # 检查是否提供了股票代码或股票池文件
    if not args.code and not args.pool:
        logger.error("请提供股票代码 (--code) 或股票池文件 (--pool)")
        parser.print_help()
        sys.exit(1)

    # 处理股票池文件
    stock_codes = []

    if args.pool and os.path.exists(args.pool):
        with open(args.pool, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                # 去除行内注释并获取股票代码
                if '#' in line:
                    code = line.split('#')[0].strip()
                else:
                    code = line.strip()
                if code:
                    stock_codes.append(code)

        if not stock_codes:
            logger.error("股票池文件中没有有效的股票代码")
            sys.exit(1)

        if not args.batch:
            # 非批量模式，只取第一个股票
            args.code = stock_codes[0]
            logger.info(f"从股票池文件读取第一个股票代码: {args.code}")
            stock_codes = [args.code]
    elif args.code:
        # 处理带注释的股票代码
        if '#' in args.code:
            args.code = args.code.split('#')[0].strip()
        stock_codes = [args.code]

    # 处理日期
    if not args.end:
        args.end = datetime.now().strftime('%Y%m%d')

    if not args.start:
        start_dt = datetime.now() - timedelta(days=args.days)
        args.start = start_dt.strftime('%Y%m%d')

    # 创建分析器
    analyzer = AdvancedTechnicalAnalyzer(use_local_db=args.use_local_db)

    # 批量分析或单个分析
    analysis_results = []

    for stock_code in stock_codes:
        # 设置输出重定向到文件
        log_filename = os.path.join(OUTPUT_DIR, f'advanced_analysis_{stock_code}.txt')
        tee = TeeOutput(log_filename)
        sys.stdout = tee

        # 同时设置日志到文件
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.addHandler(file_handler)

        try:
            logger.info(f"\n{'='*50}")
            logger.info(f"开始分析股票: {stock_code}")
            logger.info(f"{'='*50}")

            # 获取数据
            df = analyzer.fetch_data(stock_code, args.start, args.end)

            if df is not None:
                # 计算所有指标
                df = analyzer.calculate_trend_indicators(df)
                df = analyzer.calculate_momentum_indicators(df)
                df = analyzer.calculate_volatility_indicators(df)
                df = analyzer.calculate_volume_indicators(df)
                df = analyzer.calculate_support_resistance(df)
                df = analyzer.identify_candle_patterns(df)  # K线形态识别
                df = analyzer.identify_signals(df)
                df = analyzer.identify_divergence(df)

                # 显示汇总报告
                analyzer.print_comprehensive_report(df, stock_code, recent_days=args.report_days)

                # 显示每日详细指标（新增）
                analyzer.print_daily_indicators(df, stock_code, recent_days=args.report_days)

                # 保存结果
                if args.output:
                    output_file = os.path.join(OUTPUT_DIR, args.output)
                else:
                    output_file = os.path.join(OUTPUT_DIR, f'advanced_analysis_{stock_code}.csv')

                analyzer.save_to_csv(df, output_file)
                print(f"\n详细数据已保存到: {output_file}")
                print(f"分析日志已保存到: {log_filename}")

            # 记录分析结果（用于批量分析汇总）
            if len(stock_codes) > 1 and not df.empty:
                latest = df.iloc[-1]

                # 获取打分等级
                if 'Total_Score' in latest and pd.notna(latest['Total_Score']):
                    total_score = latest['Total_Score']
                    if total_score >= 8:
                        score_level = "强烈看多"
                    elif total_score >= 5:
                        score_level = "看多"
                    elif total_score >= 2:
                        score_level = "偏多"
                    elif total_score >= -1:
                        score_level = "中性"
                    elif total_score >= -4:
                        score_level = "偏空"
                    elif total_score >= -7:
                        score_level = "看空"
                    else:
                        score_level = "强烈看空"
                else:
                    total_score = 0
                    score_level = "未评分"

                result = {
                    '股票代码': stock_code,
                    '最新价': latest['Close'],
                    '综合打分': total_score,
                    '打分等级': score_level,
                    'RSI': f"{latest['RSI']:.1f}" if pd.notna(latest['RSI']) else '',
                    'MACD': '多头' if pd.notna(latest['MACD_DIF']) and pd.notna(latest['MACD_DEA']) and latest['MACD_DIF'] > latest['MACD_DEA'] else '空头',
                    'KDJ_D': f"{latest['D']:.1f}" if pd.notna(latest['D']) else '',
                    'MFI': f"{latest['MFI']:.1f}" if pd.notna(latest['MFI']) else '',
                    '最新信号': latest['Buy_Signals'][:20] if latest['Buy_Signals'] else (latest['Sell_Signals'][:20] if latest['Sell_Signals'] else '无')
                }
                analysis_results.append(result)

            else:
                logger.error(f"无法获取 {stock_code} 的数据")

        finally:
            # 恢复标准输出
            sys.stdout = tee.terminal
            tee.close()
            # 移除文件处理器，防止重复写入
            logger.removeHandler(file_handler)

    # 如果是批量分析，输出汇总报告
    if len(stock_codes) > 1 and analysis_results:
        print("\n" + "="*100)
        print("批量分析汇总报告（按打分排序）")
        print("="*100)

        summary_df = pd.DataFrame(analysis_results)

        # 按综合打分降序排序
        summary_df = summary_df.sort_values('综合打分', ascending=False)

        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 30)

        print(summary_df.to_string(index=False))

        # 打分统计
        print("\n" + "-"*100)
        print("打分统计：")
        high_score_count = len(summary_df[summary_df['综合打分'] >= 8])
        buy_count = len(summary_df[summary_df['综合打分'] >= 2])
        sell_count = len(summary_df[summary_df['综合打分'] <= -2])
        low_score_count = len(summary_df[summary_df['综合打分'] <= -8])

        if high_score_count > 0:
            print(f"★ 强烈看多股票（打分≥8）: {high_score_count}个")
            high_stocks = summary_df[summary_df['综合打分'] >= 8]['股票代码'].tolist()
            print(f"   {', '.join(high_stocks)}")

        print(f"◆ 看多股票（打分≥2）: {buy_count}个")
        print(f"◇ 看空股票（打分≤-2）: {sell_count}个")

        if low_score_count > 0:
            print(f"☆ 强烈看空股票（打分≤-8）: {low_score_count}个")
            low_stocks = summary_df[summary_df['综合打分'] <= -8]['股票代码'].tolist()
            print(f"   {', '.join(low_stocks)}")

        print(f"\n平均打分: {summary_df['综合打分'].mean():.1f}")
        print(f"最高打分: {summary_df['综合打分'].max()} ({summary_df.iloc[0]['股票代码']})")
        print(f"最低打分: {summary_df['综合打分'].min()} ({summary_df.iloc[-1]['股票代码']})")

        # 保存汇总报告
        summary_file = os.path.join(OUTPUT_DIR, 'batch_analysis_summary.csv')
        summary_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
        print(f"\n批量分析汇总已保存到: {summary_file}")


if __name__ == '__main__':
    main()