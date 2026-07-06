"""
AkShare 数据获取模块
使用 AkShare 库获取股票数据

1.库有问题 akshare/stock/stock_info_em.py
def stock_individual_info_em(
    symbol: str = "603777", timeout: float = None
) -> pd.DataFrame:
...
    if "dlmkts" in temp_df.columns:
        del temp_df["dlmkts"]
     # === 添加下面这两行，删除 dsc 字段 ===
    if "dsc" in temp_df.columns:
        del temp_df["dsc"]
...

2. akshare股票涨跌板与资金流向相关分析 
https://cnloong.blog.csdn.net/article/details/143446463?spm=1001.2101.3001.6650.5&utm_medium=distribute.pc_relevant.none-task-blog-2%7Edefault%7EBlogCommendFromBaidu%7ECtr-5-143446463-blog-158175800.235%5Ev43%5Epc_blog_bottom_relevance_base9&depth_1-utm_source=distribute.pc_relevant.none-task-blog-2%7Edefault%7EBlogCommendFromBaidu%7ECtr-5-143446463-blog-158175800.235%5Ev43%5Epc_blog_bottom_relevance_base9&utm_relevant_index=9
"""
import time
from utils.akshare_helper import RequestsPatcher
import akshare as ak
from datetime import datetime, timedelta
import pandas as pd
import log_utils
import traceback

