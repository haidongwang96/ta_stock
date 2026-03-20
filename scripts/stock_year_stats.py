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

from analysis.year_stats import calculate_year_stats, get_year_start_date

# 导入数据库模块
try:
    from database.query_helper import StockDataQuery
except ImportError:
    print("错误: 无法导入 database 模块，请确保在项目根目录下运行脚本")
    sys.exit(1)

# 日志配置 - 默认不输出到控制台，除非出错
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)


class StockYearStats:
    def __init__(self):
        self.query = StockDataQuery()
        self.current_year = datetime.now().year
        self.start_date = get_year_start_date()

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
            
        except Exception as e:
            logger.error(f"加载股票池失败: {e}")

        return stock_list

    def calculate_stats(self, stock_list: List[Dict]) -> pd.DataFrame:
        """计算统计数据"""
        results = []
        total = len(stock_list)
        
        for i, stock in enumerate(stock_list, 1):
            ts_code = stock['ts_code']
            name = stock.get('name', '')
            
            # 获取年内数据
            df = self.query.daily(ts_code, start_date=self.start_date)
            
            if df is None or df.empty:
                continue
                
            year_stats = calculate_year_stats(df)
            if not year_stats:
                continue

            results.append({
                '代码': ts_code,
                '名称': name,
                '当前价格': year_stats['current_price'],
                '年内最高价': year_stats['year_high'],
                '最高价日期': year_stats['year_high_date'],
                '年内最高收盘价': year_stats['year_high_close'],
                '距最高点跌幅(%)': year_stats['drop_from_year_high_pct'],
                '最新日期': year_stats['latest_date'],
            })

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
            return

        # 2. 计算统计数据
        df = stats.calculate_stats(stock_list)
        
        if df.empty:
            return

        # 按跌幅排序（跌幅越大越靠前，即数值越大）
        df_sorted = df.sort_values('距最高点跌幅(%)', ascending=False)
        
        # 3. 确定输出路径
        output_path = args.output
        if not output_path:
            # 默认目录
            output_dir = os.path.join(project_root, 'stock_year_highpoint')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 默认文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'year_stats_{timestamp}.csv'
            output_path = os.path.join(output_dir, filename)
        
        # 4. 保存文件
        # 保存CSV
        df_sorted.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        # 保存TXT
        txt_output_path = os.path.splitext(output_path)[0] + '.txt'
        with open(txt_output_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"股票年度统计 ({stats.current_year})\n")
            f.write("="*80 + "\n")
            f.write(df_sorted.to_string(index=False))
            f.write("\n" + "="*80 + "\n")
        
        # 5. 仅输出文件绝对路径
        print(os.path.abspath(output_path))
        print(os.path.abspath(txt_output_path))
            
    finally:
        stats.close()


if __name__ == '__main__':
    main()
