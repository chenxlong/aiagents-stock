"""
TickFlow 数据获取模块
使用 TickFlow 库获取股票数据
pip install tickflow
"""

from tickflow import TickFlow
from tickflow import RateLimitError
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import time
import re
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class TickFlowDataFetcher:
    """基于 TickFlow 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.tickflow_token = os.getenv('TICKFLOW_TOKEN', '')
        if self.tickflow_token:
            self.tf_free = TickFlow(api_key=self.tickflow_token)
            self.logger.info("TickFlow 客户端初始化成功。")
        else:
            self.tf_free = TickFlow.free()
            self.logger.info("TickFlow 免费客户端初始化成功，不能获取实时行情。")

    # ===提取错误信息中等待毫秒数===
    def extract_wait_ms(self, error_msg: str) -> int | None:
        # pattern = r"(\d+)ms"
        pattern = r"(\d+)\s*ms"
        match = re.search(pattern, error_msg)
        if match:
            return int(match.group(1))
        return None

    # ===转换股票代码为TickFlow格式===
    def convert_to_tickflow_code(self, symbol):
        """
        将6位股票代码转换为TickFlow格式（带市场后缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: TickFlow格式代码（如：000001.SH）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        
        # 根据代码判断市场
        if symbol.startswith('6'):
            # 上海主板
            return f"{symbol}.SH"
        elif symbol.startswith('0') or symbol.startswith('3'):
            # 深圳主板和创业板
            return f"{symbol}.SZ"
        elif symbol.startswith('8') or symbol.startswith('4'):
            # 北交所
            return f"{symbol}.BJ"
        else:
            # 默认深圳
            return f"{symbol}.SZ"
    
    # ===获取个股基本信息===
    def get_stock_basic_info(self, symbol):
        """
        获取个股基本信息
        
        Args:
            symbol: 股票代码（格式：688549.SH 或 000001.SZ）
            
        Returns:
            dict: 包含股票基本信息的字典
        """
        self.logger.debug(f"开始获取股票 {symbol} 的基本信息")
        info = {}
        try:
            tf_symbol = self.convert_to_tickflow_code(symbol)
            # 批量获取股票基础信息
            stock_info = self.tf_free.instruments.batch(symbols=[tf_symbol])
            
            if stock_info and len(stock_info) > 0:
                item = stock_info[0]
                ext = item.get('ext', 'N/A')
                info = {
                    "symbol": item.get('symbol', symbol),
                    "name": item.get('name', 'N/A'),
                    "exchange": item.get('exchange', 'N/A'),
                    "market": item.get('exchange', 'N/A'),
                    "type": item.get('type', 'N/A'),    # 标的类型
                    "list_date": ext.get('listing_date', 'N/A'),
                    "total_share_capital": ext.get('total_shares', 'N/A'),
                    "tradable_share_capital": ext.get('float_shares', 'N/A')
                }
                self.logger.info(f"✅ 成功获取 {symbol} 的基本信息: {info}")
                return info
            else:
                self.logger.warning(f"未找到股票 {symbol} 的基本信息")
                return info
                
        except Exception as e:
            self.logger.error(f"获取股票 {symbol} 基本信息失败: {e}")

        return info
    
    # ===获取个股历史数据===
    def get_stock_history_data(self, symbol, start_date, end_date, adjust="qfq"):
        """
        获取个股历史数据
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含历史数据的DataFrame，包含日期、开盘、收盘、最高、最低、成交量等列
        """
        self.logger.debug(f"开始获取股票 {symbol} 的历史数据，日期范围: {start_date} - {end_date}, 复权: {adjust}")

        hist_data_df = pd.DataFrame()
        try:
            # 日期转换2024-01-01格式到20240101格式
            if '-' in start_date:
                start_date = start_date.replace('-', '')
            if '-' in end_date:
                end_date = end_date.replace('-', '')

            kCount = 1
            # 日期转换为datetime对象
            start_date = datetime.strptime(start_date, "%Y%m%d")
            end_date = datetime.strptime(end_date, "%Y%m%d")
            # 计算日期[start_date, end_date]范围内内的日线数量，至少1条
            if start_date > end_date:
                self.logger.error(f"开始日期 {start_date} 不能晚于结束日期 {end_date}")
                return hist_data_df
            else:
                kCount = (end_date - start_date).days + 1
            kCount = max(kCount, 1)
           
            kAdjust = "forward"
            if adjust == "qfq":
                kAdjust = "forward"
            elif adjust == "hfq":
                kAdjust = "backward"
            elif adjust == "":
                kAdjust = "none"

            tf_symbol = self.convert_to_tickflow_code(symbol)
            # 尝试获取日线数据
            hist_data_df = self.tf_free.klines.get(
                symbol=tf_symbol,
                period="1d",        # 周期 1d日线 1w周 1M月
                count=kCount,       # 获取K线数量
                adjust=kAdjust,     # forward前复权 / backward后复权 / none不复权
                as_dataframe=True   # 返回pandas DataFrame
            )
            self.logger.info(f"获取到 {symbol} 的原始历史数据:\n{hist_data_df}")
            
            if hist_data_df is not None and not hist_data_df.empty:
                # 标准化列名
                hist_data_df = hist_data_df.rename(columns={
                    'trade_date': 'Date',
                    'open': 'Open',
                    'close': 'Close',
                    'high': 'High',
                    'low': 'Low',
                    'volume': 'Volume',
                    'amount': 'Amount',
                })

                # 转换成交量单位为股数
                hist_data_df['Volume'] = hist_data_df['Volume'] * 100
                
                # 确保 Date 列为 datetime 类型并设为索引
                if 'Date' in hist_data_df.columns:
                    hist_data_df['Date'] = pd.to_datetime(hist_data_df['Date'])
                    hist_data_df.set_index('Date', inplace=True)
                
                self.logger.info(f"✅ 成功获取 {symbol} 变换后的历史数据，共 {len(hist_data_df)} 条记录，数据:\n{hist_data_df}")
                return hist_data_df
            else:
                self.logger.warning(f"未获取到 {symbol} 的历史数据")
                return hist_data_df
                
        except Exception as e:
            self.logger.error(f"获取股票 {symbol} 历史数据失败: {e}")
            return hist_data_df

    # ===获取股票实时数据===
    def get_stock_realtime_data(self, symbol):
        """
        获取股票实时数据
        Args:
            symbol: 股票代码（6位数字）
            
        Returns:
            DataFrame: 包含实时数据的DataFrame，包含时间、开盘、收盘、最高、最低、成交量等列
        返回例子：
              symbol region  last_price  prev_close   open  high    low   volume        amount      timestamp  trade_date           trade_time   ext.type ext.name  ext.change_pct  ext.change_amount  ext.amplitude  ext.turnover_rate
              688549.SH     CN       23.61        22.7  22.03  24.9  21.91  1114340  2.653530e+09  1784876401000  2026-07-24  2026-07-24 15:00:01  cn_equity    中巨芯-U        0.040088               0.91       0.131718           0.189089
        """
        self.logger.debug(f"开始获取股票 {symbol} 的实时数据")

        realtime_df = pd.DataFrame()
        try:
            tf_symbol = self.convert_to_tickflow_code(symbol)
            realtime_df = self.tf_free.quotes.get(symbols=[tf_symbol], as_dataframe=True)
            self.logger.info(f"获取到 {symbol} 的实时数据:\n{realtime_df}")

            if realtime_df is not None and not realtime_df.empty:
                return realtime_df
            else:
                self.logger.warning(f"未获取到 {symbol} 的实时数据")
                return realtime_df

        except RateLimitError as e:
            if hasattr(e, 'code') and e.code == 'RATE_LIMITED':
                ms = self.extract_wait_ms(e.message)
                if ms is None:
                    ms = 10000
                self.logger.warning(f"获取股票 {symbol} 实时数据失败，请求频率过快，等待 {ms} 毫秒后重试")
                # 额外缓冲0.2s防止卡点
                time.sleep(ms / 1000 + 0.2)
                return self.get_stock_realtime_data(symbol)
        except Exception as e:
            self.logger.error(f"获取股票 {symbol} 实时数据失败: {e}")            
            return realtime_df

    # ===获取标的池所有股票实时数据 - 收费接口 ===
    def get_universes_stock_realtime_data(self, universes: list):
        """
        获取标的池所有股票实时数据
        Args:
            universes: 标的池列表
            
        Returns:
            DataFrame: 包含所有股票实时数据的DataFrame，包含时间、开盘、收盘、最高、最低、成交量等列
        """
        self.logger.debug(f"开始获取标的池 {universes} 的所有股票的实时数据")
        realtime_df = pd.DataFrame()
        try:
            realtime_df = self.tf_free.quotes.get(universes=universes, as_dataframe=True)
            self.logger.info(f"获取到标的池 {universes} 的所有股票的实时数据:\n{realtime_df}")
        except RateLimitError as e:
            if hasattr(e, 'code') and e.code == 'RATE_LIMITED':
                ms = self.extract_wait_ms(e.message)
                if ms is None:
                    ms = 10000
                self.logger.warning(f"获取所有股票实时数据失败，请求频率过快，等待 {ms} 毫秒后重试")
                # 额外缓冲0.2s防止卡点
                time.sleep(ms / 1000 + 0.2)
                return self.get_all_stock_realtime_data(universes)
        except Exception as e:
            self.logger.error(f"获取标的池 {universes} 的所有股票实时数据失败: {e}")
            return realtime_df


