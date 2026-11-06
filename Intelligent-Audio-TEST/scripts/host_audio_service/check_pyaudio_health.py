# -*- coding: utf-8 -*-
"""pyaudio Pa_Initialize 健康自检（带超时，禁连试）—— INT-2086。

背景：Windows 音频栈楔死时（Audiosrv StartPending 或旧进程 WASAPI 会话未释放），
真实 pyaudio 的 Pa_Initialize() 会无限挂起。每多一次重试就多一个卡在全局音频锁
里的进程，越重启越死（INT-2073 实测遗留 5 个卡驱动 python 进程）。

本脚本只做一件事：**单次**自检，超时即失败退出，绝不重试；失败输出含
「重启 Audiosrv / 重启机器」指引与日志证据。

用法:
    python check_pyaudio_health.py [--timeout 60] [--python <python.exe>]

退出码:
    0 = pyaudio 可用（stdout 打印 "pyaudio OK, devices: N"）
    1 = 超时或 pyaudio 不可用（stdout/stderr 含失败原因 + 恢复指引）
    2 = 参数错误

可测性：run_selfcheck / interpret_result 是纯函数（子进程句柄可注入），
单元测试直接调，不必真跑 pyaudio。
"""

import argparse
import subprocess
import sys

# Pa_Initialize 自检代码。注意：print 必须落在 stdout（被日志重定向捕获）；
# pa.terminate() 随自检进程退出，本身不留下会话。
CHECK_SNIPPET = (
    "import pyaudio; pa = pyaudio.PyAudio(); "
    "print('pyaudio OK, devices:', pa.get_device_count()); pa.terminate()"
)

RECOVERY_GUIDANCE = (
    "real pyaudio unavailable - Windows 音频栈可能仍楔死（Audiosrv 未完全释放 / "
    "旧进程 WASAPI 会话锁在驱动里）。\n"
    "恢复步骤（管理员）: 重启 Windows Audio 服务 (net stop Audiosrv && net start Audiosrv) "
    "或重启机器，然后重跑 `python stack.py up --audio-mode real`。\n"
    "禁止连续重试：每次挂死的 Pa_Initialize 都会在全局音频锁上排队，越重试越死。"
)

# 子进程被超时强杀后，留给它的“自我退出”窗口；仍未退出则提示残留进程需人工清理。
KILL_SETTLE_SECONDS = 5.0


def run_selfcheck(python_exe, timeout, popen=subprocess.Popen):
    """在子进程中跑一次 Pa_Initialize 自检，带超时。

    Args:
        python_exe: 解释器路径（必须能解析到真实 pyaudio）。
        timeout: 自检超时秒数。
        popen: subprocess.Popen 可注入（测试用）。

    Returns:
        (returncode, output, timed_out)
        - returncode: 0 成功 / 非 0 失败 / None 超时
        - output: 子进程 stdout+stderr 合并文本
        - timed_out: 是否超时
    """
    create_no_window = 0
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        create_no_window = subprocess.CREATE_NO_WINDOW
    proc = popen(
        [python_exe, '-c', CHECK_SNIPPET],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        creationflags=create_no_window,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out, False
    except subprocess.TimeoutExpired:
        # 超时：禁连试——只杀本次子进程，不再起新进程重试。
        _kill_child(proc)
        try:
            out, _ = proc.communicate(timeout=KILL_SETTLE_SECONDS)
        except Exception:
            out = ''
        return None, out, True


def _kill_child(proc):
    """终止卡在 Pa_Initialize 的子进程。Windows 下 TerminateProcess 通常立即生效；
    个别卡在音频驱动里的进程杀不掉（INT-2073 残留），提示人工清理，不强求。
    """
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=KILL_SETTLE_SECONDS)
    except Exception:
        # 残留进程：交由运维人工清理（tasklist 里仍在的那条 python 命令行）。
        pass


def interpret_result(returncode, output, timed_out):
    """把自检结果解释为 (ok, message)。

    独立纯函数：测试可直接构造 returncode/output/timed_out 验证失败与指引。
    """
    if timed_out:
        return False, (
            f"[FATAL] pyaudio self-check TIMEOUT（Pa_Initialize 挂起超过阈值，"
            f"未重试）。自检输出:\n{output or '(no output)'}\n{RECOVERY_GUIDANCE}"
        )
    if returncode == 0:
        return True, (output or '').strip()
    return False, (
        f"[FATAL] pyaudio self-check FAILED (returncode={returncode}). "
        f"自检输出:\n{output or '(no output)'}\n{RECOVERY_GUIDANCE}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=60.0,
                        help='Pa_Initialize 自检超时秒数（默认 60，测试可调小）')
    parser.add_argument('--python', default=sys.executable,
                        help='解释器路径（默认当前 python）')
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        print("[ERROR] --timeout 必须 > 0", file=sys.stderr)
        return 2

    returncode, output, timed_out = run_selfcheck(args.python, args.timeout)
    ok, message = interpret_result(returncode, output, timed_out)
    if ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
