"""
AkShare 数据获取模块
使用 AkShare 库获取股票数据
"""
import time
from utils.akshare_helper import RequestsPatcher
import akshare as ak
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import traceback

class AkShareDataFetcher:
    """基于 AkShare 的股票数据获取类"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.days = 30  # 获取最近30个交易日
        self.logger.info("AkShare 免费客户端初始化成功")

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

    def get_stock_history_data_akshare(self, symbol, start_date=None, end_date=None, adjust='qfq'):
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

    def get_stock_basic_info_akshare(self, symbol):
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

            for retry_count in range(3):
                try:
                    with RequestsPatcher():
                        stock_info = ak.stock_individual_info_em(symbol=symbol)
                        break  # 成功获取到基本信息，跳出循环
                except Exception as e:
                    self.logger.error(f"[Akshare-东方财富] ❌ 获取失败: {e}")
                    if retry_count < 2:
                        delay = (retry_count + 1) * 2
                        self.logger.info(f"[Akshare-东方财富] ⏳ {delay}s 后重试...")
                        time.sleep(delay)
                    else:
                        self.logger.error(f"[Akshare-东方财富] ❌ 已重试 3 次，放弃")
                        return info

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

    def get_stock_realtime_info_sina(self, symbol):
        """
        使用新浪财经数据源，获取股票实时信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票实时信息
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
         # 尝试新浪单只股票接口获取实时信息
        try:
            import requests as req
            tx_code = self._convert_to_tx_code(symbol)
            url = f'https://hq.sinajs.cn/list={tx_code}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            }
            r = req.get(url, headers=headers, timeout=10)
            self.logger.info(f"[新浪个股] 获取到实时信息:\n{r.text} ")
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
                        self.logger.info(f"[新浪个股] ✅ 成功获取实时信息: {info}")
                        return info
        except Exception as e:
            self.logger.error(f"[新浪个股] ❌ 获取失败: {e}")

        return info

akshare_data_fetcher = AkShareDataFetcher()
    
if __name__ == '__main__':
    # 测试代码
    print("=" * 50)
    print("Akshare 数据获取测试")
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
    
    # 1. 测试获取基本信息(东方财富  
    # NG  ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))
    print(f"\n1. 获取 {test_symbol} 的基本信息:")
    info = akshare_data_fetcher.get_stock_basic_info_akshare(test_symbol)
    print(f"基本信息: {info}")
    
    # 2. 测试获取历史数据
    print(f"\n2. 获取 {test_symbol} 的历史数据:")
    hist_data = akshare_data_fetcher.get_stock_history_data_akshare(test_symbol,start_date="20260601",end_date="20260630",adjust="qfq")
    print(f"历史数据形状: {hist_data.shape}")
    if not hist_data.empty:
        print(f"最近5天数据:\n{hist_data.tail()}")
    
    # 3. 测试获取实时数据
    print(f"\n3. 获取 {test_symbol} 的实时信息:")
    realtime = akshare_data_fetcher.get_stock_realtime_info_sina(test_symbol)
    print(f"实时信息: {realtime}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)