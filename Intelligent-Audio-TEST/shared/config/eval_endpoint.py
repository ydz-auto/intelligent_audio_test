"""评估端点缺省值 — 维度种子脚本与 compose 同源（INT-2249）

`scripts/migrations/**/seed_*.py` 把评估端点写入 `dimensions.api_url`，取值口径是
环境变量 `EVAL_SERVER_URL`。缺省值必须与 `docker/docker-compose.yml`
（`db_bootstrap.environment.EVAL_SERVER_URL`）保持一致，否则脱离 compose 手工跑
种子（或 env 未透传的环境）会把整批维度写成不可达的历史外部端点
（`http://100.70.20.135:8888`，已下线），评估阶段整批 Connection refused。

缺省指向宿主 mock 裁判替身 `http://host.docker.internal:<MOCK_EVAL_SERVER_HTTP_PORT>`：
容器内解析到宿主、端口取自 `shared/config/service_ports.py` 唯一来源。
"""

import os

from shared.config.service_ports import MOCK_EVAL_SERVER_HTTP_PORT

# 与 docker/docker-compose.yml 的 db_bootstrap.EVAL_SERVER_URL 缺省值同源
DEFAULT_EVAL_SERVER_URL = f'http://host.docker.internal:{MOCK_EVAL_SERVER_HTTP_PORT}'


def resolve_eval_server_url(environ=None):
    """读取 EVAL_SERVER_URL；未设置或为空串时回落 compose 同源缺省。

    :param environ: 环境映射，缺省读 os.environ（便于单测注入）。
    :return: 评估端点 URL（不带尾部斜杠归一，原样返回用户配置）。
    """
    environ = os.environ if environ is None else environ
    value = (environ.get('EVAL_SERVER_URL') or '').strip()
    return value or DEFAULT_EVAL_SERVER_URL
