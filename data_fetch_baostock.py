"""
baostock 数据获取模块
使用 baostock 库获取股票数据
pip install baostock
"""
import os
import baostock as bs
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import traceback
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


##########################################
#2. 获取股票基本信息
import baostock as bs
import pandas as pd

# 登录系统（每次请求前必须调用）
lg = bs.login()
print(f'登录状态: error_code={lg.error_code}, error_msg={lg.error_msg}')

# 获取单只股票的基本信息（例如浦发银行）
rs = bs.query_stock_basic(code="sh.600000")
# 也可以通过名称查询：rs = bs.query_stock_basic(code_name="浦发银行")

data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())

result = pd.DataFrame(data_list, columns=rs.fields)
print("=== 股票基本信息 ===")
print(result)

# 登出系统（操作完成后建议调用）
bs.logout()


#3. 获取历史行情数据（支持复权）
import baostock as bs
import pandas as pd

lg = bs.login()

# 获取贵州茅台（sh.600519）2023年的前复权日线数据
rs = bs.query_history_k_data_plus(
    "sh.600519",
    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
    start_date="2023-01-01",
    end_date="2023-12-31",
    frequency="d",       # 'd'日线, 'w'周线, 'm'月线, '5'/'15'/'30'/'60'分钟线
    adjustflag="2"       # 复权类型：1-后复权，2-前复权，3-不复权（默认）
)

data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())

df = pd.DataFrame(data_list, columns=rs.fields)

