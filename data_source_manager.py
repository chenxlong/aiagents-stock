"""
数据源管理器
实现akshare和tushare的自动切换机制
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import log_utils
import traceback

# 加载环境变量
load_dotenv()

# ============================================================
# 关键修复: 在引入 akshare 之前打上请求补丁
# 为所有 requests 请求注入 User-Agent 等请求头，
# 解决东方财富服务器 RemoteDisconnected 问题
# ============================================================
from utils.akshare_helper import RequestsPatcher


class DataSourceManager:
    """数据源管理器 - 实现akshare与tushare自动切换"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.logger.debug("初始化数据源管理器")
        self.tushare_token = os.getenv('TUSHARE_TOKEN', '')
        self.tushare_available = False
        self.tushare_api = None
        self.days = 30  # 获取最近30个交易日
        
        # 初始化tushare
        if self.tushare_token:
            try:
                import tushare as ts
                ts.set_token(self.tushare_token)
                self.tushare_api = ts.pro_api()
                self.tushare_available = True
                self.logger.info("✅ Tushare数据源初始化成功")
            except Exception as e:
                self.logger.error(f"⚠️ Tushare数据源初始化失败: {e}")
                self.tushare_available = False
        else:
            self.logger.info("ℹ️ 未配置Tushare Token，将仅使用Akshare数据源")

    def setLogLevel(self, level):
        """
        设置日志级别
        Args:
            level: 日志级别（'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'）
        """
        self.logger.level = level
        self.logger.setLevel(level)
        self.logger.info(f"日志级别已设置为 {level}")

    def getLogLevel(self):
        """
        获取当前日志级别
        Returns:
            str: 当前日志级别
        """
        return self.logger.level
    
    def _get_stock_hist_data_akshare(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        使用akshare数据源，获取股票历史数据
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        self.logger.debug(f"开始获取股票 {symbol} 的历史数据（akshare）")
        # 使用akshare（带重试机制）
        for retry_count in range(3):
            try:
                import akshare as ak
                self.logger.info(f"[Akshare-腾讯] 正在获取 {symbol} 的历史数据..." +
                      (f" (第{retry_count+1}次)"))
                
                # 使用腾讯数据源（proxy.finance.qq.com），避免东方财富API屏蔽(ak.stock_zh_a_hist)
                tx_symbol = self._convert_to_tx_code(symbol)

                df = ak.stock_zh_a_hist_tx(
                    symbol=tx_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                self.logger.info(f"[Akshare-腾讯] 获取到 {symbol} 的历史数据:\n {df} ")
                
                if df is not None and not df.empty:
                    # 标准化列名 Tencent 返回列名: ['date', 'open', 'close', 'high', 'low', 'amount']  amount 成交股数（单位：股）
                    df = df.rename(columns={
                        'date': 'date',
                        'open': 'open',
                        'close': 'close',
                        'high': 'high',
                        'low': 'low',
                        'amount': 'amount'
                    })

                    # 基于已有数据，新增三列，其他完全不动
                    # 1. 正常生成前收、涨跌、涨跌幅（百分比）
                    if 'pre_close' not in df.columns:
                        df["pre_close"] = df["close"].shift(1)
                        # 2. 筛选pre_close为空的行（首行），单独修复
                        mask_nan = df["pre_close"].isna()  # 标记NaN行
                        # 空行pre_close赋值为当日开盘价
                        df.loc[mask_nan, "pre_close"] = df.loc[mask_nan, "open"]

                    # 今日涨跌额（元）
                    if 'change' not in df.columns:
                        df["change"] = df["close"] - df["pre_close"]
                    # 今日涨跌幅（百分比）
                    if 'pct_chg' not in df.columns:
                        df["pct_chg"] = ((df["close"] - df["pre_close"]) / df["pre_close"] * 100).round(4)
                    
                    df['date'] = pd.to_datetime(df['date'])
                    # 腾讯 amount 成交股数（单位：股），直接作为成交量（单位：股）
                    if 'volume' not in df.columns and 'amount' in df.columns:
                        df['volume'] = df['amount']
                    # 估算成交量（成交额/均价），作为备选
                    # avg_price = (df['open'] + df['close'] + df['high'] + df['low']) / 4
                    # 均价近似收盘价
                    avg_price = df['close']
                    df['amount'] = df['amount'] * avg_price
                    
                    self.logger.info(f"[Akshare-腾讯] ✅ 成功获取 {len(df)} 条数据：\n {df} ")

                    return df
                else:
                    self.logger.warning(f"[Akshare-腾讯] ⚠️ 获取到空数据，重试中...")
                    time.sleep(1)
                    continue
            except Exception as e:
                self.logger.error(f"[Akshare-腾讯] ❌ 获取失败: {e}")
                if retry_count < 2:
                    delay = (retry_count + 1) * 2
                    self.logger.info(f"[Akshare-腾讯] ⏳ {delay}s 后重试...")
                    time.sleep(delay)
                else:
                    self.logger.error(f"[Akshare-腾讯] ❌ 已重试 3 次，放弃")
        return None

    def _get_stock_hist_data_tushare(self, symbol, start_date=None, end_date=None, adjust='qfq'):
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
            
            df = self.tushare_api.daily(
                                ts_code=ts_code,
                                start_date=start_date,
                                end_date=end_date,
                                adj=adj
                            )
            # 返回列格式：ts_code       date   open   high    low  close  pre_close  change  pct_chg       volume        amount
            # 直接使用 requests 调用 API（绕过 tushare 库的问题）
            # import requests
            # req_params = {
            #     'api_name': 'daily',
            #     'token': self.tushare_token,
            #     'params': {
            #         'ts_code': ts_code,
            #         'start_date': start_date,
            #         'end_date': end_date,
            #         'adj': adj
            #     },
            #     'fields': ''
            # }
            # headers = {
            #     'Content-Type': 'application/json',
            #     'Accept-Encoding': 'gzip, deflate'
            # }
            # res = requests.post('https://api.waditu.com/dataapi/daily', json=req_params, headers=headers, timeout=30)
            
            # # 解析 JSON 响应
            # import json
            # resp_data = res.json()
            
            # # 检查 API 返回码
            # if resp_data.get('code') != 0:
            #     error_msg = resp_data.get('msg', 'Unknown error')
            #     self.logger.error(f"[Tushare] API返回错误: code={resp_data.get('code')}, msg={error_msg}")
            #     return None
            
            # # 提取数据
            # data = resp_data.get('data', {})
            # fields = data.get('fields', [])
            # items = data.get('items', [])
            
            # if not items:
            #     self.logger.warning(f"[Tushare] 未获取到 {symbol} 的数据")
            #     return None
            
            # # 构建 DataFrame
            # df = pd.DataFrame(items, columns=fields)

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

    def get_stock_hist_data(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        获取股票历史数据（优先akshare，失败时使用tushare）
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        self.logger.debug(f"开始获取股票 {symbol} 的历史数据")
        # 标准化日期格式
        if start_date:
            start_date = start_date.replace('-', '')
        if end_date:
            end_date = end_date.replace('-', '')
        else:
            end_date = datetime.now().strftime('%Y%m%d')
        
        # 数据源1，优先使用akshare（带重试机制）
        df = self._get_stock_hist_data_akshare(symbol, start_date, end_date, adjust)
        if df is not None:
            return df
        
        # 数据源2，尝试tushare
        if self.tushare_available:
            df = self._get_stock_hist_data_tushare(symbol, start_date, end_date, adjust)
            if df is not None:
                return df
        
        # 两个数据源都失败
        self.logger.error("❌ 获取股票历史数据，所有数据源均获取失败")
        return None
    
    def _get_stock_basic_info_akshare(self, symbol):
        """
        使用akshare数据源，获取股票基本信息
        
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
            import akshare as ak
            self.logger.info(f"[Akshare-东方财富] 正在获取 {symbol} 的基本信息...")
            
            stock_info = None
            with RequestsPatcher():
                stock_info = ak.stock_individual_info_em(symbol=symbol)

            self.logger.info(f"[Akshare-东方财富] 获取到基本信息:\n {stock_info} ")

            if stock_info is not None and not stock_info.empty:
                for _, row in stock_info.iterrows():
                    key = row['item']
                    value = row['value']
                    
                    if key == '股票简称':
                        info['name'] = value
                    elif key == '所处行业':
                        info['industry'] = value
                    elif key == '上市时间':
                        info['list_date'] = value
                    elif key == '总市值':
                        info['market_cap'] = value
                    elif key == '流通市值':
                        info['circulating_market_cap'] = value
                    elif key == '最新':
                        info['current_price'] = value
                    elif key == '总股本':
                        info['Total_share_capital'] = value
                    elif key == '流通股':
                        info['tradable_share_capital'] = value
                
                self.logger.info(f"[Akshare-东方财富] ✅ 成功获取基本信息")
                return info
        except Exception as e:
            self.logger.error(f"[Akshare-东方财富] ❌ 获取失败: {e}")
            self.logger.error(f"[Tushare] 完整错误堆栈:\n{traceback.format_exc()}")

        return info

    def _get_stock_basic_info_sina(self, symbol):
        """
        使用新浪财经数据源，获取股票基本信息
        
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
         # 尝试新浪单只股票接口获取名称
        try:
            import requests as req
            tx_code = self._convert_to_tx_code(symbol)
            url = f'https://hq.sinajs.cn/list={tx_code}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            }
            r = req.get(url, headers=headers, timeout=10)
            self.logger.info(f"[新浪个股] 获取到基本信息（实时信息）:\n{r.text} ")
            # 返回格式: var hq_str_sh603212="名称,open,pre_close,current,...";
            if r.status_code == 200 and f'hq_str_{tx_code}' in r.text:
                # 提取引号内的数据
                start = r.text.find('"') + 1
                end = r.text.find('"', start)
                if start > 0 and end > start:
                    fields = r.text[start:end].split(',')
                    if len(fields) >= 1 and fields[0]:
                        info['name'] = fields[0]
                        info['open'] = fields[1]
                        info['pre_close'] = fields[2]
                        info['current_price'] = fields[3]
                        info['high'] = fields[4]
                        info['low'] = fields[5]
                        info['volume'] = fields[8]
                        info['amount'] = fields[9]
                        info['market'] = '中国A股'
                        self.logger.info(f"[新浪个股] ✅ 成功获取基本信息: {info}")
                        return info
        except Exception as e:
            self.logger.error(f"[新浪个股] ❌ 获取失败: {e}")

        return info

    def _get_stock_basic_info_tushare(self, symbol):
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
                
                self.logger.info(f"[Tushare] ✅ 成功获取基本信息")
                return info
        except Exception as e:
            self.logger.error(f"[Tushare] ❌ 获取失败: {e}")

        return info

    def _get_stock_basic_info_tushare2(self, symbol):
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

    def get_stock_basic_info(self, symbol):
        """
        获取股票基本信息（优先akshare，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票基本信息
        """
        self.logger.debug(f"开始获取股票 {symbol} 的基本信息")
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
        
        # 优先使用akshare（东方财富）
        info = self._get_stock_basic_info_akshare(symbol)
        if info['name'] != 'N/A':
            return info
        
        # 使用新浪财经（新浪财经）
        info = self._get_stock_basic_info_sina(symbol)
        if info['name'] != 'N/A':
            return info
        
        # akshare失败，尝试tushare（备用数据源）
        if self.tushare_available:
            info = self._get_stock_basic_info_tushare(symbol)
            if info['name'] != 'N/A':
                return info
        
        self.logger.error(f"❌ 获取股票 {symbol} 的基本信息失败")
        return info
    
    def _get_realtime_quotes_akshare(self, symbol):
        """
        获取实时行情数据（akshare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        try:
            import akshare as ak
            self.logger.info(f"[Akshare-东方财富] 正在获取 {symbol} 的实时行情...")
            
            df = ak.stock_zh_a_spot_em()
            stock_df = df[df['代码'] == symbol]
            
            if not stock_df.empty:
                row = stock_df.iloc[0]
                quotes = {
                    'symbol': symbol,
                    'name': row['名称'],
                    'price': row['最新价'],
                    'change_percent': row['涨跌幅'],
                    'change': row['涨跌额'],
                    'volume': row['成交量'],
                    'amount': row['成交额'],
                    'high': row['最高'],
                    'low': row['最低'],
                    'open': row['今开'],
                    'pre_close': row['昨收']
                }
                self.logger.info(f"[Akshare-东方财富] ✅ 成功获取实时行情")
                return quotes
        except Exception as e:
            self.logger.error(f"[Akshare-东方财富] ❌ 获取失败: {e}")
        
        return quotes

    def _get_realtime_quotes_sina(self, symbol):
        """
        获取实时行情数据（新浪财经）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        for retry_count in range(3):
            try:
                import requests as req_sina
                tx_code = self._convert_to_tx_code(symbol)
                url = f'https://hq.sinajs.cn/list={tx_code}'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://finance.sina.com.cn/',
                }
                r = req_sina.get(url, headers=headers, timeout=10)
                self.logger.info(f"[新浪个股] 获取到实时行情:\n {r.text} ")
                
                if r.status_code == 200 and f'hq_str_{tx_code}' in r.text:
                    start = r.text.find('"') + 1
                    end = r.text.find('"', start)
                    if start > 0 and end > start:
                        fields = r.text[start:end].split(',')
                        if len(fields) >= 32:
                            def safe_float(val, default=0):
                                try: return float(val) if val else default
                                except: return default
                            
                            quotes = {
                                'symbol': symbol,
                                'name': fields[0] if fields[0] else '',
                                'open': safe_float(fields[1]),
                                'pre_close': safe_float(fields[2]),
                                'price': safe_float(fields[3]),
                                'high': safe_float(fields[4]),
                                'low': safe_float(fields[5]),
                                'volume': safe_float(fields[8]),
                                'amount': safe_float(fields[9]),
                            }
                            # 计算涨跌幅
                            if quotes['pre_close'] > 0:
                                quotes['change'] = round(quotes['price'] - quotes['pre_close'], 3)
                                quotes['change_percent'] = round(
                                    (quotes['change'] / quotes['pre_close']) * 100, 2
                                )
                            self.logger.info(f"[新浪个股] ✅ 成功获取实时行情:\n {quotes}")
                            return quotes
            except Exception as e:
                self.logger.error(f"[新浪个股] ❌ 获取失败: {e}")
                if retry_count < 2:
                    delay = (retry_count + 1) * 2
                    self.logger.info(f"[新浪个股] ⏳ {delay}s 后重试...")
                    time.sleep(delay)
        
        return quotes

    def _get_realtime_quotes_tushare(self, symbol):
        """
        获取实时行情数据（tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        try:
            self.logger.info(f"[Tushare] 正在获取 {symbol} 的实时行情（备用数据源）...")
            
            ts_code = self._convert_to_ts_code(symbol)

            start_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')

            # 历史日线数据
            df = self.tushare_api.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                quotes = {
                    'symbol': symbol,
                    'price': row['close'],
                    'change_percent': row['pct_chg'],
                    'volume': row['vol'] * 100,
                    'amount': row['amount'] * 1000,
                    'high': row['high'],
                    'low': row['low'],
                    'open': row['open'],
                    'pre_close': row['pre_close']
                }
                self.logger.info(f"[Tushare] ✅ 成功获取实时行情:\n{quotes}")
                return quotes
        except Exception as e:
            self.logger.error(f"[Tushare] ❌ 获取失败: {e}")
        
        return quotes

    def get_realtime_quotes(self, symbol):
        """
        获取实时行情数据（优先akshare，新浪接口，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        
        # 优先使用akshare
        quotes = self._get_realtime_quotes_akshare(symbol)
        if quotes != {}:
            return quotes
        
        # 使用新浪财经接口（比全市场遍历快得多）
        quotes = self._get_realtime_quotes_sina(symbol)
        if quotes != {}:
            return quotes
                    
        # akshare失败，尝试tushare（备用数据源）
        if self.tushare_available:
            quotes = self._get_realtime_quotes_tushare(symbol)
            if quotes != {}:
                return quotes
        
        self.logger.error(f"❌ {symbol}获取实时行情数据失败")
        return quotes
    
    def _get_financial_data_akshare(self, symbol, report_type='income'):
        """
        获取财务数据（akshare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        
        df = None
        # 使用akshare（带重试机制）
        for retry_count in range(3):
            try:
                import akshare as ak
                self.logger.info(f"[Akshare-新浪财经] 正在获取 {symbol} 的财务数据..." + (f" (第{retry_count+1}次)"))
                
                if report_type == 'income':
                    df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
                elif report_type == 'balance':
                    df = ak.stock_financial_report_sina(stock=symbol, symbol="资产负债表")
                elif report_type == 'cashflow':
                    df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
                else:
                    df = None
                
                if df is not None and not df.empty:
                    self.logger.info(f"[Akshare-新浪财经] ✅ 成功获取财务数据:\n{df}")
                    return df
            except Exception as e:
                self.logger.error(f"[Akshare-新浪财经] ❌ 获取失败: {e}")
                if retry_count < 2:
                    delay = (retry_count + 1) * 2
                    self.logger.info(f"[Akshare-新浪财经] ⏳ {delay}s 后重试...")
                    time.sleep(delay)
        return df
    
    def _get_financial_data_tushare(self, symbol, report_type='income'):
        """
        获取财务数据（tushare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        
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

    def get_financial_data(self, symbol, report_type='income'):
        """
        获取财务数据（优先akshare，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        # 优先使用akshare（带重试机制）
        df = self._get_financial_data_akshare(symbol, report_type)
        if df is not None:
            return df
        
        # akshare失败，尝试tushare
        if self.tushare_available:
            df = self._get_financial_data_tushare(symbol, report_type)
            if df is not None:
                return df
        
        self.logger.error(f"❌ {symbol}获取财务数据失败")
        return None
    
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
    
    def _convert_from_ts_code(self, ts_code):
        """
        将tushare格式代码转换为6位代码
        
        Args:
            ts_code: tushare格式代码（如：000001.SZ）
            
        Returns:
            str: 6位股票代码
        """
        if '.' in ts_code:
            return ts_code.split('.')[0]
        return ts_code

    def _convert_to_tx_code(self, symbol):
        """
        将6位股票代码转换为腾讯数据源格式（带 sh/sz 前缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: 腾讯格式代码（如：sh603212, sz000001）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        
        if symbol.startswith('6'):
            return f"sh{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"sz{symbol}"
        elif symbol.startswith('8') or symbol.startswith('4'):
            return f"bj{symbol}"
        else:
            return f"sz{symbol}"

    def _get_individual_fund_flow_akshare(self, symbol, market):
        """获取个股资金流向数据（akshare）"""
        df = None
        akshare_df = None
        import akshare as ak
        for retry_count in range(3):
            try:
                self.logger.info(f"[Akshare] 正在获取资金流向 (市场: {market})..." + (f" (第{retry_count+1}次)"))
                
                akshare_df = ak.stock_individual_fund_flow(stock=symbol, market=market)
                self.logger.debug(f"   [Akshare] -资金流向原始数据: {akshare_df}")

                if akshare_df is not None and not akshare_df.empty:
                    self.logger.info(f"[Akshare] 获取到 {len(akshare_df)} 条资金流向数据")
                    df = akshare_df
                    break
            except Exception as e:
                self.logger.error(f"[Akshare] 获取失败: {e}")
                if retry_count < 2:
                    delay = (retry_count + 1) * 2
                    self.logger.info(f"[Akshare] {delay}s 后重试...")
                    time.sleep(delay)
        return df
    
    def _get_individual_fund_flow_tushare(self, symbol, market):
        """获取个股资金流向数据（tushare）"""
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
    
    def get_individual_fund_flow(self, symbol, market):
        """获取个股资金流向数据（支持akshare和tushare自动切换）"""
        # 优先使用akshare获取资金流向数据
        self.logger.info(f"正在获取资金流向 (市场: {market})...")
        df = None
        df = self._get_individual_fund_flow_akshare(symbol, market)
        
        if df is None or df.empty:
            self.logger.info(f"[Akshare] 未找到资金流向数据，尝试备用数据源...")
            # akshare失败，尝试tushare
            if self.tushare_available:
                df = self._get_individual_fund_flow_tushare(symbol, market)
                if df is None or df.empty:
                    self.logger.warning(f"[Tushare] 未找到资金流向数据")
                    return None
            else:
                return None

        return df

# 全局数据源管理器实例
data_source_manager = DataSourceManager()

if __name__ == "__main__":
    import time
    import concurrent.futures
    import threading
    import logging
    
    # 设置日志级别为 DEBUG，以便在控制台看到详细日志
    log_utils.setup_root_logger(
        root_log_level=logging.DEBUG,
        console_level=logging.DEBUG,  # 控制台显示 DEBUG 级别
        file_level=logging.DEBUG
    )
    print("\n[测试模式] 日志级别已设置为 DEBUG，将显示所有日志输出\n")
    data_source_manager.setLogLevel("DEBUG")
    
    def test_get_stock_hist_data():
        """测试获取股票历史数据"""
        print("\n=== 测试 get_stock_hist_data ===")
        symbols = ["688549", "000001", "600036"]
        for symbol in symbols:
            start_time = time.time()
            df = data_source_manager.get_stock_hist_data(symbol, start_date="2026-06-01", end_date="2026-06-30")
            elapsed = time.time() - start_time
            if df is not None:
                print(f"  {symbol}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test_get_stock_basic_info():
        """测试获取股票基本信息"""
        print("\n=== 测试 get_stock_basic_info ===")
        symbols = ["688549", "000001", "600036", "300750"]
        for symbol in symbols:
            start_time = time.time()
            info = data_source_manager.get_stock_basic_info(symbol)
            elapsed = time.time() - start_time
            if info is not None:
                print(f"  {symbol}: 成功获取信息，公司名称: {info.get('name', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test_get_realtime_quotes():
        """测试获取实时报价"""
        print("\n=== 测试 get_realtime_quotes ===")
        symbols = ["688549", "000001", "600036"]
        for symbol in symbols:
            start_time = time.time()
            quotes = data_source_manager.get_realtime_quotes(symbol)
            elapsed = time.time() - start_time
            if quotes is not None:
                print(f"  {symbol}: 成功获取报价，价格: {quotes.get('price', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test_get_financial_data():
        """测试获取财务数据"""
        print("\n=== 测试 get_financial_data ===")
        symbols = ["688549", "600036"]
        for symbol in symbols:
            for report_type in ['income', 'balance', 'cash']:
                start_time = time.time()
                df = data_source_manager.get_financial_data(symbol, report_type=report_type)
                elapsed = time.time() - start_time
                if df is not None:
                    print(f"  {symbol} {report_type}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
                else:
                    print(f"  {symbol} {report_type}: 获取失败")
    
    def test_get_individual_fund_flow():
        """测试获取个股资金流"""
        print("\n=== 测试 get_individual_fund_flow ===")
        test_cases = [("688549", "sh"), ("000001", "sz")]
        for symbol, market in test_cases:
            start_time = time.time()
            df = data_source_manager.get_individual_fund_flow(symbol, market)
            elapsed = time.time() - start_time
            if df is not None:
                print(f"  {symbol}({market}): 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}({market}): 获取失败")
    
    def stress_test_concurrent_requests():
        """压力测试：并发请求"""
        print("\n=== 压力测试：并发请求 ===")
        symbols = ["688549", "000001", "600036", "300750", "601318", "000858", "002594", "300059"]
        
        def fetch_data(symbol):
            start = time.time()
            df = data_source_manager.get_stock_hist_data(symbol, start_date="2026-06-01", end_date="2026-06-30")
            elapsed = time.time() - start
            return symbol, df is not None, elapsed
        
        # 测试并发请求
        for threads in [4, 8, 16]:
            print(f"\n  并发数: {threads}")
            start_time = time.time()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                futures = [executor.submit(fetch_data, symbol) for symbol in symbols]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]
            
            total_elapsed = time.time() - start_time
            success_count = sum(1 for _, success, _ in results if success)
            avg_time = sum(elapsed for _, _, elapsed in results) / len(results)
            
            print(f"    总耗时: {total_elapsed:.2f}s, 成功率: {success_count}/{len(symbols)}, 平均耗时: {avg_time:.2f}s")
    
    def stress_test_rate_limit():
        """压力测试：请求频率限制"""
        print("\n=== 压力测试：请求频率 ===")
        symbol = "688549"
        request_count = 20
        print(f"  连续请求 {request_count} 次...")
        
        start_time = time.time()
        success_count = 0
        for i in range(request_count):
            df = data_source_manager.get_realtime_quotes(symbol)
            if df is not None:
                success_count += 1
            if i > 0 and i % 5 == 0:
                elapsed = time.time() - start_time
                print(f"    已完成 {i+1}/{request_count} 请求，耗时 {elapsed:.2f}s")
        
        total_elapsed = time.time() - start_time
        print(f"  完成 {request_count} 次请求，耗时 {total_elapsed:.2f}s，成功率: {success_count}/{request_count}")
        print(f"  请求频率: {request_count/total_elapsed:.2f} 请求/秒")
    
    def stress_test_mixed_workload():
        """压力测试：混合工作负载"""
        print("\n=== 压力测试：混合工作负载 ===")
        symbols = ["688549", "000001", "600036"]
        
        def mixed_task(symbol, task_id):
            if task_id % 3 == 0:
                return data_source_manager.get_stock_hist_data(symbol, start_date="2026-06-01", end_date="2026-06-30")
            elif task_id % 3 == 1:
                return data_source_manager.get_stock_basic_info(symbol)
            else:
                return data_source_manager.get_realtime_quotes(symbol)
        
        start_time = time.time()
        tasks = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            for i, symbol in enumerate(symbols * 4):  # 每个股票4次任务
                tasks.append(executor.submit(mixed_task, symbol, i))
            
            results = [f.result() for f in concurrent.futures.as_completed(tasks)]
        
        total_elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r is not None)
        
        print(f"  完成 {len(tasks)} 个混合任务，耗时 {total_elapsed:.2f}s，成功率: {success_count}/{len(tasks)}")
    
    def test__get_stock_hist_data_akshare():
        """测试_获取股票历史数据(akshare)"""
        print("\n=== 测试 _get_stock_hist_data_akshare ===")
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            df = data_source_manager._get_stock_hist_data_akshare(symbol, start_date="20260601", end_date="20260630")
            elapsed = time.time() - start_time
            if df is not None and not df.empty:
                print(f"_get_stock_hist_data_akshare函数测试 success  {symbol}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"_get_stock_hist_data_akshare函数测试 fail  {symbol}: 获取失败")
    
    def test__get_stock_hist_data_tushare():
        """测试_获取股票历史数据(tushare)"""
        print("\n=== 测试 _get_stock_hist_data_tushare ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            df = data_source_manager._get_stock_hist_data_tushare(symbol, start_date="20260601", end_date="20260630")
            elapsed = time.time() - start_time
            if df is not None and not df.empty:
                print(f"_get_stock_hist_data_tushare函数测试 success  {symbol}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"_get_stock_hist_data_tushare函数测试 fail  {symbol}: 获取失败")
    
    def test__get_stock_basic_info_akshare():
        """测试_获取股票基本信息(akshare)"""
        print("\n=== 测试 _get_stock_basic_info_akshare ===")
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            info = data_source_manager._get_stock_basic_info_akshare(symbol)
            elapsed = time.time() - start_time
            if info is not None:
                print(f"  {symbol}: 成功获取信息，公司名称: {info.get('name', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_stock_basic_info_sina():
        """测试_获取股票基本信息(sina)"""
        print("\n=== 测试 _get_stock_basic_info_sina ===")
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            info = data_source_manager._get_stock_basic_info_sina(symbol)
            elapsed = time.time() - start_time
            if info is not None:
                print(f"  {symbol}: 成功获取信息，公司名称: {info.get('name', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_stock_basic_info_tushare():
        """测试_获取股票基本信息(tushare)"""
        print("\n=== 测试 _get_stock_basic_info_tushare ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            info = data_source_manager._get_stock_basic_info_tushare(symbol)
            elapsed = time.time() - start_time
            if info['name'] != "N/A":
                print(f"  {symbol}: 成功获取信息，公司名称: {info.get('name', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_stock_basic_info_tushare2():
        """测试_获取股票基本信息(tushare2)"""
        print("\n=== 测试 _get_stock_basic_info_tushare2 ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            info = data_source_manager._get_stock_basic_info_tushare2(symbol)
            elapsed = time.time() - start_time
            if info['name'] != "N/A":
                print(f"  {symbol}: 成功获取信息，公司名称: {info.get('name', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_realtime_quotes_akshare():
        """测试_获取实时报价(akshare)"""
        print("\n=== 测试 _get_realtime_quotes_akshare ===")
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            quotes = data_source_manager._get_realtime_quotes_akshare(symbol)
            elapsed = time.time() - start_time
            if quotes != {}:
                print(f"  {symbol}: 成功获取报价，价格: {quotes.get('price', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_realtime_quotes_sina():
        """测试_获取实时报价(sina)"""
        print("\n=== 测试 _get_realtime_quotes_sina ===")
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            quotes = data_source_manager._get_realtime_quotes_sina(symbol)
            elapsed = time.time() - start_time
            if quotes != {}:
                print(f"  {symbol}: 成功获取报价，价格: {quotes.get('price', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_realtime_quotes_tushare():
        """测试_获取实时报价(tushare)"""
        print("\n=== 测试 _get_realtime_quotes_tushare ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        symbols = ["688549", "000001"]
        for symbol in symbols:
            start_time = time.time()
            quotes = data_source_manager._get_realtime_quotes_tushare(symbol)
            elapsed = time.time() - start_time
            if quotes != {}:
                print(f"  {symbol}: 成功获取报价，价格: {quotes.get('price', '未知')}，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}: 获取失败")
    
    def test__get_financial_data_akshare():
        """测试_获取财务数据(akshare)"""
        print("\n=== 测试 _get_financial_data_akshare ===")
        symbols = ["688549", "600036"]
        for symbol in symbols:
            for report_type in ['income', 'balance', 'cashflow']:
                start_time = time.time()
                df = data_source_manager._get_financial_data_akshare(symbol, report_type=report_type)
                elapsed = time.time() - start_time
                if df is not None and not df.empty:
                    print(f"  {symbol} {report_type}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
                else:
                    print(f"  {symbol} {report_type}: 获取失败")
    
    def test__get_financial_data_tushare():
        """测试_获取财务数据(tushare)"""
        print("\n=== 测试 _get_financial_data_tushare ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        symbols = ["688549", "600036"]
        for symbol in symbols:
            for report_type in ['income', 'balance', 'cashflow']:
                start_time = time.time()
                df = data_source_manager._get_financial_data_tushare(symbol, report_type=report_type)
                elapsed = time.time() - start_time
                if df is not None and not df.empty:
                    print(f"  {symbol} {report_type}: 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
                else:
                    print(f"  {symbol} {report_type}: 获取失败")
    
    def test__convert_to_ts_code():
        """测试_转换为tushare代码"""
        print("\n=== 测试 _convert_to_ts_code ===")
        test_cases = [
            ("688549", "688549.SH"),
            ("000001", "000001.SZ"),
            ("600036", "600036.SH"),
            ("300750", "300750.SZ"),
        ]
        for symbol, expected in test_cases:
            result = data_source_manager._convert_to_ts_code(symbol)
            status = "✓" if result == expected else f"✗ (期望: {expected}, 实际: {result})"
            print(f"  {symbol} -> {result} {status}")
    
    def test__convert_from_ts_code():
        """测试_从tushare代码转换"""
        print("\n=== 测试 _convert_from_ts_code ===")
        test_cases = [
            ("688549.SH", "688549"),
            ("000001.SZ", "000001"),
            ("600036.SH", "600036"),
            ("300750.SZ", "300750"),
        ]
        for ts_code, expected in test_cases:
            result = data_source_manager._convert_from_ts_code(ts_code)
            status = "✓" if result == expected else f"✗ (期望: {expected}, 实际: {result})"
            print(f"  {ts_code} -> {result} {status}")
    
    def test__convert_to_tx_code():
        """测试_转换为腾讯代码"""
        print("\n=== 测试 _convert_to_tx_code ===")
        test_cases = [
            ("688549", "sh688549"),
            ("000001", "sz000001"),
            ("600036", "sh600036"),
            ("300750", "sz300750"),
        ]
        for symbol, expected in test_cases:
            result = data_source_manager._convert_to_tx_code(symbol)
            status = "✓" if result == expected else f"✗ (期望: {expected}, 实际: {result})"
            print(f"  {symbol} -> {result} {status}")
    
    def test__get_individual_fund_flow_akshare():
        """测试_获取个股资金流(akshare)"""
        print("\n=== 测试 _get_individual_fund_flow_akshare ===")
        test_cases = [("688549", "sh"), ("000001", "sz")]
        for symbol, market in test_cases:
            start_time = time.time()
            df = data_source_manager._get_individual_fund_flow_akshare(symbol, market)
            elapsed = time.time() - start_time
            if df is not None and not df.empty:
                print(f"  {symbol}({market}): 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}({market}): 获取失败")
    
    def test__get_individual_fund_flow_tushare():
        """测试_获取个股资金流(tushare)"""
        print("\n=== 测试 _get_individual_fund_flow_tushare ===")
        if not data_source_manager.tushare_available:
            print("  Tushare不可用，跳过测试")
            return
        test_cases = [("688549", "sh"), ("000001", "sz")]
        for symbol, market in test_cases:
            start_time = time.time()
            df = data_source_manager._get_individual_fund_flow_tushare(symbol, market)
            elapsed = time.time() - start_time
            if df is not None and not df.empty:
                print(f"  {symbol}({market}): 成功获取 {len(df)} 条数据，耗时 {elapsed:.2f}s")
            else:
                print(f"  {symbol}({market}): 获取失败")
    
    # 运行所有测试
    print("=" * 60)
    print("Data Source Manager 测试套件")
    print("=" * 60)
    
    # 私有方法测试
    #test__get_stock_hist_data_akshare()
    #test__get_stock_hist_data_tushare()
# NG    test__get_stock_basic_info_akshare()
    # 实时行情 test__get_stock_basic_info_sina()
# 次数受限    test__get_stock_basic_info_tushare()
# 返回空数据，且次数受限    test__get_stock_basic_info_tushare2()
# NG    test__get_realtime_quotes_akshare()
    # test__get_realtime_quotes_sina()
    #test__get_realtime_quotes_tushare() # 非实时行情
    #test__get_financial_data_akshare()
# 权限不够    test__get_financial_data_tushare()
    # test__convert_to_ts_code()
    # test__convert_from_ts_code()
    # test__convert_to_tx_code()
    # test__get_individual_fund_flow_akshare()
# 权限不够        test__get_individual_fund_flow_tushare()
        
    # 基础功能测试
    test_get_stock_hist_data()
    test_get_stock_basic_info()
    test_get_realtime_quotes()
    test_get_financial_data()
    test_get_individual_fund_flow()
    
    # 压力测试
    stress_test_concurrent_requests()
    stress_test_rate_limit()
    stress_test_mixed_workload()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)