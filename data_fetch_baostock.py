"""
baostock 数据获取模块
使用 baostock 库获取股票数据
pip install baostock

# 自动登陆，退出系统。代码示例：
with BaostockDataFetcher() as client:
        df = client.get_stock_history_data_baostock("sh.600519", "2026-01-01", "2026-06-01")
        print(df.head())
"""
import os
import baostock as bs
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import traceback
import time

class BaostockDataFetcher:
    """基于 baostock 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.is_logged = False

        if self.login():
            self.logger.info("✅ 登录baostock系统成功")
        else:
            self.logger.info("✅ 登录baostock系统失败")

    def __enter__(self):
        """
        进入上下文管理器，自动登录baostock系统
        """
        if not self.is_logged:
            self.login_result = bs.login()
            if self.login_result.error_code != "0":
                raise Exception(f"登录失败：{self.login_result.error_msg}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文管理器，自动登出baostock系统
        """
        # 代码块结束/异常崩溃都会自动登出
        if self.is_logged:
            bs.logout()
            self.logger.info("✅ 登出baostock系统成功")

    def login(self):
        """
        登录baostock系统
        """
        lg = bs.login()
        if lg.error_code == '0':
            self.logger.info(f"登录baostock系统成功")
            self.is_logged = True
        else:
            self.logger.error(f"登录baostock系统失败: {lg.error_msg}")
            self.is_logged = False
        
        return self.is_logged

    def logout(self):
        """
        登出baostock系统
        """
        self.logger.info("登出baostock系统...")
        if self.is_logged:
            bs.logout()
        self.is_logged = False
        return self.is_logged
        
    def convert_to_baostock_code(self, symbol):
        """
        将6位股票代码转换为baostock格式（带市场后缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: baostock格式代码（如：sh.000001）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        
        # 根据代码判断市场
        if symbol.startswith('6'):
            # 上海主板
            return f"sh.{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            # 深圳主板和创业板
            return f"sz.{symbol}"
        elif symbol.startswith('8') or symbol.startswith('4'):
            # 北交所
            return f"bj.{symbol}"
        else:
            # 默认深圳
            return f"sz.{symbol}"
            
    def get_stock_history_data_baostock(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        使用baostock数据源，获取股票历史数据
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        try:
            self.logger.info(f"[Baostock] 正在获取 {symbol} 的历史数据（备用数据源）...")
            
            # 转换股票代码格式（添加市场后缀）
            ts_code = self.convert_to_baostock_code(symbol)
            
            # 转换复权类型
            adj_dict = {'qfq': '2', 'hfq': '1', '': '3'}
            adj = adj_dict.get(adjust, '2')
            
            # 日期格式转换（20240101 -> 2024-01-01）
            if start_date and len(start_date) == 8:
                bs_start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            if end_date and len(end_date) == 8:
                bs_end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
            else:
                bs_end_date = datetime.now().strftime('%Y-%m-%d')

            self.logger.debug(f"[Baostock] 转换后代码: {ts_code}, 开始日期: {bs_start_date}, 结束日期: {bs_end_date}, 复权类型: {adjust}")
            
            # 获取贵州茅台（sh.600519）2023年的前复权日线数据
            rs = bs.query_history_k_data_plus(
                ts_code,
                "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,psTTM,pcfNcfTTM,pbMRQ,isST",
                start_date=bs_start_date,
                end_date=bs_end_date,
                frequency="d",       # 'd'日线, 'w'周线, 'm'月线, '5'/'15'/'30'/'60'分钟线
                adjustflag=adj       # 复权类型：1-后复权，2-前复权，3-不复权（默认）
            )

            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 数据类型转换（Baostock返回的数据默认都是字符串类型）
            df['date'] = pd.to_datetime(df['date'])
            df[['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg', 'peTTM', 'psTTM', 'pcfNcfTTM', 'pbMRQ']] = df[
                ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg', 'peTTM', 'psTTM', 'pcfNcfTTM', 'pbMRQ']].astype(float)

            self.logger.info(f"[Baostock] 获取到 {symbol} 的历史数据:\n{df}")
            
            if df is not None and not df.empty:
                # 标准化列名和数据格式
                df = df.rename(columns={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'pre_close': 'pre_close',
                    'change': 'pct_chg',     # 涨跌幅
                    'turn': 'turn',          # 换手率
                    'isST': 'is_st',
                    'pctChg': 'pct_chg',     # 涨跌幅
                    'peTTM': 'pe_ttm',       # 市盈率（动态）滚动市盈率
                    'psTTM': 'ps_ttm',       # 滚动市销率
                    'pcfNcfTTM': 'pcf_ttm',  # 滚动市现率
                    'pbMRQ': 'pb_mrq',       # 市净率（静态）
                    'volume': 'volume',      # 成交量	单位：股
                    'amount': 'amount',      # 成交额	单位：元
                })
                df['date'] = pd.to_datetime(df['date'])
                # 按日期排序（确保按日期顺序，从早到晚）
                df = df.sort_values('date', ascending=True).reset_index(drop=True)
                
                self.logger.info(f"[Baostock] ✅ 成功获取 {len(df)} 条数据，转换后数据:\n{df}")
                return df
        except Exception as e:
            self.logger.error(f"[Baostock] ❌ 获取失败: {e} 错误类型: {type(e).__name__}")
            self.logger.error(f"[Baostock] 完整错误堆栈:\n{traceback.format_exc()}")
        
        return None

    def get_stock_basic_info_baostock(self, symbol):
        """
        使用baostock数据源，获取股票基本信息
        
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
            "total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }

        try:
            self.logger.info(f"[Baostock] 正在获取 {symbol} 的基本信息（备用数据源）...")
            
            ts_code = self.convert_to_baostock_code(symbol)
            # 获取单只股票的基本信息
            rs_basic = bs.query_stock_basic(code=ts_code)
            # 也可以通过名称查询：rs = bs.query_stock_basic(code_name="浦发银行")
            time.sleep(1)

            data_list_basic = []
            while (rs_basic.error_code == '0') & rs_basic.next():
                # 获取一条记录，将记录合并在一起
                data_list_basic.append(rs_basic.get_row_data())

            df_basic = pd.DataFrame(data_list_basic, columns=rs_basic.fields)
            self.logger.info(f"[Baostock] 获取到基本信息:\n {df_basic} ")

            # 获取股票行业信息
            rs_industry = bs.query_stock_industry(code=ts_code)
            time.sleep(1)
            data_list_industry = []
            while (rs_industry.error_code == '0') & rs_industry.next():
                # 获取一条记录，将记录合并在一起
                data_list_industry.append(rs_industry.get_row_data())
            df_industry = pd.DataFrame(data_list_industry, columns=rs_industry.fields)
            self.logger.info(f"[Baostock] 获取到行业信息:\n {df_industry} ")


            # 查询季频估值指标盈利能力（股票股本信息）
            profit_list = []
            rs_profit = bs.query_profit_data(code=ts_code)
            time.sleep(1)
            while (rs_profit.error_code == '0') & rs_profit.next():
                profit_list.append(rs_profit.get_row_data())
            result_profit = pd.DataFrame(profit_list, columns=rs_profit.fields)
            self.logger.info(f"[Baostock] 获取到季频估值指标盈利能力:\n {result_profit} ")
            
            if df_basic is not None and not df_basic.empty:
                info['name'] = df_basic.iloc[0]['code_name']
                info['industry'] = "N/A"
                info['market'] = "N/A"
                info['list_date'] = df_basic.iloc[0]['ipoDate']
                info['area'] = "N/A"
                info['total_share_capital'] = "N/A"
                info['tradable_share_capital'] = "N/A"
                # 合并行业信息
                if df_industry is not None and not df_industry.empty:
                    info['industry'] = df_industry.iloc[0]['industry']

                # 合并季频估值指标 股本信息
                if result_profit is not None and not result_profit.empty:
                    info['total_share_capital'] = result_profit.iloc[0]['totalShare']
                    info['tradable_share_capital'] = result_profit.iloc[0]['liqaShare']

                self.logger.info(f"[Baostock] ✅ 成功获取基本信息:\n{info}")
                return info
        except Exception as e:
            self.logger.error(f"[Baostock] ❌ 获取失败: {e} 错误类型: {type(e).__name__}")
            self.logger.error(f"[Baostock] 完整错误堆栈:\n{traceback.format_exc()}")

        return info

    def get_stock_realtime_data_baostock(self, symbol):
        """
        使用baostock数据源，获取股票实时数据
        
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
            "total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }
        try:
            self.logger.info(f"[Baostock] 正在获取 {symbol} 的实时数据...")
            
            ts_code = self.convert_to_baostock_code(symbol)
            # 行情数据 ToDo
            df = None
            self.logger.info(f"[Baostock] 获取到实时数据:\n {df} ")
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                realtime_data['current_price'] = row.get('close', 'N/A')
                realtime_data['volume'] = row.get('vol', 'N/A')
                realtime_data['amount'] = row.get('amount', 'N/A')
                realtime_data['open'] = row.get('open', 'N/A')
                realtime_data['high'] = row.get('high', 'N/A')
                realtime_data['low'] = row.get('low', 'N/A')
                realtime_data['close'] = row.get('close', 'N/A')
               
                self.logger.info(f"[Baostock] ✅ 成功获取实时数据")
                return realtime_data
        except Exception as te:
            self.logger.error(f"[Baostock] ❌ 获取失败: {te}")

        return realtime_data

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

    # 创建全局实例
    baostock_fetcher = BaostockDataFetcher()
    # 测试股票代码
    test_symbol = "688549"  # 中巨芯
    
    # 1. 测试获取基本信息
    print(f"\n1. 获取 {test_symbol} 的基本信息:") 
    with BaostockDataFetcher() as client:
        info = client.get_stock_basic_info_baostock(test_symbol)
        print(info)
    
    # 2. 测试获取历史数据
    print(f"\n2. 获取 {test_symbol} 的历史数据:") 
    baostock_fetcher.login()
    hist_data = baostock_fetcher.get_stock_history_data_baostock(test_symbol, start_date="20260601", end_date="20260630", adjust='qfq')
    if not hist_data.empty:
        print(f"最近5天数据:\n{hist_data.tail()}")

    baostock_fetcher.logout()
    # 3. 测试获取实时数据(无测试)

    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)