# 数据类型转换（Baostock返回的数据默认都是字符串类型）
df['date'] = pd.to_datetime(df['date'])
df[['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg']] = df[
    ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg']].astype(float)

print("=== 历史行情数据 ===")
print(df.head())

bs.logout()

#4. 获取实时行情数据
import baostock as bs
import time

rd = bs.BaoStock()
ret, error_info = rd.login()

if ret == 'success':
    # 订阅实时行情数据（例如浦发银行）
    data_set = rd.subscribe_realtime_data('sh600000')
    
    # 持续接收并打印最新数据（这里仅循环5次作为演示）
    count = 0
    while data_set.error_code == '0' and count < 5:
        data_set.next()
        print("实时数据:", data_set.get_row_data())
        time.sleep(2)  # 暂停2秒，避免过于频繁的请求
        count += 1
else:
    print("登录失败:", error_info)

rd.logout()
##########################################
class BaostockDataFetcher:
    """基于 baostock 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.logger.info("✅ Baostock数据源初始化成功")
           
    
    def _convert_to_ts_code(self, symbol):
        """
        将6位股票代码转换为tushare格式（带市场后缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: tushare格式代码（如：000001.SZ）
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
            
    def get_stock_history_data_tushare(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        使用tushare数据源，获取股票历史数据
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的历史数据（备用数据源）...")
            
            # 转换股票代码格式（添加市场后缀）
            ts_code = self._convert_to_ts_code(symbol)
            
            # 转换复权类型
            adj_dict = {'qfq': 'qfq', 'hfq': 'hfq', '': None}
            adj = adj_dict.get(adjust, 'qfq')
            
            self.logger.debug(f"[Tushare] 转换后代码: {ts_code}, 开始日期: {start_date}, 结束日期: {end_date}, 复权类型: {adjust}")
            
            # daily：日线行情数据 不复权
            df = self.tushare_api.daily(
                                ts_code=ts_code,
                                start_date=start_date,
                                end_date=end_date,
                                adj=adj
                            )
            # 前复权日线数据 您访问接口(adj_factor)频率超限(1次/分钟)，请稍后重试
            # df = ts.pro_bar(
            #     ts_code=ts_code,
            #     api=self.tushare_api,
            #     adj= adj,
            #     freq='D',
            #     start_date=start_date,
            #     end_date=end_date
            # )
            # 返回列格式：ts_code       date   open   high    low  close  pre_close  change  pct_chg       volume        amount
            self.logger.info(f"[Tushare] 获取到 {symbol} 的历史数据:\n{df}")
            
            if df is not None and not df.empty:
                # 标准化列名和数据格式
                df = df.rename(columns={
                    'trade_date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'pre_close': 'pre_close',
                    'change': 'change',
                    'pct_chg': 'pct_chg',
                    'vol': 'volume',
                    'amount': 'amount'
                })
                df['date'] = pd.to_datetime(df['date'])
                # 按日期排序（确保按日期顺序，从早到晚）
                df = df.sort_values('date', ascending=True).reset_index(drop=True)
                
                # 转换成交量单位（tushare单位是手，转换为股）
                df['volume'] = df['volume'] * 100
                # 转换成交额单位（tushare单位是千元，转换为元）
                df['amount'] = df['amount'] * 1000
                
                self.logger.info(f"[Tushare] ✅ 成功获取 {len(df)} 条数据，转换后数据:\n{df}")
                return df
        except Exception as e:
            self.logger.error(f"[Tushare] ❌ 获取失败: {e} 错误类型: {type(e).__name__}")
            self.logger.error(f"[Tushare] 完整错误堆栈:\n{traceback.format_exc()}")
        
        return None

    def get_stock_basic_info_tushare(self, symbol):
        """
        使用tushare数据源，获取股票基本信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票基本信息
        """
        info = {
            "symbol": symbol,
            "name": "N/A",
            "current_price": "N/A",
            "industry": "N/A",
            "market": "N/A",
            "list_date": "N/A",
            "market_cap": "N/A",
            "circulating_market_cap": "N/A",
            "Total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }

        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的基本信息（备用数据源）...")
            
            ts_code = self._convert_to_ts_code(symbol)
            # stock_basic：股票基础信息
            df = self.tushare_api.stock_basic(
                ts_code=ts_code,
                fields='ts_code,name,area,industry,market,list_date'
            )
            self.logger.info(f"[Tushare] 获取到基本信息:\n {df} ")
            
            if df is not None and not df.empty:
                info['name'] = df.iloc[0]['name']
                info['industry'] = df.iloc[0]['industry']
                info['market'] = df.iloc[0]['market']
                info['list_date'] = df.iloc[0]['list_date']
                info['area'] = df.iloc[0]['area']
                
                self.logger.info(f"[Tushare] ✅ 成功获取基本信息:\n{info}")
                return info
        except Exception as e:
            self.logger.error(f"[Tushare] ❌ 获取失败: {e}")

        return info

    def get_stock_basic_info_tushare2(self, symbol):
        """
        使用tushare数据源，获取股票详细信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票详细信息
        """
        info = {
            "symbol": symbol,
            "name": "N/A",
            "current_price": "N/A",
            "industry": "N/A",
            "market": "N/A",
            "list_date": "N/A",
            "market_cap": "N/A",
            "circulating_market_cap": "N/A",
            "Total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }

        self.logger.info(f"[Tushare] 尝试获取详细信息（tushare）...")
        try:
            ts_code = self._convert_to_ts_code(symbol)
            # daily_basic：每日的基础面和技术面指标
            df = self.tushare_api.daily_basic(
                ts_code=ts_code,
                trade_date=datetime.now().strftime('%Y%m%d')
            )
            self.logger.info(f"[Tushare] 获取股票 {symbol} 获取到详细信息:\n {df} ")

            if df is not None and not df.empty:
                row = df.iloc[0]
                info['pe_ratio'] = row.get('pe', 'N/A')
                info['pb_ratio'] = row.get('pb', 'N/A')
                info['market_cap'] = row.get('total_mv', 'N/A')
                self.logger.info(f"[Tushare] ✅ 成功获取部分信息")
        except Exception as te:
            self.logger.error(f"[Tushare] ❌ 获取失败: {te}")

        return info

    def get_stock_realtime_data_tushare(self, symbol):
        """
        使用tushare数据源，获取股票实时数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票实时数据
        """
        realtime_data = {
            "symbol": symbol,
            "current_price": "N/A",
            "volume": "N/A",
            "amount": "N/A",
            "open": "N/A",
            "high": "N/A",
            "low": "N/A",
            "close": "N/A",
            "pe_ratio": "N/A",
            "pb_ratio": "N/A",
            "market_cap": "N/A",
            "circulating_market_cap": "N/A",
            "Total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }
        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的实时数据...")
            
            ts_code = self._convert_to_ts_code(symbol)
            # daily：日线行情数据
            df = self.tushare_api.daily(
                ts_code=ts_code,
                trade_date=datetime.now().strftime('%Y%m%d')
            )
            self.logger.info(f"[Tushare] 获取到实时数据:\n {df} ")
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                realtime_data['current_price'] = row.get('close', 'N/A')
                realtime_data['volume'] = row.get('vol', 'N/A')
                realtime_data['amount'] = row.get('amount', 'N/A')
                realtime_data['open'] = row.get('open', 'N/A')
                realtime_data['high'] = row.get('high', 'N/A')
                realtime_data['low'] = row.get('low', 'N/A')
                realtime_data['close'] = row.get('close', 'N/A')
               

                self.logger.info(f"[Tushare] ✅ 成功获取实时数据")
                return realtime_data
        except Exception as te:
            self.logger.error(f"[Tushare] ❌ 获取失败: {te}")

        return realtime_data



# 创建全局实例
tushare_fetcher = TushareDataFetcher()

if __name__ == '__main__':
    # 测试代码
    print("=" * 50)
    print("tushare 数据获取测试")
    print("=" * 50)
    
    import logging
    # 设置日志级别为 DEBUG，以便在控制台看到详细日志
    log_utils.setup_root_logger(
        root_log_level=logging.DEBUG,
        console_level=logging.DEBUG,  # 控制台显示 DEBUG 级别
        file_level=logging.DEBUG
    )

    # 测试股票代码
    test_symbol = "688549"  # 中巨芯
    
    # 1. 测试获取基本信息
    print(f"\n1. 获取 {test_symbol} 的基本信息:")  # 第一次成功 (stock_basic)频率超限(1次/小时)，
    info = tushare_fetcher.get_stock_basic_info_tushare(test_symbol)
    print(f"基本信息: {info}")

    info2 = tushare_fetcher.get_stock_basic_info_tushare2(test_symbol)  # 第一次成功 (daily_basic)频率超限(1次/小时)
    print(f"基本信息2: {info2}")
    
    # 2. 测试获取历史数据
    print(f"\n2. 获取 {test_symbol} 的历史数据:") 
    hist_data = tushare_fetcher.get_stock_history_data_tushare(test_symbol, start_date="20260601", end_date="20260630", adjust='qfq')
    print(f"历史数据形状: {hist_data.shape}")
    if not hist_data.empty:
        print(f"最近5天数据:\n{hist_data.tail()}")
    
    # 3. 测试获取实时数据
    print(f"\n3. 获取 {test_symbol} 的实时信息:") 
    realtime = tushare_fetcher.get_stock_realtime_data_tushare(test_symbol)
    print(f"实时信息: {realtime}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)