import os
import sys
import json
import logging
import logging.config
from logging.handlers import RotatingFileHandler
import pandas as pd

# 全局设置：让 pandas 完整打印所有行、所有列
pd.set_option('display.max_rows', None)       # 显示所有行
pd.set_option('display.max_columns', None)     # 显示所有列
pd.set_option('display.width', None)           # 自动适应宽度
pd.set_option('display.max_colwidth', None)    # 显示完整列内容（不省略）


# 全局日志配置标志，防止重复配置
_configured = False

# 设置全局日志配置
def setup_root_logger(root_log_level=logging.DEBUG, console_level=logging.INFO, file_level=logging.DEBUG):
    """
    设置全局日志配置，所有模块共用同一套日志处理器
    
    Args:
        root_log_level: 日志级别，默认 DEBUG
        console_level: 控制台日志级别，默认 INFO
        file_level: 文件日志级别，默认 DEBUG
    
    Returns:
        配置好的 logger 实例
    """
    global _configured
    
    # 将 handlers 添加到 root logger，确保全局共用
    root_logger = logging.getLogger()
    root_logger.setLevel(root_log_level)
    
    # 避免重复添加 handler
    if not _configured:
        _configured = True
        # 打印已有 handler，查看是谁添加的
        for h in root_logger.handlers:
            root_logger.warning(f"已有 logger handler: {type(h).__name__}, formatter={h.formatter}")

        # 通过检查 root logger 上是否已有 RotatingFileHandler 来判断是否已配置
        # 这种方式不受模块热重载影响，因为 handler 是保存在 root logger 上的
        has_our_handler = any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
        if has_our_handler:
            root_logger.warning("已配置 RotatingFileHandler，无需重复添加")
            return root_logger

        # 创建日志目录
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 创建格式化器
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 创建文件处理器（写入文件，支持日志滚动）
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=1024 * 1024 * 10,  # 10MB
            backupCount=5,  # 保留 5 个备份
            encoding='utf-8'
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    return root_logger

# 获取 logger 实例
def get_logger(name=None):
    """
    获取已配置的 logger 实例
    
    Args:
        name: logger 名称，通常使用 __name__
    
    Returns:
        logger 实例
    """
    return logging.getLogger(name)


# Pandas数据转CSV文件
def pandas_to_csv(df: pd.DataFrame, file_path: str = 'logs/data_frame.csv', print_index: bool = False):
    """
    将 pandas DataFrame 导出为 CSV 文件
    
    Args:
        df: 输入的 pandas DataFrame
        file_path: 输出的 CSV 文件路径
        index: 是否包含索引列，默认 False
    
    Returns:
        None
    """
     # 确保文件路径存在
    parent_dir = os.path.dirname(file_path)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    df.to_csv(file_path, index=print_index)


def setup_logger_from_dict_config(config_file='logging_config.json'):
    """
    从 dictConfig 格式的 JSON 配置文件加载日志配置
    
    Args:
        config_file: 配置文件路径，默认为 logging_config.json
    
    Returns:
        配置好的 logger 实例
        
    配置文件格式示例（JSON）:
    {
        "version": 1,
        "disable_existing_loggers": false,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "standard"
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "standard",
                "filename": "logs/app.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8"
            }
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console", "file"]
        }
    }
    """
    global _configured
    
    if _configured:
        return logging.getLogger()
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 确保日志目录存在
            handlers = config.get('handlers', {})
            for handler_name, handler_config in handlers.items():
                filename = handler_config.get('filename')
                if filename:
                    log_dir = os.path.dirname(filename)
                    if log_dir and not os.path.exists(log_dir):
                        os.makedirs(log_dir)
            
            logging.config.dictConfig(config)
            _configured = True
            return logging.getLogger()
        
        except Exception as e:
            print(f"加载日志配置文件失败: {e}，使用默认配置")
    
    # 如果配置文件不存在或加载失败，使用默认配置
    return setup_root_logger()
