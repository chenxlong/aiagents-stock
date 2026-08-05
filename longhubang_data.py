"""
智瞰龙虎数据采集模块
使用StockAPI获取龙虎榜数据
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import log_utils

warnings.filterwarnings('ignore')

import akshare as ak
seat_mapping = {
    # ====================== 【一线顶级游资】（市场关注度最高，复盘重点） ======================
    # 章盟主（章建平）核心席位【新旧券商名称全覆盖，解决国泰海通更名】
    "国泰君安证券股份有限公司上海江苏路证券营业部": {"nick": "章盟主", "style": "趋势大票、主线龙头波段"},
    "国泰海通证券股份有限公司上海长宁区江苏路证券营业部": {"nick": "章盟主", "style": "趋势大票、主线龙头波段"},
    "国泰海通证券股份有限公司上海浦东新区海阳西路证券营业部": {"nick": "章盟主", "style": "趋势大票、主线龙头波段"},
    "国泰君安证券股份有限公司宁波彩虹北路证券营业部": {"nick": "章盟主", "style": "趋势大票、主线龙头波段"},
    "中信证券股份有限公司杭州四季路证券营业部": {"nick": "章盟主", "style": "趋势大票、主线龙头波段"},
    # 作手新一【新旧名称】
    "国泰君安证券股份有限公司南京太平南路证券营业部": {"nick": "作手新一", "style": "高位连板、人气高标接力"},
    "国泰海通证券股份有限公司南京太平南路证券营业部": {"nick": "作手新一", "style": "高位连板、人气高标接力"},
    # 赵老哥（赵强）
    "中国银河证券股份有限公司绍兴证券营业部": {"nick": "赵老哥", "style": "龙头战法，二板定龙头"},
    "浙商证券股份有限公司绍兴解放北路证券营业部": {"nick": "赵老哥", "style": "龙头战法，二板定龙头"},
    # 小鳄鱼
    "国泰君安证券股份有限公司南京太平南路证券营业部": {"nick": "小鳄鱼", "style":"主线龙头、AI大票打板"},
    # 方新侠
    "中信证券股份有限公司西安朱雀大街证券营业部": {"nick": "方新侠", "style": "重仓主线趋势龙头"},
    "兴业证券股份有限公司陕西分公司": {"nick": "方新侠", "style": "重仓主线趋势龙头"},
    # 炒股养家
    "华鑫证券有限责任公司上海宛平南路证券营业部": {"nick": "炒股养家", "style": "通道、潜伏、一字板"},
    # 孙哥(溧阳路)
    "中信证券股份有限公司上海溧阳路证券营业部": {"nick": "孙哥(溧阳路)", "style": "妖股短线、快进快出"},
    # 欢乐海岸
    "华泰证券股份有限公司深圳益田路荣超商务中心证券营业部": {"nick": "欢乐海岸", "style": "龙头锁仓，情绪核心"},
    # 佛山无影脚（佛山系）
    "光大证券股份有限公司佛山绿景路证券营业部": {"nick": "佛山系", "style": "首板、撬板、隔日出货"},
    "光大证券股份有限公司佛山季华六路证券营业部": {"nick": "佛山系", "style":"首板、撬板、隔日出货"},
    # 上塘路（砸盘王）
    "财通证券股份有限公司杭州上塘路证券营业部": {"nick": "上塘路", "style": "首板/连板，次日经常核按钮"},
    # 陈小群
    "中国银河证券股份有限公司大连黄河路证券营业部": {"nick": "陈小群", "style": "情绪连板龙头"},
    # 宁波桑田路
    "国盛证券有限责任公司宁波桑田路证券营业部": {"nick": "桑田路", "style": "情绪套利、低位挖掘"},
    # 成都系（职业炒手）【新旧名称】
    "国泰君安证券股份有限公司成都北一环路证券营业部": {"nick": "成都系", "style": "首板挖掘，板块轮动"},
    "国泰海通证券股份有限公司成都北一环路证券营业部": {"nick": "成都系", "style": "首板挖掘，板块轮动"},
    "华泰证券股份有限公司成都南一环路第二证券营业部": {"nick": "成都系", "style": "首板挖掘，板块轮动"},

    # ====================== 【二线活跃游资】（中等体量地方性资金） ======================
    "财通证券股份有限公司温岭中华路证券营业部": {"nick": "温岭解放北游资", "style": "首板挖掘"},
    "中信建投证券股份有限公司杭州庆春路证券营业部": {"nick": "庆春路", "style": "趋势中线"},
    "东吴证券股份有限公司苏州相城大道证券营业部": {"nick": "相城大道游资", "style": "连板"},
    "湘财证券股份有限公司上海陆家嘴证券营业部": {"nick": "陆家嘴游资", "style": "短线轮动"},
    "华泰证券股份有限公司上海武定路证券营业部": {"nick": "武定路游资", "style": "低位潜伏"},
    "国泰君安证券股份有限公司上海新闸路证券营业部": {"nick": "新闸路游资", "style": "题材套利"},
    "兴业证券股份有限公司厦门湖里大道证券营业部": {"nick": "湖里大道游资", "style": "趋势票"},

    # ====================== 【老牌帮派游资（温州帮 / 山东帮 核心旗舰席位）】 ======================
    # 温州帮 代表席位（历史知名，近年马甲分散，仅作参考）
    "中国银河证券股份有限公司温州锦绣路证券营业部": {"nick": "温州帮", "style": "短线控盘、A字出货，警惕闪崩"},
    "华鑫证券有限责任公司乐清双雁路证券营业部": {"nick": "温州帮", "style": "短线控盘、A字出货，警惕闪崩"},
    "天风证券股份有限公司武汉八一路证券营业部": {"nick": "温州帮", "style": "短线控盘、A字出货，警惕闪崩"},
    "华泰证券股份有限公司郑州经三路证券营业部": {"nick": "温州帮", "style": "短线控盘、A字出货，警惕闪崩"},
    # 山东帮 代表席位（历史主打次新股，多席位联动）
    "国海证券股份有限公司济南济安街证券营业部": {"nick": "山东帮", "style": "次新股联动拉升，多席位协同"},
    "国海证券股份有限公司济宁邹城市兴石街证券营业部": {"nick": "山东帮", "style": "次新股联动拉升，多席位协同"},
    "中泰证券股份有限公司荣成石岛黄海中路证券营业部": {"nick": "山东帮", "style": "次新股联动拉升，多席位协同"},

    # ====================== 【散户席位】拉萨天团（东财散户大本营） ======================
    "东方财富证券股份有限公司拉萨团结路第一证券营业部": {"nick": "拉萨天团", "style": "散户合力，波动巨大"},
    "东方财富证券股份有限公司拉萨团结路第二证券营业部": {"nick": "拉萨天团", "style": "散户合力，波动巨大"},
    "东方财富证券股份有限公司拉萨东环路第一证券营业部": {"nick": "拉萨天团", "style": "散户合力，波动巨大"},
    "东方财富证券股份有限公司拉萨东环路第二证券营业部": {"nick": "拉萨天团", "style": "散户合力，波动巨大"},

    # ====================== 【量化席位 · 量化打板 / 高频程序化】 ======================
    # 华鑫系：A股老牌通道量化，主打短线打板
    "华鑫证券有限责任公司上海分公司": {"nick": "量化打板", "style": "程序化打板、隔日套利"},
    "华鑫证券有限责任公司上海茅台路证券营业部": {"nick": "量化打板", "style": "高频量化打板"},
    "华鑫证券有限责任公司上海淞滨路证券营业部": {"nick": "量化打板", "style": "高频量化交易"},
    # 开源西安军团：近几年最强批量首板量化集群
    "开源证券股份有限公司西安西大街证券营业部": {"nick": "量化打板", "style": "批量首板量化，隔日卖出为主"},
    "开源证券股份有限公司西安太华路证券营业部": {"nick": "量化打板", "style": "批量首板量化，隔日卖出为主"},
    # 券商总部：自营、中型量化私募，多因子、日内T，不一定打板
    "华泰证券股份有限公司上海总部": {"nick": "华泰量化总部", "style": "程序化量化、日内T+0"},
    "中信证券股份有限公司上海总部": {"nick": "中信量化总部", "style": "量化趋势交易"},
    "招商证券股份有限公司上海总部": {"nick": "招商量化总部", "style": "算法套利、日内交易"},
    "国泰海通证券股份有限公司总部": {"nick": "国泰海通量化总部", "style": "高频量化、多因子策略"},
    # 中金通道：大型头部量化私募专用
    "中国国际金融股份有限公司上海分公司": {"nick": "量化基金", "style": "头部量化私募、外资算法交易"},

    # ====================== 【外资量化席位】 ======================
    "瑞银证券有限责任公司上海花园石桥路证券营业部": {"nick": "外资量化", "style": "北向外资、高频对冲交易"},
}

def get_capital_tag(seat_name: str):
    """
    根据营业部名称匹配游资昵称与风格
    :param seat_name: 原始龙虎榜营业部全称
    :return: nick, style
    """
    if seat_name in seat_mapping:
        info = seat_mapping[seat_name]
        return info["nick"], info["style"]
    
    # 关键词兜底，应对券商更名，防止漏识别
    if "上海长宁区江苏路证券营业部" in seat_name or "上海江苏路证券营业部" in seat_name:
        return "章盟主", "趋势大票、主线龙头波段"
    if "南京太平南路证券营业部" in seat_name:
        return "作手新一", "高位连板、人气高标接力"
    if "成都北一环路证券营业部" in seat_name:
        return "成都系", "首板挖掘，板块轮动"

    # 通用特殊席位分类
    if "机构专用" in seat_name:
        return "机构专用", "机构资金（公募/私募/社保）"
    if "东方财富证券股份有限公司" in seat_name:
        return "东财散户营业部", "散户"
    if "沪股通专用" in seat_name or "深股通专用" in seat_name:
        return "北向资金", "外资资金"
    return "未知营业部", "待识别"


class LonghubangDataFetcher:
    """龙虎榜数据获取类"""
    
    def __init__(self, api_key=None):
        """
        初始化数据获取器
        
        Args:
            api_key: StockAPI的API密钥（可选，普通请求每日免费1000次）
        """
        self.logger = log_utils.get_logger(__name__)
        # self.base_url = "https://api-lhb.zhongdu.net"
        self.base_url = "http://lhb-api.ws4.cn/v1"
       # self.base_url = "https://www.stockapi.com.cn/v1"
        self.api_key = api_key
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2  # 重试延迟（秒）
        self.request_delay = 0.025  # 请求间隔（秒），40次/秒 = 0.025秒/次
        self.logger.info("[智瞰龙虎] 龙虎榜数据获取类 LonghubangDataFetcher 初始化完成")
    
    def _safe_request(self, url, params=None):
        """
        安全的HTTP请求，包含重试机制
        
        Args:
            url: 请求URL
            params: 请求参数
            
        Returns:
            dict: 响应数据
        """
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, params=params, timeout=10)
                
                # 添加请求延迟，遵守40次/秒的限制
                time.sleep(self.request_delay)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('code') == 20000:
                        self.logger.info(f" ✓ 成功获取龙虎榜记录：\n {data['data']} ")
                        return data
                    else:
                        self.logger.error(f" ✗ API返回错误: {data.get('msg', '未知错误')}")
                        return None
                else:
                    self.logger.error(f" ✗ HTTP错误: {response.status_code}")
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    self.logger.error(f" ✗ 请求失败，{self.retry_delay}秒后重试... (尝试 {attempt + 1}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f" ✗ 请求失败，已达最大重试次数: {e}")
                    return None
        
        return None
    
    def get_longhubang_data_old(self, date):
        """
        获取指定日期的龙虎榜数据
        
        Args:
            date: 日期，格式为 YYYY-MM-DD，如 "2023-03-21"
            
        Returns:
            dict: 龙虎榜数据
        """
        self.logger.info(f"[智瞰龙虎] 获取 {date} 的龙虎榜数据...")
        
        # url = f"{self.base_url}"
        url = f"{self.base_url}/youzi/all"
        params = {'date': date}
        
        result = self._safe_request(url, params)
        
        if result and result.get('data'):
            self.logger.info(f" ✓ 成功获取 {len(result['data'])} 条龙虎榜记录")
            return result
        else:
            self.logger.error(f" ✗ 未获取到数据")
            return None

    def get_longhubang_data(self, date):
        """
        获取指定日期的龙虎榜数据
        
        Args:
            date: 日期，格式为 YYYY-MM-DD，如 "2023-03-21"
            
        Returns:
            dict: 龙虎榜数据
        """
        self.logger.info(f"[智瞰龙虎] 获取 {date} 的龙虎榜数据...")
        
        df_data = self.fetch_lhb_all_seat(date)
        if df_data.empty:
            self.logger.error(f" ✗ 未获取到数据")
            return None
        
        self.logger.debug(f" ✓ 成功获取 {len(df_data)} 条龙虎榜记录,数据:\n{df_data}")
        # 保存到CSV文件
        df_data.to_csv(f"logs/龙虎榜席位_{date}.csv", index=False, encoding="utf-8-sig")

        # 转换为字典列表
        data_list = df_data.to_dict(orient='records')
        result = {"data": data_list}
        return result
    
    def get_longhubang_data_range(self, start_date, end_date):
        """
        获取日期范围内的龙虎榜数据
        
        Args:
            start_date: 开始日期，格式为 YYYY-MM-DD
            end_date: 结束日期，格式为 YYYY-MM-DD
            
        Returns:
            list: 龙虎榜数据列表
        """
        self.logger.info(f"[智瞰龙虎] 获取 {start_date} 至 {end_date} 的龙虎榜数据...")
        
        all_data = []
        
        # 转换日期
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current_date <= end_date_obj:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 跳过周末
            if current_date.weekday() < 5:  # 0-4表示周一到周五
                result = self.get_longhubang_data(date_str)
                if result and result.get('data'):
                    all_data.extend(result['data'])
            
            # 下一天
            current_date += timedelta(days=1)
        
        self.logger.info(f"[智瞰龙虎] ✓ 共获取 {len(all_data)} 条记录")
        return all_data
    
    def get_recent_days_data(self, days=5):
        """
        获取最近N个交易日的龙虎榜数据
        
        Args:
            days: 天数（默认5天）
            
        Returns:
            list: 龙虎榜数据列表
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)  # 乘以2以确保包含足够的交易日
        
        return self.get_longhubang_data_range(
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
    
    def parse_to_dataframe_old(self, data_list):
        """
        将龙虎榜数据转换为DataFrame
        
        Args:
            data_list: 龙虎榜数据列表
            
        Returns:
            pd.DataFrame: 数据框
        """
        if not data_list:
            return pd.DataFrame()
        
        df = pd.DataFrame(data_list)
        
        # 重命名列
        column_mapping = {
            'yzmc': '游资名称',
            'yyb': '营业部',
            'sblx': '榜单类型',
            'gpdm': '股票代码',
            'gpmc': '股票名称',
            'mrje': '买入金额',
            'mcje': '卖出金额',
            'jlrje': '净流入金额',
            'rq': '日期',
            'gl': '概念'
        }
        
        df = df.rename(columns=column_mapping)
        
        # 转换数据类型
        numeric_columns = ['买入金额', '卖出金额', '净流入金额']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 排序
        if '净流入金额' in df.columns:
            df = df.sort_values('净流入金额', ascending=False)
        
        self.logger.debug(f"[智瞰龙虎] 转换后的数据:\n{df}")
        
        return df
    
    def parse_to_dataframe(self, data_list):
        """
        将龙虎榜数据转换为DataFrame
        
        Args:
            data_list: 龙虎榜数据列表
            
        Returns:
            pd.DataFrame: 数据框
        """
        if not data_list:
            return pd.DataFrame()
        
        df = pd.DataFrame(data_list)
        
        # 重命名列
        column_mapping = {
            '游资名称': '游资名称',
            '资金风格': '资金风格',
            '营业部名称': '营业部名称',
            '类型': '类型',
            '股票代码': '股票代码',
            '股票名称': '股票名称',
            '买入金额': '买入金额',
            '买入金额-占总成交比例': '买入金额-占总成交比例',
            '卖出金额': '卖出金额',
            '卖出金额-占总成交比例': '卖出金额-占总成交比例',
            '净额': '净流入金额',
            '上榜日期': '上榜日期',
            '买卖方向': '买卖方向',
            '概念': '概念'
        }
        
        df = df.rename(columns=column_mapping)
        
        # 转换数据类型
        numeric_columns = ['买入金额', '卖出金额', '净流入金额', '买入金额-占总成交比例', '卖出金额-占总成交比例']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 排序（沪股通/深股通 被拆分的买榜行、卖榜行，这个排序，实际无意义）
        if '净流入金额' in df.columns:
            df = df.sort_values('净流入金额', ascending=False)
        
        self.logger.debug(f"[智瞰龙虎] 转换后的数据:\n{df}")
        
        return df
    
    def analyze_data_summary(self, data_list):
        """
        分析龙虎榜数据，生成摘要统计
        
        Args:
            data_list: 龙虎榜数据列表
            
        Returns:
            dict: 统计摘要
        """
        if not data_list:
            return {}
        
        df = self.parse_to_dataframe(data_list)
        
        summary = {
            'total_records': len(df),
            'total_stocks': df['股票代码'].nunique() if '股票代码' in df.columns else 0,
            'total_youzi': df['游资名称'].nunique() if '游资名称' in df.columns else 0,
            'total_buy_amount': df['买入金额'].sum() if '买入金额' in df.columns else 0,
            'total_sell_amount': df['卖出金额'].sum() if '卖出金额' in df.columns else 0,
            'total_net_inflow': df['净流入金额'].sum() if '净流入金额' in df.columns else 0,
        }
        
        # Top游资排名
        if '游资名称' in df.columns and '净流入金额' in df.columns:
            top_youzi = df.groupby('游资名称')['净流入金额'].sum().sort_values(ascending=False)
            self.logger.debug(f"[智瞰龙虎] Top游资排名:\n{top_youzi}")
            summary['top_youzi'] = top_youzi.head(10).to_dict()
        
        # Top股票排名
        if '股票代码' in df.columns and '净流入金额' in df.columns:
            top_stocks = df.groupby(['股票代码', '股票名称'])['净流入金额'].sum().sort_values(ascending=False)
            self.logger.debug(f"[智瞰龙虎] Top股票排名:\n{top_stocks}")
            summary['top_stocks'] = [
                {'code': code, 'name': name, 'net_inflow': amount}
                for (code, name), amount in top_stocks.head(20).items()
            ]
        
        # 热门概念统计
        if '概念' in df.columns:
            all_concepts = []
            for concepts in df['概念'].dropna():
                all_concepts.extend([c.strip() for c in str(concepts).split(',')])
            
            self.logger.debug(f"[智瞰龙虎] 所有概念:\n{all_concepts}")
            from collections import Counter
            concept_counter = Counter(all_concepts)
            self.logger.debug(f"[智瞰龙虎] 热门概念统计:\n{concept_counter.most_common(20)}")
            summary['hot_concepts'] = dict(concept_counter.most_common(20))
        
        return summary
    
    def format_data_for_ai(self, data_list, summary=None):
        """
        将龙虎榜数据格式化为适合AI分析的文本格式
        
        Args:
            data_list: 龙虎榜数据列表
            summary: 统计摘要（可选）
            
        Returns:
            str: 格式化的文本
        """
        if not data_list:
            return "暂无龙虎榜数据"
        
        df = self.parse_to_dataframe(data_list)
        
        if summary is None:
            summary = self.analyze_data_summary(data_list)
        
        text_parts = []
        
        # 总体概况
        text_parts.append(f"""
【龙虎榜总体概况】
数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
记录总数: {summary.get('total_records', 0)}
涉及股票: {summary.get('total_stocks', 0)} 只
涉及游资: {summary.get('total_youzi', 0)} 个
总买入金额: {summary.get('total_buy_amount', 0):,.2f} 元
总卖出金额: {summary.get('total_sell_amount', 0):,.2f} 元
净流入金额: {summary.get('total_net_inflow', 0):,.2f} 元
""")
        
        # Top游资 csv格式化
        if summary.get('top_youzi'):
            top_youzi_df = pd.DataFrame(
                list(summary['top_youzi'].items()),
                columns=['游资名称', '净流入金额']
            )
            top_youzi_df.sort_values(by='净流入金额', ascending=False, inplace=True)
            top_youzi_df.insert(0, '排名', range(1, len(top_youzi_df) + 1))

            text_parts.append("\n【活跃游资 TOP10】（CSV格式，金额单位：元）")
            # 转换为CSV格式字符串
            top_youzi_csv = top_youzi_df.to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
            text_parts.append(top_youzi_csv)
        
        # Top股票
        if summary.get('top_stocks'):
            top_stocks_df = pd.DataFrame(summary['top_stocks'])
            top_stocks_df.rename(columns={'code': '股票代码', 'name': '股票名称', 'net_inflow': '净流入金额'}, inplace=True)
            top_stocks_df.sort_values(by='净流入金额', ascending=False, inplace=True)
            top_stocks_df.insert(0, '排名', range(1, len(top_stocks_df) + 1))

            text_parts.append("\n【资金净流入 TOP20股票】（CSV格式，金额单位：元）")
             # 转换为CSV格式字符串
            top_stocks_csv = top_stocks_df.to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
            text_parts.append(top_stocks_csv)
        
        # 热门概念
        if summary.get('hot_concepts'):
            text_parts.append("\n【热门概念 TOP20】")
            for idx, (concept, count) in enumerate(list(summary['hot_concepts'].items())[:20], 1):
                text_parts.append(f"{idx}. {concept}: {count} 次")
        
        # 详细交易记录（前50条）
        text_parts.append("\n【详细交易记录 TOP50】（CSV格式，金额单位：元）")

        df = self.merge_buy_sell_rows(df)
        self.logger.debug(f"[智瞰龙虎] 合并龙虎榜同一个股票下：沪股通/深股通 被拆分的买榜行、卖榜行:\n{df}")
        df = df.sort_values('席位净额', ascending=False)
        df.insert(0, '排名', range(1, len(df) + 1))
        # 转换为CSV格式字符串
        top_records_csv = df.head(100).to_csv(index=False, encoding='utf-8-sig').replace('\r\n', '\n').strip()
        text_parts.append(top_records_csv)

        over_view = "\n".join(text_parts)
        self.logger.debug(f"[智瞰龙虎] 龙虎榜总体概况:\n{over_view}")
        return over_view

    def fetch_lhb_all_seat(self, trade_date: str, sleep_sec=1.3):
        """
        采集单日龙虎榜全部席位+自动游资标签
        :param trade_date: 日期 格式 20260729
        :param sleep_sec: 请求间隔，防止限流
        :return: 全市场龙虎席位明细df
        """
        # 日期转换为YYYYMMDD格式
        trade_date = trade_date.replace("-", "")
        try:
            # 第一步：获取当日上榜个股清单
            stock_list_df = ak.stock_lhb_detail_em(
                start_date=trade_date,
                end_date=trade_date
            )
        except Exception as e:
            self.logger.error(f"获取上榜个股清单失败：{e}")
            return pd.DataFrame()

        # =========【新增：构建代码→股票名称映射字典】=========
        code_name_map = dict(zip(stock_list_df["代码"], stock_list_df["名称"]))
        codes = stock_list_df["代码"].unique()
        self.logger.info(f"当日龙虎榜个股数量：{len(codes)}")

        all_data = []
        for code in codes:
            try:
                stock_name = code_name_map[code]  # 根据代码取出股票名称
                # 获取该股当日全部榜单（含三日+多条单日）
                # 买入前五席位
                buy_df = ak.stock_lhb_stock_detail_em(
                    symbol=code, date=trade_date, flag="买入"
                )
                buy_df["股票代码"] = code
                buy_df["股票名称"] = stock_name
                buy_df["上榜日期"] = trade_date
                buy_df["买卖方向"] = "买入前五"
                all_data.append(buy_df)

                # 卖出前五席位
                sell_df = ak.stock_lhb_stock_detail_em(
                    symbol=code, date=trade_date, flag="卖出"
                )
                sell_df["股票代码"] = code
                sell_df["股票名称"] = stock_name
                sell_df["上榜日期"] = trade_date
                sell_df["买卖方向"] = "卖出前五"
                all_data.append(sell_df)
                # 限流延时必不可少
                time.sleep(sleep_sec)
            except Exception as err:
                self.logger.error(f"{code} 获取席位异常: {str(err)}")
                continue

        if not all_data:
            return pd.DataFrame()

        result_df = pd.concat(all_data, ignore_index=True)
        # 增加游资标签
        result_df.rename(columns={"交易营业部名称": "营业部名称"}, inplace=True)
        result_df[["游资名称", "资金风格"]] = result_df["营业部名称"].apply(
            lambda x: pd.Series(get_capital_tag(x))
        )

        # ==========核心清洗：区分单日/三日榜单，去重重复单日数据=========
        # 标记榜单周期
        def mark_cycle_type(title):
            if "连续三个交易日" in title:
                return "三日累计"
            else:
                return "单日当日"
        
        result_df["榜单周期"] = result_df["类型"].apply(mark_cycle_type)

         # 1、提取纯单日数据，去除重复的涨幅/换手率两套相同数据
        day_df = result_df[result_df["榜单周期"] == "单日当日"].copy()
        # 同股票、同营业部、同买卖金额视为重复，只保留1份
        day_df = day_df.drop_duplicates(subset=["股票代码","营业部名称","买入金额","卖出金额"])
        
        return day_df

    def merge_buy_sell_rows(self, lhb_df: pd.DataFrame) -> pd.DataFrame:
        """
        合并龙虎榜同一个股票下：沪股通/深股通 被拆分的买榜行、卖榜行
        普通营业部、多条机构专用保持多条，不强行合并
        lhb_df：来自 day_df / three_day_df
        返回：每条【股票+营业部】一行，总买入、总卖出、净额
        """
        agg_df = lhb_df.groupby(
            ["营业部名称", "榜单周期", "上榜日期", "类型", "游资名称", "资金风格", "股票代码", "股票名称"]
        ).agg(
            总买入=("买入金额", "sum"),
            总卖出=("卖出金额", "sum"),
        ).reset_index()

        agg_df["席位净额"] = agg_df["总买入"] - agg_df["总卖出"]
        # 净额占比，如果有个股总成交额字段
        if "个股总成交额" in lhb_df.columns:
            amount_map = dict(zip(lhb_df["股票代码"], lhb_df["个股总成交额"]))
            agg_df["个股总成交额"] = agg_df["股票代码"].map(amount_map)
            agg_df["净额占成交额%"] = (agg_df["席位净额"] / agg_df["个股总成交额"] * 100).round(3)

        return agg_df


# 测试函数
if __name__ == "__main__":
    print("=" * 60)
    print("测试智瞰龙虎数据采集模块")
    print("=" * 60)

    log_utils.setup_root_logger()
    logger = log_utils.get_logger()

    fetcher = LonghubangDataFetcher()

    # # 计算耗时
    # start_time = time.time()
    # df_lhb = fetcher.fetch_lhb_all_seat(trade_date="20260803")
    # end_time = time.time()
    # logger.info(f"[智瞰龙虎] 获取到 {len(df_lhb)} 条龙虎榜数据，耗时：{end_time - start_time} 秒")
    # logger.info(f"[智瞰龙虎] 获取到 {len(df_lhb)} 条龙虎榜数据:\n{df_lhb}")
    # df_lhb.to_csv("logs/龙虎榜席位_20260803.csv", index=False, encoding="utf-8-sig")
    
    # 测试获取单日数据
    date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    date = "20260803"
    result = fetcher.get_longhubang_data(date)
    
    if result and result.get('data'):
        # 分析数据
        summary = fetcher.analyze_data_summary(result['data'])
        
        print("\n" + "=" * 60)
        print("数据采集成功！")
        print("=" * 60)
        
        # 格式化输出
        formatted_text = fetcher.format_data_for_ai(result['data'], summary)
        print(formatted_text[:2000])  # 显示前2000字符
        print(f"\n... (总长度: {len(formatted_text)} 字符)")
    else:
        print("\n数据采集失败")

