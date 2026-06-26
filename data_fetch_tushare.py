"""
tushare 数据获取模块
使用 tushare 库获取股票数据
"""
import os
import tushare as ts
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import traceback
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class TushareDataFetcher:
    """基于 tushare 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.tushare_token = os.getenv('TUSHARE_TOKEN', '')
        self.tushare_available = False
        self.tushare_api = None
        # 初始化tushare
        if self.tushare_token:
            try:
                ts.set_token(self.tushare_token)
                self.tushare_api = ts.pro_api()
                self.tushare_available = True
                self.logger.info("✅ Tushare数据源初始化成功")
            except Exception as e:
                self.logger.error(f"⚠️ Tushare数据源初始化失败: {e}")
                self.tushare_available = False
        else:
            self.logger.error("ℹ️ 未配置Tushare Token，Tushare数据源初始化失败")
    
    def convert_to_ts_code(self, symbol):
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
    

    ## 是不复权的历史数据
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
        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的历史数据")
            return None
        
        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的历史数据（备用数据源）...")
            
            # 转换股票代码格式（添加市场后缀）
            ts_code = self.convert_to_ts_code(symbol)
            
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

    ##  基本不可用 第一次成功 (stock_basic)频率超限(1次/小时)，
    def get_stock_basic_info_tushare(self, symbol):
        """
        使用tushare数据源，获取股票基本信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票基本信息
        """

        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的基本信息")
            return None

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
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的基本信息（备用数据源）...")
            
            ts_code = self.convert_to_ts_code(symbol)
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


    ## 基本不可用 第一次成功 (daily_basic)频率超限(1次/小时)
    def get_stock_basic_info_tushare2(self, symbol):
        """
        使用tushare数据源，获取股票详细信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票详细信息
        """
        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的详细信息")
            return None

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
            ts_code = self.convert_to_ts_code(symbol)
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

    ## 非实时数据，基本不可用 第一次成功 (daily)频率超限(1次/小时)
    def get_stock_realtime_data_tushare(self, symbol):
        """
        使用tushare数据源，获取股票实时数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票实时数据
        """

        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的实时数据")
            return None

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
            
            ts_code = self.convert_to_ts_code(symbol)
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

    # 权限不够 无法获取  请在tushare官网申请权限
    def get_financial_data_tushare(self, symbol, report_type='income'):
        """
        获取财务数据（tushare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的财务数据")
            return None

        df = None
        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的财务数据（备用数据源）...")
            
            ts_code = self._convert_to_ts_code(symbol)
            
            if report_type == 'income':
                df = self.tushare_api.income(ts_code=ts_code)
            elif report_type == 'balance':
                df = self.tushare_api.balancesheet(ts_code=ts_code)
            elif report_type == 'cashflow':
                df = self.tushare_api.cashflow(ts_code=ts_code)
            else:
                df = None
            
            if df is not None and not df.empty:
                self.logger.info(f"[Tushare] ✅ 成功获取财务数据:\n{df}")
                return df
        except Exception as e:
            self.logger.error(f"[Tushare] ❌ 获取失败: {e}")
        
        return df

    # 权限不够 无法获取  请在tushare官网申请权限
    def get_individual_fund_flow_tushare(self, symbol, market):
        """获取个股资金流向数据（tushare）"""
        if not self.tushare_available:
            self.logger.warning(f"⚠️ Tushare数据源未初始化，无法获取 {symbol} 的资金流向数据")
            return None
        
        df = None
        try:
            self.logger.info(f"[Tushare] 正在获取资金流向数据（备用数据源）...")
            ts_code = self._convert_to_ts_code(symbol)
            
            # 计算日期范围（最近N个交易日）
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=self.days)).strftime('%Y%m%d')
            
            # 获取资金流向数据
            df = self.tushare_api.moneyflow(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            self.logger.info(f"[Tushare] -资金流向原始数据: {df}")
            
            if df is not None and not df.empty:
                # 标准化列名以匹配akshare格式
                df = df.rename(columns={
                    'trade_date': '日期',
                    'buy_sm_amount': '小单买入',
                    'sell_sm_amount': '小单卖出',
                    'buy_md_amount': '中单买入',
                    'sell_md_amount': '中单卖出',
                    'buy_lg_amount': '大单买入',
                    'sell_lg_amount': '大单卖出',
                    'buy_elg_amount': '超大单买入',
                    'sell_elg_amount': '超大单卖出',
                    'net_mf_amount': '净额'
                })
                
                # 限制为最近N天
                df = df.head(self.days)
                self.logger.info(f"[Tushare] ✅ 成功获取 {len(df)} 条资金流向数据")
            else:
                self.logger.warning(f"[Tushare] ❌ 未找到资金流向数据")
                return None
        except Exception as te:
            self.logger.error(f"[Tushare] ❌ 获取失败: {te}")
            return None
        return df


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
    tushare_fetcher = TushareDataFetcher()
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