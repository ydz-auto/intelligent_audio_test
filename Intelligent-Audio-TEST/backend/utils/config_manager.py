import os
import json

try:
    from threading import Lock
except ImportError:
    from dummy_threading import Lock

from flask import Flask

class ConfigManager:
    """
    配置管理器，用于加载和管理统一的并发配置
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance.config = {}
                cls._instance.config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'config',
                    'concurrency_config.json'
                )
                cls._instance.flask_config = None
                cls._instance.load_config()
            return cls._instance

    def set_flask_config(self, app_config):
        """
        设置 Flask 应用配置，用于从 Flask Config 中读取配置

        Args:
            app_config: Flask 应用配置对象
        """
        self.flask_config = app_config

    def load_config(self):
        """
        加载配置文件
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {
                "api_executor": {
                    "max_queue_size": 100,
                    "max_wait_time": 300
                },
                "evaluation_service": {
                    "max_queue_size": 100,
                    "max_wait_time": 30
                }
            }
        except json.JSONDecodeError:
            self.config = {
                "api_executor": {
                    "max_queue_size": 100,
                    "max_wait_time": 300
                },
                "evaluation_service": {
                    "max_queue_size": 100,
                    "max_wait_time": 30
                }
            }

    def get_config(self, service_name):
        """
        获取指定服务的配置

        Args:
            service_name: 服务名称

        Returns:
            dict: 服务配置
        """
        return self.config.get(service_name, {})

    def get_value(self, service_name, key, default=None):
        """
        获取指定服务的配置值

        Args:
            service_name: 服务名称
            key: 配置项名称
            default: 默认值

        Returns:
            配置值
        """
        service_config = self.get_config(service_name)

        value = service_config.get(key)

        if value is None and self.flask_config is not None:
            flask_key = f"{service_name.upper()}_{key.upper()}"
            if flask_key.startswith("EXECUTION_ENGINE_"):
                flask_key = flask_key
            else:
                flask_key = f"EXECUTION_ENGINE_{service_name.upper()}_{key.upper()}"
            value = self.flask_config.get(flask_key)

        return value if value is not None else default

config_manager = ConfigManager()