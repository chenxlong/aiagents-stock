"""
市场情绪数据获取和计算模块
使用akshare获取市场情绪相关指标，包括ARBR、恐慌指数、市场资金情绪等
"""

import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta
import warnings
import sys
import io
from data_source_manager import data_source_manager
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


class MarketSentimentDataFetcher:
    """市场情绪数据获取和计算类"""
    
    def __init__(self):
        self.arbr_period = 26  # ARBR计算周期
        self.logger = log_utils.get_logger(__name__)
        self.logger.debug("市场情绪数据获取器初始化")
    
    def get_market_sentiment_data(self, symbol, stock_data=None):
        """
        获取完整的市场情绪分析数据
        
        Args:
            symbol: 股票代码
            stock_data: 股票历史数据（如果已有）
            
        Returns:
            dict: 包含各类市场情绪指标的字典
        """
        self.logger.info(f"   [Akshare] -获取市场情绪数据: {symbol}")

        sentiment_data = {
            "symbol": symbol,
            "arbr_data": None,          # ARBR指标数据
            "market_index": None,       # 大盘指数数据
            "sector_index": None,       # 板块指数数据
            "turnover_rate": None,      # 换手率数据
            "limit_up_down": None,      # 涨跌停数据
            "margin_trading": None,     # 融资融券数据
            "fear_greed_index": None,   # 市场恐慌贪婪指数
            "data_success": False
        }
        
        try:
            # 判断是否为中国股票
            is_chinese = self._is_chinese_stock(symbol)
            
            if is_chinese:
                # 1. 计算ARBR指标
                self.logger.info("📊 正在计算ARBR情绪指标...")
                arbr_data = self._calculate_arbr(symbol, stock_data)
                if arbr_data:
                    sentiment_data["arbr_data"] = arbr_data
                
                # 2. 获取换手率数据
                self.logger.info("📊 正在获取换手率数据...")
                turnover_data = self._get_turnover_rate(symbol, stock_data)
                if turnover_data:
                    sentiment_data["turnover_rate"] = turnover_data
                
                # 3. 获取大盘情绪
                self.logger.info("📊 正在获取大盘情绪数据...")
                market_data = self._get_market_index_sentiment()
                if market_data:
                    sentiment_data["market_index"] = market_data
                
                # 4. 获取涨跌停数据
                self.logger.info("📊 正在获取涨跌停数据...")
                limit_data = self._get_limit_up_down_stats()
                if limit_data:
                    sentiment_data["limit_up_down"] = limit_data
                
                # 5. 获取融资融券数据
                self.logger.info("📊 正在获取融资融券数据...")
                margin_data = self._get_margin_trading_data(symbol)
                if margin_data:
                    sentiment_data["margin_trading"] = margin_data
                
                # 6. 获取市场恐慌指数
                self.logger.info("📊 正在计算市场恐慌指数...")
                fear_greed = self._get_fear_greed_index()
                if fear_greed:
                    sentiment_data["fear_greed_index"] = fear_greed
                
                sentiment_data["data_success"] = True
                self.logger.info("✅ 市场情绪数据获取完成")
            else:
                # 美股的情绪指标（简化版）
                self.logger.info("ℹ️ 美股暂不支持完整的市场情绪数据")
                sentiment_data["error"] = "美股暂不支持完整的市场情绪数据"
            
        except Exception as e:
            self.logger.error(f"❌ 获取市场情绪数据失败: {e}")
            sentiment_data["error"] = str(e)
        
        return sentiment_data
    
    def _is_chinese_stock(self, symbol):
        """判断是否为中国股票"""
        return symbol.isdigit() and len(symbol) == 6
    
    def _calculate_arbr(self, symbol, stock_data=None):
        """
        计算ARBR指标
        AR = (N日内(H-O)之和 / N日内(O-L)之和) × 100
        BR = (N日内(H-CY)之和 / N日内(CY-L)之和) × 100
        """
        try:
            # 如果没有提供stock_data，则重新获取（支持akshare和tushare自动切换）
            if stock_data is None or stock_data.empty:
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=150)).strftime('%Y%m%d')
                
                # 使用数据源管理器获取数据
                df = data_source_manager.get_stock_hist_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust='qfq'
                )
                
                if df is None or df.empty:
                    return None
                
                # 数据源管理器返回的数据列名已经是小写，无需重命名
            else:
                # 使用已有数据
                df = stock_data.copy()
                # 确保列名正确
                if 'Open' in df.columns:
                    df = df.rename(columns={
                        'Open': 'open',
                        'Close': 'close',
                        'High': 'high',
                        'Low': 'low',
                        'Volume': 'volume'
                    })
                df = df.reset_index()
                if 'Date' in df.columns:
                    df = df.rename(columns={'Date': 'date'})
            
            # 确保日期列为datetime类型
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            # 计算各项差值
            df['HO'] = df['high'] - df['open']    # 最高价-开盘价
            df['OL'] = df['open'] - df['low']     # 开盘价-最低价
            df['HCY'] = df['high'] - df['close'].shift(1)  # 最高价-前收
            df['CYL'] = df['close'].shift(1) - df['low']   # 前收-最低价
            
            # 过滤负数（标准BR指标只统计正数部分）
            df['HCY'] = df['HCY'].clip(lower=0)   # 买方力量：最高价超过前收的部分
            df['CYL'] = df['CYL'].clip(lower=0)   # 卖方力量：最低价低于前收的部分
            
            # 计算AR指标 人气指标
            df['AR'] = (df['HO'].rolling(window=self.arbr_period).sum() / 
                       df['OL'].rolling(window=self.arbr_period).sum()) * 100
            
            # 计算BR指标 买卖意愿指标
            df['BR'] = (df['HCY'].rolling(window=self.arbr_period).sum() / 
                       df['CYL'].rolling(window=self.arbr_period).sum()) * 100
            
            # 处理无穷大和空值
            df['AR'] = df['AR'].replace([np.inf, -np.inf], np.nan)
            df['BR'] = df['BR'].replace([np.inf, -np.inf], np.nan)
            
            # 移除空值
            df = df.dropna(subset=['AR', 'BR'])
            
            if df.empty:
                return None
            
            # 获取最新值和统计信息
            latest = df.iloc[-1]
            ar_value = latest['AR']
            br_value = latest['BR']
            
            # 解读ARBR Todo: 现在数据单一，完善ARBR 买卖信号完整量化策略(考虑多数据，ARBR的金叉死叉信号)
            interpretation = self._interpret_arbr(ar_value, br_value)
            
            # 生成交易信号
            signals = self._generate_arbr_signals(ar_value, br_value)
            
            # 计算历史统计
            stats = {
                "ar_mean": df['AR'].mean(),
                "ar_std": df['AR'].std(),
                "ar_min": df['AR'].min(),
                "ar_max": df['AR'].max(),
                "br_mean": df['BR'].mean(),
                "br_std": df['BR'].std(),
                "br_min": df['BR'].min(),
                "br_max": df['BR'].max(),
            }
            
            # 计算信号统计
            df['ar_signal'] = 0
            df['br_signal'] = 0
            df.loc[df['AR'] > 150, 'ar_signal'] = -1
            df.loc[df['AR'] < 70, 'ar_signal'] = 1
            df.loc[df['BR'] > 300, 'br_signal'] = -1
            df.loc[df['BR'] < 50, 'br_signal'] = 1
            df['combined_signal'] = df['ar_signal'] + df['br_signal']
            
            buy_signals = len(df[df['combined_signal'] > 0])
            sell_signals = len(df[df['combined_signal'] < 0])
            neutral_signals = len(df) - buy_signals - sell_signals
            
            signal_stats = {
                "buy_signals": buy_signals,
                "sell_signals": sell_signals,
                "neutral_signals": neutral_signals,
                "total_signals": len(df),
                "buy_ratio": f"{buy_signals/len(df)*100:.1f}%" if len(df) > 0 else "0%",
                "sell_ratio": f"{sell_signals/len(df)*100:.1f}%" if len(df) > 0 else "0%"
            }
            
            return {
                "latest_ar": float(ar_value),
                "latest_br": float(br_value),
                "interpretation": interpretation,
                "signals": signals,
                "statistics": stats,
                "signal_statistics": signal_stats,
                "calculation_date": latest.get('date', datetime.now()).strftime('%Y-%m-%d') if pd.notna(latest.get('date')) else datetime.now().strftime('%Y-%m-%d'),
                "period": self.arbr_period
            }
            
        except Exception as e:
            self.logger.error(f"计算ARBR指标失败: {e}")
            return None
    
    def _interpret_arbr(self, ar_value, br_value):
        """解读ARBR数值的含义"""
        self.logger.info(f"解读ARBR数值的含义 AR={ar_value:.2f}, BR={br_value:.2f}")

        interpretation = []
        
        # AR指标解读
        if ar_value > 180:
            interpretation.append("AR极度超买（>180），市场过热，风险极高，建议谨慎")
        elif ar_value > 150:
            interpretation.append("AR超买（>150），市场情绪过热，注意回调风险")
        elif ar_value < 40:
            interpretation.append("AR极度超卖（<40），市场过冷，可能存在机会")
        elif ar_value < 70:
            interpretation.append("AR超卖（<70），市场情绪低迷，可关注反弹机会")
        else:
            interpretation.append(f"AR处于正常区间（{ar_value:.2f}），市场情绪相对平稳")
        
        # BR指标解读
        if br_value > 400:
            interpretation.append("BR极度超买（>400），投机情绪过热，警惕泡沫")
        elif br_value > 300:
            interpretation.append("BR超买（>300），投机情绪旺盛，注意风险")
        elif br_value < 30:
            interpretation.append("BR极度超卖（<30），投机情绪冰点，可能触底")
        elif br_value < 50:
            interpretation.append("BR超卖（<50），投机情绪低迷，关注企稳信号")
        else:
            interpretation.append(f"BR处于正常区间（{br_value:.2f}），投机情绪适中")
        
        # ARBR关系解读
        if ar_value > 100 and br_value > 100:
            interpretation.append("多头力量强劲（AR>100且BR>100），但需警惕过热风险")
        elif ar_value < 100 and br_value < 100:
            interpretation.append("空头力量占优（AR<100且BR<100），市场情绪偏空")
        
        if ar_value > br_value:
            interpretation.append("人气指标强于意愿指标（AR>BR），市场基础较好，投资者信心相对稳定")
        else:
            interpretation.append("意愿指标强于人气指标（BR>AR），投机性较强，需注意资金稳定性")
        
        return interpretation
    
    def _generate_arbr_signals(self, ar_value, br_value):
        """生成ARBR交易信号"""
        self.logger.info(f"生成ARBR交易信号 AR={ar_value:.2f}, BR={br_value:.2f}")

        signals = []
        signal_strength = 0
        
        # AR信号
        if ar_value > 150:
            signals.append("AR卖出信号")
            signal_strength -= 1
        elif ar_value < 70:
            signals.append("AR买入信号")
            signal_strength += 1
        
        # BR信号
        if br_value > 300:
            signals.append("BR卖出信号")
            signal_strength -= 1
        elif br_value < 50:
            signals.append("BR买入信号")
            signal_strength += 1

        # BRAR金叉信号
        if br_value > ar_value:
            signals.append("BRAR金叉信号")
            signal_strength += 1
        elif br_value < ar_value:
            signals.append("BRAR死叉信号")
            signal_strength -= 1
        
        # 综合信号
        if signal_strength >= 3:
            overall = "强烈买入信号"
        elif signal_strength == 2:
            overall = "买入信号"
        elif signal_strength == -2:
            overall = "卖出信号"
        elif signal_strength <= -3:
            overall = "强烈卖出信号"
        else:
            overall = "中性信号"
        
        return {
            "individual_signals": signals if signals else ["中性"],
            "overall_signal": overall,
            "signal_strength": signal_strength
        }
    
    def _get_turnover_rate(self, symbol, stock_data):
        """获取换手率数据"""
        # 获取最近的换手率数据
        if stock_data is None or stock_data.empty:
            self.logger.debug(f" 正在获取换手率数据...")
            # 获取A股实时行情数据
            df = data_source_manager.get_realtime_quotes(symbol)
            self.logger.debug(f"获取到实时行情数据:\n {df}")
        else:
            df = stock_data

        if df is not None and not df.empty:
            # 最新数据行
            latest_row = df.iloc[-1]
            # 提取换手率
            if 'turn' in df.columns:
                turnover_rate = latest_row['turn']
            else:
                turnover_rate = 'N/A'
            
            # 解读换手率
            interpretation = ""
            if turnover_rate != 'N/A':
                try:
                    turnover = float(turnover_rate)
                    if turnover > 20:
                        interpretation = "换手率极高（>20%），资金活跃度极高，可能存在炒作"
                    elif turnover > 10:
                        interpretation = "换手率较高（>10%），交易活跃"
                    elif turnover > 5:
                        interpretation = "换手率正常（5%-10%），交易适中"
                    elif turnover > 2:
                        interpretation = "换手率偏低（2%-5%），交易相对清淡"
                    else:
                        interpretation = "换手率很低（<2%），交易清淡"
                except:
                    pass
            
            return {
                "current_turnover_rate": turnover_rate,
                "interpretation": interpretation
            }
        
        return None
    
    def _evaluate_market_sentiment(self, sentiment_score, limit_up_count, limit_down_count, limit_ratio, up_ratio):
        """
        综合评估市场情绪（多维度）
        
        Args:
            sentiment_score: 涨跌家数差指数
            limit_up_count: 涨停数量
            limit_down_count: 跌停数量
            limit_ratio: 涨停/跌停比
            up_ratio: 上涨家数占比
            
        Returns:
            str: 综合情绪解读
        """
        # 基础评级
        if sentiment_score > 60:
            base_level = "极端亢奋"
        elif sentiment_score > 40:
            base_level = "强势乐观"
        elif sentiment_score > 20:
            base_level = "偏多"
        elif sentiment_score > 5:
            base_level = "略偏多"
        elif sentiment_score > -5:
            base_level = "中性"
        elif sentiment_score > -20:
            base_level = "略偏空"
        elif sentiment_score > -40:
            base_level = "偏空"
        elif sentiment_score > -60:
            base_level = "弱势悲观"
        else:
            base_level = "极端恐慌"
        
        # 增强因子评估
        factors = []
        
        # 涨停强度评估
        if limit_up_count > 100:
            factors.append(f"涨停家数较多({limit_up_count}家)")
        elif limit_up_count > 50:
            factors.append(f"涨停家数适中({limit_up_count}家)")
        elif limit_up_count > 10:
            factors.append(f"涨停家数偏少({limit_up_count}家)")
        
        # 跌停评估
        if limit_down_count > 50:
            factors.append(f"跌停家数较多({limit_down_count}家)")
        elif limit_down_count > 20:
            factors.append(f"跌停家数适中({limit_down_count}家)")
        
        # 涨跌停比评估
        if limit_ratio > 10:
            factors.append("涨停远超跌停，多头力量强劲")
        elif limit_ratio > 5:
            factors.append("涨停明显多于跌停")
        elif limit_ratio > 2:
            factors.append("涨停多于跌停")
        elif limit_ratio > 0.5:
            factors.append("涨跌停数量相当")
        else:
            factors.append("跌停多于涨停")
        
        # 上涨占比评估
        if up_ratio > 70:
            factors.append(f"上涨家数占比高({up_ratio:.1f}%)")
        elif up_ratio > 60:
            factors.append(f"上涨家数占优({up_ratio:.1f}%)")
        elif up_ratio > 50:
            factors.append(f"上涨家数略多({up_ratio:.1f}%)")
        
        # 综合生成解读
        if factors:
            sentiment = f"市场情绪{base_level}，" + "，".join(factors)
        else:
            sentiment = f"市场情绪{base_level}"
        
        return sentiment
    
    def _get_market_index_sentiment(self):
        """获取大盘指数情绪"""
        try:
            # 获取上证指数数据
            self.logger.debug(f"正在获取大盘指数数据...")
            # 获取上证指数最近15天数据
            # 当前日期
            current_date = datetime.now().strftime("%Y-%m-%d")
            # 计算15天前的日期
            start_date = (datetime.strptime(current_date, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
            sh_index_df = data_source_manager.get_stock_hist_data(symbol="000001", start_date=start_date, end_date=current_date)
            change_pct = 0
            if sh_index_df is not None and not sh_index_df.empty:
                # 最新数据的涨跌幅
                if 'pctChg' in sh_index_df.columns:
                    change_pct = float(sh_index_df.iloc[-1]['pctChg'])
                elif 'pct_chg' in sh_index_df.columns:
                    change_pct = float(sh_index_df.iloc[-1]['pct_chg'])
                    
            # 获取涨跌家数
            try:
                market_sentiment_df = data_source_manager.get_stock_market_activity()
                if market_sentiment_df is not None and not market_sentiment_df.empty:
                    data = market_sentiment_df.set_index('item')['value'].to_dict()
                    up_count = float(data.get('上涨', 0))
                    down_count = float(data.get('下跌', 0))
                    flat_count = float(data.get('平盘', 0))
                    suspended_count = float(data.get('停牌', 0))
                    limit_up_count = float(data.get('涨停', 0))
                    limit_down_count = float(data.get('跌停', 0))
                    activity_rate = data.get('活跃度', '0%')
                    stat_datetime = data.get('统计日期', 'N/A')

                    # 计算总家数
                    total_count = up_count + down_count + flat_count + suspended_count

                    if total_count == 0:
                        return 0
                    
                    # 计算市场情绪指数（涨跌家数差）
                    sentiment_score = (up_count - down_count) / total_count * 100
                    
                    # 计算上涨占比
                    up_ratio = (up_count / total_count) * 100
                    # 计算涨停占比
                    limit_up_ratio = (limit_up_count / up_count) * 100 if up_count > 0 else 0
                    # 计算跌停占比
                    limit_down_ratio = (limit_down_count / down_count) * 100 if down_count > 0 else 0
                    # 计算涨跌停比
                    limit_up_down_ratio = (limit_up_count / limit_down_count) if limit_down_count > 0 else float('inf')
                    
                    # 综合评估市场情绪
                    sentiment = self._evaluate_market_sentiment(
                        sentiment_score, limit_up_count, limit_down_count, 
                        limit_up_down_ratio, up_ratio
                    )
                    
                    self.logger.info(f"综合评估市场情绪: {sentiment}")
                    return {
                        "index_name": "上证指数",
                        "change_percent": change_pct,
                        "up_count": up_count,
                        "down_count": down_count,
                        "flat_count": flat_count,
                        "suspended_count": suspended_count,
                        "total_count": total_count,
                        "limit_up_count": limit_up_count,
                        "limit_down_count": limit_down_count,
                        "activity_rate": activity_rate,
                        "up_ratio": up_ratio,
                        "limit_up_ratio": limit_up_ratio,
                        "limit_down_ratio": limit_down_ratio,
                        "limit_up_down_ratio": limit_up_down_ratio,
                        "sentiment_score": f"{sentiment_score:.2f}",
                        "sentiment_interpretation": sentiment,
                        "stat_datetime": stat_datetime
                    }
            except Exception as e:
                self.logger.error(f"获取大盘指数涨跌家数失败: {e}")
        
        except Exception as e:
            self.logger.error(f"获取大盘指数情绪失败: {e}")

        return None
    
    def _get_limit_up_down_stats(self):
        """获取涨跌停统计数据"""
        try:
            self.logger.info(f"正在获取涨跌停数据...")
            # 获取今日涨停和跌停统计
            today = datetime.now().strftime('%Y%m%d')
            
            # 获取涨停股票
            try:
                limit_up_df = data_source_manager.get_stock_limit_up_data(today)
                limit_up_count = len(limit_up_df) if limit_up_df is not None and not limit_up_df.empty else 0
            except:
                limit_up_count = 0
            
            # 获取跌停股票
            try:
                limit_down_df = data_source_manager.get_stock_limit_down_data(today)
                limit_down_count = len(limit_down_df) if limit_down_df is not None and not limit_down_df.empty else 0
            except:
                limit_down_count = 0
            
            # 计算涨跌停比例
            if limit_up_count + limit_down_count > 0:
                limit_ratio = limit_up_count / (limit_up_count + limit_down_count) * 100
            else:
                limit_ratio = 50
            
            # 解读涨跌停情况
            if limit_ratio > 70:
                interpretation = "涨停股远多于跌停股，市场情绪火热"
            elif limit_ratio > 60:
                interpretation = "涨停股多于跌停股，市场情绪较好"
            elif limit_ratio > 40:
                interpretation = "涨跌停数量相当，市场情绪分化"
            elif limit_ratio > 30:
                interpretation = "跌停股多于涨停股，市场情绪较弱"
            else:
                interpretation = "跌停股远多于涨停股，市场情绪低迷"
            
            return {
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "limit_ratio": f"{limit_ratio:.1f}%",
                "interpretation": interpretation,
                "date": today
            }
        except Exception as e:
            self.logger.error(f"获取涨跌停数据失败: {e}")
        return None
    
    def _get_margin_trading_data(self, symbol):
        """获取融资融券数据"""
        self.logger.info(f"正在获取 {symbol} 的个股融资融券数据...")
        try:
            current_price = 0
            date_str = datetime.now().strftime('%Y%m%d')
            
            # 获取股票当前价格（沪深通用）
            start_date = (datetime.strptime(date_str, '%Y%m%d') - timedelta(days=15)).strftime('%Y%m%d')
            end_date = date_str
            stock_info = data_source_manager.get_stock_hist_data(symbol, start_date, end_date)
            if stock_info is not None and not stock_info.empty:
                current_price = float(stock_info.iloc[-1]['close'])
            
            # 获取融资融券明细
            if symbol.startswith("00") or symbol.startswith("30"):
                df = data_source_manager.get_stock_margin_detail_data_sz(date_str=date_str)
            else:
                df = data_source_manager.get_stock_margin_detail_data_sh(date_str=date_str)
                if df is not None:
                    df.rename(columns={
                        "标的证券代码": "证券代码",
                        "标的证券简称": "证券简称"
                    }, inplace=True)

            if df is not None and not df.empty:
                stock_data = df[df['证券代码'] == symbol]
                if not stock_data.empty:
                    latest = stock_data.iloc[0]
                    
                    # 融资融券数据
                    margin_balance = float(latest.get('融资余额', 0))
                    short_volume = float(latest.get('融券余量', 0))
                    
                    # 将融券余量转换为金额（融券余额）
                    short_balance = short_volume * current_price if current_price > 0 else 0
                    
                    # 解读融资融券数据
                    interpretation = []
                    if short_balance > 0:
                        margin_short_ratio = margin_balance / short_balance
                        if margin_short_ratio > 10:
                            interpretation.append(f"融资余额远大于融券余额({margin_short_ratio:.1f}倍)，投资者看多情绪强")
                        elif margin_short_ratio > 5:
                            interpretation.append(f"融资余额大于融券余额({margin_short_ratio:.1f}倍)，投资者偏看多")
                        elif margin_short_ratio > 2:
                            interpretation.append(f"融资余额略大于融券余额({margin_short_ratio:.1f}倍)，多头略占优")
                        elif margin_short_ratio > 0.5:
                            interpretation.append(f"融资融券相对平衡(融资/融券={margin_short_ratio:.1f}倍)")
                        elif margin_short_ratio > 0.2:
                            interpretation.append(f"融券余额略大于融资余额({margin_short_ratio:.1f}倍)，空头略占优")
                        else:
                            interpretation.append(f"融券余额远大于融资余额({margin_short_ratio:.1f}倍)，投资者看空情绪强")
                    else:
                        interpretation.append("融券数据不足")
                    
                    return {
                        "margin_balance": margin_balance,
                        "short_balance": short_balance,
                        "interpretation": interpretation,
                        "date": datetime.now().strftime('%Y-%m-%d')
                    }
            
        except Exception as e:
            self.logger.error(f"获取融资融券数据失败: {e}")
        return None
    
    def _get_fear_greed_index(self):
        """计算市场恐慌贪婪指数（基于多个指标综合计算）
        多维度指标：
        1. 涨跌家数比例
        2. 涨跌停比例
        3. 真实涨跌停比例
        4. 涨停率（权重10%）- 上涨股票中涨停的比例
        5. 成交量变化率
        """
        try:
            score = 50  # 基准分数
            factors = []
            
            # 获取涨跌家数
            market_sentiment_df = data_source_manager.get_stock_market_activity()
            if market_sentiment_df is not None and not market_sentiment_df.empty:
                data = market_sentiment_df.set_index('item')['value'].to_dict()
                up_count = float(data.get('上涨', 0))
                down_count = float(data.get('下跌', 0))
                flat_count = float(data.get('平盘', 0))
                suspended_count = float(data.get('停牌', 0))
                limit_up_count = float(data.get('涨停', 0))
                limit_down_count = float(data.get('跌停', 0))
                real_limit_up = float(data.get('真实涨停', 0))
                real_limit_down = float(data.get('真实跌停', 0))
                activity_rate = data.get('活跃度', '0%')
                stat_datetime = data.get('统计日期', 'N/A')

                total_count = up_count + down_count + flat_count + suspended_count
                
                # 1. 涨跌家数比例（权重40%）
                if total_count > 0:
                    up_ratio = up_count / total_count
                    score += (up_ratio - 0.5) * 80
                    factors.append(f"涨跌家数比例: {up_ratio:.1%}")
                
                # 2. 涨跌停比例（权重30%）
                limit_total = limit_up_count + limit_down_count
                if limit_total > 0:
                    limit_up_ratio = limit_up_count / limit_total
                    score += (limit_up_ratio - 0.5) * 60
                    factors.append(f"涨跌停比例: {limit_up_ratio:.1%}（涨停{int(limit_up_count)}家/跌停{int(limit_down_count)}家）")
                
                # 3. 真实涨跌停比例（权重20%）- 剔除ST股
                real_limit_total = real_limit_up + real_limit_down
                if real_limit_total > 0:
                    real_limit_up_ratio = real_limit_up / real_limit_total
                    score += (real_limit_up_ratio - 0.5) * 40
                    factors.append(f"真实涨跌停比例: {real_limit_up_ratio:.1%}（涨停{int(real_limit_up)}家/跌停{int(real_limit_down)}家）")
                
                # 4. 涨停率（权重10%）- 上涨股票中涨停的比例
                if up_count > 0:
                    limit_up_rate = limit_up_count / up_count
                    score += (limit_up_rate - 0.05) * 50
                    factors.append(f"涨停率: {limit_up_rate:.2%}（涨停{int(limit_up_count)}家/上涨{int(up_count)}家）")
            
            # 确保分数在0-100之间
            score = max(0, min(100, score))
            
            # 解读恐慌贪婪指数
            if score >= 80:
                level = "极度贪婪"
                interpretation = "市场情绪极度乐观，投资者贪婪，需警惕回调风险"
            elif score >= 65:
                level = "贪婪"
                interpretation = "市场情绪乐观，投资者偏向贪婪，注意追高风险"
            elif score >= 55:
                level = "偏乐观"
                interpretation = "市场情绪偏乐观，短期可能继续上涨"
            elif score >= 45:
                level = "中性"
                interpretation = "市场情绪中性，投资者相对理性"
            elif score >= 35:
                level = "偏悲观"
                interpretation = "市场情绪偏悲观，短期可能继续下跌"
            elif score >= 20:
                level = "恐慌"
                interpretation = "市场情绪悲观，投资者偏向恐慌"
            else:
                level = "极度恐慌"
                interpretation = "市场情绪极度悲观，投资者恐慌，可能存在超卖机会"
            
            return {
                "score": f"{score:.1f}",
                "level": level,
                "interpretation": interpretation,
                "factors": factors,
                "stat_datetime": stat_datetime if 'stat_datetime' in locals() else 'N/A'
            }
        except Exception as e:
            self.logger.error(f"计算恐慌贪婪指数失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        return None
    
    def format_sentiment_data_for_ai(self, sentiment_data):
        """
        将市场情绪数据格式化为适合AI阅读的文本
        """
        self.logger.info(f"将市场情绪数据格式化为适合AI阅读的文本")

        if not sentiment_data or not sentiment_data.get("data_success"):
            return "未能获取市场情绪数据"
        
        text_parts = []
        
        # ARBR指标
        if sentiment_data.get("arbr_data"):
            arbr = sentiment_data["arbr_data"]
            text_parts.append(f"""
【ARBR市场情绪指标】
- 计算周期：{arbr.get('period', 26)}日
- AR值：{arbr.get('latest_ar', 'N/A'):.2f}（人气指标）
- BR值：{arbr.get('latest_br', 'N/A'):.2f}（意愿指标）
- 信号：{arbr.get('signals', {}).get('overall_signal', 'N/A')}
- 解读：
{chr(10).join(['  * ' + item for item in arbr.get('interpretation', [])])}

ARBR统计数据：
- AR历史均值：{arbr.get('statistics', {}).get('ar_mean', 0):.2f}
- BR历史均值：{arbr.get('statistics', {}).get('br_mean', 0):.2f}
- 历史买入信号比例：{arbr.get('signal_statistics', {}).get('buy_ratio', 'N/A')}
- 历史卖出信号比例：{arbr.get('signal_statistics', {}).get('sell_ratio', 'N/A')}
""")
        
        # 换手率
        if sentiment_data.get("turnover_rate"):
            turnover = sentiment_data["turnover_rate"]
            text_parts.append(f"""
【换手率数据】
- 当前换手率：{turnover.get('current_turnover_rate', 'N/A')}%
- 解读：{turnover.get('interpretation', 'N/A')}
""")
        
        # 大盘情绪
        if sentiment_data.get("market_index"):
            market = sentiment_data["market_index"]
            text_parts.append(f"""
【大盘市场情绪】
- 指数：{market.get('index_name', 'N/A')}
- 涨跌幅：{market.get('change_percent', 'N/A')}%
""")
            if market.get('sentiment_score'):
                text_parts.append(f"""- 市场情绪得分：{market.get('sentiment_score', 'N/A')}
- 涨家数：{market.get('up_count', 'N/A')}只
- 跌家数：{market.get('down_count', 'N/A')}只
- 平家数：{market.get('flat_count', 'N/A')}只
- 市场情绪：{market.get('sentiment_interpretation', 'N/A')}
""")
        
        # 涨跌停统计
        if sentiment_data.get("limit_up_down"):
            limit = sentiment_data["limit_up_down"]
            text_parts.append(f"""
【涨跌停统计】
- 涨停股数量：{limit.get('limit_up_count', 0)}只
- 跌停股数量：{limit.get('limit_down_count', 0)}只
- 涨停占比：{limit.get('limit_ratio', 'N/A')}
- 解读：{limit.get('interpretation', 'N/A')}
""")
        
        # 融资融券
        if sentiment_data.get("margin_trading"):
            margin = sentiment_data["margin_trading"]
            text_parts.append(f"""
【融资融券数据】
- 融资余额：{margin.get('margin_balance', 'N/A')}元
- 融券余额：{margin.get('short_balance', 'N/A')}元
- 融资买入额：{margin.get('margin_buy', 'N/A')}元
- 解读：{'; '.join(margin.get('interpretation', []))}
""")
        
        # 恐慌贪婪指数
        if sentiment_data.get("fear_greed_index"):
            fear_greed = sentiment_data["fear_greed_index"]
            text_parts.append(f"""
【市场恐慌贪婪指数】
- 指数得分：{fear_greed.get('score', 'N/A')}/100
- 情绪等级：{fear_greed.get('level', 'N/A')}
- 解读：{fear_greed.get('interpretation', 'N/A')}
""")
        
        return "\n".join(text_parts)


# 测试函数
if __name__ == "__main__":
    print("测试市场情绪数据获取...")
    fetcher = MarketSentimentDataFetcher()
    
    # 测试平安银行
    symbol = "000001"
    print(f"\n正在获取 {symbol} 的市场情绪数据...")
    
    sentiment_data = fetcher.get_market_sentiment_data(symbol)
    
    if sentiment_data.get("data_success"):
        print("\n" + "="*60)
        print("市场情绪数据获取成功！")
        print("="*60)
        
        formatted_text = fetcher.format_sentiment_data_for_ai(sentiment_data)
        print(formatted_text)
    else:
        print(f"\n获取失败: {sentiment_data.get('error', '未知错误')}")

