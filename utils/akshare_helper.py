"""
Akshare 请求补丁模块

解决 Akshare 因缺少请求头（User-Agent）导致东方财富等服务器
关闭连接（RemoteDisconnected）的问题。

工作原理：
1. 提供 RequestsPatcher 上下文管理器，临时注入默认请求头，退出时自动还原
2. 提供 patch_requests_context() 函数，返回上下文管理器
3. 保留全局 patch_requests() 函数（向后兼容）
4. 提供 retry_on_failure 装饰器，方便包装有问题的 Akshare 接口

使用方式：
    # 方式 1: 上下文管理器（推荐）
    from utils.akshare_helper import RequestsPatcher
    
    with RequestsPatcher():
        # 此范围内的 akshare 请求会使用自定义请求头
        result = ak.stock_zh_a_spot_em()
    # 退出后自动还原

    from utils.akshare_helper import RequestsPatcher
    # 基本用法
    with RequestsPatcher():
        result = ak.stock_zh_a_spot_em()
    # 退出后自动还原

    # 自定义请求头
    with RequestsPatcher(headers={'X-Custom': 'value'}):
        result = ak.stock_zh_a_spot_em()
    
    # 自定义超时
    with RequestsPatcher(timeout=60):
        result = ak.stock_zh_a_spot_em()
    
    # 自定义 User-Agent
    with RequestsPatcher(custom_user_agent='MyBot/1.0'):
        result = ak.stock_zh_a_spot_em()
    
    # 方式 2: 使用函数
    from utils.akshare_helper import patch_requests_context
    
    with patch_requests_context():
        result = ak.stock_zh_a_spot_em()
"""

import functools
import time
import random
from contextlib import contextmanager


# 默认请求头 — 模拟现代 Chrome 浏览器
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,'
        'image/avif,image/webp,image/apng,*/*;q=0.8'
    ),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://quote.eastmoney.com/',
    'Cache-Control': 'no-cache',
}

# 多个 User-Agent 轮换，降低被屏蔽概率
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# 不需要注入浏览器头的域名白名单（API 服务）
API_DOMAINS = {
    'api.waditu.com',      # Tushare API
    'api.deepseek.com',    # DeepSeek API
    'api.openai.com',      # OpenAI API
}