if __name__ == '__main__':
    # 测试代码
    print("=" * 50)
    print("TickFlow 数据获取测试")
    print("=" * 50)

    import logging
    # 设置日志级别为 DEBUG，以便在控制台看到详细日志
    log_utils.setup_root_logger(
        root_log_level=logging.DEBUG,
        console_level=logging.DEBUG,  # 控制台显示 DEBUG 级别
        file_level=logging.DEBUG
    )

    # 创建全局实例
    tickflow_fetcher = TickFlowDataFetcher()
    # 测试股票代码
    test_symbol = "688549"  # 中巨芯
    
    # # 1. 测试获取基本信息
    # print(f"\n1. 获取 {test_symbol} 的基本信息:")
    # info = tickflow_fetcher.get_stock_basic_info(test_symbol)
    # print(f"基本信息: {info}")
    
    # # 2. 测试获取历史数据
    # print(f"\n2. 获取 {test_symbol} 的历史数据:")
    # hist_data = tickflow_fetcher.get_stock_history_data(test_symbol,  start_date="20260601", end_date="20260630", adjust="qfq")
    # print(f"历史数据形状: {hist_data.shape}")
    # if not hist_data.empty:
    #     print(f"最近5天数据:\n{hist_data.tail()}")
    
    # # 3. 测试获取实时数据
    # print(f"\n3. 获取 {test_symbol} 的实时信息:")
    # realtime = tickflow_fetcher.get_stock_realtime_data(test_symbol)
    # print(f"实时信息: {realtime}")
    
    index_symbols_ths = [
        "000001.SH",   # 上证指数
        "399001.SZ",   # 深证成指
        "399006.SZ",   # 创业板指
        "899050.BJ",   # 北证50
        "000688.SH",   # 科创50
        "000680.SH",   # 科创综指
        "000510.SH",   # 中证A500
        "000300.SH",   # 沪深300
        "000852.SH",   # 中证1000
        "000016.SH",   # 上证50
        "000905.SH",   # 中证500
        "399330.SZ",   # 深证100R
        "000698.SH",   # 科创100
    ]

    index_symbols = [
        # ========== 上证系列 ==========
        "000001.SH",   # 上证综指
        "000016.SH",   # 上证50
        "000010.SH",   # 上证180
        "000688.SH",   # 科创50
        "000698.SH",   # 科创100
        "000699.SH",   # 科创200
        "000680.SH",   # 科创综指

        # ========== 深证系列 ==========
        "399001.SZ",   # 深证成指
        "399006.SZ",   # 创业板指
        "399330.SZ",   # 深证100R
        "399673.SZ",   # 创业板50

        # ========== 中证宽基 ==========
        "000300.SH",   # 沪深300
        "000905.SH",   # 中证500
        "000852.SH",   # 中证1000
        "000906.SH",   # 中证2000
        "000985.SH",   # 中证全指
        "000922.SH",   # 中证红利
        "000510.SH",   # 中证A500

        # ========== 科创创业 ==========
        "931643.SH",   # 双创50

        # ========== 国证系列 ==========
        "399303.SZ",   # 国证2000
        "399317.SZ",   # 国证A指

        # ========== 北证系列 ==========
        "899050.BJ",   # 北证50
        "899601.BJ",   # 北证专精特新
        "899001.BJ"    # 北证综合指数
    ]

    for index_symbol in index_symbols_ths:
        realtime = tickflow_fetcher.get_stock_realtime_data(index_symbol)
        print(f"{index_symbol} 实时信息: {realtime}")
    
    # 5. 测试获取标的池所有股票实时数据
    # print(f"\n5. 获取全部 A 股行情实时数据:")
    # universes=["CN_Equity_A"]
    # realtime_df = tickflow_fetcher.get_universes_stock_realtime_data(universes)
    # print(f"标的池 {universes} 的所有股票实时数据:\n{realtime_df}")

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)