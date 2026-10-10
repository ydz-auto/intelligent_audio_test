"""INT-95 验收夹具：pyaudio 影子模块（仅注入 audio_service 进程的 PYTHONPATH 最前端）。

背景：Windows 音频栈楔死（Audiosrv 卡 StartPending，真实 pyaudio 的 Pa_Initialize
无限挂起），导致 audio_service 预初始化挂死、gRPC 50052 无法绑定，API 执行链
（RenderService 混音下沉）被阻断。本模块让 PyAudio() 实例化立即抛错，
由 audio_service server.py 的 try/except 吸收后正常起服（无真实设备 I/O 能力，
文件级渲染/混音不受影响）。

用途边界：仅供 API 链验收使用。E2E 物理链（真机放音/采集）必须移除本影子：
负责人以管理员修复 Windows Audio（或重启机器）后，杀掉挂本夹具的 audio_service
实例，按 run_all 标准命令重启即可恢复真实驱动。
"""

PA_OK = 0


class PyAudio:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "pyaudio shadow fixture (INT-95): OS audio stack wedged "
            "(Audiosrv StartPending) - real device I/O unavailable"
        )


# 与真实 portaudio 常量保持一致（回调比较语义不变）
paFloat32 = 1
paInt32 = 2
paInt16 = 8
paInt24 = 0x8000
paInt8 = 16
paUInt8 = 32
paContinue = 0
paComplete = 1
paAbort = 2
