# -*- coding: utf-8 -*-
"""生产环境全链路日志捕获器。

拉起三个服务(asr_server / eval_server / 后端),每个进程 stdout+stderr 落到日志文件,
并通过 sitecustomize.py patch requests/httpx,把所有出站 HTTP 请求(后端->eval_server,
eval_server->asr_server/LLM judge)记成 JSONL。停止后把后端 logs/app.log 一并收进
capture 目录并打 zip,供拿回分析整体链路。

用法:
  cd D:\\work\\20260630
  python prod_capture\\run_capture.py            # 启动三服务,开始捕获
  # ... 在平台 UI 里跑测试用例 ...
  # 停止: Ctrl-C  或  在 capture 目录下建 stop.flag 文件

产出: prod_capture/run_<时间戳>/
  backend.log / eval_server.log / asr_server.log   各服务 stdout+stderr
  backend_app.log                                    后端 RotatingFileHandler 日志(拷贝)
  http_requests.jsonl                                所有出站 HTTP(JSONL,每行一请求)
  capture_<时间戳>.zip                              上述全部打包

注意: 启动前请先停掉已在运行的 asr_server/eval_server/后端(避免端口冲突)。
      各服务仍读各自的 .env,本脚本只叠加捕获相关环境变量,不改业务配置。
"""
import os
import sys
import time
import shutil
import zipfile
import signal
import pathlib
import datetime
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent          # 工作区根 D:/work/20260630
CAPTURE_DIR = pathlib.Path(__file__).resolve().parent          # prod_capture/
RUN_DIR = CAPTURE_DIR / ('run_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
IS_WIN = sys.platform.startswith('win')

# (服务名, cwd, cmd, IAT_SERVICE, env追加)
SERVICES = [
    ('asr_server',  ROOT / 'asr_server',                [sys.executable, 'asr_server.py'],           'asr'),
    ('eval_server', ROOT / 'eval_server',               [sys.executable, 'app.py'],                  'eval'),
    ('backend',     ROOT / 'Intelligent-Audio-TEST',    [sys.executable, 'run.py'],                  'backend'),
]


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def open_log(name):
    f = open(RUN_DIR / name, 'w', encoding='utf-8', buffering=1)  # 行缓冲
    return f


def start_services():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    http_log = RUN_DIR / 'http_requests.jsonl'
    # 清空旧 http 日志
    http_log.write_text('', encoding='utf-8')

    procs = []
    log_files = {}
    for name, cwd, cmd, svc in SERVICES:
        env = dict(os.environ)
        # 注入 sitecustomize:把 prod_capture 加到 PYTHONPATH 头
        pp = str(CAPTURE_DIR)
        env['PYTHONPATH'] = pp + os.pathsep + env.get('PYTHONPATH', '')
        env['PYTHONUNBUFFERED'] = '1'
        env['IAT_HTTP_LOG'] = str(http_log)
        env['IAT_SERVICE'] = svc
        if name == 'backend':
            env.setdefault('CONSOLE_LOG_ENABLED', 'true')  # 保险:后端 console 日志开

        lf = open_log(f'{name}.log')
        log_files[name] = lf
        kwargs = dict(cwd=str(cwd), env=env, stdout=lf, stderr=subprocess.STDOUT,
                      text=True, encoding='utf-8', errors='replace')
        if IS_WIN:
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['preexec_fn'] = os.setsid
        try:
            p = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            lf.write(f'\n!! 启动 {name} 失败: {e}\n')
            log(f'!! 启动 {name} 失败: {e}')
            p = None
        procs.append((name, p))
        log(f'启动 {name}: PID={p.pid if p else "N/A"}  cwd={cwd}  -> {RUN_DIR / (name + ".log")}')
    return procs, log_files


def kill_tree(name, p):
    if p is None:
        return
    try:
        if IS_WIN:
            # taskkill 整个进程树
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                            capture_output=True, timeout=15)
        else:
            import signal as _sig
            os.killpg(os.getpgid(p.pid), _sig.SIGTERM)
    except Exception:
        try:
            p.terminate()
        except Exception:
            pass
    try:
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def collect_backend_applog():
    """把后端 RotatingFileHandler 的 logs/app.log 连同轮转副本一并拷进 RUN_DIR。"""
    src_dir = ROOT / 'Intelligent-Audio-TEST' / 'logs'
    if not src_dir.exists():
        log('后端 logs/ 不存在,跳过 app.log 拷贝')
        return
    copied = []
    for f in sorted(src_dir.glob('app.log*')):
        dst = RUN_DIR / (f'backend_app{"_" + f.name.replace("app.log","").strip(".") if f.name != "app.log" else ""}.log')
        try:
            shutil.copy2(f, dst)
            copied.append(dst.name)
        except Exception as e:
            log(f'拷贝 {f.name} 失败: {e}')
    log(f'后端 app.log 已拷贝: {copied}')


def zip_capture():
    zip_path = CAPTURE_DIR / ('capture_' + RUN_DIR.name.replace('run_', '') + '.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in RUN_DIR.iterdir():
            if f.is_file():
                z.write(f, f.name)
    log(f'打包完成: {zip_path}')
    return zip_path


def main():
    log('=' * 64)
    log(f'全链路日志捕获  RUN_DIR={RUN_DIR}')
    log('=' * 64)
    procs, log_files = start_services()
    stop_flag = RUN_DIR / 'stop.flag'
    log('-' * 64)
    log('三服务已启动。现在去平台 UI 跑测试用例。')
    log('停止方式: Ctrl-C  或  创建文件 ' + str(stop_flag))
    log('-' * 64)

    def cleanup():
        log('正在停止所有服务...')
        for name, p in reversed(procs):
            kill_tree(name, p)
            log(f'已停止 {name}')
        for lf in log_files.values():
            try:
                lf.close()
            except Exception:
                pass
        collect_backend_applog()
        zip_capture()
        log('=' * 64)
        log(f'捕获完成。日志目录: {RUN_DIR}')
        log(f'分析时关注: http_requests.jsonl(出站HTTP链路) + backend.log/backend_app.log + eval_server.log + asr_server.log')
        log('=' * 64)

    def handle_sig(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_sig)
    if not IS_WIN:
        signal.signal(signal.SIGTERM, handle_sig)

    try:
        while True:
            # 任一服务意外退出则全部停
            for name, p in procs:
                if p is not None and p.poll() is not None:
                    log(f'!! {name} 已退出(code={p.returncode}),停止全部')
                    raise KeyboardInterrupt
            if stop_flag.exists():
                log('收到 stop.flag,停止...')
                raise KeyboardInterrupt
            time.sleep(2)
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        import traceback
        log('异常: ' + repr(e) + '\n' + traceback.format_exc())
        cleanup()


if __name__ == '__main__':
    main()
