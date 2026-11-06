"""Launch audio_service WITHOUT the INT-95 pyaudio shadow.

Why this file exists: the original entry point
    tests/fixtures/pyaudio_shim/_run_audio_service_shimmed.py
is located INSIDE the shim directory, so Python puts that directory on sys.path[0]
and `import pyaudio` still resolves to the shadow module even when PYTHONPATH is
clean. Starting from a directory that contains no pyaudio.py makes the REAL
pyaudio (user site-packages) win.

Use only when Windows Audio is healthy (sc query Audiosrv -> STATE 4 RUNNING).
INT-2086：启动前必须先跑 scripts/host_audio_service/check_pyaudio_health.py
（带超时的单次 Pa_Initialize 自检，超时即失败退出，禁连试）。

部署：本文件是仓库内规范版本（scripts/host_audio_service/）；宿主运行副本在
D:\\00_env\\host_audio_service\\run_audio_service_noshim.py，两者内容一致。
"""

import os
import runpy


def _resolve_repo():
    """解析仓库根（shared/audio_service/scripts 所在层）。

    仓库规范版（scripts/host_audio_service/../.. = 仓库根）与宿主运行副本
    （AUDIO_SERVICE_REPO 由启动器 cmd 传入；裸调用回退主 clone 部署路径）
    都能解析到同一 repo。多退一层（'..','..','..'）会解析到仓库根父级，
    audio_service 模块找不到、noshim 服务起不来（INT-2086 审计 P2-2）。
    """
    repo = os.environ.get('AUDIO_SERVICE_REPO')
    if repo:
        return repo
    _here = os.path.dirname(os.path.abspath(__file__))
    if (os.path.basename(_here) == 'host_audio_service'
            and os.path.basename(os.path.dirname(_here)) == 'scripts'):
        # 仓库内：<repo>/scripts/host_audio_service/run_audio_service_noshim.py
        return os.path.abspath(os.path.join(_here, '..', '..'))
    # 宿主运行副本兜底：主 clone 部署路径（与启动器 cmd 的 REPO 同源）。
    return r'D:\00_code\V9.7.31\Intelligent-Audio-TEST'


REPO = _resolve_repo()

if __name__ == '__main__':
    os.chdir(REPO)

    from dotenv import load_dotenv

    load_dotenv(os.path.join(REPO, '.env'))
    os.environ.setdefault('PYTHONUTF8', '1')
    os.environ.setdefault('SERVICE_NAME', 'audio_service')
    os.environ.setdefault('GRPC_PORT', '50052')

    runpy.run_module('audio_service.interfaces.grpc.server',
                     run_name='__main__', alter_sys=True)