class RequestsPatcher:
    """
    请求补丁上下文管理器
    
    临时修补 requests 库的请求方法，注入默认请求头和超时设置。
    退出上下文时自动还原到原始状态。
    
    用法:
        with RequestsPatcher():
            result = ak.stock_zh_a_spot_em()
        # 退出后自动还原
    """
    
    def __init__(self, headers=None, timeout=30, custom_user_agent=None):
        """
        初始化补丁上下文
        
        :param headers: 自定义请求头（可选），会与默认请求头合并
        :param timeout: 请求超时时间（秒），默认 30 秒
        :param custom_user_agent: 自定义 User-Agent（可选），如果提供则不使用随机轮换
        """
        self._timeout = timeout
        self._custom_headers = headers
        self._custom_user_agent = custom_user_agent
        self._original_get = None
        self._original_post = None
        self._original_request = None
        self._original_retry_json = None
        self._patched = False
    
    def _get_headers(self):
        """获取合并后的请求头"""
        headers = dict(DEFAULT_HEADERS)
        
        # 设置 User-Agent
        if self._custom_user_agent:
            headers['User-Agent'] = self._custom_user_agent
        else:
            headers['User-Agent'] = random.choice(USER_AGENTS)
        
        # 合并自定义请求头
        if self._custom_headers:
            headers.update(self._custom_headers)
        
        return headers
    
    def _make_patched_request(self, original_request):
        """创建修补后的 request 方法"""
        @functools.wraps(original_request)
        def patched_request(self_obj, method, url, **kwargs):
            from urllib.parse import urlparse
            
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # API 域名白名单，不注入浏览器头
            if domain in API_DOMAINS:
                if 'timeout' not in kwargs or kwargs['timeout'] is None:
                    kwargs['timeout'] = self._timeout
                return original_request(self_obj, method, url, **kwargs)
            
            # 注入请求头
            kwargs['headers'] = self._get_headers()
            
            # 默认超时
            if 'timeout' not in kwargs or kwargs['timeout'] is None:
                kwargs['timeout'] = self._timeout
            
            return original_request(self_obj, method, url, **kwargs)
        
        return patched_request
    
    def _make_patched_get(self, original_get):
        """创建修补后的 get 方法"""
        @functools.wraps(original_get)
        def patched_get(url, **kwargs):
            from urllib.parse import urlparse
            
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            if domain in API_DOMAINS:
                if 'timeout' not in kwargs or kwargs['timeout'] is None:
                    kwargs['timeout'] = self._timeout
                return original_get(url, **kwargs)
            
            kwargs['headers'] = self._get_headers()
            
            if 'timeout' not in kwargs or kwargs['timeout'] is None:
                kwargs['timeout'] = self._timeout
            
            return original_get(url, **kwargs)
        
        return patched_get
    
    def _make_patched_post(self, original_post):
        """创建修补后的 post 方法"""
        @functools.wraps(original_post)
        def patched_post(url, **kwargs):
            from urllib.parse import urlparse
            
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            if domain in API_DOMAINS:
                if 'timeout' not in kwargs or kwargs['timeout'] is None:
                    kwargs['timeout'] = self._timeout
                return original_post(url, **kwargs)
            
            kwargs['headers'] = self._get_headers()
            
            if 'timeout' not in kwargs or kwargs['timeout'] is None:
                kwargs['timeout'] = self._timeout
            
            return original_post(url, **kwargs)
        
        return patched_post
    
    def _patch_akshare_retry(self):
        """修补 akshare 内部的重试函数"""
        try:
            import akshare as _ak
            if hasattr(_ak, 'request') and hasattr(_ak.request, 'make_request_with_retry_json'):
                orig_retry = _ak.request.make_request_with_retry_json
                self._original_retry_json = orig_retry
                
                @functools.wraps(orig_retry)
                def patched_retry_json(url, params=None, headers=None, proxies=None, max_retries=3, retry_delay=1):
                    final_headers = self._get_headers()
                    if headers:
                        final_headers.update(headers)
                    return orig_retry(url, params=params, headers=final_headers,
                                     proxies=proxies, max_retries=max_retries, retry_delay=retry_delay)
                
                _ak.request.make_request_with_retry_json = patched_retry_json
                return True
        except (ImportError, AttributeError):
            pass
        return False
    
    def _restore_akshare_retry(self):
        """还原 akshare 内部的重试函数"""
        try:
            import akshare as _ak
            if hasattr(_ak, 'request') and hasattr(_ak.request, 'make_request_with_retry_json'):
                if self._original_retry_json is not None:
                    _ak.request.make_request_with_retry_json = self._original_retry_json
        except (ImportError, AttributeError):
            pass
    
    def __enter__(self):
        """进入上下文时应用补丁"""
        import requests as req_lib
        
        # 保存原始函数
        self._original_get = req_lib.get
        self._original_post = req_lib.post
        self._original_request = req_lib.Session.request
        
        # 应用补丁
        req_lib.Session.request = self._make_patched_request(self._original_request)
        req_lib.get = self._make_patched_get(self._original_get)
        req_lib.post = self._make_patched_post(self._original_post)
        
        # 修补 akshare 内部函数
        self._patch_akshare_retry()
        
        self._patched = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时还原"""
        if not self._patched:
            return False
        
        import requests as req_lib
        
        # 还原原始函数
        if self._original_request is not None:
            req_lib.Session.request = self._original_request
        if self._original_get is not None:
            req_lib.get = self._original_get
        if self._original_post is not None:
            req_lib.post = self._original_post
        
        # 还原 akshare 内部函数
        self._restore_akshare_retry()
        
        self._patched = False
        
        # 不抑制异常
        return False


@contextmanager
def patch_requests_context(headers=None, timeout=30, custom_user_agent=None):
    """
    返回一个上下文管理器，临时应用请求补丁
    
    用法:
        with patch_requests_context():
            result = ak.stock_zh_a_spot_em()
    
    :param headers: 自定义请求头（可选）
    :param timeout: 请求超时时间（秒），默认 30 秒
    :param custom_user_agent: 自定义 User-Agent（可选）
    """
    patcher = RequestsPatcher(headers=headers, timeout=timeout, custom_user_agent=custom_user_agent)
    with patcher:
        yield patcher


################################################################################################
# 全局补丁状态（向后兼容）
_global_patched = False
_global_originals = {}


def patch_requests():
    """
    【已废弃】全局修补 requests.get / requests.post / requests.request
    
    此函数会导致全局修改，无法还原。建议使用 RequestsPatcher 上下文管理器。
    
    在 import akshare 之前调用一次即可。
    """
    global _global_patched
    if _global_patched:
        return
    _global_patched = True
    
    import requests as req_lib
    
    # 保存原始函数
    _global_originals['get'] = req_lib.get
    _global_originals['post'] = req_lib.post
    _global_originals['request'] = req_lib.Session.request
    
    # 创建临时补丁实例
    temp_patcher = RequestsPatcher()
    
    # 应用补丁
    req_lib.Session.request = temp_patcher._make_patched_request(_global_originals['request'])
    req_lib.get = temp_patcher._make_patched_get(_global_originals['get'])
    req_lib.post = temp_patcher._make_patched_post(_global_originals['post'])
    
    # 修补 akshare 内部函数
    temp_patcher._patch_akshare_retry()
    
    print("[AkshareHelper] 请求补丁已应用 — 默认请求头 + 超时 30s")


def unpatch_requests():
    """
    【已废弃】还原全局请求补丁到原始状态
    
    此函数用于配合 patch_requests() 使用。
    建议使用 RequestsPatcher 上下文管理器替代这两个函数。
    """
    global _global_patched
    if not _global_patched:
        return
    _global_patched = False
    
    import requests as req_lib
    
    # 还原原始函数
    if 'request' in _global_originals:
        req_lib.Session.request = _global_originals['request']
    if 'get' in _global_originals:
        req_lib.get = _global_originals['get']
    if 'post' in _global_originals:
        req_lib.post = _global_originals['post']
    
    # 还原 akshare 内部函数
    try:
        import akshare as _ak
        if hasattr(_ak, 'request') and hasattr(_ak.request, 'make_request_with_retry_json'):
            if 'retry_json' in _global_originals:
                _ak.request.make_request_with_retry_json = _global_originals['retry_json']
    except (ImportError, AttributeError):
        pass
    
    _global_originals.clear()
    print("[AkshareHelper] 请求补丁已还原")

#############################################################################################
def retry_on_failure(max_retries=3, base_delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """
    重试装饰器 — 用于包装不稳定的数据获取函数。
    
    用法:
        @retry_on_failure(max_retries=3)
        def fetch_something():
            return ak.stock_xxx(...)
    """
    def decorator(func):
        """
        装饰器内层函数 — 接收被装饰的函数作为参数
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """
            包装函数 — 实现重试逻辑的核心部分
            :param args: 原函数的位置参数
            :param kwargs: 原函数的关键字参数
            """
            last_exc = None  # 保存最后一次异常，用于全部失败时抛出
            
            # 循环执行重试逻辑，最多尝试 max_retries 次
            for attempt in range(max_retries):
                try:
                    # 尝试调用原函数，如果成功则直接返回结果
                    return func(*args, **kwargs)
                except exceptions as e:
                    # 捕获到指定类型的异常
                    last_exc = e  # 保存当前异常
                    
                    # 判断是否还有重试机会（不是最后一次尝试）
                    if attempt < max_retries - 1:
                        # 计算重试延迟：指数退避 + 随机抖动
                        # base_delay * (backoff ** attempt) = 指数增长的延迟
                        # random.uniform(0, 0.5) = 添加 0-0.5 秒随机抖动，避免请求集中
                        delay = base_delay * (backoff ** attempt) + random.uniform(0, 0.5)
                        
                        # 打印重试日志，包含函数名、尝试次数、异常信息和延迟时间
                        print(f"[Retry] {func.__name__} 失败 (第{attempt+1}次): {e}, "
                              f"{delay:.1f}s 后重试...")
                        
                        # 等待指定时间后继续重试
                        time.sleep(delay)
            
            # 如果所有重试都失败，抛出最后一次捕获的异常
            raise last_exc
        
        return wrapper  # 返回包装后的函数
    return decorator
