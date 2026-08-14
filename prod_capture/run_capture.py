# -*- coding: utf-8 -*-
"""生产环境日志+PCM 收集打包器(仅最近一次任务)。

收集后端日志(app.log + 轮转副本)和 case_pcm 下最新任务目录的 PCM 文件,打包成 zip。

用法:
  python prod_capture\run_capture.py [任务ID]
  # 不传任务ID则自动取 case_pcm 下最大编号目录
  python prod_capture\run_capture.py 109
"""
import os
import sys
import time
import shutil
import zipfile
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURE_DIR = pathlib.Path(__file__).resolve().parent
RUN_DIR = CAPTURE_DIR / ('run_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def collect_logs():
    """收集后端 app.log + 轮转副本。"""
    for src_dir in [ROOT / 'Intelligent-Audio-TEST' / 'logs',
                    ROOT / 'Intelligent-Audio-TEST' / 'backend' / 'logs']:
        if not src_dir.exists():
            log(f'日志目录不存在,跳过: {src_dir}')
            continue
        for f in sorted(src_dir.glob('app.log*')):
            suffix = f.name.replace('app.log', '').strip('.')
            tag = f'backend_app{"_" + suffix if suffix else ""}.log'
            if src_dir.name == 'backend':
                tag = f'backend_src_app{"_" + suffix if suffix else ""}.log'
            dst = RUN_DIR / tag
            try:
                shutil.copy2(f, dst)
                log(f'已拷贝 {f.relative_to(ROOT)} -> {tag}')
            except Exception as e:
                log(f'拷贝 {f.name} 失败: {e}')


def collect_pcm(task_id=None):
    """收集 case_pcm 下指定任务(或最新任务)的 PCM 文件,保留相对目录结构。"""
    pcm_root = ROOT / 'Intelligent-Audio-TEST' / 'static' / 'case_pcm'
    if not pcm_root.exists():
        log('case_pcm 目录不存在,跳过')
        return
    # 确定任务 ID
    if task_id is None:
        dirs = [d for d in pcm_root.iterdir() if d.is_dir() and d.name.isdigit()]
        if not dirs:
            log('case_pcm 下无任务目录,跳过')
            return
        task_id = max(d.name for d in dirs)
    task_dir = pcm_root / str(task_id)
    if not task_dir.exists():
        log(f'任务目录不存在: {task_dir},跳过')
        return
    count = 0
    pcm_dir = RUN_DIR / 'case_pcm' / str(task_id)
    for f in task_dir.rglob('*.pcm'):
        rel = f.relative_to(task_dir)
        dst = pcm_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, dst)
            count += 1
        except Exception as e:
            log(f'拷贝 PCM 失败 {rel}: {e}')
    log(f'已拷贝任务 {task_id} 的 {count} 个 PCM 文件 -> case_pcm/{task_id}/')


def zip_capture():
    zip_path = CAPTURE_DIR / ('capture_' + RUN_DIR.name.replace('run_', '') + '.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in RUN_DIR.rglob('*'):
            if f.is_file():
                z.write(f, f.relative_to(RUN_DIR))
    log(f'打包完成: {zip_path}')
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f'包大小: {size_mb:.1f} MB')
    return zip_path


def main():
    task_id = sys.argv[1] if len(sys.argv) > 1 else None
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    log('=' * 64)
    log(f'日志+PCM 收集打包(最近一次任务)  RUN_DIR={RUN_DIR}')
    log('=' * 64)

    collect_logs()
    collect_pcm(task_id)
    zip_path = zip_capture()

    log('=' * 64)
    log(f'完成。产出: {zip_path}')
    log('=' * 64)


if __name__ == '__main__':
    main()
