"""
TickFlow 数据获取模块
使用 TickFlow 库获取股票数据
pip install tickflow
"""

from tickflow import TickFlow
from datetime import datetime, timedelta
import pandas as pd
import log_utils

class TickFlowDataFetcher:
    """基于 TickFlow 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.tf_free = TickFlow.free()
        self.logger.info("TickFlow 免费客户端初始化成功")

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
    
    # 1. 测试获取基本信息
    print(f"\n1. 获取 {test_symbol} 的基本信息:")
    info = tickflow_fetcher.get_stock_basic_info(test_symbol)
    print(f"基本信息: {info}")
    
    # 2. 测试获取历史数据
    print(f"\n2. 获取 {test_symbol} 的历史数据:")
    hist_data = tickflow_fetcher.get_stock_history_data(test_symbol,  start_date="20260601", end_date="20260630", adjust="qfq")
    print(f"历史数据形状: {hist_data.shape}")
    if not hist_data.empty:
        print(f"最近5天数据:\n{hist_data.tail()}")
    
    # # 3. 测试获取实时数据
    # print(f"\n3. 获取 {test_symbol} 的实时信息:")
    # realtime = tickflow_fetcher.get_stock_realtime_data(test_symbol)
    # print(f"实时信息: {realtime}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)