# -*- coding: utf-8 -*-
"""INT-2471 报告写意图工具实测：真实 docker 网关上的生成 / Studio / 导出链路。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/report/test_report_manage_live.py -s

纪律（devloop §4.3）：真实库栈只写本 run 自建的 ``接线测试_INT2471_`` 记录，
run 结束前删掉；真实报告只读，不改不删。

覆盖：
- ``generate`` 对已有报告的任务返回 ``exists`` 且指向同一报告（不产生第二份）；
- Studio 链路：起草（版本 1）→ 编辑（版本 2）→ 恢复版本 1（新版本 3）→
  导出 html（固定版本 3）→ 鉴权下载可得到 HTML 产物；
- 清理：按本 run 创建的 doc_id 精确删除文档 / 版本 / 导出作业行；导出产物文件
  在 report_service 容器内（非宿主卷），删行前把路径打印成手工清理命令。

注意：docker 栈跑的是 V10.11.2 当前镜像 —— PDF/PPTX 渲染与「重复导出复用
同一作业」是 INT-2471 新代码，需合入并重建 report_service 镜像后才能实测；
本文件只覆盖既有镜像已支持的 html 链路（PDF/PPTX/幂等由
``tests/unit/test_report_studio.py`` 在代码层覆盖）。
"""
import json
import os
import urllib.error
import urllib.request

import pytest

