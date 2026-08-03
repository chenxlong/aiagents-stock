"""
智策板块数据采集模块
使用AKShare获取板块相关数据
"""

import akshare as ak
from jinja2.utils import F
import pandas as pd
from datetime import datetime, timedelta
import warnings
import time
import log_utils
import os
from dotenv import load_dotenv
from sector_strategy_db import SectorStrategyDatabase
from utils.akshare_helper import RequestsPatcher
import random
from data_fetch_tickflow import TickFlowDataFetcher
import requests
from bs4 import BeautifulSoup

# 加载环境变量
load_dotenv()

warnings.filterwarnings('ignore')


class SectorStrategyDataFetcher:
    """板块策略数据获取类"""
    
    def __init__(self):
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 1  # 重试延迟（秒）
        self.request_delay = 0.5  # 请求间隔（秒）
        
        # 初始化数据库和日志
        self.database = SectorStrategyDatabase()
        self.logger = log_utils.get_logger(__name__)
        self.tickflow = TickFlowDataFetcher()
        self.logger.debug("[智策] 板块数据获取器初始化完成")
    
    def _safe_request(self, func, *args, **kwargs):
        """安全的请求函数，包含重试机制"""
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                # 添加请求延迟，避免请求过快
                time.sleep(self.request_delay)
                return result
            except Exception as e:
                if attempt < self.max_retries - 1:
                    # 随机抖动，避免请求过快
                    delay = self.retry_delay + random.uniform(0.5, 1.0)
                    self.logger.warning(f"{func.__name__} 请求失败，[{delay:.2f}] 秒后重试... (尝试 {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                else:
                    self.logger.error(f"{func.__name__} 请求失败，已达最大重试次数（{self.max_retries}次）: {e}")
                    return None
    
    def get_all_sector_data(self):
        """
        获取所有板块的综合数据
        
        Returns:
            dict: 包含多个维度的板块数据
        """
        self.logger.info("[智策] 开始获取板块综合数据...")
        
        data = {
            "success": False,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "sectors": {},
            "sector_fund_flow": {},
            "market_overview": {},
            "north_flow": {},
            "news": []
        }
        
        try:
            # 1. 获取行业板块数据
            self.logger.info(" [1/6] 获取行业板块行情...")
            sectors_data = self._get_sector_performance()
            if sectors_data:
                data["sectors"] = sectors_data
                self.logger.info(f" ✓ 成功获取 {len(sectors_data)} 个行业板块数据")
            
            time.sleep(1 + random.uniform(0.5, 1.0))
            # 2. 获取概念板块数据
            self.logger.info(" [2/6] 获取概念板块行情...")
            concept_data = self._get_concept_performance()
            if concept_data:
                data["concepts"] = concept_data
                self.logger.info(f" ✓ 成功获取 {len(concept_data)} 个概念板块数据")
            
            time.sleep(1 + random.uniform(0.5, 1.0))
            # 3. 获取板块资金流向
            self.logger.info(" [3/6] 获取行业资金流向...")
            fund_flow_data = self._get_sector_fund_flow()
            if fund_flow_data:
                data["sector_fund_flow"] = fund_flow_data
                self.logger.info(f" ✓ 成功获取资金流向数据")
            
            time.sleep(1 + random.uniform(0.5, 1.0))
            # 4. 获取市场总体情况
            self.logger.info(" [4/6] 获取市场总体情况...")
            market_data = self._get_market_overview()
            if market_data:
                data["market_overview"] = market_data
                self.logger.info(f" ✓ 成功获取市场概况")
            
            time.sleep(1 + random.uniform(0.5, 1.0))
            # 5. 获取北向资金流向
            self.logger.info(" [5/6] 获取北向资金流向...")
            north_flow = self._get_north_money_flow()
            if north_flow:
                data["north_flow"] = north_flow
                self.logger.info(f" ✓ 成功获取北向资金数据")
            
            time.sleep(1 + random.uniform(0.5, 1.0))
            # 6. 获取财经新闻
            self.logger.info(" [6/6] 获取财经新闻...")
            news_data = self._get_financial_news()
            if news_data:
                data["news"] = news_data
                self.logger.info(f" ✓ 成功获取 {len(news_data)} 条新闻")
            
            data["success"] = True
            self.logger.info("[智策] ✓ 板块数据获取完成！")
            
            # 保存原始数据到数据库
            self._save_raw_data_to_db(data)
            
        except Exception as e:
            self.logger.error(f"[智策] ✗ 数据获取出错: {e}")
            data["error"] = str(e)
        
        return data
    
    def _get_sector_performance(self):
        """获取行业板块表现"""
        try:
            if 0 : # 容易失败
                # 获取行业板块实时行情（使用重试机制）
                with RequestsPatcher():
                    df = self._safe_request(ak.stock_board_industry_name_em)

                if df is not None and not df.empty:
                    self.logger.info(f"[东方财富] 成功获取 {len(df)} 条行业板块行情数据:\n{df}")
                    # 转换为字典格式
                    sectors = {}
                    for idx, row in df.iterrows():
                        sector_name = row.get('板块名称', '')
                        if sector_name:
                            sectors[sector_name] = {
                                "name": sector_name,
                                "change_pct": row.get('涨跌幅', 0),
                                "turnover": row.get('换手率', 0),
                                "total_market_cap": row.get('总市值', 0),
                                "top_stock": row.get('领涨股票', ''),
                                "top_stock_change": row.get('领涨股票-涨跌幅', 0),
                                "up_count": row.get('上涨家数', 0),
                                "down_count": row.get('下跌家数', 0)
                            }
                    self.logger.info(f" [智策] 行业板块数据成功转换为 {len(sectors)} 条字典数据：\n{sectors}")
                    return sectors

            self.logger.info(f"[同花顺] 获取到行业板块行情数据")
            df = self._safe_request(ak.stock_board_industry_summary_ths)
            self.logger.debug(f"[同花顺] 成功获取 {len(df)} 条行业板块行情数据:\n{df}")
            if df is not None and not df.empty:
                # 转换为字典格式
                sectors = {}
                for idx, row in df.iterrows():
                    sector_name = row.get('板块', '')
                    if sector_name:
                        sectors[sector_name] = {
                            "name": sector_name,
                            "change_pct": row.get('涨跌幅', 0),
                            "total_volume": row.get('总成交量', 0), # （万手）
                            "total_amount": row.get('总成交额', 0), # （亿元）
                            "net_flow": row.get('净流入', 0),       # （亿元）
                            "up_count": row.get('上涨家数', 0),
                            "down_count": row.get('下跌家数', 0),
                            "top_stock": row.get('领涨股', ''),
                            "top_stock_price": row.get('领涨股-最新价', 0),
                            "top_stock_change": row.get('领涨股-涨跌幅', 0),
                            "turnover": row.get('换手率', 0),
                            "total_market_cap": row.get('总市值', 0)
                        }
                self.logger.info(f" [智策] 行业板块数据成功转换为 {len(sectors)} 条字典数据：\n{sectors}")
                return sectors
            else:
                self.logger.error(f"[智策] 获取行业板块数据失败")
                return {}
        except Exception as e:
            self.logger.error(f"[智策] 获取行业板块数据失败: {e}")
            return {}
    
    def _get_concept_performance(self):
        """获取概念板块表现"""
        return {}
        try:
            # 获取概念板块实时行情（使用重试机制）
            with RequestsPatcher():
                df = self._safe_request(ak.stock_board_concept_name_em)
            
            if df is not None and not df.empty:
                self.logger.info(f"[东方财富] 成功获取 {len(df)} 条概念板块行情数据:\n{df}")
                
                # 转换为字典格式
                concepts = {}
                for idx, row in df.iterrows():
                    concept_name = row.get('板块名称', '')
                    if concept_name:
                        concepts[concept_name] = {
                            "name": concept_name,
                            "change_pct": row.get('涨跌幅', 0),
                            "turnover": row.get('换手率', 0),
                            "total_market_cap": row.get('总市值', 0),
                            "top_stock": row.get('领涨股票', ''),
                            "top_stock_change": row.get('领涨股票-涨跌幅', 0),
                            "up_count": row.get('上涨家数', 0),
                            "down_count": row.get('下跌家数', 0)
                        }
                self.logger.info(f" [智策] 板块数据成功转换为 {len(concepts)} 条字典数据：\n{concepts}")
                return concepts
            
            # self.logger.warning(f"[东方财富] 未获取到概念板块行情数据，尝试从ths获取...")
            # df = self._safe_request(ak.stock_board_concept_summary_ths)

            # if df is not None and not df.empty:
            #     self.logger.info(f"[同花顺] 成功获取 {len(df)} 条概念板块行情数据:\n{df}")
                
            #     # 转换为字典格式
            #     concepts = {}
            #     for idx, row in df.iterrows():
            #         concept_name = row.get('板块名称', '')
            #         if concept_name:
            #             concepts[concept_name] = {
            #                 "name": concept_name,
            #                 "change_pct": row.get('涨跌幅', 0),
            #                 "turnover": row.get('换手率', 0),
            #                 "total_market_cap": row.get('总市值', 0),
            #                 "top_stock": row.get('领涨股票', ''),
            #                 "top_stock_change": row.get('领涨股票-涨跌幅', 0),
            #                 "up_count": row.get('上涨家数', 0),
            #                 "down_count": row.get('下跌家数', 0)
            #             }
            #     self.logger.info(f" [智策] 板块数据成功转换为 {len(concepts)} 条字典数据：\n {concepts}")
            #     return concepts

            self.logger.error(f"[智策] 获取概念板块数据失败")
            return {}
        except Exception as e:
            self.logger.error(f"[智策] 获取概念板块数据失败: {e}")
            return {}
    
    def _get_sector_fund_flow(self):
        """获取行业资金流向"""
        try:
            if 0 : # 容易失败
                # 获取行业资金流向（使用重试机制）
                with RequestsPatcher():
                    df = self._safe_request(ak.stock_sector_fund_flow_rank, indicator="今日")
                
                if df is not None and not df.empty:
                    self.logger.info(f"[东方财富] 成功获取 {len(df)} 条行业资金流向数据:\n{df}")
                    # 转换为字典格式
                    fund_flow = {
                        "today": [],
                        "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    for idx, row in df.head(50).iterrows():  # 取前50个
                        fund_flow["today"].append({
                            "sector": row.get('名称', ''),
                            "main_net_inflow": row.get('今日主力净流入-净额', 0),
                            "main_net_inflow_pct": row.get('今日主力净流入-净占比', 0),
                            "super_large_net_inflow": row.get('今日超大单净流入-净额', 0),
                            "large_net_inflow": row.get('今日大单净流入-净额', 0),
                            "medium_net_inflow": row.get('今日中单净流入-净额', 0),
                            "small_net_inflow": row.get('今日小单净流入-净额', 0),
                            "change_pct": row.get('今日涨跌幅', 0)
                        })
                    self.logger.info(f" [智策] 行业资金流向数据成功转换为 {len(fund_flow['today'])} 条字典数据：\n {fund_flow}")
                    return fund_flow

            df = ak.stock_fund_flow_industry()
            if df is not None and not df.empty:
                self.logger.info(f"[同花顺] 成功获取 {len(df)} 条行业资金流向数据:\n{df}")
                # 转换为字典格式
                fund_flow = {
                    "today": [],
                    "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                for idx, row in df.iterrows():
                    main_net_inflow = row.get('流入资金', 0)
                    main_net_outflow = row.get('流出资金', 0)
                    net_inflow = row.get('净额', 0)
                    fund_flow["today"].append({
                        "sector": row.get('行业', ''),
                        "change_pct": row.get('行业-涨跌幅', 0),
                        "main_net_inflow": main_net_inflow,
                        "main_net_outflow": main_net_outflow,
                        "net_inflow": net_inflow,
                        "main_net_inflow_pct": round(net_inflow / main_net_inflow * 100, 2) if main_net_inflow != 0 else 0,
                    })
                self.logger.info(f"[智策] 行业资金流向数据成功转换为 {len(fund_flow['today'])} 条字典数据：\n{fund_flow}")
                return fund_flow

            self.logger.error(f"[智策] 获取行业资金流向失败")
            return {}
            
        except Exception as e:
            self.logger.error(f"[智策] 获取行业资金流向失败: {e}")
            return {}
    
    def _get_market_overview(self):
        """获取市场总体情况"""
        try:
            # 获取A股市场统计
            overview = {}
            
            # # 涨跌家数
            # try:
            #     with RequestsPatcher():
            #         df_stat = self._safe_request(ak.stock_zh_a_spot_em)
            #     self.logger.info(f" [Akshare] 成功获取 {len(df_stat)} 条A股市场统计数据:\n{df_stat}")
            #     # ak.stock_zh_index_spot_sina()
            #     if df_stat is not None and not df_stat.empty:
            #         total_count = len(df_stat)
            #         up_count = len(df_stat[df_stat['涨跌幅'] > 0])
            #         down_count = len(df_stat[df_stat['涨跌幅'] < 0])
            #         flat_count = total_count - up_count - down_count
                    
            #         overview["total_stocks"] = total_count
            #         overview["up_count"] = up_count
            #         overview["down_count"] = down_count
            #         overview["flat_count"] = flat_count
            #         overview["up_ratio"] = round(up_count / total_count * 100, 2) if total_count > 0 else 0
                    
            #         # 涨停跌停
            #         limit_up = len(df_stat[df_stat['涨跌幅'] >= 9.5])
            #         limit_down = len(df_stat[df_stat['涨跌幅'] <= -9.5])
            #         overview["limit_up"] = limit_up
            #         overview["limit_down"] = limit_down
            # except:
            #     self.logger.error(f"[智策] 获取A股市场统计数据失败: {e}")
            
            # 涨跌家数
            try:
                df = self._safe_request(ak.stock_market_activity_legu)
                self.logger.info(f"[乐咕乐股] 获取A股市场统计数据:\n{df}")
                if df is not None and not df.empty:
                    data = df.set_index('item')['value'].to_dict()
                    up_count = float(data.get('上涨', 0))
                    down_count = float(data.get('下跌', 0))
                    flat_count = float(data.get('平盘', 0))
                    suspended_count = float(data.get('停牌', 0))
                    limit_up_count = float(data.get('涨停', 0))
                    limit_down_count = float(data.get('跌停', 0))
                    activity_rate = data.get('活跃度', '0%')
                    stat_datetime = data.get('统计日期', 'N/A')

                    total_count = up_count + down_count + flat_count
                    overview["total_stocks"] = total_count
                    overview["up_count"] = up_count
                    overview["down_count"] = down_count
                    overview["flat_count"] = flat_count
                    overview["up_ratio"] = round(up_count / total_count * 100, 2) if total_count > 0 else 0
                    overview["limit_up"] = limit_up_count
                    overview["limit_down"] = limit_down_count
                else:
                    self.logger.error(f"[智策] [乐咕乐股]获取A股市场统计数据失败。")

            except Exception as e:
                self.logger.error(f"[智策] 获取A股市场涨跌家数统计数据失败: {e}")

            time.sleep(1 + random.uniform(0.5, 1))
            # 大盘指数
            try:
                # 上证指数
                # with RequestsPatcher():
                #     df_sh = self._safe_request(ak.stock_zh_index_spot_em, symbol="上证系列指数")
                # self.logger.info(f" [Akshare] 成功获取 {len(df_sh)} 条上证系列指数数据:\n{df_sh}")

                # if df_sh is not None and not df_sh.empty:
                #     overview["sh_index"] = {
                #         "code": "000001",
                #         "name": "上证指数",
                #         "close": df_sh.iloc[0].get('最新价', 0),
                #         "change_pct": df_sh.iloc[0].get('涨跌幅', 0),
                #         "change": df_sh.iloc[0].get('涨跌额', 0)
                #     }
                # 上证指数
                tick_df = self.tickflow.get_stock_realtime_data("000001.SH")
                if tick_df is not None and not tick_df.empty:
                    row_data = tick_df.iloc[0]
                    overview["sh_index"] = {
                        "code": "000001",
                        "name": "上证指数",
                        "close": float(row_data.get("last_price", 0)),
                        "change_pct": float(row_data.get("ext.change_pct", 0)) * 100,
                        "change": float(row_data.get("ext.change_amount", 0))
                    }
                
                time.sleep(1 + random.uniform(0.5, 1))
                # 深证成指
                # with RequestsPatcher():
                #     df_sz = self._safe_request(ak.stock_zh_index_spot_em, symbol="深证系列指数")
                # self.logger.info(f" [Akshare] 成功获取 {len(df_sz)} 条深证系列指数数据:\n{df_sz}")
                
                # if df_sz is not None and not df_sz.empty:
                #     overview["sz_index"] = {
                #         "code": "399001",
                #         "name": "深证成指",
                #         "close": df_sz.iloc[0].get('最新价', 0),
                #         "change_pct": df_sz.iloc[0].get('涨跌幅', 0),
                #         "change": df_sz.iloc[0].get('涨跌额', 0)
                #     }
                # 深证成指
                tick_df = self.tickflow.get_stock_realtime_data("399001.SZ")
                if tick_df is not None and not tick_df.empty:
                    row_data = tick_df.iloc[0]
                    overview["sz_index"] = {
                        "code": "399001",
                        "name": "深证成指",
                        "close": float(row_data.get("last_price", 0)),
                        "change_pct": float(row_data.get("ext.change_pct", 0)) * 100,
                        "change": float(row_data.get("ext.change_amount", 0))
                    }

                time.sleep(1 + random.uniform(0.5, 1))
                # # 创业板指
                # with RequestsPatcher():
                #     df_cyb = self._safe_request(ak.stock_zh_index_spot_em, symbol="中证系列指数")
                # self.logger.info(f" [Akshare] 成功获取 {len(df_cyb)} 条中证系列指数数据:\n{df_cyb}")
                
                # if df_cyb is not None and not df_cyb.empty:
                #     overview["cyb_index"] = {
                #         "code": "399006",
                #         "name": "创业板指",
                #         "close": df_cyb.iloc[0].get('最新价', 0),
                #         "change_pct": df_cyb.iloc[0].get('涨跌幅', 0),
                #         "change": df_cyb.iloc[0].get('涨跌额', 0)
                #     }
                # 创业板指
                tick_df = self.tickflow.get_stock_realtime_data("399006.SZ")
                if tick_df is not None and not tick_df.empty:
                    row_data = tick_df.iloc[0]
                    overview["cyb_index"] = {
                        "code": "399006",
                        "name": "创业板指",
                        "close": float(row_data.get("last_price", 0)),
                        "change_pct": float(row_data.get("ext.change_pct", 0)) * 100,
                        "change": float(row_data.get("ext.change_amount", 0))
                    }
                # 科创综指
                tick_df = self.tickflow.get_stock_realtime_data("000680.SH")
                if tick_df is not None and not tick_df.empty:
                    row_data = tick_df.iloc[0]
                    overview["kcb_index"] = {
                        "code": "000680",
                        "name": "科创综指",
                        "close": float(row_data.get("last_price", 0)),
                        "change_pct": float(row_data.get("ext.change_pct", 0)) * 100,
                        "change": float(row_data.get("ext.change_amount", 0))
                    }
            except Exception as e:
                self.logger.error(f"[智策] 获取大盘指数数据失败: {e}")
            
            self.logger.info(f"[智策] 市场概况数据成功转换为 {len(overview)} 条字典数据：\n{overview}")
            return overview
            
        except Exception as e:
            self.logger.error(f"[智策] 获取市场概况失败: {e}")
            return {}
    
    def _get_north_money_flow(self):
        """获取北向资金流向（优先使用Tushare，失败时使用Akshare）"""
        if 0 : # 收费接口
            # 优先使用Tushare获取沪深港通资金流向
            tushare_token = os.getenv('TUSHARE_TOKEN', '')
            try:
                # 初始化Tushare（如果尚未初始化）
                if not hasattr(self, '_tushare_api'):
                    TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')
                    if TUSHARE_TOKEN:
                        try:
                            import tushare as ts
                            ts.set_token(tushare_token)
                            self._tushare_api = ts.pro_api()
                            self.logger.info(" [Tushare] ✅ 初始化成功")
                        except Exception as e:
                            self.logger.error(f"[Tushare] 初始化失败: {e}")
                            self._tushare_api = None
                    else:
                        self.logger.info(" [Tushare] 未配置Token")
                        self._tushare_api = None
                
                
                # 如果Tushare可用，获取数据
                if hasattr(self, '_tushare_api') and self._tushare_api:
                    self.logger.info(" [Tushare] 正在获取沪深港通资金流向...")
                    
                    # 获取最近30天的数据
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=20)
                    
                    df = self._tushare_api.moneyflow_hsgt(
                        start_date=start_date.strftime('%Y%m%d'),
                        end_date=end_date.strftime('%Y%m%d')
                    )
                    
                    if df is not None and not df.empty:
                        self.logger.info(f" [Tushare] ✅ 成功获取 {len(df)} 条沪深港通资金流向数据:\n {df}")
                        
                        # 按日期降序排列，获取最新数据
                        df = df.sort_values('trade_date', ascending=False)
                        latest = df.iloc[0]
                        
                        # 转换数据格式以匹配原有结构
                        north_flow = {
                            "date": str(latest['trade_date']),
                            "north_net_inflow": float(latest['north_money']),
                            "hgt_net_inflow": float(latest['hgt']),
                            "sgt_net_inflow": float(latest['sgt']),
                            "north_total_amount": float(latest['north_money'])  # Tushare没有总成交金额，使用净流入作为近似值
                        }
                        
                        # 获取历史趋势（最近20天）
                        history = []
                        for idx, row in df.head(20).iterrows():
                            history.append({
                                "date": str(row['trade_date']),
                                "net_inflow": float(row['north_money'])
                            })
                        north_flow["history"] = history
                        self.logger.debug(f" 获取历史趋势（最近20天）:\n {history}")
                        
                        return north_flow
                    else:
                        self.logger.info(" [Tushare] ❌ 未获取到数据")
                else:
                    self.logger.info(" [Tushare] 不可用")
            except Exception as e:
                self.logger.error(f" [Tushare] 获取北向资金失败: {e}")
        
        # Tushare失败，尝试使用Akshare
        try:
            self.logger.info(" [Akshare] 正在获取沪深港通资金流向（备用数据源）...")
            with RequestsPatcher():
                df = self._safe_request(ak.stock_hsgt_fund_flow_summary_em)
            
            if df is not None and not df.empty:
                self.logger.info(f" [Akshare] ✅ 成功获取 {len(df)} 条沪深港通资金流向数据:\n{df}")

                # 1. 拆分北向、南向
                df_north = df[df["资金方向"] == "北向"].copy()
                df_south = df[df["资金方向"] == "南向"].copy()
                # 北向合计：沪股通 + 深股通 (不再披露数据)
                north_inflow_total = df_north["成交净买额"].sum()
                # 南向合计：港股通(沪) + 港股通(深)
                south_inflow_total = df_south["成交净买额"].sum()

                # 获取最新数据
                latest = df.iloc[0]
                
                north_flow = {
                    "date": str(latest.get('交易日', '')),
                    "south_net_inflow": south_inflow_total,
                    "north_net_inflow": "N/A"
                }
                
                # 获取北向资金活跃前10股票
                north_top_active_stocks = self.get_north_top_active_aastocks()
                self.logger.debug(f"获取北向资金活跃前10股票:\n{north_top_active_stocks}")
                if north_top_active_stocks.get("success"):
                    north_flow["north_top_active_stocks"] = north_top_active_stocks
                else:
                    north_flow["north_top_active_stocks"] = {}
                
                return north_flow
            else:
                self.logger.info(" [Akshare] ❌ 未获取到数据")
        except Exception as e:
            self.logger.error(f" [Akshare] 获取北向资金失败: {e}")
        
        # 所有数据源都失败
        self.logger.info(" ❌ 所有数据源均获取失败")
        return {}
    
    def _get_financial_news(self):
        """获取财经新闻"""
        try:
            # 获取东方财富财经新闻（使用重试机制）
            with RequestsPatcher():
                df = self._safe_request(ak.stock_news_em, symbol="全球")
            self.logger.info(f"[Akshare] 成功获取 {len(df)} 条财经新闻数据:\n{df}")
            
            if df is None or df.empty:
                return []
            
            news_list = []
            for idx, row in df.head(100).iterrows():  # 取前100条
                news_list.append({
                    "title": row.get('新闻标题', ''),
                    "content": row.get('新闻内容', ''),
                    "publish_time": str(row.get('发布时间', '')),
                    "source": row.get('文章来源', ''),
                    "url": row.get('新闻链接', '')
                })
            
            return news_list
            
        except Exception as e:
            self.logger.error(f"[Akshare] 获取财经新闻失败: {e}")
            return []
    
    def format_data_for_ai(self, data):
        """
        将数据格式化为适合AI分析的文本格式
        """
        if not data.get("success"):
            return "数据获取失败"
        
        text_parts = []
        
        # 市场概况
        if data.get("market_overview"):
            market = data["market_overview"]
            text_parts.append(f"""
【市场总体情况】
时间: {data.get('timestamp', 'N/A')}
大盘指数:""")
            if market.get("sh_index"):
                sh = market["sh_index"]
                text_parts.append(f"  上证指数: {sh['close']} ({sh['change_pct']:+.2f}%)")
            if market.get("sz_index"):
                sz = market["sz_index"]
                text_parts.append(f"  深证成指: {sz['close']} ({sz['change_pct']:+.2f}%)")
            if market.get("cyb_index"):
                cyb = market["cyb_index"]
                text_parts.append(f"  创业板指: {cyb['close']} ({cyb['change_pct']:+.2f}%)")
            if market.get("kcb_index"):
                kcb = market["kcb_index"]
                text_parts.append(f"  科创板指: {kcb['close']} ({kcb['change_pct']:+.2f}%)")
            
            if market.get("total_stocks"):
                text_parts.append(f"""
市场统计:
  总股票数: {market['total_stocks']}
  上涨: {market['up_count']} (占比{market['up_ratio']:.1f}%)
  下跌: {market['down_count']}
  平盘: {market['flat_count']}
  涨停: {market['limit_up']}
  跌停: {market['limit_down']}
""")

#         # 北向资金
#         if data.get("north_flow"):
#             north = data["north_flow"]
#             text_parts.append(f"""
# 【北向资金流向】
# 日期: {north.get('date', 'N/A')}
# 北向资金净流入: {north.get('north_net_inflow', 0):.2f} 万元
#   沪股通: {north.get('hgt_net_inflow', 0):.2f} 万元
#   深股通: {north.get('sgt_net_inflow', 0):.2f} 万元
# """)
        # 北向资金活跃前10股票
        if data.get("north_flow"):
            north = data["north_flow"]
            north_top_active_stocks = north["north_top_active_stocks"]
            if north_top_active_stocks.get("success"):
                data_date = north_top_active_stocks["数据日期"]
                fgt_df = north_top_active_stocks["沪股通北向TOP10"]
                sgt_df = north_top_active_stocks["深股通北向TOP10"]
                fgt_csv = fgt_df.to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
                sgt_csv = sgt_df.to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
                text_parts.append(f"""
【北向资金活跃表现】
{data_date} 沪股通北向资金活跃前10股票(CSV格式):
{fgt_csv}

{data_date} 深股通北向资金活跃前10股票(CSV格式):
{sgt_csv}
""")
#         # 行业板块表现（前20）
#         if data.get("sectors"):
#             sectors = data["sectors"]
#             sorted_sectors = sorted(sectors.items(), key=lambda x: x[1]["change_pct"], reverse=True)
            
#             text_parts.append(f"""
# 【行业板块表现 TOP20】
# 涨幅榜前10:
# """)
#             for name, info in sorted_sectors[:10]:
#                 text_parts.append(f"  {name}: {info['change_pct']:+.2f}% | 领涨: {info['top_stock']} ({info['top_stock_change']:+.2f}%)")
            
#             text_parts.append(f"""
# 跌幅榜前10:
# """)
#             for name, info in sorted_sectors[-10:]:
#                 text_parts.append(f"  {name}: {info['change_pct']:+.2f}% | 领跌: {info['top_stock']} ({info['top_stock_change']:+.2f}%)")
        
#         # 概念板块表现（前20）
#         if data.get("concepts"):
#             concepts = data["concepts"]
#             sorted_concepts = sorted(concepts.items(), key=lambda x: x[1]["change_pct"], reverse=True)
            
#             text_parts.append(f"""
# 【概念板块表现 TOP20】
# 涨幅榜前10:
# """)
#             for name, info in sorted_concepts[:10]:
#                 text_parts.append(f"  {name}: {info['change_pct']:+.2f}% | 领涨: {info['top_stock']} ({info['top_stock_change']:+.2f}%)")
        
        # 行业板块表现（前20）
        if data.get("sectors"):
            sectors = data["sectors"]
            list_sectors = list(sectors.values())
            df = pd.DataFrame(list_sectors)
            df.rename(columns = {
                "name": '行业板块',
                "change_pct": '涨跌幅',
                "total_volume": '总成交量（万手）',
                "total_amount": '总成交额（亿元）',
                "net_flow": '净流入（亿元）',
                "up_count": '上涨家数',
                "down_count": '下跌家数',
                "top_stock": '领涨股',
                "top_stock_price": '领涨股-最新价',
                "top_stock_change": '领涨股-涨跌幅',
            }, inplace = True)

            df = df.sort_values(by="涨跌幅", ascending=False)
            # 去除无效的两列
            df = df.drop(columns=["turnover", "total_market_cap"])

            top10_csv = df.head(10).to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
            tail10_csv = df.tail(10).to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
            
            text_parts.append(f"""
【行业板块表现】
涨幅榜前10名数据(CSV格式):
{top10_csv}

涨幅榜后10名数据(CSV格式):
{tail10_csv}
""")

        # 板块资金流向（前15）
        if data.get("sector_fund_flow") and data["sector_fund_flow"].get("today"):
            flow = data["sector_fund_flow"]["today"]
            df = pd.DataFrame(flow)
            df.rename(columns = {
                "sector": '行业板块',
                "change_pct": '行业-涨跌幅',
                "main_net_inflow": '流入资金（亿元）',
                "main_net_outflow": '流出资金（亿元）',
                "net_inflow": '净额（亿元）',
                "main_net_inflow_pct": '流入比率（净额/流入资金）',
            }, inplace = True)
            
            df = df.sort_values(by="流入资金（亿元）", ascending=False)
            top15_csv = df.head(15).to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
            text_parts.append(f"""
【行业资金流向】
资金净流入前15名数据(CSV格式):
{top15_csv}
""")
#         # 板块资金流向（前15）
#         if data.get("sector_fund_flow") and data["sector_fund_flow"].get("today"):
#             flow = data["sector_fund_flow"]["today"]
            
#             text_parts.append(f"""
# 【行业资金流向 TOP15】
# 主力资金净流入前15:
# """)
#             sorted_flow = sorted(flow, key=lambda x: x["main_net_inflow"], reverse=True)
#             for item in sorted_flow[:15]:
#                 text_parts.append(f"  {item['sector']}: {item['main_net_inflow']:.2f}万 ({item['main_net_inflow_pct']:+.2f}%) | 涨跌: {item['change_pct']:+.2f}%")
        
        # 重要新闻（前20条）
        if data.get("news"):
            text_parts.append(f"""
【重要财经新闻】""")
            for idx, news in enumerate(data["news"][:20], 1):
                text_parts.append(f"{idx}. [{news['publish_time']}] {news['title']}")
                if news.get('content'):
                    text_parts.append(f"   {news['content'][:500]}...")
        
        ai_overview = "\n".join(text_parts)
        self.logger.info(f"[智策数据] 成功获取市场概况数据:\n {ai_overview}")

        return ai_overview
    
    def _save_raw_data_to_db(self, data):
        """保存原始数据到数据库"""
        try:
            if not data.get("success"):
                self.logger.warning("[智策数据] 数据获取失败，跳过保存")
                return
            
            # 保存板块数据
            if data.get("sectors"):
                # 将字典转换为DataFrame并映射必要列
                sectors_df = pd.DataFrame([
                    {
                        '板块名称': v.get('name', k),
                        '涨跌幅': v.get('change_pct', 0),
                        '成交额': 0,
                        '总市值': v.get('total_market_cap', 0),
                        '市盈率': v.get('pe_ratio', 0),
                        '市净率': v.get('pb_ratio', 0),
                        '最新价': 0,
                        '成交量': 0,
                        'turnover': v.get('turnover', 0)  # 兼容保存方法中的fallback
                    }
                    for k, v in data["sectors"].items()
                ])
                self.database.save_sector_raw_data(
                    data_date=datetime.now().strftime('%Y-%m-%d'),
                    data_type="industry",
                    data_df=sectors_df
                )
                self.logger.info(f"[智策数据] 保存行业板块数据: {len(data['sectors'])} 个板块")
            
            # 保存概念板块数据
            if data.get("concepts"):
                concepts_df = pd.DataFrame([
                    {
                        '板块名称': v.get('name', k),
                        '涨跌幅': v.get('change_pct', 0),
                        '成交额': 0,
                        '总市值': v.get('total_market_cap', 0),
                        '市盈率': v.get('pe_ratio', 0),
                        '市净率': v.get('pb_ratio', 0),
                        '最新价': 0,
                        '成交量': 0,
                        'turnover': v.get('turnover', 0)
                    }
                    for k, v in data["concepts"].items()
                ])
                self.database.save_sector_raw_data(
                    data_date=datetime.now().strftime('%Y-%m-%d'),
                    data_type="concept",
                    data_df=concepts_df
                )
                self.logger.info(f"[智策数据] 保存概念板块数据: {len(data['concepts'])} 个概念")
            
            # 保存资金流向数据
            if data.get("sector_fund_flow"):
                flow_today = data["sector_fund_flow"].get("today", [])
                fund_df = pd.DataFrame([
                    {
                        '行业': item.get('sector', ''),
                        '主力净流入-净额': item.get('main_net_inflow', 0),
                        '主力净流入-净占比': item.get('main_net_inflow_pct', 0),
                        '超大单净流入-净额': item.get('super_large_net_inflow', 0),
                        '超大单净流入-净占比': item.get('super_large_net_inflow_pct', 0),
                        '大单净流入-净额': item.get('large_net_inflow', 0),
                        '大单净流入-净占比': item.get('large_net_inflow_pct', 0)
                    }
                    for item in flow_today
                ])
                if not fund_df.empty:
                    self.database.save_sector_raw_data(
                        data_date=datetime.now().strftime('%Y-%m-%d'),
                        data_type="fund_flow",
                        data_df=fund_df
                    )
                self.logger.info("[智策数据] 保存资金流向数据")
            
            # 保存市场概况数据
            if data.get("market_overview"):
                market = data["market_overview"]
                mo_df = pd.DataFrame([
                    {'名称': '上证指数', '最新价': market.get('sh_index', {}).get('close', 0), '涨跌幅': market.get('sh_index', {}).get('change_pct', 0), '成交量': market.get('sh_index', {}).get('volume', 0), '成交额': market.get('sh_index', {}).get('turnover', 0)},
                    {'名称': '深证成指', '最新价': market.get('sz_index', {}).get('close', 0), '涨跌幅': market.get('sz_index', {}).get('change_pct', 0), '成交量': market.get('sz_index', {}).get('volume', 0), '成交额': market.get('sz_index', {}).get('turnover', 0)},
                    {'名称': '创业板指', '最新价': market.get('cyb_index', {}).get('close', 0), '涨跌幅': market.get('cyb_index', {}).get('change_pct', 0), '成交量': market.get('cyb_index', {}).get('volume', 0), '成交额': market.get('cyb_index', {}).get('turnover', 0)},
                    {'名称': '科创板指', '最新价': market.get('kcb_index', {}).get('close', 0), '涨跌幅': market.get('kcb_index', {}).get('change_pct', 0), '成交量': market.get('kcb_index', {}).get('volume', 0), '成交额': market.get('kcb_index', {}).get('turnover', 0)}
                ])
                self.database.save_sector_raw_data(
                    data_date=datetime.now().strftime('%Y-%m-%d'),
                    data_type="market_overview",
                    data_df=mo_df
                )
                self.logger.info("[智策数据] 保存市场概况数据")
            
            # 保存北向资金数据
            # 注：north_flow结构与原始表不一致，此处暂不保存以避免歧义
            
            # 保存新闻数据
            if data.get("news"):
                self.database.save_news_data(
                    news_list=data["news"],
                    news_date=datetime.now().strftime('%Y-%m-%d'),
                    source="akshare"
                )
                self.logger.info(f"[智策数据] 保存财经新闻: {len(data['news'])} 条")
                
        except Exception as e:
            self.logger.error(f"[智策数据] 保存原始数据失败: {e}")
    
    def get_cached_data_with_fallback(self):
        """获取缓存数据，支持回退机制"""
        try:
            # 首先尝试获取最新数据
            self.logger.info("[智策] 尝试获取最新数据...")
            fresh_data = self.get_all_sector_data()
            
            if fresh_data.get("success"):
                return fresh_data
            
            # 如果获取失败，回退到缓存数据
            self.logger.info("[智策] 获取最新数据失败，尝试加载缓存数据...")
            cached_data = self._load_cached_data()
            
            if cached_data:
                self.logger.info("[智策] ✓ 成功加载缓存数据")
                cached_data["from_cache"] = True
                cached_data["cache_warning"] = "当前显示为缓存数据（24小时内），可能不是最新信息"
                return cached_data
            else:
                self.logger.info("[智策] ✗ 无可用缓存数据")
                return {
                    "success": False,
                    "error": "无法获取数据且无可用缓存",
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
        except Exception as e:
            self.logger.error(f"[智策数据] 获取数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def _load_cached_data(self):
        """加载缓存数据"""
        try:
            # 获取最近的各类数据
            cached_data = {
                "success": True,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "sectors": {},
                "concepts": {},
                "sector_fund_flow": {},
                "market_overview": {},
                "north_flow": {},
                "news": []
            }
            
            # 加载板块数据
            sectors_data = self.database.get_latest_raw_data("sectors")
            if sectors_data:
                cached_data["sectors"] = sectors_data.get("data_content", {})
            
            # 加载概念数据
            concepts_data = self.database.get_latest_raw_data("concepts")
            if concepts_data:
                cached_data["concepts"] = concepts_data.get("data_content", {})
            
            # 加载资金流向数据
            fund_flow_data = self.database.get_latest_raw_data("fund_flow")
            if fund_flow_data:
                cached_data["sector_fund_flow"] = fund_flow_data.get("data_content", {})
            
            # 加载市场概况数据
            market_data = self.database.get_latest_raw_data("market_overview")
            if market_data:
                cached_data["market_overview"] = market_data.get("data_content", {})
            
            # 加载北向资金数据
            north_data = self.database.get_latest_raw_data("north_flow")
            if north_data:
                cached_data["north_flow"] = north_data.get("data_content", {})
            
            # 加载新闻数据
            news_data = self.database.get_latest_news_data()
            if news_data:
                # 仅传递内容列表给下游分析，避免结构不一致
                cached_data["news"] = news_data.get("data_content", [])
            
            # 检查是否有有效数据
            has_data = any([
                cached_data["sectors"],
                cached_data["concepts"],
                cached_data["sector_fund_flow"],
                cached_data["market_overview"],
                cached_data["north_flow"],
                cached_data["news"]
            ])
            
            return cached_data if has_data else None
            
        except Exception as e:
            self.logger.error(f"[智策数据] 加载缓存数据失败: {e}")
            return None

    def get_north_top_active_aastocks(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
            "Referer": "http://www.aastocks.com/"
        }
        url = "https://www.aastocks.com/sc/cnhk/market/top-turnover/northbound"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        result = {}
        result["success"] = False
        
        date_str = ""
        date_div = soup.find("div", id="listDataDateCurrent")
        if date_div:
            date_str = date_div.get_text(strip=True)
        
        result["数据日期"] = date_str
        
        rank_divs = soup.find_all("div", class_="rank")
        for rank_div in rank_divs:
            title_div = rank_div.find("div", class_="rank_title")
            if not title_div:
                continue
            title_text = title_div.get_text(strip=True)
            
            content_div = rank_div.find("div", class_="rank_content")
            if not content_div:
                continue
            table = content_div.find("table")
            if not table:
                continue
            
            rows = []
            tbody = table.find("tbody")
            if not tbody:
                continue
            trs = tbody.find_all("tr")
            for tr in trs:
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                rank = tds[0].get_text(strip=True)
                
                name_td = tds[1]
                a_tag = name_td.find("a")
                if a_tag:
                    stock_name = a_tag.get_text(separator="\n", strip=True).split("\n")[0].strip()
                    symbol_span = a_tag.find("span", class_="symbol")
                    stock_code = symbol_span.get_text(strip=True) if symbol_span else ""
                else:
                    name_code_text = name_td.get_text(strip=True)
                    parts = name_code_text.split()
                    stock_code = parts[-1] if parts else ""
                    stock_name = " ".join(parts[:-1]) if len(parts) > 1 else name_code_text
                
                last_price_text = tds[2].get_text(strip=True)
                turnover = tds[3].get_text(strip=True)
                
                last_price = ""
                change_price = ""
                change_percent = ""
                import re
                match = re.match(r'([\d,.]+)([+-]?[\d.]+)\s*\(([\d.]+%)\)', last_price_text)
                if match:
                    last_price = match.group(1)
                    change_price = match.group(2)
                    raw_percent = match.group(3)
                    if change_price.startswith('+'):
                        change_percent = '+' + raw_percent
                    elif change_price.startswith('-'):
                        change_percent = '-' + raw_percent
                    else:
                        change_percent = raw_percent

                rows.append({
                    "排名": rank,
                    "股票代码": stock_code,
                    "股票名称": stock_name,
                    "最新价": last_price,
                    "涨跌额": change_price,
                    "涨跌幅": change_percent,
                    "成交总额": turnover
                })
            df = pd.DataFrame(rows)
            if "沪股通" in title_text:
                result["success"] = True
                result["沪股通北向TOP10"] = df
            elif "深股通" in title_text:
                result["success"] = True
                result["深股通北向TOP10"] = df

        return result


# 测试函数
if __name__ == "__main__":

    log_utils.setup_root_logger()
    logger = log_utils.get_logger(__name__)

    print("=" * 60)
    print("测试智策板块数据采集模块")
    print("=" * 60)
    fetcher = SectorStrategyDataFetcher()
    
    # try:
    #     df = ak.stock_board_industry_summary_ths()
    #     logger.info(f"成功获取行业板块数据，共 {len(df)} 条记录,\n {df}")

    #     df = ak.stock_board_concept_summary_ths()
    #     logger.info(f"成功获取概念板块数据，共 {len(df)} 条记录,\n {df}")
    # except Exception as e:
    #     logger.error(f"获取行业板块数据失败: {e}")

    # df = ak.stock_hsgt_fund_flow_summary_em()
    # logger.info(f"成功获取资金流向数据，共 {len(df)} 条记录,\n {df}")
    # # 1. 拆分北向、南向
    # df_north = df[df["资金方向"] == "北向"].copy()
    # df_south = df[df["资金方向"] == "南向"].copy()
    # # 北向合计：沪股通 + 深股通
    # north_inflow_total = df_north["成交净买额"].sum()
    # # 南向合计：港股通(沪) + 港股通(深)
    # south_inflow_total = df_south["成交净买额"].sum()
    # # 成交总额 (可能akshare名字不对)
    # #north_total = df_north["资金净流入"].sum()
    # # 成交总额
    # #south_total = df_south["资金净流入"].sum()
    # north_total = 0
    # south_total = 0

    # logger.info(f"北向资金净流入合计(沪+深)：{north_inflow_total:.2f} 亿元，成交总额：{north_total}")
    # logger.info(f"南向资金净流入合计(沪+深)：{south_inflow_total:.2f} 亿元，成交总额：{south_total}")
   
    # # df = ak.stock_hsgt_hist_em(symbol="北向资金")
    # # logger.info(f"成功获取北向资金数据，共 {len(df)} 条记录,\n {df}")
    # # df = ak.stock_hsgt_hist_em(symbol="南向资金")
    # # logger.info(f"成功获取南向资金数据，共 {len(df)} 条记录,\n {df}")

    # data = fetcher.get_north_top_active_aastocks()
    # if "数据日期" in data:
    #     print(f"数据日期: {data['数据日期']}")
    # for name, df in data.items():
    #     if name == "数据日期":
    #         continue
    #     print(f"\n==== {name} ====")
    #     print(df)


    data = fetcher.get_all_sector_data()
    
    if data.get("success"):
        print("\n" + "=" * 60)
        print("数据采集成功！")
        print("=" * 60)
        
        formatted_text = fetcher.format_data_for_ai(data)
        print(formatted_text[:3000])  # 显示前3000字符
        print(f"\n... (总长度: {len(formatted_text)} 字符)")
    else:
        print(f"\n数据采集失败: {data.get('error', '未知错误')}")

