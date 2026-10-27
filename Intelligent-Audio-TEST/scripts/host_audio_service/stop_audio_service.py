# -*- coding: utf-8 -*-
"""audio_service（:50052）优雅停止器 —— INT-2086 防楔死。

强停带流的 audio_service 会把 WASAPI 会话锁在声卡驱动里，下一个进程
Pa_Initialize 撞锁挂死（INT-2073 实测）。停止必须按顺序：

    1. 定位 50052 监听 PID；
    2. 先走优雅停止：gRPC AudioService.Shutdown RPC
       （服务端停全部播放 → 等流关闭 → pa.terminate() → 停 server → 进程退出）；
    3. 优雅停止失败/超时/服务端是旧代码（UNIMPLEMENTED）→ 回退 taskkill /F，
       打印楔死风险警告（最后手段）；
    4. 等待 TCP 50052 完全释放（监听 socket 消失）；
    5. 冷却 ≥ COOLDOWN_DEFAULT 秒（确认旧 WASAPI 会话释放）后才算完成。

用法（通常由 stop_audio_service.cmd 包装调用）:
    python stop_audio_service.py [--port 50052] [--cooldown 8]
                                 [--graceful-timeout 15] [--release-timeout 60]
                                 [--log <文件>]

退出码:
    0 = 已停止且端口已释放 + 冷却完成（可以安全启动）
    1 = 停止失败（端口未释放 / 冷却被跳过? 不——冷却永远执行）等
    2 = 参数错误

可测性：find_listener_pid / graceful_stop / wait_port_released / cooldown 都是
纯函数（依赖可注入），单元测试直接调。
"""

import argparse
import os
import socket
import subprocess
import sys
import time

PORT_DEFAULT = 50052
# 冷却窗口（负责人拍板 5~10s）：等旧 WASAPI 会话释放后再 Pa_Initialize。
COOLDOWN_DEFAULT = 8.0
GRACEFUL_TIMEOUT_DEFAULT = 15.0
RELEASE_TIMEOUT_DEFAULT = 60.0
GRPC_MAX_MESSAGE_MB = 64

# taskkill /F 是最后手段：强停会楔死 Windows 音频栈（见模块 docstring）。
LAST_RESORT_WARNING = (
    "[WARN] 优雅停止失败，回退 taskkill /F（最后手段）。\n"
    "       强停带流的 audio_service 有楔死 Windows 音频栈的风险：旧进程 WASAPI 会话"
    "可能锁在驱动里，重启后新进程 Pa_Initialize 会撞锁挂死。\n"
    "       若本机音频栈已被楔死，需管理员重启 Audiosrv（net stop Audiosrv && "
    "net start Audiosrv）或重启机器后再 start_audio_service_noshim.cmd。"
)


