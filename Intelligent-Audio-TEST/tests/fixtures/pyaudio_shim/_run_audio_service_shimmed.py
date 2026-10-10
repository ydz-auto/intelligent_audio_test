"""INT-95 验收夹具：加载 .env 后以影子 pyaudio 启动 audio_service gRPC server。

用途：run_all.py 以外的独立拉起入口——先 load_dotenv 注入运行配置（DATABASE_URL 等），
再以 __main__ 方式运行 audio_service.interfaces.grpc.server。pyaudio 影子模块通过
PYTHONPATH 最前端注入（见同目录 pyaudio.py），由启动方环境变量保证。
"""

import os
import runpy

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))

from dotenv import load_dotenv

load_dotenv(os.path.join(_REPO, '.env'))
os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('SERVICE_NAME', 'audio_service')
os.environ.setdefault('GRPC_PORT', '50052')

runpy.run_module('audio_service.interfaces.grpc.server', run_name='__main__', alter_sys=True)
