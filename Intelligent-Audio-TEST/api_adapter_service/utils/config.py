# -*- coding: utf-8 -*-
"""Configuration loader for api_adapter_service.

Loads YAML configuration from config/application.yml with environment
variable substitution support (${VAR:default}).
"""

import os
import re
import yaml
from typing import Any, Optional


class Config:
    """YAML-based configuration with dot-path access and env var substitution."""

    def __init__(self, config_path: Optional[str] = None):
        self._data: dict = {}
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'config',
                'application.yml',
            )
        self._config_path = config_path
        self.load()

    def load(self):
        """Load YAML config file with env var substitution."""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            # Environment variable substitution: ${VAR:default}
            raw = self._substitute_env(raw)
            self._data = yaml.safe_load(raw) or {}
        except FileNotFoundError:
            self._data = self._defaults()
        except yaml.YAMLError:
            self._data = self._defaults()

    @staticmethod
    def _substitute_env(text: str) -> str:
        """Replace ${VAR:default} patterns with env vars."""
        pattern = re.compile(r'\$\{([^}:]+)(?::([^}]*))?\}')

        def _replacer(match):
            var_name = match.group(1)
            default = match.group(2) if match.group(2) is not None else ''
            return os.environ.get(var_name, default)

        return pattern.sub(_replacer, text)

    def get(self, path: str, default: Any = None) -> Any:
        """Get config value by dot-separated path.

        Example: config.get('vendor.voice_llm.base_url')
        """
        keys = path.split('.')
        value = self._data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    def get_vendor_config(self, vendor: str) -> dict:
        """Get vendor-specific configuration."""
        return self.get(f'vendor.{vendor}', {}) or {}

    @staticmethod
    def _defaults() -> dict:
        return {
            'server': {
                'host': '0.0.0.0',
                'port': 8000,
                'dev_mode': False,
            },
            'vendor': {
                'mock': {'protocol': 'mock'},
            },
        }


# Singleton
config = Config()
