# -*- coding: utf-8 -*-
"""INT-1862：部署模板 / compose 注释的 source_map 服务标识守卫（纯文件断言）。

背景：INT-1822（D2 source_map 一致性审计）实测发现，D0 A4 要求的
`DATA_TRANSFER_SERVER_ID`（本端稳定标识，换容器 / 换机不能变）在部署侧根本没配，
容器回落成 `task_service-<容器 hostname>`；而仓库模板 `docker/.env.compose.example`
也没有这个键——照模板部署必然重犯。另外 `docker/docker-compose.yml` 的注释把方向
写反了（写成「导入写 manifest.serverInfo.source」），与实现和设计文档 §5.3 相反：
**导出**写 `manifest.serverInfo.source`，**导入侧读它**作 `source_map.source_server`。

本文件把三件事变成机械门禁：

1. 模板必须有**生效行** `DATA_TRANSFER_SERVER_ID=<非空>`（注释掉的键等于没配）；
2. 该键上方注释必须写清值口径（A/B 各自不同、留空即断链），否则只加裸键仍会踩坑；
3. compose 必须继续把该变量透传给 task_service，且注释方向为「导出写 / 导入侧读」。

DB：无；docker：无；纯文本断言。
"""
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_ENV_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, 'docker', '.env.compose.example')
_COMPOSE_PATH = os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.yml')

_KEY = 'DATA_TRANSFER_SERVER_ID'
_ACTIVE_LINE = re.compile(r'^' + _KEY + r'=(\S+)\s*$', re.MULTILINE)


def _read(path):
    # utf-8-sig：模板在 Windows 上可能带 BOM；newline 统一成 \n 便于按行断言
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return f.read().replace('\r\n', '\n').replace('\r', '\n')


def _comment_block_above(text, key):
    """取 `key=` 生效行上方连续的注释行（遇非注释行即停）。"""
    lines = text.split('\n')
    for idx, line in enumerate(lines):
        if line.strip().startswith(key + '='):
            block = []
            for prev in reversed(lines[:idx]):
                if not prev.strip().startswith('#'):
                    break
                block.append(prev)
            return '\n'.join(reversed(block))
    return ''


def test_env_example_has_active_key():
    """模板必须收录**生效行**：注释掉的键照抄部署等于没配（本卡根因）。"""
    text = _read(_ENV_EXAMPLE_PATH)
    active = _ACTIVE_LINE.findall(text)
    assert active, (
        f'{_ENV_EXAMPLE_PATH} 缺少生效行 `{_KEY}=<值>`；'
        '照模板部署会回落 task_service-<容器 hostname>，跨机 source_map 断链')
    assert all(v.strip() for v in active), f'{_ENV_EXAMPLE_PATH} 的 {_KEY} 值不能为空'


def test_env_example_documents_value_semantics():
    """只加裸键不够：值口径（A/B 不同 / 留空即断链）必须写在键上方。"""
    block = _comment_block_above(_read(_ENV_EXAMPLE_PATH), _KEY)
    assert block, f'模板的 `{_KEY}=` 上方没有说明注释（只加裸键，照抄者仍会配错）'
    assert 'A/B' in block.upper(), f'`{_KEY}` 上方注释须写明 A/B 两侧各自不同'
    assert '留空' in block or '不配' in block, (
        f'`{_KEY}` 上方注释须写明留空（不配）时的回落后果')
    assert '断链' in block, (
        f'`{_KEY}` 上方注释须写明留空会导致 source_map / 增量回导断链')


def test_compose_passes_variable_to_task_service():
    """compose 继续透传（缺 `${...:-}` 则 .env 里配了也进不了容器）。"""
    compose = _read(_COMPOSE_PATH)
    assert f'- {_KEY}=${{{_KEY}:-}}' in compose, (
        f'compose 未把 {_KEY} 透传给服务（期望 `- {_KEY}=${{{_KEY}:-}}`）')


def test_compose_comment_direction_matches_implementation():
    """注释方向 = 实现 / 设计文档 §5.3：导出写、导入侧读。"""
    compose = _read(_COMPOSE_PATH)
    assert '导出写' in compose, 'compose 注释须说明「导出写 manifest.serverInfo.source」'
    assert '导入侧读' in compose, 'compose 注释须说明「导入侧读它作 source_map.source_server」'
    assert '导入写 manifest' not in compose, (
        'compose 注释仍有反向文案「导入写 manifest」（实际是导出写），与实现/文档 §5.3 矛盾')


def test_env_example_and_compose_do_not_contradict():
    """模板与 compose 都是「导出写 / 导入读」，两处不得各写一版。"""
    env_text = _read(_ENV_EXAMPLE_PATH)
    assert '导出写' in env_text and '导入' in env_text, (
        '模板注释须与 compose 同向（导出写 manifest.serverInfo.source，导入侧读它）')
    assert '导入写 manifest' not in env_text, '模板注释方向写反了'
