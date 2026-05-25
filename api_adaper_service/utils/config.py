import os
import yaml
from dotenv import load_dotenv

class ConfigLoader:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        
        # Load YAML configuration
        self.config = self._load_yaml_config()
        
        # Merge environment variables into config
        self._merge_env_vars()
    
    def _load_yaml_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'application.yml')
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _merge_env_vars(self):
        # Merge server config
        if 'SERVER_HOST' in os.environ:
            self.config['server']['host'] = os.environ['SERVER_HOST']
        if 'SERVER_PORT' in os.environ:
            self.config['server']['port'] = int(os.environ['SERVER_PORT'])
        
        # Merge vendor config
        if 'VOLC_WS_URL' in os.environ:
            self.config['vendor']['volc_ast']['ws_url'] = os.environ['VOLC_WS_URL']
        if 'VOLC_APP_KEY' in os.environ:
            self.config['vendor']['volc_ast']['connect_headers']['X-Api-App-Key'] = os.environ['VOLC_APP_KEY']
        if 'VOLC_ACCESS_KEY' in os.environ:
            self.config['vendor']['volc_ast']['connect_headers']['X-Api-Access-Key'] = os.environ['VOLC_ACCESS_KEY']
        if 'VOLC_RESOURCE_ID' in os.environ:
            self.config['vendor']['volc_ast']['connect_headers']['X-Api-Resource-Id'] = os.environ['VOLC_RESOURCE_ID']
    
    def get(self, path, default=None):
        """Get config value by dot path"""
        keys = path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def __getitem__(self, key):
        return self.config[key]

# Singleton instance
config = ConfigLoader()
