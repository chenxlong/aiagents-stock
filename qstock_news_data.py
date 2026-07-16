"""
新闻数据获取模块
使用akshare获取股票的最新新闻信息（替代qstock）
"""

import pandas as pd
import sys
import io
import warnings
from datetime import datetime, timedelta
from data_source_manager import data_source_manager
import akshare as ak
import log_utils

warnings.filterwarnings('ignore')

# 设置标准输出编码为UTF-8（仅在命令行环境，避免streamlit冲突）
def _setup_stdout_encoding():
    """仅在命令行环境设置标准输出编码"""
    if sys.platform == 'win32' and not hasattr(sys.stdout, '_original_stream'):
        try:
            # 检测是否在streamlit环境中
            import streamlit
            # 在streamlit中不修改stdout
            return
        except ImportError:
            # 不在streamlit环境，可以安全修改
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='ignore')
            except:
                pass

_setup_stdout_encoding()


class QStockNewsDataFetcher:
    """新闻数据获取类"""
    
    def __init__(self):
        self.max_items = 30  # 最多获取的新闻数量
        self.available = True
        self.logger = log_utils.get_logger(__name__)
        self.logger.info("✓ 新闻数据获取器初始化成功")
    
    def get_stock_news(self, symbol):
        """
        获取股票的新闻数据
        
        Args:
            symbol: 股票代码（6位数字）
            
        Returns:
            dict: 包含新闻数据的字典
        """
        self.logger.debug(f"开始获取股票 {symbol} 的新闻数据...")

        data = {
            "symbol": symbol,
            "news_data": None,
            "data_success": False,
            "source": "qstock"
        }
        
        if not self.available:
            data["error"] = "qstock库未安装或不可用"
            return data
        
        # 只支持中国股票
        if not self._is_chinese_stock(symbol):
            data["error"] = "新闻数据仅支持中国A股股票"
            return data
        
        try:
            # 获取新闻数据
            self.logger.info(f"📰 正在获取 {symbol} 的最新新闻...")
            news_data = self._get_news_data(symbol)
            
            if news_data:
                data["news_data"] = news_data
                self.logger.info(f"✓ 成功获取 {len(news_data.get('items', []))} 条新闻")
                data["data_success"] = True
                self.logger.info("✅ 新闻数据获取完成")
            else:
                self.logger.warning("⚠️ 未能获取到新闻数据")
                
        except Exception as e:
            self.logger.error(f"❌ 获取新闻数据失败: {e}")
            data["error"] = str(e)
        
        return data
    
    def _is_chinese_stock(self, symbol):
        """判断是否为中国股票"""
        return symbol.isdigit() and len(symbol) == 6
    
    def _get_news_data(self, symbol):
        """获取新闻数据"""
        try:
            self.logger.info(f"获取新闻...")
            news_items = []
            # 方法1: 东方财富新闻
            news_items = data_source_manager.get_stock_news(symbol)

            # 方法2: 全球财经直播
            if not news_items or len(news_items) < 5:
                ths_news_items = data_source_manager.get_stock_global_news_from_ths()
                if ths_news_items is not None and len(ths_news_items) > 0:
                    news_items.extend(ths_news_items)


            # 方法3: 尝试获取新浪财经新闻
            if not news_items or len(news_items) < 15:
                    #  新浪财经
                    sina_news_items = data_source_manager.get_stock_global_news_from_sina()
                    
                    if sina_news_items is not None and len(sina_news_items) > 0:
                        news_items.extend(sina_news_items)
            
            if not news_items and len(news_items) == 0:
                self.logger.error(f"未找到股票 {symbol} 的新闻")
                return None
            
            # 限制数量
            news_items = news_items[:self.max_items]
            
            return {
                "items": news_items,
                "count": len(news_items),
                "query_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "date_range": "最近新闻"
            }
            
        except Exception as e:
            self.logger.error(f"获取新闻数据异常: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def format_news_for_ai(self, data):
        """
        将新闻数据格式化为适合AI阅读的文本
        """
        self.logger.info(f"将新闻数据格式化为适合AI阅读的文本")
        
        if not data or not data.get("data_success"):
            return "未能获取新闻数据"
        
        text_parts = []
        
        # 新闻数据
        if data.get("news_data"):
            news_data = data["news_data"]
            text_parts.append(f"""
【最新新闻】
查询时间：{news_data.get('query_time', 'N/A')}
时间范围：{news_data.get('date_range', 'N/A')}
新闻数量：{news_data.get('count', 0)}条
""")
            
            for idx, item in enumerate(news_data.get('items', []), 1):
                text_parts.append(f"新闻 {idx}:")
                
                # 优先显示的字段
                priority_fields = ['title', 'date', 'time', 'source', 'content', 'url']
                
                # 先显示优先字段
                for field in priority_fields:
                    if field in item:
                        value = item[field]
                        # 限制content长度
                        if field == 'content' and len(str(value)) > 500:
                            value = str(value)[:500] + "..."
                        text_parts.append(f"  {field}: {value}")
                
                # 再显示其他字段
                for key, value in item.items():
                    if key not in priority_fields and key != 'source':
                        # 跳过过长的字段
                        if len(str(value)) > 500:
                            value = str(value)[:500] + "..."
                        text_parts.append(f"  {key}: {value}")
                
                text_parts.append("")  # 空行分隔
        result_txt = "\n".join(text_parts)
        self.logger.debug(f"新闻数据格式化为适合AI阅读的文本:\n{result_txt}")
        return result_txt


# 测试函数
if __name__ == "__main__":
    log_utils.setup_root_logger()

    print("测试新闻数据获取（akshare数据源）...")
    print("="*60)
    
    fetcher = QStockNewsDataFetcher()
    
    if not fetcher.available:
        print("❌ 新闻数据获取器不可用")
        sys.exit(1)
    
    # 测试股票
    test_symbols = ["000001", "600519"]  # 平安银行、贵州茅台
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"正在测试股票: {symbol}")
        print(f"{'='*60}\n")
        
        data = fetcher.get_stock_news(symbol)
        
        if data.get("data_success"):
            print("\n" + "="*60)
            print("新闻数据获取成功！")
            print("="*60)
            
            formatted_text = fetcher.format_news_for_ai(data)
            print(formatted_text)
        else:
            print(f"\n获取失败: {data.get('error', '未知错误')}")
        
        print("\n")

