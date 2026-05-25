import sys
import os

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import config

# Print vendor configurations
print("Vendor configurations:")
print(config['vendor'])
print(f"\nMock vendor config: {config['vendor'].get('mock')}")
print(f"Volc AST vendor config: {config['vendor'].get('volc_ast')}")
