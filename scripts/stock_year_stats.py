#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票年度统计工具

功能：
1. 读取股票池文件
2. 从本地数据库获取年内数据
3. 计算：现价、年内最高价、年内最高收盘价、距最高点跌幅
4. 输出结果到控制台和CSV文件
"""

import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入数据库模块
try:
    from database.query_helper import StockDataQuery
except ImportError:
    print("错误: 无法导入 database 模块，请确保在项目根目录下运行脚本")
    sys.exit(1)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class StockYearStats:
    def __init__(self):
        self.query = StockDataQuery()
        self.current_year = datetime.now().year
        self.start_date = f"{self.current_year}0101"
        logger.info(f"初始化统计工具，统计年份: {self.current_year}")

    def load_stock_pool(self, pool_file: str) -> List[Dict]:
        """加载股票池"""
        stock_list = []
        if not os.path.exists(pool_file):
            logger.error(f"股票池文件不存在: {pool_file}")
            return stock_list

        try:
            with open(pool_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # 支持多种格式
                    if '#' in line:
                        parts = line.split('#')
                        ts_code = parts[0].strip()
                        name = parts[1].strip() if len(parts) > 1 else ''
                    else:
                        parts = line.replace(',', ' ').split()
                        ts_code = parts[0]
                        name = parts[1] if len(parts) > 1 else ''

                    stock_list.append({'ts_code': ts_code, 'name': name})
            
            logger.info(f"加载股票池: {pool_file} (共{len(stock_list)}只)")
        except Exception as e:
            logger.error(f"加载股票池失败: {e}")

        return stock_list

    def calculate_stats(self, stock_list: List[Dict]) -> pd.DataFrame:
        """计算统计数据"""
        results = []
        total = len(stock_list)
        
        logger.info("开始计算统计数据...")
        
        for i, stock in enumerate(stock_list, 1):
            ts_code = stock['ts_code']
            name = stock.get('name', '')
            
            # 获取年内数据
            df = self.query.daily(ts_code, start_date=self.start_date)
            
            if df is None or df.empty:
                logger.warning(f"[{i}/{total}] {ts_code} {name}: 无数据")
                continue
                
            # 计算统计指标
            current_price = df['close'].iloc[-1]
            ytd_high = df['high'].max()
            ytd_high_close = df['close'].max()
            
            # 计算距最高点跌幅
            drop_from_high = 0.0
            if ytd_high > 0:
                drop_from_high = (ytd_high - current_price) / ytd_high * 100
                
            results.append({
                '代码': ts_code,
                '名称': name,
                '当前价格': round(current_price, 2),
                '年内最高价': round(ytd_high, 2),
                '年内最高收盘价': round(ytd_high_close, 2),
                '距最高点跌幅(%)': round(drop_from_high, 2),
                '最新日期': df['trade_date'].iloc[-1]
            })
            
            if i % 10 == 0:
                logger.info(f"已处理 {i}/{total} 只股票")

        return pd.DataFrame(results)

    def close(self):
        self.query.close()


def main():
    parser = argparse.ArgumentParser(description='股票年度统计工具')
    parser.add_argument('--pool', type=str, required=True, help='股票池文件路径')
    parser.add_argument('--output', type=str, help='输出CSV文件路径')
    
    args = parser.parse_args()
    
    stats = StockYearStats()
    try:
        # 1. 加载股票池
        stock_list = stats.load_stock_pool(args.pool)
        if not stock_list:
            logger.error("股票池为空，退出")
            return

        # 2. 计算统计数据
        df = stats.calculate_stats(stock_list)
        
        if df.empty:
            logger.warning("未生成任何统计数据")
            return

        # 3. 输出结果
        print("\n" + "="*80)
        print(f"股票年度统计 ({stats.current_year})")
        print("="*80)
        
        # 设置pandas显示选项
        pd.set_option('display.max_rows', None)
        pd.set_option('display.unicode.east_asian_width', True)
        pd.set_option('display.float_format', '{:.2f}'.format)
        
        # 按跌幅排序（跌幅越大越靠前，即数值越大）
        df_sorted = df.sort_values('距最高点跌幅(%)', ascending=False)
        
        print(df_sorted.to_string(index=False))
        print("="*80)
        
        # 4. 保存文件
        if args.output:
            df_sorted.to_csv(args.output, index=False, encoding='utf-8-sig')
            logger.info(f"结果已保存至: {args.output}")
            
    finally:
        stats.close()


if __name__ == '__main__':
    main()
