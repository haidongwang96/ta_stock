#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票技术形态检测工具
输入股票池文件，检测每只股票最新一日的技术形态，并写入数据库
"""

import os
import sys
import logging
import argparse
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd
import pandas_ta as ta
import numpy as np

warnings.filterwarnings('ignore')

# ==================== 路径配置 ====================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from analysis.year_stats import calculate_year_stats, get_year_start_date

try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False

from database.db_manager import StockDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ==================== 分析器 ====================

class StockAnalyzer:

    PARAMS = {
        'ma_periods': [5, 10, 20, 60],
        'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
        'rsi_period': 14,
        'kdj_period': 9,
        'cci_period': 14,
        'boll_period': 20, 'boll_std': 2,
        'atr_period': 14,
        'obv_ma_period': 20,
        'mfi_period': 14,
        'sar_af': 0.02, 'sar_max_af': 0.2,
    }

    def __init__(self, use_local_db=True, suppress_logs=False):
        self.use_local_db = use_local_db and LOCAL_DB_AVAILABLE
        self.suppress_logs = suppress_logs

        if not self.use_local_db:
            raise ImportError("未安装本地数据库查询模块，无法运行 stock_analysis.py")

        if suppress_logs:
            logging.getLogger('database.db_manager').setLevel(logging.WARNING)
            logging.getLogger('database.query_helper').setLevel(logging.WARNING)
        self.local_query = StockDataQuery()

    # ---------- 数据获取 ----------

    def fetch_data(self, stock_code, start_date, end_date):
        try:
            df = self.local_query.daily(stock_code, start_date, end_date)

            if df is None or df.empty:
                return None

            df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
            df.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'vol': 'Volume'
            }, inplace=True)
            return df
        except Exception as e:
            if not self.suppress_logs:
                logger.error(f"获取 {stock_code} 数据失败: {e}")
            return None

    # ---------- 指标计算 ----------

    def calculate_indicators(self, df):
        p = self.PARAMS

        for period in p['ma_periods']:
            df[f'MA{period}'] = ta.sma(df['Close'], length=period)

        if len(df) >= p['macd_slow'] + p['macd_signal']:
            macd = ta.macd(df['Close'],
                           fast=p['macd_fast'], slow=p['macd_slow'], signal=p['macd_signal'])
            if macd is not None and not macd.empty:
                df['MACD_DIF']       = macd.iloc[:, 0]
                df['MACD_DEA']       = macd.iloc[:, 1]
                df['MACD_Histogram'] = macd.iloc[:, 2]

        sar = ta.psar(df['High'], df['Low'], df['Close'],
                      af=p['sar_af'], max_af=p['sar_max_af'])
        if sar is not None and not sar.empty:
            df['SAR'] = sar.iloc[:, 1]

        df['RSI'] = ta.rsi(df['Close'], length=p['rsi_period'])

        stoch = ta.stoch(df['High'], df['Low'], df['Close'],
                         k=p['kdj_period'], d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            df['K'] = stoch.iloc[:, 0]
            df['D'] = stoch.iloc[:, 1]
            df['J'] = 3 * df['K'] - 2 * df['D']

        df['CCI'] = ta.cci(df['High'], df['Low'], df['Close'], length=p['cci_period'])

        if len(df) >= p['boll_period']:
            bbands = ta.bbands(df['Close'], length=p['boll_period'], std=p['boll_std'])
            if bbands is not None and not bbands.empty:
                df['BOLL_Lower']     = bbands.iloc[:, 0]
                df['BOLL_Middle']    = bbands.iloc[:, 1]
                df['BOLL_Upper']     = bbands.iloc[:, 2]
                df['BOLL_Bandwidth'] = bbands.iloc[:, 3]

        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=p['atr_period'])

        df['Volume_MA5']   = ta.sma(df['Volume'], length=5)
        df['Volume_MA20']  = ta.sma(df['Volume'], length=20)
        df['Volume_Ratio'] = df['Volume'] / (df['Volume_MA5'] + 1e-9)
        df['OBV']          = ta.obv(df['Close'], df['Volume'])
        df['OBV_MA']       = ta.sma(df['OBV'], length=p['obv_ma_period'])
        df['MFI']          = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'],
                                    length=p['mfi_period'])

        if 'trade_date' in df.columns:
            df_temp = df.set_index('trade_date', drop=False)
            try:
                df_temp['VWAP'] = ta.vwap(df_temp['High'], df_temp['Low'],
                                          df_temp['Close'], df_temp['Volume'])
                df['VWAP'] = df_temp['VWAP'].values
            except Exception:
                df['VWAP'] = np.nan

        df['Support']    = df['Low'].rolling(window=20, min_periods=1).min()
        df['Resistance'] = df['High'].rolling(window=20, min_periods=1).max()

        # K 线结构
        df['body']         = abs(df['Close'] - df['Open'])
        df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['total_range']  = df['High'] - df['Low']
        df['body_ratio']   = (df['body'] / df['total_range'].replace(0, np.nan)).fillna(0)

        df['is_hammer']        = ((df['lower_shadow'] > df['body'] * 2) &
                                   (df['upper_shadow'] < df['body'] * 0.3) &
                                   (df['body_ratio'] > 0.1))
        df['is_shooting_star'] = ((df['upper_shadow'] > df['body'] * 2) &
                                   (df['lower_shadow'] < df['body'] * 0.3) &
                                   (df['body_ratio'] > 0.1))
        df['is_doji']          = ((df['body_ratio'] < 0.05) &
                                   (df['upper_shadow'] > 0) & (df['lower_shadow'] > 0))
        df['is_big_bullish']   = (df['Close'] > df['Open']) & (df['body_ratio'] > 0.7)
        df['is_big_bearish']   = (df['Close'] < df['Open']) & (df['body_ratio'] > 0.7)

        # 背离（对所有行）
        df = self._identify_divergence(df)

        return df

    def _identify_divergence(self, df, lookback=5):
        df = df.reset_index(drop=True)
        df['RSI_Divergence']  = ''
        df['MACD_Divergence'] = ''
        for i in range(lookback * 2, len(df)):
            if 'RSI' in df.columns and pd.notna(df.loc[i, 'RSI']):
                rp, rr = df.loc[i - lookback:i, 'Close'], df.loc[i - lookback:i, 'RSI']
                if df.loc[i, 'Close'] > rp.max() and df.loc[i, 'RSI'] < rr.max():
                    df.loc[i, 'RSI_Divergence'] = '顶背离'
                elif df.loc[i, 'Close'] < rp.min() and df.loc[i, 'RSI'] > rr.min():
                    df.loc[i, 'RSI_Divergence'] = '底背离'
            if 'MACD_Histogram' in df.columns and pd.notna(df.loc[i, 'MACD_Histogram']):
                rp, rm = df.loc[i - lookback:i, 'Close'], df.loc[i - lookback:i, 'MACD_Histogram']
                if df.loc[i, 'Close'] > rp.max() and df.loc[i, 'MACD_Histogram'] < rm.max():
                    df.loc[i, 'MACD_Divergence'] = '顶背离'
                elif df.loc[i, 'Close'] < rp.min() and df.loc[i, 'MACD_Histogram'] > rm.min():
                    df.loc[i, 'MACD_Divergence'] = '底背离'
        return df

    # ---------- 形态检测（最新一日）----------

    def detect_patterns(self, df):
        """检测最新一日所有技术形态，返回按类别分组的 dict"""
        if df is None or df.empty or len(df) < 2:
            return {}

        df = df.reset_index(drop=True)
        i  = len(df) - 1

        def has(col):   return col in df.columns
        def notna(col): return has(col) and pd.notna(df.loc[i, col])
        def prev_notna(col): return has(col) and i > 0 and pd.notna(df.loc[i - 1, col])

        result = {
            'trend':      [],
            'momentum':   [],
            'volatility': [],
            'volume':     [],
            'candle':     [],
            'divergence': [],
            'signals':    [],   # 多指标组合信号
        }

        # ---- 趋势：MACD ----
        if notna('MACD_DIF') and notna('MACD_DEA') and prev_notna('MACD_DIF'):
            dif,  dea  = df.loc[i, 'MACD_DIF'],     df.loc[i, 'MACD_DEA']
            pdif, pdea = df.loc[i - 1, 'MACD_DIF'], df.loc[i - 1, 'MACD_DEA']
            if pdif <= pdea and dif > dea:
                result['trend'].append('MACD低位金叉' if dif < 0 else 'MACD金叉')
            elif pdif >= pdea and dif < dea:
                result['trend'].append('MACD高位死叉' if dif > 0 else 'MACD死叉')
            elif dif > dea:
                result['trend'].append('MACD多头')
            else:
                result['trend'].append('MACD空头')

            if notna('MACD_Histogram') and prev_notna('MACD_Histogram'):
                h, ph = df.loc[i, 'MACD_Histogram'], df.loc[i - 1, 'MACD_Histogram']
                if   h > 0 and h > ph: result['trend'].append('MACD红柱扩张')
                elif h > 0 and h < ph: result['trend'].append('MACD红柱收缩')
                elif h < 0 and h < ph: result['trend'].append('MACD绿柱扩张')
                elif h < 0 and h > ph: result['trend'].append('MACD绿柱收缩')

        # ---- 趋势：SAR ----
        if notna('SAR') and prev_notna('SAR'):
            cur_bull = df.loc[i, 'Close'] > df.loc[i, 'SAR']
            prv_bull = df.loc[i - 1, 'Close'] > df.loc[i - 1, 'SAR']
            if cur_bull and not prv_bull:   result['trend'].append('SAR空转多')
            elif not cur_bull and prv_bull: result['trend'].append('SAR多转空')
            elif cur_bull:                  result['trend'].append('SAR多头')
            else:                           result['trend'].append('SAR空头')

        # ---- 趋势：均线 ----
        if all(notna(c) for c in ['MA5', 'MA10', 'MA20']):
            cl = df.loc[i, 'Close']
            ma5, ma10, ma20 = df.loc[i, 'MA5'], df.loc[i, 'MA10'], df.loc[i, 'MA20']
            if cl > ma5 > ma10 > ma20:   result['trend'].append('均线多头排列')
            elif cl < ma5 < ma10 < ma20: result['trend'].append('均线空头排列')
            elif cl > ma5:               result['trend'].append('站上MA5')
            else:                        result['trend'].append('跌破MA5')
            if notna('MA60'):
                if ma20 > df.loc[i, 'MA60']: result['trend'].append('MA20在MA60上方')
                else:                         result['trend'].append('MA20在MA60下方')

        # ---- 动量：RSI ----
        if notna('RSI'):
            rsi = df.loc[i, 'RSI']
            if   rsi < 20: result['momentum'].append('RSI严重超卖')
            elif rsi < 30: result['momentum'].append('RSI超卖')
            elif rsi > 80: result['momentum'].append('RSI严重超买')
            elif rsi > 70: result['momentum'].append('RSI超买')
            if prev_notna('RSI'):
                prv = df.loc[i - 1, 'RSI']
                if prv <= 50 < rsi:   result['momentum'].append('RSI突破中轴')
                elif prv >= 50 > rsi: result['momentum'].append('RSI跌破中轴')

        # ---- 动量：KDJ ----
        if all(notna(c) for c in ['K', 'D', 'J']):
            k, d, j = df.loc[i, 'K'], df.loc[i, 'D'], df.loc[i, 'J']
            if i > 0 and all(pd.notna(df.loc[i - 1, c]) for c in ['K', 'D']):
                pk, pd_ = df.loc[i - 1, 'K'], df.loc[i - 1, 'D']
                if pk <= pd_ and k > d:
                    result['momentum'].append('KDJ低位金叉' if d < 20 else 'KDJ金叉')
                elif pk >= pd_ and k < d:
                    result['momentum'].append('KDJ高位死叉' if d > 80 else 'KDJ死叉')
            if   j < 0:   result['momentum'].append('J值极度超卖')
            elif j > 100: result['momentum'].append('J值极度超买')

        # ---- 动量：CCI ----
        if notna('CCI'):
            cci = df.loc[i, 'CCI']
            if prev_notna('CCI'):
                pcci = df.loc[i - 1, 'CCI']
                if pcci <= -100 < cci:  result['momentum'].append('CCI脱离超卖区')
                elif pcci >= 100 > cci: result['momentum'].append('CCI脱离超买区')
            if   cci > 100:  result['momentum'].append('CCI强势')
            elif cci < -100: result['momentum'].append('CCI弱势')

        # ---- 波动：布林带 ----
        if all(notna(c) for c in ['BOLL_Upper', 'BOLL_Lower']):
            cl = df.loc[i, 'Close']
            bu, bl = df.loc[i, 'BOLL_Upper'], df.loc[i, 'BOLL_Lower']
            if   cl > bu:           result['volatility'].append('突破布林上轨')
            elif cl < bl:           result['volatility'].append('突破布林下轨')
            elif cl >= bu * 0.98:   result['volatility'].append('触及布林上轨')
            elif cl <= bl * 1.02:   result['volatility'].append('触及布林下轨')

            if notna('BOLL_Bandwidth') and prev_notna('BOLL_Bandwidth'):
                bw, pbw = df.loc[i, 'BOLL_Bandwidth'], df.loc[i - 1, 'BOLL_Bandwidth']
                if bw > pbw:
                    result['volatility'].append(
                        '布林带开口上涨' if df.loc[i, 'Close'] > df.loc[i - 1, 'Close']
                        else '布林带开口下跌'
                    )
                else:
                    result['volatility'].append('布林带收口')

        # ---- 波动：ATR ----
        if notna('ATR') and i >= 20:
            atr_mean = df.loc[max(0, i - 20):i, 'ATR'].mean()
            if df.loc[i, 'ATR'] > atr_mean * 1.5 and i > 0:
                result['volatility'].append(
                    'ATR放大+上涨' if df.loc[i, 'Close'] > df.loc[i - 1, 'Close']
                    else 'ATR放大+下跌'
                )

        # ---- 成交量：VWAP ----
        if notna('VWAP'):
            cl, vw = df.loc[i, 'Close'], df.loc[i, 'VWAP']
            if   cl > vw * 1.02:  result['volume'].append('价格大幅高于VWAP')
            elif cl > vw:         result['volume'].append('价格高于VWAP')
            elif cl < vw * 0.98:  result['volume'].append('价格大幅低于VWAP')
            elif cl < vw:         result['volume'].append('价格低于VWAP')

        # ---- 成交量：MFI ----
        if notna('MFI'):
            mfi = df.loc[i, 'MFI']
            if   mfi < 10:  result['volume'].append('MFI严重超卖')
            elif mfi < 20:  result['volume'].append('MFI超卖')
            elif mfi > 90:  result['volume'].append('MFI严重超买')
            elif mfi > 80:  result['volume'].append('MFI超买')

        # ---- 成交量：OBV ----
        if all(notna(c) for c in ['OBV', 'OBV_MA']):
            result['volume'].append(
                'OBV上升趋势' if df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA'] else 'OBV下降趋势'
            )

        # ---- 成交量：量比 ----
        if notna('Volume_Ratio') and i > 0:
            vr  = df.loc[i, 'Volume_Ratio']
            up  = df.loc[i, 'Close'] > df.loc[i - 1, 'Close']
            if vr > 1.5:
                result['volume'].append('放量上涨' if up else '放量下跌')
            elif vr < 0.7:
                result['volume'].append('缩量上涨' if up else '缩量下跌')

        # ---- K 线形态 ----
        for col, label in [
            ('is_hammer', '锤子线'), ('is_shooting_star', '射击之星'),
            ('is_doji', '十字星'), ('is_big_bullish', '大阳线'), ('is_big_bearish', '大阴线'),
        ]:
            if has(col) and df.loc[i, col]:
                result['candle'].append(label)

        # ---- 支撑 / 阻力 ----
        if all(notna(c) for c in ['Support', 'Resistance']) and i > 0:
            cl, pcl = df.loc[i, 'Close'], df.loc[i - 1, 'Close']
            sup, res = df.loc[i, 'Support'], df.loc[i, 'Resistance']
            if   cl > res and pcl <= res:                          result['candle'].append('突破阻力位')
            elif cl < sup and pcl >= sup:                          result['candle'].append('跌破支撑位')
            elif df.loc[i, 'Low'] <= sup * 1.02 and cl > sup:     result['candle'].append('获得支撑')
            elif df.loc[i, 'High'] >= res * 0.98 and cl < res:    result['candle'].append('遇到阻力')

        # ---- 背离 ----
        for col, prefix in [('RSI_Divergence', 'RSI'), ('MACD_Divergence', 'MACD')]:
            if has(col) and df.loc[i, col]:
                result['divergence'].append(f"{prefix}{df.loc[i, col]}")

        # ---- 组合信号（来自 technical_analysis.py）----
        if i > 0:
            prev_close = df.loc[i - 1, 'Close']
            mfi = df.loc[i, 'MFI'] if notna('MFI') else None

            if (has('is_hammer') and df.loc[i, 'is_hammer'] and
                    has('Volume_Ratio') and df.loc[i, 'Volume_Ratio'] > 1.5 and
                    mfi is not None and mfi < 30):
                result['signals'].append('锤子线+放量+MFI超卖')

            if (all(notna(c) for c in ['OBV', 'OBV_MA']) and
                    df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA'] and
                    df.loc[i, 'Close'] > prev_close):
                result['signals'].append('OBV上升+价格上涨')

            if (has('is_big_bullish') and df.loc[i, 'is_big_bullish'] and
                    has('Volume_Ratio') and df.loc[i, 'Volume_Ratio'] > 1.5 and
                    mfi is not None and mfi < 70):
                result['signals'].append('大阳线+放量')

            if (has('is_shooting_star') and df.loc[i, 'is_shooting_star'] and
                    has('Volume_Ratio') and df.loc[i, 'Volume_Ratio'] > 1.5 and
                    mfi is not None and mfi > 70):
                result['signals'].append('射击之星+放量+MFI超买')

            if has('is_big_bearish') and df.loc[i, 'is_big_bearish'] and \
                    has('Volume_Ratio') and df.loc[i, 'Volume_Ratio'] > 1.5:
                result['signals'].append('大阴线+放量')

            if mfi is not None:
                if mfi > 80 and df.loc[i, 'Close'] < prev_close:
                    result['signals'].append('MFI超买+价格回落')
                elif mfi < 20 and df.loc[i, 'Close'] > prev_close:
                    result['signals'].append('MFI超卖+价格企稳')

        return result


# ==================== 辅助函数 ====================

def read_stock_pool(pool_file):
    stocks = []
    if not os.path.exists(pool_file):
        logger.error(f"股票池文件不存在: {pool_file}")
        return stocks
    with open(pool_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '#' in line:
                parts = line.split('#')
                code, name = parts[0].strip(), parts[1].strip()
            else:
                code, name = line.strip(), ''
            if code:
                stocks.append({'code': code, 'name': name})
    logger.info(f"读取股票池: {len(stocks)} 只")
    return stocks


def get_latest_db_date(stock_codes):
    if not LOCAL_DB_AVAILABLE:
        return None, stock_codes
    from database.db_manager import StockDatabase
    db = StockDatabase()
    date_map = {}
    for code in stock_codes:
        d = db.get_latest_date(code)
        if d:
            date_map[code] = d
    db.close()
    if not date_map:
        return None, []
    latest  = max(date_map.values())
    valid   = [c for c, d in date_map.items() if d == latest]
    excluded = len(stock_codes) - len(valid)
    if excluded:
        logger.warning(f"{excluded} 只股票数据未到最新日期 ({latest})，已排除")
    return latest, valid


def _f(val, prec=2):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return round(float(val), prec)
    except Exception:
        return None


def save_analysis_results_to_db(results, db_path=None):
    """在主进程中批量保存分析结果，避免多进程直接写 SQLite。"""
    if not results:
        return

    db = StockDatabase(db_path)
    try:
        db.save_pattern_analysis_results(results, source='local_db')
    finally:
        db.close()


# ==================== 多进程工作函数 ====================

def analyze_single_stock(args):
    stock_code, stock_name, start_date, end_date, use_local_db, include_year_stats = args
    try:
        analyzer = StockAnalyzer(use_local_db=use_local_db, suppress_logs=True)
        df = analyzer.fetch_data(stock_code, start_date, end_date)
        if df is None or df.empty:
            return None

        df = analyzer.calculate_indicators(df)
        patterns = analyzer.detect_patterns(df)

        latest     = df.iloc[-1]
        change_pct = (
            (latest['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close'] * 100
            if len(df) > 1 else 0.0
        )

        result = {
            'code':       stock_code,
            'name':       stock_name,
            'date':       latest['trade_date'].strftime('%Y%m%d'),
            'close':      _f(latest['Close']),
            'change_pct': _f(change_pct),
            'indicators': {
                'rsi':          _f(latest.get('RSI')),
                'mfi':          _f(latest.get('MFI')),
                'cci':          _f(latest.get('CCI')),
                'k':            _f(latest.get('K')),
                'd':            _f(latest.get('D')),
                'j':            _f(latest.get('J')),
                'macd_dif':     _f(latest.get('MACD_DIF'), 4),
                'macd_dea':     _f(latest.get('MACD_DEA'), 4),
                'macd_hist':    _f(latest.get('MACD_Histogram'), 4),
                'volume_ratio': _f(latest.get('Volume_Ratio')),
                'vwap':         _f(latest.get('VWAP')),
                'atr':          _f(latest.get('ATR')),
            },
            'patterns': patterns,
        }

        if include_year_stats:
            year_stats = None
            year_start_date = get_year_start_date(end_date)
            if start_date <= year_start_date:
                year_df = df[df['trade_date'] >= pd.to_datetime(year_start_date, format='%Y%m%d')]
                year_stats = calculate_year_stats(year_df)
            else:
                year_df = analyzer.fetch_data(stock_code, year_start_date, end_date)
                year_stats = calculate_year_stats(year_df)

            if year_stats:
                result['year_stats'] = year_stats

        return result
    except Exception as e:
        return None


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description='股票技术形态检测工具（结果写入数据库）')
    parser.add_argument('--pool',    type=str, required=True, help='股票池文件路径')
    parser.add_argument('--days',    type=int, default=120,   help='历史数据天数，默认 120')
    parser.add_argument('--workers', type=int, default=4,     help='并发进程数，默认 4')
    parser.add_argument('--skip-year-stats', action='store_true',
                        help='跳过年内高点统计，减少额外数据读取')
    args = parser.parse_args()

    stocks = read_stock_pool(args.pool)
    if not stocks:
        sys.exit(1)

    stock_codes = [s['code'] for s in stocks]
    end_date    = datetime.now().strftime('%Y%m%d')
    start_date  = (datetime.now() - timedelta(days=args.days)).strftime('%Y%m%d')

    latest_date, valid_codes = get_latest_db_date(stock_codes)
    if latest_date is None:
        logger.error("无法确定数据库最新日期，退出")
        sys.exit(1)
    end_date        = latest_date
    filtered_stocks = [s for s in stocks if s['code'] in valid_codes]
    logger.info(f"数据库最新日期: {end_date}，有效股票: {len(filtered_stocks)} 只")

    logger.info(f"开始分析 {len(filtered_stocks)} 只股票，日期范围: {start_date} ~ {end_date}")

    tasks = [
        (s['code'], s['name'], start_date, end_date, True)
        + (not args.skip_year_stats,)
        for s in filtered_stocks
    ]

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(analyze_single_stock, t): t for t in tasks}
        done = 0
        for future in as_completed(futures):
            done += 1
            result = future.result()
            if result:
                results.append(result)
            if done % 20 == 0 or done == len(tasks):
                logger.info(f"进度: {done}/{len(tasks)}，成功: {len(results)}")

    save_analysis_results_to_db(results)

    logger.info("完成，分析结果已写入 daily_pattern_analysis")
    logger.info(f"成功分析: {len(results)}/{len(filtered_stocks)} 只")


if __name__ == '__main__':
    main()
