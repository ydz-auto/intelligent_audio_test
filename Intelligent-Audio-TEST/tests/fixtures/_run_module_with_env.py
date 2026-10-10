"""INT-95 验收夹具：加载 .env 后运行任意模块的 __main__（用于独立拉起 run_all 未覆盖的服务组件）。"""

import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))

from dotenv import load_dotenv

load_dotenv(os.path.join(_REPO, '.env'))
os.environ.setdefault('PYTHONUTF8', '1')

if len(sys.argv) < 2:
    raise SystemExit('usage: python _run_module_with_env.py <module.name> [args...]')
runpy.run_module(sys.argv[1], run_name='__main__', alter_sys=True)
