"""
数据源管理器
实现akshare和tushare的自动切换机制
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import log_utils
import traceback


from utils.akshare_helper import RequestsPatcher
from data_fetch_akshare import AkshareDataFetcher
from data_fetch_tushare import TushareDataFetcher
from data_fetch_baostock import BaostockDataFetcher
from data_fetch_tickflow import TickFlowDataFetcher


class DataSourceManager:
    """数据源管理器 - 实现akshare与tushare自动切换"""
    
    def __init__(self):
        self.logger = log_utils.get_logger(__name__)
        self.logger.debug("初始化数据源管理器")
        # 客户端实例
        self.akshare_fetcher = AkshareDataFetcher()
        self.tushare_fetcher = TushareDataFetcher()
        self.tickflow_fetcher = TickFlowDataFetcher()

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

        # 历史数据格式
        # history_data = pd.DataFrame(columns=['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'pre_close', 'change', 'pct_chg'])
        
        # 数据源4，尝试baostock
        with BaostockDataFetcher() as client:
            df = client.get_stock_history_data_baostock(symbol, start_date, end_date, adjust)
            if df is not None:
                return df

        # 数据源3，尝试tickflow
        df = self.tickflow_fetcher.get_stock_history_data(symbol, start_date, end_date, adjust)
        if df is not None:
            return df

        # 数据源1，优先使用akshare（带重试机制）
        df = self.akshare_fetcher.get_stock_history_data_akshare(symbol, start_date, end_date, adjust)
        if df is not None:
            return df
        
        # 数据源2，尝试tushare
        df = self.tushare_fetcher.get_stock_history_data_tushare(symbol, start_date, end_date, adjust)
        if df is not None:
            return df
        
        # 两个数据源都失败
        self.logger.error("❌ 获取股票历史数据，所有数据源均获取失败")
        return None
    

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
            "total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }
        
        # 数据源4，尝试baostock
        with BaostockDataFetcher() as client:
            info = client.get_stock_basic_info_baostock(symbol)
            if info['name'] != 'N/A':
                return info

        # 数据源3，尝试tickflow
        info = self.tickflow_fetcher.get_stock_basic_info(symbol)
        if info['name'] != 'N/A':
            return info
        
        # 优先使用akshare（东方财富）
        info = self.akshare_fetcher.get_stock_basic_info_akshare(symbol)
        if info['name'] != 'N/A':
            return info
        
        # akshare失败，尝试tushare（备用数据源）
        info = self.tushare_fetcher.get_stock_basic_info_tushare(symbol)
        if info['name'] != 'N/A':
            return info
        
        self.logger.error(f"❌ 获取股票 {symbol} 的基本信息失败")
        return info
    

    def get_realtime_quotes(self, symbol):
        """
        获取实时行情数据（优先akshare，新浪接口，失败时使用tushare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        
        # 使用新浪财经接口（比全市场遍历快得多）
        quotes = self.akshare_fetcher.get_stock_realtime_info_sina(symbol)
        if quotes != {}:
            return quotes
                    
        # akshare失败，尝试tushare（备用数据源）
        quotes = self.tushare_fetcher.get_stock_realtime_data_tushare(symbol)
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
        

        df = self.tushare_fetcher.get_financial_data_tushare(symbol, report_type)
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


    def get_individual_fund_flow(self, symbol, market):
        """获取个股资金流向数据（支持akshare和tushare自动切换）"""
        # 优先使用akshare获取资金流向数据
        self.logger.info(f"正在获取资金流向 (市场: {market})...")
        df = None
        df = self.akshare_fetcher.get_individual_fund_flow_akshare(symbol, market)
        
        if df is None or df.empty:
            self.logger.info(f"[Akshare] 未找到资金流向数据，尝试备用数据源...")
            
            # akshare失败，尝试tushare
            df = self.tushare_fetcher.get_individual_fund_flow_tushare(symbol, market)
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
    
    
    # 运行所有测试
    print("=" * 60)
    print("Data Source Manager 测试套件")
    print("=" * 60)
    
    # 私有方法测试
    # test__convert_to_ts_code()
    # test__convert_from_ts_code()
    # test__convert_to_tx_code()
        
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