#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拆分股票池文件，按行业分类保存
"""

import os
import re
from pypinyin import lazy_pinyin


def industry_to_pinyin(industry_name):
    """将行业名称转换为拼音"""
    # 使用pypinyin转换为拼音
    pinyin_list = lazy_pinyin(industry_name)
    # 拼接成一个单词，全部小写
    pinyin_str = ''.join(pinyin_list).lower()
    return pinyin_str


def parse_stock_pool_file(input_file):
    """解析股票池文件，按行业分组"""
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    industries = {}
    current_industry = None
    current_stocks = []
    header_lines = []

    # 正在读取文件头
    reading_header = True

    for line in lines:
        line = line.rstrip('\n')

        # 如果是空行
        if not line.strip():
            if current_industry and current_stocks:
                # 保存当前行业
                industries[current_industry] = current_stocks
                current_stocks = []
            continue

        # 如果是注释行
        if line.startswith('#'):
            # 提取行业名称
            industry_match = re.match(r'^#\s*(.+)$', line)
            if industry_match:
                industry_text = industry_match.group(1).strip()

                # 判断是否是文件头的注释
                if reading_header and any(keyword in industry_text for keyword in
                    ['股票池', '格式', '注释', '数据来源', '生成时间']):
                    header_lines.append(line)
                else:
                    # 这是行业名称
                    reading_header = False
                    if current_industry and current_stocks:
                        industries[current_industry] = current_stocks
                    current_industry = industry_text
                    current_stocks = []
        else:
            # 这是股票行
            reading_header = False
            if current_industry:
                current_stocks.append(line)

    # 保存最后一个行业
    if current_industry and current_stocks:
        industries[current_industry] = current_stocks

    return industries, header_lines


def write_industry_files(industries, header_lines, output_dir='pool'):
    """为每个行业创建单独的文件"""
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建目录: {output_dir}")

    # 写入每个行业文件
    for industry, stocks in industries.items():
        # 生成文件名
        pinyin = industry_to_pinyin(industry)
        filename = f"stock_pool_{pinyin}.txt"
        filepath = os.path.join(output_dir, filename)

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            # 写入文件头（简化版）
            f.write(f"# {industry}\n")
            f.write("# 格式: 股票代码.交易所  # 名称\n")
            f.write("\n")

            # 写入股票列表
            for stock in stocks:
                f.write(stock + '\n')

        print(f"创建文件: {filename} ({len(stocks)} 只股票)")


def main():
    """主函数"""
    input_file = 'pool/stock_pool_all.txt'
    output_dir = 'pool'

    print(f"开始拆分股票池文件: {input_file}")
    print("="*60)

    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 找不到文件 {input_file}")
        return

    # 解析文件
    industries, header_lines = parse_stock_pool_file(input_file)
    print(f"解析完成，共 {len(industries)} 个行业")
    print("="*60)

    # 写入行业文件
    write_industry_files(industries, header_lines, output_dir)

    print("="*60)
    print(f"拆分完成！共生成 {len(industries)} 个文件")
    print(f"输出目录: {output_dir}")


if __name__ == '__main__':
    main()
