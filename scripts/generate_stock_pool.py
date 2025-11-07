#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成A股股票池
使用tushare获取所有A股股票，按行业分类
"""

import tushare as ts
import pandas as pd
from collections import defaultdict


def init_tushare():
    """初始化tushare，从token.txt读取token"""
    try:
        with open('token.txt', 'r', encoding='utf-8') as f:
            token = f.read().strip()
        ts.set_token(token)
        return ts.pro_api()
    except FileNotFoundError:
        print("错误: 找不到token.txt文件")
        print("请确保token.txt文件存在于当前目录")
        raise
    except Exception as e:
        print(f"读取token失败: {e}")
        raise


def get_all_stocks(pro):
    """获取所有A股股票列表，排除北交所"""
    print("正在获取股票列表...")

    # 获取股票基本信息
    stock_basic = pro.stock_basic(
        exchange='',
        list_status='L',  # L:上市 D:退市 P:暂停上市
        fields='ts_code,symbol,name,area,industry,list_date'
    )

    # 排除北交所（北交所股票代码以BJ结尾，如430047.BJ）
    stock_basic = stock_basic[~stock_basic['ts_code'].str.endswith('.BJ')]

    print(f"获取到 {len(stock_basic)} 只股票（已排除北交所）")
    return stock_basic


def group_by_industry(stock_basic):
    """按行业分组"""
    industry_dict = defaultdict(list)

    for _, row in stock_basic.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        industry = row['industry'] if pd.notna(row['industry']) else '其他'

        industry_dict[industry].append({
            'code': ts_code,
            'name': name
        })

    # 按行业名称排序
    sorted_industries = sorted(industry_dict.items(), key=lambda x: x[0])

    return sorted_industries


def write_stock_pool(industries, output_file='stock_pool_all.txt'):
    """写入股票池文件"""
    print(f"正在生成股票池文件: {output_file}")

    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入文件头
        f.write("# A股全市场股票池\n")
        f.write("# 格式: 股票代码.交易所  # 名称\n")
        f.write("# 以#开头的行为注释\n")
        f.write("# 数据来源: Tushare\n")
        f.write(f"# 生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")

        # 按行业写入
        for industry, stocks in industries:
            f.write(f"# {industry}\n")

            # 按股票代码排序
            stocks.sort(key=lambda x: x['code'])

            for stock in stocks:
                f.write(f"{stock['code']}  # {stock['name']}\n")

            f.write("\n")

    print(f"股票池文件生成完成: {output_file}")


def generate_summary(industries):
    """生成统计摘要"""
    total_stocks = sum(len(stocks) for _, stocks in industries)

    print("\n" + "="*50)
    print("统计摘要")
    print("="*50)
    print(f"总股票数: {total_stocks}")
    print(f"行业数量: {len(industries)}")
    print("\n各行业股票数量:")

    # 按股票数量排序
    sorted_by_count = sorted(industries, key=lambda x: len(x[1]), reverse=True)

    for industry, stocks in sorted_by_count[:20]:  # 显示前20个行业
        print(f"  {industry}: {len(stocks)} 只")

    if len(industries) > 20:
        print(f"  ... 还有 {len(industries) - 20} 个行业")
    print("="*50)


def main():
    """主函数"""
    try:
        # 初始化tushare
        pro = init_tushare()

        # 获取所有股票
        stock_basic = get_all_stocks(pro)

        # 按行业分组
        industries = group_by_industry(stock_basic)

        # 写入文件
        write_stock_pool(industries, 'stock_pool_all.txt')

        # 生成统计摘要
        generate_summary(industries)

        print("\n处理完成！")

    except Exception as e:
        print(f"发生错误: {e}")
        print("\n请确保:")
        print("1. 已安装tushare: pip install tushare")
        print("2. 已设置正确的tushare token")
        print("3. 网络连接正常")


if __name__ == '__main__':
    main()