class AkshareDataFetcher:
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
                self.logger.info(f"[Akshare-腾讯] 正在获取 {symbol} 的历史数据..." +
                      (f" (第{retry_count+1}次)"))
                
                # 使用腾讯数据源（proxy.finance.qq.com），避免东方财富API屏蔽(ak.stock_zh_a_hist)
                tx_symbol = self._convert_to_tx_code(symbol)
                # Tencent 返回列名: ['date', 'open', 'close', 'high', 'low', 'amount']  amount 成交股数（单位：股）
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

    ## 基本不可用（第一次可用）  ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))
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
            "total_share_capital": "N/A",
            "tradable_share_capital": "N/A"
        }

        try:
            self.logger.info(f"[Akshare-东方财富] 正在获取 {symbol} 的基本信息...")
            
            stock_info = None

            for retry_count in range(3):
                try:
                    with RequestsPatcher():
                        # 东方财富-个股-股票信息 列信息 columns=["股票代码","股票简称","总股本","流通股","行业","总市值","流通市值","上市时间","最新"]
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
                        info['total_share_capital'] = value
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

    # 可用，但是太慢，全市场的快照实时行情数据
    def get_realtime_quotes_akshare(self, symbol):
        """
        获取实时行情数据（akshare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        try:
            self.logger.info(f"[Akshare-东方财富] 正在获取 {symbol} 的实时行情...")
            
            with RequestsPatcher():
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

    # 可用
    def get_individual_fund_flow_akshare(self, symbol, market):
        """获取个股资金流向数据（akshare）"""
        df = None
        akshare_df = None

        for retry_count in range(3):
            try:
                self.logger.info(f"[Akshare] 正在获取{symbol}的资金流向 (市场: {market})..." + (f" (第{retry_count+1}次)"))
                
                with RequestsPatcher():
                    # 返回列信息： 日期    收盘价    涨跌幅     主力净流入-净额  主力净流入-净占比    超大单净流入-净额  超大单净流入-净占比     大单净流入-净额  大单净流入-净占比     中单净流入-净额  中单净流入-净占比     小单净流入-净额  小单净流入-净占比
                    akshare_df = ak.stock_individual_fund_flow(stock=symbol, market=market)

                self.logger.debug(f"[Akshare] -资金流向原始数据:\n{akshare_df}")

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

    def get_financial_data_akshare(self, symbol, report_type='income'):
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
                self.logger.info(f"[Akshare-新浪财经] 正在获取 {symbol} 的财务数据..." + (f" (第{retry_count+1}次)"))
                
                if report_type == 'income':
                    # 返回列信息： 报告日         营业总收入          营业收入 利息收入 已赚保费 手续费及佣金收入 房地产销售收入 其他业务收入          营业总成本           营业成本 手续费及佣金支出 房地产销售成本  退保金 赔付支出净额 提取保险合同准备金净额 保单红利支出 分保费用 其他业务成本     营业税金及附加         研发费用         销售费用         管理费用         财务费用        利息费用 利息支出         投资收益 对联营企业和合营企业的投资收益 以摊余成本计量的金融资产终止确认产生的收益 汇兑收益 净敞口套期收益    公允价值变动收益 期货损益 托管收益 补贴收入         其他收益       资产减值损失      信用减值损失 其他业务利润    资产处置收益         营业利润        营业外收入 非流动资产处置利得       营业外支出 非流动资产处置损失         利润总额       所得税费用 未确认投资损失          净利润      持续经营净利润 终止经营净利润 归属于母公司所有者的净利润 被合并方在合并前实现净利润      少数股东损益 其他综合收益 归属于母公司所有者的其他综合收益 （一）以后不能重分类进损益的其他综合收益 重新计量设定受益计划变动额 权益法下不能转损益的其他综合收益 其他权益工具投资公允价值变动 企业自身信用风险公允价值变动 （二）以后将重分类进损益的其他综合收益 权益法下可转损益的其他综合收益 可供出售金融资产公允价值变动损益 其他债权投资公允价值变动 金融资产重分类计入其他综合收益的金额 其他债权投资信用减值准备 持有至到期投资重分类为可供出售金融资产损益 现金流量套期储备 现金流量套期损益的有效部分 外币财务报表折算差额   其他 归属于少数股东的其他综合收益       综合收益总额 归属于母公司所有者的综合收益总额 归属于少数股东的综合收益总额  基本每股收益  稀释每股收益         数据源 是否审计      公告日期   币种    类型                 更新日期
                    df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
                elif report_type == 'balance':
                    # 返回列信息： 报告日 流动资产           货币资金 结算备付金 拆出资金       交易性金融资产 买入返售金融资产 衍生金融资产     应收票据及应收账款         应收票据          应收账款       应收款项融资         预付款项 应收股利        应收利息 应收保费 应收分保账款 应收分保合同准备金 应收出口退税 应收补贴款 应收保证金 内部应收款       其他应收款    其他应收款(合计)            存货 划分为持有待售的资产 待摊费用 待处理流动资产损益 一年内到期的非流动资产        其他流动资产         流动资产合计 非流动资产 发放贷款及垫款 债权投资 其他债权投资 以公允价值计量且其变动计入其他综合收益的金融资产 以摊余成本计量的金融资产 可供出售金融资产       长期股权投资 投资性房地产 长期应收款   其他权益工具投资 其他非流动金融资产 其他长期投资         固定资产原值          累计折旧         固定资产净值    固定资产减值准备        在建工程合计          在建工程 工程物资         固定资产净额 固定资产清理      固定资产及清理合计 生产性生物资产 公益性生物资产 油气资产 合同资产       使用权资产         无形资产 开发支出          商誉      长期待摊费用 股权分置流通权      递延所得税资产     其他非流动资产        非流动资产合计           资产总计 流动负债          短期借款 向中央银行借款 吸收存款及同业存放 拆入资金 交易性金融负债 衍生金融负债     应付票据及应付账款          应付票据          应付账款        预收款项         合同负债 卖出回购金融资产款 应付手续费及佣金       应付职工薪酬         应交税费 应付利息         应付股利 应付保证金 内部应付款        其他应付款      其他应付款合计 其他应交款 担保责任赔偿准备金 应付分保账款 保险合同准备金 代理买卖证券款 代理承销证券款 国际票证结算 国内票证结算 预提费用 预计流动负债 应付短期债券 划分为持有待售的负债 一年内的递延收益  一年内到期的非流动负债       其他流动负债        流动负债合计 非流动负债          长期借款 应付债券 应付债券：优先股 应付债券：永续债        租赁负债 长期应付职工薪酬 长期应付款 长期应付款合计 专项应付款 预计非流动负债        长期递延收益      递延所得税负债 其他非流动负债       非流动负债合计           负债合计 所有者权益     实收资本(或股本) 其他权益工具  优先股  永续债           资本公积 减:库存股 其他综合收益        专项储备         盈余公积 一般风险准备 未确定的投资损失        未分配利润 拟分配现金股利 外币报表折算差额   归属于母公司股东权益合计        少数股东权益 所有者权益(或股东权益)合计 负债和所有者权益(或股东权益)总计         数据源 是否审计      公告日期   币种    类型                 更新日期
                    df = ak.stock_financial_report_sina(stock=symbol, symbol="资产负债表")
                elif report_type == 'cashflow':
                    # 返回列信息： 报告日 经营活动产生的现金流量 销售商品、提供劳务收到的现金 客户存款和同业存放款项净增加额 向中央银行借款净增加额 向其他金融机构拆入资金净增加额 收到原保险合同保费取得的现金 收到再保险业务现金净额 保户储金及投资款净增加额 处置交易性金融资产净增加额 收取利息、手续费及佣金的现金 拆入资金净增加额 回购业务资金净增加额      收到的税费返还 收到的其他与经营活动有关的现金     经营活动现金流入小计 购买商品、接受劳务支付的现金 客户贷款及垫款净增加额 存放中央银行和同业款项净增加额 支付原保险合同赔付款项的现金 支付利息、手续费及佣金的现金 支付保单红利的现金 支付给职工以及为职工支付的现金      支付的各项税费 支付的其他与经营活动有关的现金     经营活动现金流出小计 经营活动产生的现金流量净额 投资活动产生的现金流量 收回投资所收到的现金  取得投资收益收到的现金 处置固定资产、无形资产和其他长期资产所收回的现金净额 处置子公司及其他营业单位收到的现金净额 收到的其他与投资活动有关的现金 减少质押和定期存款所收到的现金 处置可供出售金融资产净增加额     投资活动现金流入小计 购建固定资产、无形资产和其他长期资产所支付的现金    投资所支付的现金 质押贷款净增加额 取得子公司及其他营业单位支付的现金净额 增加质押和定期存款所支付的现金 支付的其他与投资活动有关的现金     投资活动现金流出小计  投资活动产生的现金流量净额 筹资活动产生的现金流量      吸收投资收到的现金 子公司吸收少数股东投资收到的现金    取得借款收到的现金 发行债券收到的现金 收到其他与筹资活动有关的现金     筹资活动现金流入小计    偿还债务支付的现金 分配股利、利润或偿付利息所支付的现金 子公司支付给少数股东的股利、利润 支付其他与筹资活动有关的现金    筹资活动现金流出小计  筹资活动产生的现金流量净额 汇率变动对现金及现金等价物的影响  现金及现金等价物净增加额  期初现金及现金等价物余额       现金的期末余额       现金的期初余额 现金等价物的期末余额 现金等价物的期初余额  期末现金及现金等价物余额         数据源 是否审计      公告日期   币种    类型                 更新日期
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

    # 获取百度股市通-A股-财务报表-估值数据
    def get_valuation_value_akshare(self, symbol, indicator="总市值", period="近一年"):
        """
        获取百度股市通-A股-财务报表-估值数据（akshare）
        """
        df = None
        akshare_df = None

        for retry_count in range(3):
            try:
                self.logger.info(f"[Akshare-百度股市通] 正在获取 {symbol} 的估值（{indicator}）数据..." + (f" (第{retry_count+1}次)"))
                # 返回列信息： date    value
                akshare_df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period=period)

                self.logger.debug(f"[Akshare-百度股市通] -估值（{indicator}）数据原始数据:\n{akshare_df}")

                if akshare_df is not None and not akshare_df.empty:
                    self.logger.info(f"[Akshare-百度股市通] 获取到 {len(akshare_df)} 条估值（{indicator}）数据")
                    df = akshare_df
                    break
            except Exception as e:
                self.logger.error(f"[Akshare-百度股市通] ❌ 获取估值（{indicator}）数据失败: {e}")
                self.logger.error(f"[Akshare-百度股市通] 完整错误堆栈:\n{traceback.format_exc()}")
                if retry_count < 2:
                    delay = (retry_count + 1) * 2
                    self.logger.info(f"[Akshare-百度股市通] ⏳ {delay}s 后重试...")
                    time.sleep(delay)
        return df

    # 获取财务摘要（综合浓缩指标）
    def stock_financial_abstract_ths(self, symbol, indicator="按报告期"):
        """
        获取财务摘要（综合浓缩指标）（akshare）
        :param symbol: 股票代码
        :param indicator: 指标; choice of {"按报告期", "按年度", "按单季度"}
        """
        financial_abstract_df = None
        # 1. 获取财务摘要 （建议使用 按报告期，按单季度），应该按报告期、按年度、按单季度
        try:
            # 返回列信息： 报告期        净利润  净利润同比增长率      扣非净利润 扣非净利润同比增长率   营业总收入 营业总收入同比增长率   基本每股收益  每股净资产 每股资本公积金 每股未分配利润 每股经营现金流   销售净利率   销售毛利率  净资产收益率 净资产收益率-摊薄    营业周期  存货周转率 存货周转天数 应收账款周转天数   流动比率   速动比率 保守速动比率   产权比率   资产负债率
            financial_abstract_df =ak.stock_financial_abstract_ths(symbol=symbol, indicator=indicator)
            self.logger.info(f"获取到 {symbol} 的财务摘要:\n {financial_abstract_df}")
        except Exception as e:
            self.logger.error(f"获取财务摘要失败: {e}")
        
        return financial_abstract_df
    
    # 获取资产负债表
    def stock_financial_debt_ths(self, symbol, indicator="按报告期"):
        """
        获取资产负债表（akshare）
        :param symbol: 股票代码
        :param indicator: 指标; choice of {"按报告期", "按年度"}
        """
        balance_sheet_df = None
        # 1. 获取资产负债表 （建议使用 按报告期，按年度），应该按报告期、按年度
        try:
            # 返回列信息： 报告期 报表核心指标 *所有者权益（或股东权益）合计   *资产合计   *负债合计 *归属于母公司所有者权益合计 报表全部指标 流动资产    货币资金   交易性金融资产 应收票据及应收账款   其中：应收票据      应收账款      预付款项   其他应收款合计  其中：应收利息    其他应收款        存货    其他流动资产     总现金  流动资产合计 非流动资产    长期股权投资 其他权益工具投资  固定资产合计 其中：固定资产    在建工程合计   其中：在建工程      无形资产        商誉   长期待摊费用   递延所得税资产   其他非流动资产 非流动资产合计    资产合计 流动负债      短期借款 应付票据及应付账款   其中：应付票据      应付账款     预收款项      合同负债    应付职工薪酬      应交税费   其他应付款合计      应付股利     其他应付款 一年内到期的非流动负债    其他流动负债 流动负债合计 非流动负债      长期借款   递延所得税负债 递延收益-非流动负债   非流动负债合计    负债合计 所有者权益（或股东权益） 实收资本（或股本）      资本公积      盈余公积      未分配利润 归属于母公司所有者权益合计    少数股东权益 所有者权益（或股东权益）合计 负债和所有者权益（或股东权益）合计
            balance_sheet_df =ak.stock_financial_debt_ths(symbol=symbol, indicator=indicator)
            self.logger.info(f"获取到 {symbol} 的资产负债表:\n {balance_sheet_df}")
        except Exception as e:
            self.logger.error(f"获取资产负债表失败: {e}")
        
        return balance_sheet_df

    # 获取利润表
    def stock_financial_benefit_ths(self, symbol, indicator="按报告期"):
        """
        获取利润表（akshare）
        :param symbol: 股票代码
        :param indicator: 指标; choice of {"按报告期","按单季度", "按年度"}
        """
        profit_loss_df = None
        # 1. 获取利润表 （建议使用 按报告期，按年度），应该按报告期、按年度
        try:
            # 返回列信息： 报告期 报表核心指标       *净利润  *营业总收入  *营业总成本 *归属于母公司所有者的净利润 *扣除非经常性损益后的净利润 报表全部指标 一、营业总收入 其中：营业收入 二、营业总成本 其中：营业成本  营业税金及附加      销售费用      管理费用      研发费用       财务费用  其中：利息费用      利息收入    资产减值损失   信用减值损失 加：公允价值变动收益      投资收益 其中：联营企业和合营企业的投资收益   资产处置收益      其他收益     三、营业利润   加：营业外收入  减：营业外支出     四、利润总额   减：所得税费用      五、净利润 （一）持续经营净利润 归属于母公司所有者的净利润    少数股东损益 扣除非经常性损益后的净利润 六、每股收益 （一）基本每股收益 （二）稀释每股收益 七、其他综合收益   八、综合收益总额 归属于母公司股东的综合收益总额 归属于少数股东的综合收益总额
            profit_loss_df =ak.stock_financial_benefit_ths(symbol=symbol, indicator=indicator)
            self.logger.info(f"获取到 {symbol} 的利润表:\n {profit_loss_df}")
        except Exception as e:
            self.logger.error(f"获取利润表失败: {e}")
        
        return profit_loss_df

    # 获取现金流量表
    def stock_financial_cash_ths(self, symbol, indicator="按报告期"):
        """
        获取现金流量表（akshare）
        :param symbol: 股票代码
        :param indicator: 指标; choice of {"按报告期","按单季度", "按年度"}
        """
        cashflow_df = None
        # 1. 获取现金流量表 （建议使用 按报告期，按年度），应该按报告期、按年度
        try:
            # 返回列信息： 报告期 报表核心指标 *现金及现金等价物净增加额 *经营活动产生的现金流量净额 *投资活动产生的现金流量净额 *筹资活动产生的现金流量净额 *期末现金及现金等价物余额 报表全部指标 一、经营活动产生的现金流量 销售商品、提供劳务收到的现金  收到的税费与返还 收到其他与经营活动有关的现金 经营活动现金流入小计 购买商品、接受劳务支付的现金 支付给职工以及为职工支付的现金   支付的各项税费 支付其他与经营活动有关的现金 经营活动现金流出小计 经营活动产生的现金流量净额 二、投资活动产生的现金流量 收回投资收到的现金 取得投资收益收到的现金 处置固定资产、无形资产和其他长期资产收回的现金净额 收到其他与投资活动有关的现金 投资活动现金流入小计 购建固定资产、无形资产和其他长期资产支付的现金   投资支付的现金 取得子公司及其他营业单位支付的现金净额 支付其他与投资活动有关的现金 投资活动现金流出小计 投资活动产生的现金流量净额 三、筹资活动产生的现金流量 吸收投资收到的现金 其中：子公司吸收少数股东投资收到的现金 取得借款收到的现金 收到其他与筹资活动有关的现金 筹资活动现金流入小计 偿还债务支付的现金 分配股利、利润或偿付利息支付的现金 支付其他与筹资活动有关的现金 筹资活动现金流出小计 筹资活动产生的现金流量净额 四、汇率变动对现金及现金等价物的影响 五、现金及现金等价物净增加额 加：期初现金及现金等价物余额 六、期末现金及现金等价物余额 补充资料： 1、将净利润调节为经营活动现金流量：        净利润  加：资产减值准备 固定资产折旧、油气资产折耗、生产性生物资产折旧   无形资产摊销 长期待摊费用摊销 处置固定资产、无形资产和其他长期资产的损失 固定资产报废损失  公允价值变动损失       财务费用       投资损失 递延所得税资产减少 递延所得税负债增加      存货的减少 经营性应收项目的减少 经营性应付项目的增加        其他 间接法-经营活动产生的现金流量净额 2、不涉及现金收支的重大投资和筹资活动： 3、现金及现金等价物净变动情况：   现金的期末余额 减：现金的期初余额 间接法-现金及现金等价物净增加额
            cashflow_df =ak.stock_financial_cash_ths(symbol=symbol, indicator=indicator)
            self.logger.info(f"获取到 {symbol} 的现金流量表:\n {cashflow_df}")
        except Exception as e:
            self.logger.error(f"获取现金流量表失败: {e}")
        
        return cashflow_df

    #  获取主要财务指标 不推荐量化，缺失关键选股指标：净利润同比、ROE、毛利率、PE、总股本、流通股本、扣非净利润。
    def stock_financial_abstract_sina(self, symbol):
        """
        获取主要财务指标（新浪财经-财务报表-关键指标）
        :param symbol: 股票代码
        """
        financial_abstract = None
        # 1. 获取主要财务指标 
        try:
            # 返回列信息： 选项                  指标      20260331      20251231     ...  报告日期
            financial_abstract =ak.stock_financial_abstract(symbol=symbol)
            self.logger.info(f"获取到 {symbol} 的主要财务指标:\n {financial_abstract}")                
        except Exception as e:
            self.logger.error(f"获取主要财务指标失败: {e}")
        
        return financial_abstract

    # 获取大盘情绪指标
    def stock_market_activity(self):
        """
        获取大盘情绪指标（akshare）
        :return: 大盘情绪指标
        :rtype: pandas.DataFrame
                 item                value
        0         上涨               3527.0
        1         涨停                159.0
        2       真实涨停                139.0
        3   st st*涨停                 54.0
        4         下跌               1584.0
        5         跌停                 28.0
        6       真实跌停                 25.0
        7   st st*跌停                  5.0
        8         平盘                 82.0
        9         停牌                 11.0
        10       活跃度               67.77%
        11      统计日期  2026-07-03 15:00:00
        """
        market_sentiment_df = None
        # 1. 获取大盘情绪指标 
        try:
            market_sentiment_df =ak.stock_market_activity_legu()
            self.logger.info(f"获取到的大盘情绪指标:\n {market_sentiment_df}")                
        except Exception as e:
            self.logger.error(f"获取大盘情绪指标失败: {e}")
        
        return market_sentiment_df

    # 涨停数据
    def stock_limit_up_data(self, date_str=""):
        """
        获取大盘涨停家数（akshare）
        :return: 大盘涨停家数
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            序号      代码    名称        涨跌幅     最新价         成交额          流通市值           总市值        换手率       封板资金  首次封板时间  最后封板时间  炸板次数  涨停统计  连板数   所属行业
            1  000595  宝塔实业  10.052910    6.24    94916640  7.105216e+09  7.105216e+09   1.335873   93156960  092500  092500     0   2/2    2     电力
        """
        limit_up_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        
        try:
            # 1. 获取大盘涨停家数 
            # 返回列信息：序号      代码    名称        涨跌幅     最新价         成交额          流通市值           总市值        换手率       封板资金  首次封板时间  最后封板时间  炸板次数  涨停统计  连板数   所属行业
            limit_up_df = ak.stock_zt_pool_em(date=date_str)
            self.logger.info(f"获取到 {date_str} 的大盘涨停家数:\n {limit_up_df}")                
        except Exception as e:
            self.logger.error(f"获取大盘涨停家数失败: {e}")
        
        return limit_up_df

    # 跌停数据
    def stock_limit_down_data(self, date_str=""):
        """
        获取大盘跌停家数（akshare）
        :return: 大盘跌停家数
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
             序号      代码    名称        涨跌幅    最新价          成交额          流通市值           总市值        动态市盈率        换手率        封单资金  最后封板时间       板上成交额  连续跌停  开板次数  所属行业
             1  000890   法尔胜  -9.977827   8.12    262807097  3.406267e+09  3.406372e+09   -92.704613   7.649436     2385656  132651   160601391     1    40  环保设备
        """
        limit_down_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        
        try:
            # 1. 获取大盘跌停家数 
            limit_down_df = ak.stock_zt_pool_dtgc_em(date=date_str)
            self.logger.info(f"获取到 {date_str} 的大盘跌停家数:\n {limit_down_df}")                
        except Exception as e:
            self.logger.error(f"获取大盘跌停家数失败: {e}")
        
        return limit_down_df


    # 融资融券标的信息（深市）
    def stock_margin_trading_data_szse(self, date_str=""):
        """
        获取融资融券标的信息（akshare）
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            证券代码            证券简称 融资标的 融券标的 当日可融资 当日可融券 融券卖出价格限制 涨跌幅限制
            000001            平安银行    Y    Y     Y     Y        Y   10%
        """
        margin_trading_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        # 1. 获取融资融券标的信息
        try:
            margin_trading_df = ak.stock_margin_underlying_info_szse(date=date_str)
            self.logger.info(f"获取到 {date_str} 融资融券标的信息:\n {margin_trading_df}")
        except Exception as e:
            self.logger.error(f"获取融资融券标的信息失败: {e}")
        
        return margin_trading_df
    
    # 融资融券标的信息（沪市）
    def stock_margin_trading_data_sh(self, date_str=""):
        """
        获取融资融券标的信息（沪市）
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            证券代码            证券简称 融资标的 融券标的 当日可融资 当日可融券 融券卖出价格限制 涨跌幅限制
            000001            平安银行    Y    Y     Y     Y        Y   10%
        """
        margin_trading_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        # 1. 获取融资融券标的信息
        try:
            # Todo 未测试 获取沪市融资融券标的信息
            # 返回列信息：证券代码 证券简称 融资比例 融券比例
            # 100001 50ETF 0.000000 0.000000
            # 100002 50ETF 0.000000 0.00
            # 10
            margin_trading_df = ak.stock_margin_ratio_pa(symbol="沪市", date=date_str)
            self.logger.info(f"获取到 {date_str} 融资融券标的信息:\n {margin_trading_df}")
        except Exception as e:
            self.logger.error(f"获取融资融券标的信息失败: {e}")
        
        return margin_trading_df
    

    # 上海证券交易所-融资融券数据-融资融券明细（沪市）
    def stock_margin_detail_data_sh(self, date_str=""):
        """
        获取上海证券交易所-融资融券数据-融资融券明细（沪市）
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            信用交易日期  标的证券代码    标的证券简称         融资余额       融资买入额       融资偿还额       融券余量    融券卖出量    融券偿还量
            20260703  510050     50ETF   1492969419    29753519    95420218   37235940  1179400  1410900
        """
        margin_trading_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        # 1. 获取上海证券交易所-融资融券数据-融资融券明细
        try:
            margin_trading_df = ak.stock_margin_detail_sse(date=date_str)
            self.logger.info(f"获取时间 {date_str} 沪市融资融券明细:\n {margin_trading_df}")
        except Exception as e:
            self.logger.error(f"获取(沪市)融资融券明细失败，可能是空数据: {e}")
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return margin_trading_df
    
    # 深圳证券交易所-融资融券数据-融资融券明细（深市）
    def stock_margin_detail_data_sz(self, date_str=""):
        """
        获取深圳证券交易所-融资融券数据-融资融券明细（深市）
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            证券代码            证券简称       融资买入额         融资余额    融券卖出量       融券余量       融券余额       融资融券余额
            000001            平安银行    95032872   5327610410    53400    1697500   17450300   5345060710

        """
        margin_trading_df = None
        if not date_str:
            # 获取今日
            date_str = datetime.now().strftime('%Y%m%d')
        # 1. 获取深圳证券交易所-融资融券数据-融资融券明细
        try:
            margin_trading_df = ak.stock_margin_detail_szse(date=date_str)
            self.logger.info(f"获取时间 {date_str} 深市融资融券明细:\n {margin_trading_df}")
        except Exception as e:
            self.logger.error(f"获取(深市)融资融券明细失败: {e}")
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return margin_trading_df

    # 深圳证券交易所-融资融券汇总（深市）
    def stock_margin_szse(self, date_str=""):
        """
        获取深圳证券交易所-融资融券汇总（深市）
        :param date_str: 日期字符串，格式为YYYYMMDD，默认当前日期
        :rtype: pandas.DataFrame
        返回值例子：
            融资买入额      融资余额  融券卖出量  融券余量   融券余额    融资融券余额
            1642.67  14761.73   0.31  8.98  77.51  14839.25
        """
        margin_trading_df = None
        if not date_str:
            date_str = datetime.now().strftime('%Y%m%d')

        try:
            margin_trading_df = ak.stock_margin_szse(date=date_str)
            self.logger.info(f"获取到 {date_str} 的融资融券汇总:\n {margin_trading_df}")
        except ValueError as e:
            if "Length mismatch" in str(e):
                self.logger.warning(f"{date_str} 的融资融券汇总为空（可能是非交易日），尝试获取前一交易日数据")
                try:
                    date_obj = datetime.strptime(date_str, '%Y%m%d')
                    for i in range(1, 5):
                        prev_date = (date_obj - pd.Timedelta(days=i)).strftime('%Y%m%d')
                        margin_trading_df = ak.stock_margin_szse(date=prev_date)
                        if margin_trading_df is not None and not margin_trading_df.empty:
                            self.logger.info(f"获取到 {prev_date} 的融资融券汇总（替代{date_str}）:\n {margin_trading_df}")
                            break
                except Exception as e2:
                    self.logger.error(f"获取前一交易日融资融券汇总失败: {e2}")
            else:
                self.logger.error(f"获取融资融券汇总失败: {e}")
        except Exception as e:
            self.logger.error(f"获取融资融券汇总失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return margin_trading_df

    # 个股新闻
    def get_stock_news_from_em(self, symbol):
        """
        获取股票的新闻数据（东方财富）
        :param symbol: 股票代码，例如 "688549"
        :rtype: pandas.DataFrame
        列：关键词、新闻标题、新闻内容、发布时间、文章来源、新闻链接
        返回值例子：
            关键词                               新闻标题                                                                                                                                                    新闻内容                 发布时间   文章来源                                                    新闻链接
            688549  中巨芯股东远致富海完成减持计划 累计减持股份占公司总股本2.89%         7月2日，中巨芯（688549.SH）发布公告称，公司股东深圳远致富海十一号投资企业（有限合伙）（简称“远致富海”）在2026年5月15日至7月1日期间，通过集中竞价及大宗交易两种方式合计减持公司股份42697404股，占公司总股本的2.89%，本次减持计划已全部实施完毕，减持总金额达  2026-07-02 20:36:16   央广财经  http://finance.eastmoney.com/a/202607023792127980.html
            688549                  10股获重要股东大手笔增持（附股）     木林森 1 1 1286.63 15220.83 -6.42 002242 九阳股份 1 1 1071.02 9001.48 5.06 600509 天富能源 1 1 400.30 3290.47 -0.72 002091 江苏国泰 1 1 281.00 2031.63 3.90 688549  2026-07-06 09:35:00  证券时报网  http://finance.eastmoney.com/a/202607063794499152.html
        """
        # 尝试获取个股新闻（东方财富）
        df = None
        try:
            df = ak.stock_news_em(symbol=symbol)
            self.logger.info(f"✓ 从东方财富获取到 {symbol} 的新闻，共 {len(df)} 条，数据:\n{df}")
        except Exception as e:
            self.logger.warning(f" ⚠ 从东方财富获取失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")

        return df

    # 新浪财经新闻
    def get_stock_global_news_from_sina(self):
        """
        新浪财经-全球财经快讯
        :param symbol: 股票代码，例如 "688549"
        :rtype: pandas.DataFrame
        列：时间、内容
        返回值例子：
            时间             			内容
            2026-07-06 13:15:30         【中公教育：内外部经营环境未发生且未预计将要发生重大变化】中公教育公告，公司股票价格短期波动较大；经关注、核实，公司近期生产经营情况正常，内外部经营环境未发生且未预计将要发生重大变化，不存在应予以披露而未披露事项，公司前期披露的信息不存在需要更正、补充之处。
        """
        df = None
        # 尝试获取全球财经快讯新闻（新浪财经）
        try:
            df = ak.stock_info_global_sina()
            self.logger.info(f"✓ 从新浪财经获取全球财经快讯，共 {len(df)} 条，数据:\n{df}")
        except Exception as e:
            self.logger.error(f"从新浪财经获取全球财经快讯失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return df

    # 财联社电报（不可用）
    def get_stock_global_news_from_cls(self):
        """
        财联社-全球财经快讯
        :param symbol: 股票代码，例如 "688549"
        :rtype: pandas.DataFrame
         "标题", "内容", "发布日期", "发布时间" "等级"
        """
        df = None
        # 尝试获取全球财经快讯新闻（财联社电报）
        try:
            df = ak.stock_info_global_cls()
            self.logger.info(f"✓ 从财联社电报获取全球财经快讯，共 {len(df)} 条，数据:\n{df}")
        except Exception as e:
            self.logger.error(f"获取财联社电报全球财经快讯失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return df

    # 同花顺财经
    def get_stock_global_news_from_ths(self):
        """
        同花顺-全球财经快讯
        :rtype: pandas.DataFrame
        列：标题、内容、发布时间、链接
        返回值例子：
            标题                                                内容                                                                                                                                                            发布时间              链接
            沪深京三市成交额超2.5万亿元，较上日此时放量343亿元      据同花顺iFinD数据，沪深京三市成交额超2.5万亿元，较上日此时放量343亿元，预计全天成交金额约3.2万亿元。截至目前，沪市成交额11496亿元，深市成交额13340亿元，北证50成交额168亿元。  2026-07-06 13:38:16  https://news.10jqka.com.cn/20260706/c677970466.shtml
        """
        df = None
        # 尝试获取全球财经快讯新闻（同花顺）
        try:
            df = ak.stock_info_global_ths()
            self.logger.info(f"✓ 从同花顺获取全球财经直播，共 {len(df)} 条，数据:\n{df}")
        except Exception as e:
            self.logger.error(f"获取同花顺全球财经直播失败: {e}")
            import traceback
            self.logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
        
        return df



# 测试代码
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
    
    akshare_data_fetcher = AkshareDataFetcher()

    # 测试股票代码
    test_symbol = "688549"  # 中巨芯
    
    # # 1. 测试获取基本信息(东方财富  
    # print(f"\n1. 获取 {test_symbol} 的基本信息:")
    # info = akshare_data_fetcher.get_stock_basic_info_akshare(test_symbol)
    # print(f"基本信息: {info}")

    # time.sleep(1)
    
    # # 2. 测试获取历史数据
    # print(f"\n2. 获取 {test_symbol} 的历史数据:")
    # hist_data = akshare_data_fetcher.get_stock_history_data_akshare(test_symbol,start_date="20260601",end_date="20260630",adjust="qfq")
    # print(f"历史数据形状: {hist_data.shape}")
    # if not hist_data.empty:
    #     print(f"最近5天数据:\n{hist_data.tail()}")

    # time.sleep(1)
    
    # # 3. 测试获取实时数据
    # print(f"\n3. 获取 {test_symbol} 的实时信息:")
    # realtime = akshare_data_fetcher.get_stock_realtime_info_sina(test_symbol)
    # print(f"实时信息: {realtime}")

    # time.sleep(1)

    # # 4. 可用，但是太慢，全市场的快照实时行情数据 测试获取实时数据(东方财富)
    # print(f"\n4. 获取 {test_symbol} 的实时信息:")
    # realtime = akshare_data_fetcher.get_realtime_quotes_akshare(test_symbol)
    # print(f"实时信息: {realtime}")

    # time.sleep(2)
    
    # # 5. 个股资金流向
    print(f"\n5. 获取 {test_symbol} 的资金流向:")
    fund_flow = akshare_data_fetcher.get_individual_fund_flow_akshare(test_symbol, market="sh")
    print(f"资金流向: {fund_flow}")

    # time.sleep(2)

    # # 6. 个股财务数据
    # print(f"\n6. 获取 {test_symbol} 的财务数据:")
    # for report_type in ['income', 'balance', 'cashflow']:
    #     financial_data = akshare_data_fetcher.get_financial_data_akshare(test_symbol, report_type=report_type)
    #     print(f"{report_type}财务数据: {financial_data}")
    
    # time.sleep(2)

    # # "市盈率(TTM)", "市盈率(静)", "市净率", "市现率"
    # test_indicator = "市盈率(TTM)"
    # test_period = "近一年"
    # # 7. 个股估值数据
    # print(f"\n7. 获取 {test_symbol} 的估值数据:")
    # valuation_data = akshare_data_fetcher.get_valuation_value_akshare(test_symbol, indicator=test_indicator, period=test_period)
    # print(f"估值数据: {valuation_data}")

    # time.sleep(2)
    
    # # 8. 个股主要财务指标
    # print(f"\n8. 获取 {test_symbol} 的主要财务指标:")
    # financial_ratios = akshare_data_fetcher.stock_financial_abstract_ths(test_symbol)
    # print(f"主要财务指标: {financial_ratios}")
    # time.sleep(2)

    # # 9. 个股主要财务指标(同花顺-负债表)
    # print(f"\n9. 获取 {test_symbol} 的主要财务指标(同花顺-负债表):")
    # financial_ratios = akshare_data_fetcher.stock_financial_debt_ths(test_symbol)
    # print(f"主要财务指标(同花顺-负债表): {financial_ratios}")
    # time.sleep(2)

    # # 10. 个股主要财务指标(同花顺-利润表)
    # print(f"\n10. 获取 {test_symbol} 的主要财务指标(同花顺-利润表):")
    # financial_ratios = akshare_data_fetcher.stock_financial_benefit_ths(test_symbol)
    # print(f"主要财务指标(同花顺-利润表): {financial_ratios}")
    # time.sleep(2)
    
    # # 11. 个股主要财务指标(同花顺-现金流表)
    # print(f"\n11. 获取 {test_symbol} 的主要财务指标(同花顺-现金流表):")
    # financial_ratios = akshare_data_fetcher.stock_financial_cash_ths(test_symbol)
    # print(f"主要财务指标(同花顺-现金流表): {financial_ratios}")
    # time.sleep(2)

    # # 12. 获取主要财务指标（新浪财经-财务报表-关键指标）
    # print(f"\n12. 获取 {test_symbol} 的主要财务指标（新浪财经-财务报表-关键指标）:")
    # financial_abstract = akshare_data_fetcher.stock_financial_abstract_sina(test_symbol)
    # print(f"主要财务指标（新浪财经-财务报表-关键指标）: {financial_abstract}")
    # time.sleep(2)
    
    # # 13. 获取大盘情绪指标
    # print(f"\n13. 获取 {test_symbol} 的大盘情绪指标:")
    # market_activity_df = akshare_data_fetcher.stock_market_activity(test_symbol)
    # print(f"大盘情绪指标: {market_activity_df}")
    # time.sleep(2)

    # # 14. 涨停数据
    # print(f"\n14. 获取 {test_symbol} 的涨停数据:")
    # data_str = "20260703"
    # limit_up_data = akshare_data_fetcher.stock_limit_up_data(data_str)
    # print(f"涨停数据: {limit_up_data}")
    # time.sleep(2)

    # # 15. 跌停数据
    # print(f"\n15. 获取 {test_symbol} 的跌停数据:")
    # limit_down_data = akshare_data_fetcher.stock_limit_down_data(data_str)
    # print(f"跌停数据: {limit_down_data}")
    # time.sleep(2)

    # # 16. 融资融券标的信息
    # print(f"\n16. 获取 {test_symbol} 的融资融券标的信息:")
    # margin_trading_data = akshare_data_fetcher.stock_margin_trading_data(data_str)
    # print(f"融资融券标的信息: {margin_trading_data}")
    # time.sleep(2)

    # 17. 融资融券明细（沪市）
    data_str = "20260703"
    print(f"\n17. 获取 {test_symbol} 的融资融券明细（沪市）:")
    margin_trading_data_sh = akshare_data_fetcher.stock_margin_detail_data_sh(data_str)
    print(f"融资融券明细（沪市）: {margin_trading_data_sh}")
    time.sleep(2)

    # #18. 融资融券明细（深市） 空数据
    # print(f"\n18. 获取 {test_symbol} 的融资融券明细（深市）:")
    # margin_trading_data_sz = akshare_data_fetcher.stock_margin_detail_data_sz(data_str)
    # print(f"融资融券明细（深市）: {margin_trading_data_sz}")
    # time.sleep(2)

    # # 19. 融资融券汇总（深市）
    # print(f"\n19. 获取 {test_symbol} 的融资融券汇总（深市）:")
    # margin_trading_data_szse = akshare_data_fetcher.stock_margin_szse(data_str)
    # print(f"融资融券汇总（深市）: {margin_trading_data_szse}")
    # time.sleep(2)

    # 20. 个股新闻(东方财富)
    print(f"\n20. 获取 {test_symbol} 的新闻:")
    news_data = akshare_data_fetcher.get_stock_news_from_em(test_symbol)
    print(f"新闻: {news_data}")
    time.sleep(2)

    # 21. 全球财经快讯(新浪财经)
    print(f"\n21. 获取全球财经快讯(新浪财经):")
    news_data = akshare_data_fetcher.get_stock_global_news_from_sina()
    print(f"新闻: {news_data}")
    time.sleep(2)

    # 22. 全球财经快讯(财联社)
    print(f"\n22. 获取全球财经快讯(财联社):")
    news_data = akshare_data_fetcher.get_stock_global_news_from_cls()
    print(f"新闻: {news_data}")
    time.sleep(2)

    # 23. 全球财经快讯(同花顺)
    print(f"\n23. 获取全球财经快讯(同花顺):")
    news_data = akshare_data_fetcher.get_stock_global_news_from_ths()
    print(f"新闻: {news_data}")
    time.sleep(2)
    


    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)