def find_listener_pid(port, netstat_cmd='netstat'):
    """返回监听指定端口的 PID（首条 LISTENING 匹配），无则 None。"""
    try:
        out = subprocess.run(
            [netstat_cmd, '-ano', '-p', 'tcp'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        ).stdout
    except Exception as e:
        print(f"[WARN] netstat 不可用: {e}", file=sys.stderr)
        return None
    needle = f':{port}'
    for line in out.splitlines():
        if needle in line and 'LISTENING' in line.upper():
            parts = line.split()
            if parts:
                return parts[-1]
    return None


def _resolve_repo():
    """解析仓库根（shared/audio_service/scripts 所在层）。

    仓库规范版（scripts/host_audio_service/../.. = 仓库根）与宿主运行副本
    （AUDIO_SERVICE_REPO 由 stop_audio_service.cmd 传入；裸调用回退主 clone
    部署路径）都能解析到同一 repo。多退一层（'..','..','..'）会解析到仓库根
    父级，shared 导入失败 → 优雅停止被静默降级为 taskkill（INT-2086 审计 P2-1）。
    """
    repo = os.environ.get('AUDIO_SERVICE_REPO')
    if repo:
        return repo
    _here = os.path.dirname(os.path.abspath(__file__))
    if (os.path.basename(_here) == 'host_audio_service'
            and os.path.basename(os.path.dirname(_here)) == 'scripts'):
        # 仓库内规范版：<repo>/scripts/host_audio_service/stop_audio_service.py
        return os.path.abspath(os.path.join(_here, '..', '..'))
    # 宿主运行副本兜底：主 clone 部署路径（与启动器 cmd 的 REPO 同源）。
    return r'D:\00_code\V9.7.31\Intelligent-Audio-TEST'


def _import_grpc_stubs():
    """按需导入 shared.proto 的 audio_service 桩；失败返回 (None, 原因)。

    _resolve_repo() 负责把仓库规范版（scripts/host_audio_service/../.. = 仓库根）
    与宿主运行副本（AUDIO_SERVICE_REPO / 主 clone 兜底）解析到同一 repo。
    """
    try:
        repo = _resolve_repo()
        for p in (repo, os.path.join(repo, 'shared', 'proto')):
            if p not in sys.path:
                sys.path.insert(0, p)
        import grpc  # noqa: F401
        from shared.proto import audio_service_pb2 as pb  # noqa: F401
        from shared.proto import audio_service_pb2_grpc as pb_grpc  # noqa: F401
        return pb, pb_grpc, None
    except Exception as e:
        return None, None, f"gRPC 桩导入失败: {e}"


def graceful_stop(port, timeout=GRACEFUL_TIMEOUT_DEFAULT,
                  _stubs=None):
    """经 gRPC AudioService.Shutdown 触发优雅停止。

    Returns:
        (ok, message)
        - ok=False + message 含「不支持 Shutdown RPC / 超时 / 连接失败」时，
          调用方应回退 taskkill /F。
    """
    pb, pb_grpc, err = _stubs or _import_grpc_stubs()
    if err:
        return False, err
    try:
        import grpc
        channel = grpc.insecure_channel(
            f'127.0.0.1:{port}',
            options=[
                ('grpc.max_receive_message_length',
                 GRPC_MAX_MESSAGE_MB * 1024 * 1024),
                ('grpc.max_send_message_length',
                 GRPC_MAX_MESSAGE_MB * 1024 * 1024),
            ],
        )
        stub = pb_grpc.AudioServiceStub(channel)
        resp = stub.Shutdown(pb.ShutdownRequest(), timeout=timeout)
        return resp.success, resp.message
    except Exception as e:
        # 注意：grpc>=1.5x 的 _InactiveRpcError._state.code 是 StatusCode 枚举值
        # （不可调用），更早版本是 lambda。必须走标准 e.code() API（两者兼容），
        # 绝不能 getattr(..., 'code')(...) 把枚举当函数硬调（INT-2086 打回 P1）。
        code = getattr(e, 'code', None)
        code = code() if callable(code) else None
        if code == grpc.StatusCode.UNIMPLEMENTED:
            return False, "服务端不支持 Shutdown RPC（旧代码未含 INT-2086），回退强停"
        return False, f"gRPC Shutdown 调用失败: {e}"


def port_is_listening(port):
    """探针连接 127.0.0.1:port：能连上即仍在监听（或仅 TIME_WAIT 未清）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except (ConnectionRefusedError, OSError, socket.timeout):
            return False


def wait_port_released(port, timeout=RELEASE_TIMEOUT_DEFAULT,
                       is_listening=port_is_listening):
    """等待监听 socket 完全释放；超时返回 False。

    Returns:
        (released, elapsed_seconds)
    """
    deadline = time.monotonic() + timeout
    start = time.monotonic()
    while time.monotonic() < deadline:
        if not is_listening(port):
            return True, time.monotonic() - start
        time.sleep(0.5)
    return False, time.monotonic() - start


def cooldown(seconds):
    """冷却窗口：确认旧 WASAPI 会话释放后再 Pa_Initialize。"""
    print(f"[cooldown] 等待 {seconds}s 冷却（旧 WASAPI 会话释放窗口）...")
    time.sleep(seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=PORT_DEFAULT)
    parser.add_argument('--cooldown', type=float, default=COOLDOWN_DEFAULT)
    parser.add_argument('--graceful-timeout', type=float,
                        default=GRACEFUL_TIMEOUT_DEFAULT)
    parser.add_argument('--release-timeout', type=float,
                        default=RELEASE_TIMEOUT_DEFAULT)
    parser.add_argument('--log', default=None, help='日志文件（追加）')
    args = parser.parse_args(argv)

    def log(msg):
        print(msg)
        if args.log:
            try:
                with open(args.log, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except Exception:
                pass

    if args.port <= 0 or args.cooldown <= 0:
        log("[ERROR] --port / --cooldown 必须 > 0")
        return 2

    log(f"[stop] audio_service 停止开始 port={args.port}")
    pid = find_listener_pid(args.port)
    if pid is None:
        log(f"[stop] 端口 {args.port} 无监听进程——本来就没在跑。"
            f"跳过停止，直接进入冷却 {args.cooldown}s。")
        cooldown(args.cooldown)
        return 0

    log(f"[stop] 发现监听 PID={pid}，先尝试 gRPC 优雅停止...")
    ok, msg = graceful_stop(args.port, timeout=args.graceful_timeout)
    if ok:
        log(f"[stop] 优雅停止已触发: {msg}")
    else:
        log(f"[stop] 优雅停止不可用: {msg}")
        log(LAST_RESORT_WARNING)
        taskkill = subprocess.run(
            ['taskkill', '/PID', str(pid), '/T', '/F'],
            capture_output=True, text=True,
        )
        log(f"[stop] taskkill /PID {pid} /T /F -> rc={taskkill.returncode} "
            f"({taskkill.stdout.strip() or taskkill.stderr.strip()})")

    released, elapsed = wait_port_released(args.port, timeout=args.release_timeout)
    if not released:
        log(f"[stop][FATAL] 端口 {args.port} 在 {args.release_timeout}s 内未释放，"
            f"残留进程可能卡在音频驱动里，需人工清理（勿重复强杀）。")
        return 1
    log(f"[stop] 端口 {args.port} 已释放（{elapsed:.1f}s）")

    cooldown(args.cooldown)
    log("[stop] 冷却完成，可以安全 start_audio_service*（下一次 Pa_Initialize 不会撞锁）。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
