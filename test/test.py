
import sys
import os

# 添加项目根目录到路径，以便导入 utils 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
from utils.akshare_helper import RequestsPatcher

ts.set_token('')
tushare_api = ts.pro_api()

ts_code = '688549.SH'
start_date = '20260601'
end_date = '20260630'
adj = 'qfq'

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
            df = tushare_api.daily(
                                ts_code=symbol,
                                start_date=start_date,
                                end_date=end_date,
                                adj=adj
                            )
            return df
        except Exception as e:
            print(f"[Tushare] ❌ 获取失败: {e}")
            print(f"[Tushare] 错误类型: {type(e).__name__}")
            print(f"[Tushare] 股票代码: {symbol}, ts_code: {ts_code}")
            print(f"[Tushare] 日期范围: {start_date} ~ {end_date}")
            import traceback
            print(f"[Tushare] 完整错误堆栈:\n{traceback.format_exc()}")
        
        return None


def _get_stock_info_akshare(symbol):
        """
        使用akshare数据源，获取股票信息
        
        Args:
            symbol: 股票代码（6位数字）
            
        Returns:
            DataFrame: 包含股票信息的DataFrame
        """
        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=symbol)
            return df
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
            print(f"[Akshare] 错误类型: {type(e).__name__}")
            print(f"[Akshare] 股票代码: {symbol}")
            import traceback
            print(f"[Akshare] 完整错误堆栈:\n{traceback.format_exc()}")
            return None
        

# 新浪基础信息
def _get_stock_info_akshare_sina(symbol):
        """
        使用akshare数据源，获取股票信息
        
        Args:
            symbol: 股票代码（6位数字）
            
        Returns:
            DataFrame: 包含股票信息的DataFrame
        """
        try:

            import akshare as ak
            df = None
            with RequestsPatcher():
                df = ak.stock_individual_basic_info_xq(symbol=symbol)
            return df
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
            print(f"[Akshare] 错误类型: {type(e).__name__}")
            print(f"[Akshare] 股票代码: {symbol}")
            import traceback
            print(f"[Akshare] 完整错误堆栈:\n{traceback.format_exc()}")
            return None
        

if __name__ == '__main__':
    # df = _get_stock_hist_data_tushare(ts_code, start_date, end_date, adj)
    # print(df)
    # df = _get_stock_info_akshare('000001')
    # print(df)
    df = _get_stock_info_akshare_sina('sh688549')
    print(df)
