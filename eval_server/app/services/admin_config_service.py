# -*- coding: utf-8 -*-
""".env 管理配置服务：白名单校验 + 原子写回 + 内存热生效。

供 controllers/admin.py 的 PUT /admin/config/api_key 调用；纯函数无 Flask 依赖，
可脱离 HTTP 直接单测（env_path 参数指向临时目录）。

安全约束：本模块只写文件与内存，不记任何含 key 值的日志（日志出口收敛在
controllers/admin.py 的单行结果日志）。
"""
import os
import shutil
import tempfile
import threading
from pathlib import Path

from .. import config as _config_module
from ..config import config

# 允许通过管理端点更新的 key 白名单（新增 key 需评审扩展，拒绝魔法扩展）
_UPDATABLE_KEYS = frozenset({'LLM_JUDGE_API_KEY'})

# 串行化 .env 读-改-写（waitress 线程池下防并发请求交错写坏文件）
_ENV_LOCK = threading.Lock()


class AdminConfigError(Exception):
    """参数校验失败：key_name 不在白名单，或 api_key 非字符串 / strip 后为空。"""


def _default_env_path() -> Path:
    """.env 默认路径：与 config 模块同源解析（不硬编码）。"""
    return Path(_config_module.__file__).resolve().parent.parent / '.env'


def update_env_key(key_name, value, env_path=None):
    """更新 .env 中单个白名单 key，并让运行中进程立即生效。

    顺序：校验 → 备份(.env.bak 单槽) → 同目录临时文件 + os.replace 原子替换
    → 文件成功后才改内存（os.environ + config.LLM_JUDGE 双写）。
    任何写失败抛 OSError，此时 .env 与内存均保持原状（默认安全）。

    Raises:
        AdminConfigError: 参数校验失败。
        OSError: .env 备份 / 临时文件写入 / 原子替换失败。
    """
    # 先 isinstance 再查 frozenset：JSON 传入 list/dict 等不可哈希对象时
    # 直接 `in` 会抛 TypeError 而非走校验失败路径
    if not (isinstance(key_name, str) and key_name in _UPDATABLE_KEYS):
        raise AdminConfigError('key_name 不在白名单')
    if not (isinstance(value, str) and value.strip()):
        raise AdminConfigError('api_key 非法')
    # 存储取 strip 后的值，与 config.py 读取端 v.strip() 口径一致（热值=重启值）
    value = value.strip()

    if env_path is None:
        env_path = _default_env_path()
    env_path = Path(env_path)
    prefix = f'{key_name}='

    with _ENV_LOCK:
        if env_path.exists():
            # 单槽备份：新 key 有问题时运维可从 .env.bak 回滚
            shutil.copy2(env_path, env_path.parent / (env_path.name + '.bak'))
            with open(env_path, encoding='utf-8', newline='') as f:
                raw = f.read()
        else:
            raw = ''

        # 逐行读改写：newline='' 保留原行尾，避免 CRLF 被规范化
        lines = raw.splitlines(keepends=True)
        new_lines = []
        replaced = False
        for line in lines:
            body = line.rstrip('\r\n')
            if not replaced and body.strip().startswith(prefix):
                # 命中白名单 key 行：整行替换，保留原行尾
                new_lines.append(prefix + value + line[len(body):])
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            # 不存在则追加；先补行尾避免粘行，行尾风格跟随原文件
            eol = '\r\n' if '\r\n' in raw else '\n'
            if raw and not raw.endswith(('\n', '\r')):
                new_lines.append(eol)
            new_lines.append(prefix + value + eol)

        # mkstemp 同目录 + 唯一命名：保证 os.replace 原子性，且并发下不互踩
        fd, tmp_name = tempfile.mkstemp(dir=str(env_path.parent), prefix='.env.tmp.')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
                f.write(''.join(new_lines))
            os.replace(tmp_name, env_path)
        finally:
            # 替换抛错时清理残留临时文件（成功时已被 replace 移走，此处不存在）
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

        # 文件成功后才改内存（两行赋值无失败路径）：
        # get_llm_config() 调用期实时读取 config.LLM_JUDGE，即刻热生效；
        # os.environ 双写保证重启前新起子进程也读到新值
        os.environ[key_name] = value
        if key_name == 'LLM_JUDGE_API_KEY':
            config.LLM_JUDGE['api_key'] = value
