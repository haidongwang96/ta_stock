#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专业K线图绘制工具（仿交易软件风格）
读取K线数据和技术分析结果，绘制专业的K线图
包含：K线、成交量、均线、MFI、OBV等技术指标
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
import argparse
import os
from datetime import datetime

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 交易软件配色方案
COLORS = {
    'up': '#FF4444',      # 涨-红色
    'down': '#00CC00',    # 跌-绿色
    'ma5': '#FF00FF',     # MA5-紫色
    'ma10': '#FFFF00',    # MA10-黄色
    'ma20': '#FFFFFF',    # MA20-白色
    'ma60': '#00FFFF',    # MA60-青色
    'mfi': '#FFA500',     # MFI-橙色
    'obv': '#4169E1',     # OBV-蓝色
    'bg': '#000000',      # 背景-黑色
    'grid': '#333333',    # 网格-深灰
    'text': '#CCCCCC',    # 文字-浅灰
}


def load_full_analysis_data(analysis_file):
    """
    加载完整的技术分析数据
    :param analysis_file: 技术分析CSV文件路径
    :return: DataFrame
    """
    df = pd.read_csv(analysis_file, encoding='utf-8-sig')

    # 确保trade_date是datetime类型
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')

    return df


def plot_professional_kline(df, stock_code, output_file=None):
    """
    绘制专业K线图（仿交易软件风格）
    包含：主图（K线+均线）、成交量、MFI、OBV

    :param df: 完整的技术分析数据
    :param stock_code: 股票代码
    :param output_file: 输出文件路径
    """
    # 创建图表（黑色背景）
    fig = plt.figure(figsize=(18, 12), facecolor=COLORS['bg'])

    # 创建网格布局：主图(占3份)、成交量(占1份)、MFI(占1份)、OBV(占1份)
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.05)

    ax_main = fig.add_subplot(gs[0])      # 主图：K线+均线
    ax_vol = fig.add_subplot(gs[1], sharex=ax_main)   # 成交量
    ax_mfi = fig.add_subplot(gs[2], sharex=ax_main)   # MFI
    ax_obv = fig.add_subplot(gs[3], sharex=ax_main)   # OBV

    # 设置所有子图的背景色
    for ax in [ax_main, ax_vol, ax_mfi, ax_obv]:
        ax.set_facecolor(COLORS['bg'])
        ax.tick_params(colors=COLORS['text'])
        ax.spines['bottom'].set_color(COLORS['grid'])
        ax.spines['top'].set_color(COLORS['grid'])
        ax.spines['left'].set_color(COLORS['grid'])
        ax.spines['right'].set_color(COLORS['grid'])

    # ==================== 主图：K线 + 均线 ====================
    width = 0.6

    # 计算均线
    if 'Close' in df.columns:
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()

    # 绘制K线
    for idx in range(len(df)):
        if idx >= len(df):
            break

        row = df.iloc[idx]

        # 检查必需的字段
        if pd.isna(row['Open']) or pd.isna(row['Close']):
            continue

        open_price = row['Open']
        high_price = row['High']
        low_price = row['Low']
        close_price = row['Close']

        # 判断涨跌
        is_up = close_price >= open_price
        color = COLORS['up'] if is_up else COLORS['down']

        # 绘制K线实体
        height = abs(close_price - open_price)
        bottom = min(open_price, close_price)

        if height < 0.001:  # 十字星
            height = high_price * 0.001  # 设置最小高度

        rect = Rectangle((idx - width/2, bottom), width, height,
                         facecolor=color, edgecolor=color, linewidth=0.8)
        ax_main.add_patch(rect)

        # 绘制上下影线
        ax_main.plot([idx, idx], [low_price, high_price],
                    color=color, linewidth=0.8, alpha=0.8)

    # 绘制均线
    if 'MA5' in df.columns:
        ax_main.plot(range(len(df)), df['MA5'], label='MA5',
                    color=COLORS['ma5'], linewidth=1.2, alpha=0.9)
    if 'MA10' in df.columns:
        ax_main.plot(range(len(df)), df['MA10'], label='MA10',
                    color=COLORS['ma10'], linewidth=1.2, alpha=0.9)
    if 'MA20' in df.columns:
        ax_main.plot(range(len(df)), df['MA20'], label='MA20',
                    color=COLORS['ma20'], linewidth=1.2, alpha=0.9)
    if 'MA60' in df.columns:
        ax_main.plot(range(len(df)), df['MA60'], label='MA60',
                    color=COLORS['ma60'], linewidth=1.2, alpha=0.9)

    # 主图设置
    ax_main.set_xlim(-1, len(df))
    ax_main.grid(True, alpha=0.3, color=COLORS['grid'], linestyle='--')
    ax_main.legend(loc='upper left', facecolor=COLORS['bg'],
                  edgecolor=COLORS['grid'], labelcolor=COLORS['text'])
    ax_main.set_ylabel('价格 (元)', fontsize=11, color=COLORS['text'])

    # 添加标题信息
    if len(df) > 0:
        latest = df.iloc[-1]
        title_text = f"{stock_code}  "
        title_text += f"收盘:{latest['Close']:.2f}  "
        if 'pct_change' in df.columns and not pd.isna(latest['pct_change']):
            title_text += f"涨跌:{latest['pct_change']:+.2f}%  "
        if 'Volume' in df.columns:
            title_text += f"成交量:{latest['Volume']/10000:.0f}万"

        ax_main.set_title(title_text, fontsize=13, color=COLORS['text'],
                         loc='left', pad=10, fontweight='bold')

    # 隐藏x轴标签（除了最下面的子图）
    ax_main.set_xticklabels([])

    # ==================== 成交量 ====================
    if 'Volume' in df.columns:
        for idx in range(len(df)):
            if idx >= len(df):
                break

            row = df.iloc[idx]

            if pd.isna(row.get('Open')) or pd.isna(row.get('Close')):
                continue

            volume = row['Volume']
            is_up = row['Close'] >= row['Open']
            color = COLORS['up'] if is_up else COLORS['down']

            ax_vol.bar(idx, volume, width=width, color=color, alpha=0.7)

        # 成交量均线
        df['VOL_MA5'] = df['Volume'].rolling(window=5).mean()
        df['VOL_MA10'] = df['Volume'].rolling(window=10).mean()

        ax_vol.plot(range(len(df)), df['VOL_MA5'],
                   color=COLORS['ma5'], linewidth=1, alpha=0.8, label='VOL_MA5')
        ax_vol.plot(range(len(df)), df['VOL_MA10'],
                   color=COLORS['ma10'], linewidth=1, alpha=0.8, label='VOL_MA10')

        ax_vol.set_ylabel('成交量', fontsize=10, color=COLORS['text'])
        ax_vol.legend(loc='upper left', fontsize=8, facecolor=COLORS['bg'],
                     edgecolor=COLORS['grid'], labelcolor=COLORS['text'])
        ax_vol.grid(True, alpha=0.3, color=COLORS['grid'], linestyle='--')
        ax_vol.set_xticklabels([])
        ax_vol.ticklabel_format(style='plain', axis='y')

    # ==================== MFI (Money Flow Index) ====================
    if 'MFI' in df.columns:
        # 绘制MFI线
        ax_mfi.plot(range(len(df)), df['MFI'],
                   color=COLORS['mfi'], linewidth=1.5, label='MFI')

        # 绘制超买超卖线
        ax_mfi.axhline(y=80, color='red', linestyle='--', linewidth=0.8, alpha=0.5)
        ax_mfi.axhline(y=20, color='green', linestyle='--', linewidth=0.8, alpha=0.5)
        ax_mfi.axhline(y=50, color=COLORS['text'], linestyle=':', linewidth=0.5, alpha=0.3)

        # 填充超买超卖区域
        ax_mfi.fill_between(range(len(df)), 80, 100, color='red', alpha=0.1)
        ax_mfi.fill_between(range(len(df)), 0, 20, color='green', alpha=0.1)

        ax_mfi.set_ylim(0, 100)
        ax_mfi.set_ylabel('MFI', fontsize=10, color=COLORS['text'])
        ax_mfi.legend(loc='upper left', fontsize=8, facecolor=COLORS['bg'],
                     edgecolor=COLORS['grid'], labelcolor=COLORS['text'])
        ax_mfi.grid(True, alpha=0.3, color=COLORS['grid'], linestyle='--')
        ax_mfi.set_xticklabels([])

        # 添加数值标签
        if len(df) > 0:
            latest_mfi = df['MFI'].iloc[-1]
            if not pd.isna(latest_mfi):
                mfi_status = "超买" if latest_mfi > 80 else ("超卖" if latest_mfi < 20 else "正常")
                ax_mfi.text(0.02, 0.95, f'MFI: {latest_mfi:.1f} ({mfi_status})',
                           transform=ax_mfi.transAxes, fontsize=9,
                           color=COLORS['text'], verticalalignment='top')

    # ==================== OBV (On-Balance Volume) ====================
    if 'OBV' in df.columns:
        # 绘制OBV及其均线
        ax_obv.plot(range(len(df)), df['OBV'],
                   color=COLORS['obv'], linewidth=1.5, label='OBV')

        if 'OBV_MA' in df.columns:
            ax_obv.plot(range(len(df)), df['OBV_MA'],
                       color=COLORS['ma20'], linewidth=1.2,
                       linestyle='--', alpha=0.8, label='OBV_MA20')

        ax_obv.set_ylabel('OBV', fontsize=10, color=COLORS['text'])
        ax_obv.legend(loc='upper left', fontsize=8, facecolor=COLORS['bg'],
                     edgecolor=COLORS['grid'], labelcolor=COLORS['text'])
        ax_obv.grid(True, alpha=0.3, color=COLORS['grid'], linestyle='--')
        ax_obv.ticklabel_format(style='plain', axis='y')

        # 添加趋势标签
        if 'OBV_MA' in df.columns and len(df) > 0:
            latest_obv = df['OBV'].iloc[-1]
            latest_obv_ma = df['OBV_MA'].iloc[-1]
            if not pd.isna(latest_obv) and not pd.isna(latest_obv_ma):
                trend = "上升" if latest_obv > latest_obv_ma else "下降"
                ax_obv.text(0.02, 0.95, f'OBV趋势: {trend}',
                           transform=ax_obv.transAxes, fontsize=9,
                           color=COLORS['text'], verticalalignment='top')

    # ==================== X轴设置（日期） ====================
    # 只在最下面的子图显示日期
    date_indices = range(0, len(df), max(1, len(df)//12))
    ax_obv.set_xticks(list(date_indices))

    date_labels = []
    for i in date_indices:
        if i < len(df):
            date = df.iloc[i]['trade_date']
            date_labels.append(date.strftime('%Y-%m-%d'))

    ax_obv.set_xticklabels(date_labels, rotation=45, ha='right', fontsize=9)
    ax_obv.set_xlabel('日期', fontsize=10, color=COLORS['text'])

    # ==================== 添加交易信号标注 ====================
    if 'signal' in df.columns and 'signal_strength' in df.columns:
        for idx in range(len(df)):
            if idx >= len(df):
                break

            row = df.iloc[idx]

            # 只标注强信号
            if pd.notna(row['signal_strength']) and abs(row['signal_strength']) >= 2:
                if row['signal_strength'] > 0:
                    # 买入信号 - 向上箭头
                    ax_main.annotate('', xy=(idx, row['Low'] * 0.995),
                                   xytext=(idx, row['Low'] * 0.985),
                                   arrowprops=dict(arrowstyle='->',
                                                 color='red', lw=2))
                    ax_main.text(idx, row['Low'] * 0.98, 'B',
                               fontsize=8, color='red', ha='center',
                               fontweight='bold')
                else:
                    # 卖出信号 - 向下箭头
                    ax_main.annotate('', xy=(idx, row['High'] * 1.005),
                                   xytext=(idx, row['High'] * 1.015),
                                   arrowprops=dict(arrowstyle='->',
                                                 color='green', lw=2))
                    ax_main.text(idx, row['High'] * 1.02, 'S',
                               fontsize=8, color='green', ha='center',
                               fontweight='bold')

    # ==================== 添加图表说明 ====================
    # 在右上角添加K线形态说明
    if 'is_hammer' in df.columns or 'is_big_bullish' in df.columns:
        info_text = "K线形态:\n"

        # 统计最近10天的形态
        recent_df = df.tail(10)

        if 'is_hammer' in df.columns:
            hammer_count = recent_df['is_hammer'].sum()
            if hammer_count > 0:
                info_text += f"锤子线: {int(hammer_count)}次\n"

        if 'is_big_bullish' in df.columns:
            bullish_count = recent_df['is_big_bullish'].sum()
            if bullish_count > 0:
                info_text += f"大阳线: {int(bullish_count)}次\n"

        if 'is_big_bearish' in df.columns:
            bearish_count = recent_df['is_big_bearish'].sum()
            if bearish_count > 0:
                info_text += f"大阴线: {int(bearish_count)}次\n"

        if len(info_text) > len("K线形态:\n"):
            ax_main.text(0.98, 0.98, info_text.strip(),
                        transform=ax_main.transAxes,
                        fontsize=8, color=COLORS['text'],
                        verticalalignment='top', horizontalalignment='right',
                        bbox=dict(boxstyle='round', facecolor=COLORS['bg'],
                                edgecolor=COLORS['grid'], alpha=0.8))

    # 调整布局
    plt.tight_layout()

    # 保存或显示
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight',
                   facecolor=COLORS['bg'], edgecolor='none')
        print(f"专业K线图已保存到: {output_file}")
    else:
        plt.show()

    plt.close()


def plot_simple_kline(kline_file, stock_code, output_file=None):
    """
    从简化的K线数据文件绘制基础K线图（无技术指标）

    :param kline_file: K线数据文件（只有OHLCV）
    :param stock_code: 股票代码
    :param output_file: 输出文件路径
    """
    # 读取数据
    df = pd.read_csv(kline_file, encoding='utf-8-sig')

    # 统一列名（兼容中英文）
    column_mapping = {
        '日期': 'trade_date',
        '开盘价': 'Open',
        '最高价': 'High',
        '最低价': 'Low',
        '收盘价': 'Close',
        '成交量': 'Volume'
    }
    df = df.rename(columns=column_mapping)

    # 转换日期
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')

    # 调用专业绘图函数（会自动计算均线）
    plot_professional_kline(df, stock_code, output_file)


def main():
    parser = argparse.ArgumentParser(description='专业K线图绘制工具（仿交易软件风格）')
    parser.add_argument('--input', type=str, required=True,
                       help='输入文件：完整技术分析CSV或K线数据CSV')
    parser.add_argument('--code', type=str, help='股票代码（用于标题）')
    parser.add_argument('--output', type=str, help='输出图片文件路径')
    parser.add_argument('--type', type=str, choices=['full', 'simple'],
                       default='auto',
                       help='数据类型：full=完整分析数据，simple=仅K线数据，auto=自动检测')

    args = parser.parse_args()

    # 自动提取股票代码
    if not args.code:
        basename = os.path.basename(args.input)
        # 尝试从文件名提取代码
        parts = basename.split('_')
        if len(parts) >= 2:
            args.code = parts[1].split('.')[0]
        else:
            args.code = "股票"

    # 自动生成输出文件名
    if not args.output:
        input_name = os.path.splitext(os.path.basename(args.input))[0]
        output_dir = 'technical_analysis_results'
        os.makedirs(output_dir, exist_ok=True)
        args.output = os.path.join(output_dir, f"{input_name}_professional.png")

    print(f"读取数据: {args.input}")

    # 自动检测数据类型
    df = pd.read_csv(args.input, encoding='utf-8-sig')
    has_mfi = 'MFI' in df.columns or 'mfi' in df.columns

    if args.type == 'auto':
        args.type = 'full' if has_mfi else 'simple'

    print(f"数据类型: {args.type}")
    print(f"数据量: {len(df)} 条记录")

    # 绘制K线图
    if args.type == 'full':
        # 完整技术分析数据
        df_full = load_full_analysis_data(args.input)
        plot_professional_kline(df_full, args.code, args.output)
    else:
        # 简单K线数据
        plot_simple_kline(args.input, args.code, args.output)

    print(f"\n绘图完成！")
    print(f"输出文件: {args.output}")


if __name__ == '__main__':
    main()
