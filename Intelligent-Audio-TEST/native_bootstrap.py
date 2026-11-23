# -*- coding: utf-8 -*-
"""原生（无 Docker）数据库引导：复用 db_bootstrap_entrypoint 的 BOOTSTRAP_STEPS 链。

用法（venv python）：
    python native_bootstrap.py
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'docker'))

from db_bootstrap_entrypoint import BOOTSTRAP_STEPS, build_pgoptions  # noqa: E402

DATABASE_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:5433/intelligent_audio_test')


def main():
    env = os.environ.copy()
    env['DATABASE_URL'] = DATABASE_URI
    env['DATABASE_URI'] = DATABASE_URI
    env.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
    env.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')
    env['PGOPTIONS'] = build_pgoptions({
        'lock_timeout_ms': 5000,
        'statement_timeout_ms': 300000,
        'idle_in_tx_timeout_ms': 60000,
    })
    env['PGAPPNAME'] = 'db_bootstrap'
    env['PYTHONUTF8'] = '1'

    confirmations = ['y'] * len(BOOTSTRAP_STEPS)
    for i, step in enumerate(BOOTSTRAP_STEPS, 1):
        script = step[1]
        cmd = [sys.executable, script] + list(step[2:])
        print(f'==> [{i}/{len(BOOTSTRAP_STEPS)}] {script}', flush=True)
        try:
            r = subprocess.run(cmd, cwd=REPO, env=env,
                               input=confirmations[i - 1] + '\n', text=True,
                               timeout=900)
        except subprocess.TimeoutExpired:
            print(f'FAIL(超时) {script}', flush=True)
            return 1
        if r.returncode != 0:
            print(f'FAIL {script} rc={r.returncode}', flush=True)
            return r.returncode
    print('BOOTSTRAP DONE', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
