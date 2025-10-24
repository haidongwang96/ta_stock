#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量分析调试测试脚本
"""

import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time

def test_single_stock(ts_code):
    """测试单只股票数据获取"""
    print(f"\n测试获取 {ts_code} 的数据...")

    # 设置token
    ts_token = "c105f106ea6ac80b4208c5f4bdc3d6630e47efbf27d821739ca4441d"
    ts.set_token(ts_token)
    pro = ts.pro_api()

    # 日期设置
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

    try:
        # 尝试获取数据
        df = pro.daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

        if df.empty:
            print(f"  ❌ 未获取到数据")
            # 尝试其他接口
            print(f"  尝试使用pro_bar接口...")
            df = ts.pro_bar(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                print(f"  ✓ pro_bar接口成功获取 {len(df)} 条数据")
                print(f"  数据日期范围: {df['trade_date'].min()} - {df['trade_date'].max()}")
            else:
                print(f"  ❌ pro_bar接口也未获取到数据")
        else:
            print(f"  ✓ 成功获取 {len(df)} 条数据")
            print(f"  数据日期范围: {df['trade_date'].min()} - {df['trade_date'].max()}")
            print(f"  最新收盘价: {df.iloc[0]['close']}")

    except Exception as e:
        print(f"  ❌ 获取失败: {e}")
        print(f"  错误类型: {type(e).__name__}")

def test_batch_stocks():
    """测试批量获取"""
    print("\n" + "="*60)
    print("测试批量获取股票数据")
    print("="*60)

    # 读取股票池
    pool_file = 'stock_pool_small.txt'
    with open(pool_file, 'r', encoding='utf-8') as f:
        stocks = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"\n从 {pool_file} 读取到的股票代码:")
    for i, stock in enumerate(stocks, 1):
        print(f"  {i}. {stock}")

    # 逐个测试
    for stock in stocks:
        test_single_stock(stock)
        time.sleep(0.5)  # 避免频繁调用

def test_stock_info():
    """测试获取股票基本信息"""
    print("\n" + "="*60)
    print("测试获取股票基本信息")
    print("="*60)

    ts_token = "c105f106ea6ac80b4208c5f4bdc3d6630e47efbf27d821739ca4441d"
    ts.set_token(ts_token)
    pro = ts.pro_api()

    try:
        # 获取股票列表
        print("\n获取上交所科创板股票列表...")
        df = pro.stock_basic(exchange='SSE', market='科创板', list_status='L')

        if not df.empty:
            print(f"  ✓ 找到 {len(df)} 只科创板股票")
            # 查找特定股票
            test_stocks = ['688256', '603893']
            for code in test_stocks:
                matches = df[df['symbol'] == code]
                if not matches.empty:
                    stock_info = matches.iloc[0]
                    print(f"\n  股票代码: {stock_info['ts_code']}")
                    print(f"  股票名称: {stock_info['name']}")
                    print(f"  所属市场: {stock_info.get('market', 'N/A')}")
                else:
                    print(f"\n  ❌ 未找到股票 {code}")
                    # 尝试在主板查找
                    df_main = pro.stock_basic(exchange='SH', list_status='L')
                    matches_main = df_main[df_main['symbol'] == code]
                    if not matches_main.empty:
                        stock_info = matches_main.iloc[0]
                        print(f"    ✓ 在主板找到: {stock_info['ts_code']} - {stock_info['name']}")

    except Exception as e:
        print(f"  ❌ 获取股票信息失败: {e}")

def test_alternative_codes():
    """测试不同的股票代码格式"""
    print("\n" + "="*60)
    print("测试不同的股票代码格式")
    print("="*60)

    # 测试各种可能的格式
    test_codes = [
        '688256.SH',  # 原格式
        'SH688256',   # 前缀格式
        '688256',     # 纯代码
        '603893.SH',
        'SH603893',
        '603893'
    ]

    ts_token = "c105f106ea6ac80b4208c5f4bdc3d6630e47efbf27d821739ca4441d"
    ts.set_token(ts_token)
    pro = ts.pro_api()

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')

    for code in test_codes:
        print(f"\n测试代码: {code}")
        try:
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
            if not df.empty:
                print(f"  ✓ 成功！获取到 {len(df)} 条数据")
                break
            else:
                print(f"  ❌ 无数据")
        except Exception as e:
            print(f"  ❌ 失败: {str(e)[:50]}")

if __name__ == '__main__':
    # 运行测试
    test_stock_info()        # 先测试股票基本信息
    test_alternative_codes() # 测试代码格式
    test_batch_stocks()      # 测试批量获取

    print("\n" + "="*60)
    print("调试测试完成")
    print("="*60)