from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import (
    ToolApproval, ToolInvocationContext,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_eval.domains.evaluation.test_evaluation_live_contract import (
    GATEWAY, _login,
)

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')

PREFIX = '接线测试_INT2471_'
LIVE_DB_URL = os.environ.get(
    'AGENT_LIVE_DB_URL',
    'host=localhost port=5432 dbname=intelligent_audio_test '
    'user=intelligent_audio_test password=intelligent_audio_test666')
WRITE_PERMISSIONS = ('*',)
CREATED_DOC_IDS: list = []


def _ctx(permissions=WRITE_PERMISSIONS):
    return ToolInvocationContext(
        run_id='live-run', session_id='live-session', owner_id=1,
        tenant_id='default', step_id='live', permissions=tuple(permissions),
        idempotency_key='live', approval=ToolApproval(
            approval_id='live-approval', risk=ToolRisk.WRITE, proposal={}))


@pytest.fixture(scope='module')
def live():
    try:
        login = _login()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f'网关不可用：{exc}')
    if 'access_token' not in login:  # pragma: no cover
        pytest.skip(f'网关登录失败：{str(login)[:200]}')
    token = login['access_token']
    credentials = RunCredentialRegistry()
    credentials.put('live-run', f'Bearer {token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY), credentials=credentials)
    yield {'gateway': gateway, 'token': token}
    _cleanup_studio_rows()


def _run(gateway, tool, **arguments):
    return gateway.execute(
        ToolCallRequest(tool_call_id=f'live-{tool}-{len(CREATED_DOC_IDS)}',
                        name=tool, arguments=arguments),
        _ctx())


def _query(gateway, action, **arguments):
    result = gateway.execute(
        ToolCallRequest(tool_call_id=f'live-q-{action}', name='report_query',
                        arguments={'action': action, **arguments}),
        ToolInvocationContext(
            run_id='live-run', session_id='live', owner_id=1,
            tenant_id='default', step_id='live',
            permissions=('report:read',), idempotency_key='live'))
    assert result.ok, result.content
    return json.loads(result.content).get('data') or {}


def _envelope(result):
    """REST 映射类工具的返回：上游统一信封 ``{success, code, message, data}``。"""
    assert result.ok, result.content
    return json.loads(result.content)


def _rest_data(result):
    return _envelope(result).get('data') or {}


def _local_payload(result):
    """本地编排工具（report_export）的返回：工具自建的 JSON 对象。"""
    assert result.ok, result.content
    return json.loads(result.content)


def _download(token, download_ref):
    url = f'{GATEWAY}{download_ref}'
    request = urllib.request.Request(
        url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return resp.status, resp.read()


def _cleanup_studio_rows():
    """删除本 run 创建的 Studio 文档 / 版本 / 图表 / 导出作业行。

    产物文件落在 report_service 容器内（``/app/report_studio_exports``，不是
    宿主卷），本清理只能删库行；文件路径在删行前取出来打印成手工清理命令，
    避免每跑一次留一个孤儿文件却没人知道在哪。
    """
    if not CREATED_DOC_IDS:
        return
    try:
        import psycopg2
        conn = psycopg2.connect(LIVE_DB_URL)
        try:
            orphan_files = []
            with conn.cursor() as cur:
                for doc_id in CREATED_DOC_IDS:
                    cur.execute(
                        'SELECT file_path FROM report_studio_export_jobs '
                        'WHERE doc_id=%s AND file_path IS NOT NULL', (doc_id,))
                    orphan_files.extend(row[0] for row in cur.fetchall())
                    cur.execute(
                        'DELETE FROM report_studio_export_jobs WHERE doc_id=%s',
                        (doc_id,))
                    cur.execute(
                        'DELETE FROM report_studio_chart_specs WHERE doc_id=%s',
                        (doc_id,))
                    cur.execute(
                        'DELETE FROM report_studio_document_versions WHERE doc_id=%s',
                        (doc_id,))
                    cur.execute(
                        'DELETE FROM report_studio_documents WHERE doc_id=%s',
                        (doc_id,))
            conn.commit()
            if orphan_files:
                print('[INT-2471] 容器内产物文件需手工清理：\n  docker exec '
                      '<report_service 容器> rm -f ' + ' '.join(orphan_files))
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - 清理失败要显式提示
        print(f'[INT-2471] 清理 Studio 测试数据失败，需人工删除 {CREATED_DOC_IDS}: {exc}')


def _first_task_report(gateway):
    items = _query(gateway, 'list', report_type='task', page=1,
                   per_page=1).get('items') or []
    assert items, '真实库里没有任务报告，无法实测'
    return items[0]


# ---------------------------------------------------------------- 生成

def test_generate_existing_report_returns_exists(live):
    """重复生成不产生重复报告：已有报告时返回 exists 且指向同一份。"""
    gateway = live['gateway']
    report = _first_task_report(gateway)
    task_id = report.get('task_id')
    assert task_id, report

    result = _run(gateway, 'report_generate', action='generate',
                  task_id=int(task_id))
    data = _rest_data(result)
    assert data.get('status') == 'exists', data
    assert int(data.get('id')) == int(report['id']), data

    # 仍然只有这一份报告
    by_task = _query(gateway, 'by_task', task_id=int(task_id))
    assert int(by_task['id']) == int(report['id'])


# ---------------------------------------------------------------- Studio 链路

def test_studio_chain_draft_edit_restore_export(live):
    """起草 → 编辑 → 恢复 → 导出 → 下载，全链路可重放。"""
    gateway = live['gateway']
    report = _first_task_report(gateway)

    draft_md = (f'# {PREFIX}报告草稿\n\n'
                '## 一、总体结论\n\n'
                f'- 报告 ID：{report["id"]}\n'
                f'- 通过率：{(report.get("summary") or {}).get("pass_rate")}\n\n'
                '| 指标 | 值 |\n| --- | --- |\n| 通过率 | '
                f'{(report.get("summary") or {}).get("pass_rate")} |')
    doc = _rest_data(_run(
        gateway, 'report_generate', action='studio_draft',
        report_id=int(report['id']),
        body={'title': f'{PREFIX}草稿', 'markdown_content': draft_md}))
    doc_id = doc.get('doc_id')
    assert doc_id, doc
    CREATED_DOC_IDS.append(doc_id)
    assert doc.get('current_version') == 1
    assert doc.get('agent_session_id') == 'live-session', doc

    edit_md = draft_md + '\n\n## 二、补充\n\n- 第二次编辑（版本 2）'
    edited_doc = _rest_data(_run(
        gateway, 'report_generate', action='studio_edit', doc_id=doc_id,
        body={'expected_version': 1, 'markdown_content': edit_md}))
    assert edited_doc.get('current_version') == 2, edited_doc

    # 冲突口径：用旧版本再编辑 → 409，不覆盖
    conflict = _run(gateway, 'report_generate', action='studio_edit',
                    doc_id=doc_id,
                    body={'expected_version': 1,
                          'markdown_content': edit_md + '\n冲突'})
    assert conflict.ok is False
    assert conflict.error_code == 'UPSTREAM_ERROR' or '409' in conflict.content
    assert '版本冲突' in conflict.content or '409' in conflict.content

    restored_doc = _rest_data(_run(
        gateway, 'report_generate', action='studio_restore', doc_id=doc_id,
        body={'version': 1, 'expected_version': 2}))
    assert restored_doc.get('current_version') == 3, restored_doc

    export_payload = _local_payload(_run(
        gateway, 'report_export', doc_id=doc_id, version=3, format='html'))
    assert export_payload.get('export_id'), export_payload
    # 既有镜像同步渲染 html；未完成时用同一入参再查一次（新代码会复用作业，
    # 旧镜像会新建作业，但同样得到可下载产物）
    if export_payload.get('status') != 'done':
        for _ in range(10):
            import time
            time.sleep(1)
            export_payload = _local_payload(_run(
                gateway, 'report_export', doc_id=doc_id, version=3,
                format='html'))
            if export_payload.get('status') == 'done':
                break
    assert export_payload.get('status') == 'done', export_payload
    status, content = _download(live['token'], export_payload['download_ref'])
    assert status == 200
    assert content.startswith(b'<!DOCTYPE html>') or b'<html>' in content
    assert PREFIX.encode('utf-8') in content


def test_export_writes_require_approval_context(live):
    """无审批凭据不执行：写工具在真实网关上同样先到审批。"""
    gateway = live['gateway']
    report = _first_task_report(gateway)
    result = gateway.execute(
        ToolCallRequest(tool_call_id='live-no-approval',
                        name='report_generate',
                        arguments={'action': 'studio_draft',
                                   'report_id': int(report['id']),
                                   'body': {'markdown_content': '# x'}}),
        ToolInvocationContext(
            run_id='live-run', session_id='live', owner_id=1,
            tenant_id='default', step_id='live', permissions=('*',),
            idempotency_key='live'))
    assert result.ok is False
    assert result.error_code == 'APPROVAL_REQUIRED'
