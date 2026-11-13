# -*- coding: utf-8 -*-
"""INT-2458 音频域只读实机探针：audio_query 10 个动作 → docker 栈 REST 逐字段比对。

做三件事（不接受 mock）：

1. 用本 worktree 的 ``SharedToolGateway`` + ``RestToolClient`` 逐动作回源
   ``http://127.0.0.1:15000``（docker 网关，真实库），打印工具结果；
2. 同一动作、同一参数再走一次直连 REST，与工具结果**逐字段比对**；
3. 负例：不存在的 audio_id 返回普通拒绝文本；权限不足在网关层拒绝且不回源。

运行：
    python -I tests/verify/int2458_audio_query_probe.py
环境变量：AUDIO_PROBE_BASE（默认 http://127.0.0.1:15000）、
          AUDIO_PROBE_USER / AUDIO_PROBE_PASSWORD（默认 dev_user / dev_password）
只读：只调用 GET / POST 读接口，不写库。
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

from agent_service.application.tool_gateway import (  # noqa: E402
    INVALID_ARGUMENTS, PERMISSION_DENIED, SharedToolGateway,
)
from agent_service.domain.model.entities import ToolCallRequest  # noqa: E402
from agent_service.domain.ports.tool_gateway import ToolInvocationContext  # noqa: E402
from agent_service.infrastructure.tools.registry_bridge import (  # noqa: E402
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)

BASE = os.environ.get('AUDIO_PROBE_BASE', 'http://127.0.0.1:15000')
USERNAME = os.environ.get('AUDIO_PROBE_USER', 'dev_user')
PASSWORD = os.environ.get('AUDIO_PROBE_PASSWORD', 'dev_password')

FAILURES = []
CHECKS = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (('  | ' + detail) if detail else ''),
          flush=True)
    CHECKS.append(name)
    if not ok:
        FAILURES.append(name)
    return ok


def build_gateway(token):
    credentials = RunCredentialRegistry()
    credentials.put('probe-run', f'Bearer {token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(BASE),
        credentials=credentials)
    context = ToolInvocationContext(
        run_id='probe-run', session_id='probe-session', owner_id=0,
        tenant_id='', step_id='probe-step', permissions=('*',),
        idempotency_key='probe')
    return gateway, context


def run_action(gateway, context, action, **arguments):
    call = ToolCallRequest(tool_call_id=f'{action}-1', name='audio_query',
                          arguments={'action': action, **arguments})
    return gateway.execute(call, context)


def compare(name, result, direct):
    """工具结果（JSON 文本）与直连 REST 响应逐字段比对。"""
    if not result.ok:
        return check(name, False, f'工具失败 {result.error_code}: {result.content}')
    try:
        payload = json.loads(result.content)
    except ValueError:
        return check(name, False, '工具结果不是 JSON')
    same = payload == direct
    detail = '' if same else '工具=%s 直连=%s' % (
        json.dumps(payload, ensure_ascii=False)[:300],
        json.dumps(direct, ensure_ascii=False)[:300])
    return check(name, same, detail)


def main():
    client = ApiClient(BASE)
    client.login(USERNAME, PASSWORD)
    gateway, context = build_gateway(client.token)

    listing = client.request('GET', '/audios?page=1&per_page=5')
    items = (listing.get('data') or {}).get('items') or []
    if not items:
        print('FAIL  真实库无音频数据，无法验证', flush=True)
        return 1
    audio_id = items[0]['id']
    print(f'样本音频 id={audio_id} name={items[0].get("name")}', flush=True)

    # 1) 列表
    compare('list 逐字段一致',
            run_action(gateway, context, 'list', page=1, per_page=5),
            client.request('GET', '/audios?page=1&per_page=5'))

    # 2) 详情
    compare('detail 逐字段一致',
            run_action(gateway, context, 'detail', audio_id=audio_id),
            client.request('GET', f'/audios/{audio_id}'))

    # 3) 按 ID 批量
    compare('by_ids 逐字段一致',
            run_action(gateway, context, 'by_ids', ids=[audio_id]),
            client.request('POST', '/audios/by-ids', {'ids': [audio_id]}))

    # 4) 按 MD5（真实库遗留记录 md5 多为 null；这里验证请求体口径与空命中形态）
    probe_md5 = '0d6a1c6d9f2b7e4a8c3f5d1b2e9a7c40'
    md5_result = run_action(gateway, context, 'by_md5', md5_list=[probe_md5])
    compare('by_md5 逐字段一致（空命中）',
            md5_result,
            client.request('POST', '/audios/by-md5', {'md5_list': [probe_md5]}))
    check('by_md5 空命中返回映射对象而非报错',
          md5_result.ok and json.loads(md5_result.content).get('data') == {},
          md5_result.content[:120])

    # 5) 标签
    compare('tags 逐字段一致',
            run_action(gateway, context, 'tags'),
            client.request('GET', '/audios/tags'))

    # 6) 目录树
    compare('folder_tree 逐字段一致',
            run_action(gateway, context, 'folder_tree', depth=1),
            client.request('POST', '/audios/folder-tree', {'depth': 1}))

    # 7) 特征
    compare('features 逐字段一致',
            run_action(gateway, context, 'features', audio_id=audio_id),
            client.request('GET', f'/audios/{audio_id}/features'))

    # 8) 质量
    compare('quality 逐字段一致',
            run_action(gateway, context, 'quality', audio_id=audio_id),
            client.request('GET', f'/audios/{audio_id}/quality'))

    # 9) 已配算法
    compare('algorithms 逐字段一致',
            run_action(gateway, context, 'algorithms', audio_id=audio_id),
            client.request('GET', f'/audios/{audio_id}/algorithms'))

    # 10) 播放历史
    compare('playback_history 逐字段一致',
            run_action(gateway, context, 'playback_history',
                       audio_id=audio_id, page=1, per_page=5),
            client.request(
                'GET', f'/audios/{audio_id}/playback-history?page=1&per_page=5'))

    # ---------------- 复核打回项（INT-2458 第二轮） ----------------

    # 打回 1：folder_tree 的 sample_rate 曾在工具层无任何可用形态
    # （字符串回源 400，数字被 Schema 拒绝）。现在三种写法都归一成 Hz。
    direct_tree_rate = client.request(
        'POST', '/audios/folder-tree', {'depth': 1, 'sample_rate': 48000})
    for label, value in (('number 48000', 48000),
                         ('string "48000"', '48000'),
                         ('string "48 kHz"', '48 kHz'),
                         ('string "48"', '48')):
        compare(f'folder_tree sample_rate={label} 逐字段一致',
                run_action(gateway, context, 'folder_tree',
                           depth=1, sample_rate=value),
                direct_tree_rate)

    # 打回 2：list 的 folder 过滤服务端未实现，工具层不再暴露该参数
    folder_result = run_action(gateway, context, 'list', page=1, per_page=1,
                               folder='环境理解')
    check('list folder 参数被显式拒绝（不再静默返回全量）',
          (not folder_result.ok
           and folder_result.error_code == INVALID_ARGUMENTS
           and '不支持参数' in folder_result.content),
          f'{folder_result.error_code}: {folder_result.content[:120]}')

    # 打回 3：duration 只认档位（REST 真实口径），非档位值被拒绝
    short_direct = client.request(
        'GET', '/audios', params={'page': 1, 'per_page': 5,
                                  'duration': 'short'})
    compare('list duration=short 逐字段一致',
            run_action(gateway, context, 'list', page=1, per_page=5,
                       duration='short'),
            short_direct)
    range_result = run_action(gateway, context, 'list', page=1, per_page=1,
                              duration='0-60')
    check('list duration 区间写法被拒绝',
          (not range_result.ok
           and range_result.error_code == INVALID_ARGUMENTS
           and 'duration' in range_result.content),
          f'{range_result.error_code}: {range_result.content[:120]}')

    # 打回 3/4：sample_rate 单位归一 + tags 字符串 AND
    rate_direct = client.request(
        'GET', '/audios', params={'page': 1, 'per_page': 5,
                                  'sample_rate': '48'})
    compare('list sample_rate="48 kHz" 归一为 kHz 后逐字段一致',
            run_action(gateway, context, 'list', page=1, per_page=5,
                       sample_rate='48 kHz'),
            rate_direct)
    compare('list sample_rate=48000(Hz) 归一为 kHz 后逐字段一致',
            run_action(gateway, context, 'list', page=1, per_page=5,
                       sample_rate=48000),
            rate_direct)

    tags_payload = client.request('GET', '/audios/tags')
    tag_items = (tags_payload.get('data') or {}).get('items') or []
    if tag_items:
        tag = tag_items[0]
        compare('list tags 字符串 AND 与直连一致',
                run_action(gateway, context, 'list', page=1, per_page=5,
                           tags=[tag]),
                client.request('GET', '/audios',
                               params={'page': 1, 'per_page': 5,
                                       'tags': tag}))
        compare('folder_tree tags OR 对象与直连一致',
                run_action(gateway, context, 'folder_tree', depth=1,
                           tags=[{'name': tag, 'mode': 'or'}]),
                client.request('POST', '/audios/folder-tree',
                               {'depth': 1,
                                'tags': [{'name': tag, 'mode': 'or'}]}))
    else:
        check('标签库为空，跳过 tags 过滤实机比对', True)

    # 打回 4：list 的 tags 对象 OR 写法不再被放行（GET 服务端解析不了对象）
    or_result = run_action(gateway, context, 'list', page=1, per_page=1,
                           tags=[{'name': 'noise', 'mode': 'or'}])
    check('list tags 对象写法被显式拒绝',
          (not or_result.ok
           and or_result.error_code == INVALID_ARGUMENTS
           and '只支持字符串' in or_result.content),
          f'{or_result.error_code}: {or_result.content[:120]}')

    # 负例 1：不存在的资源 → 普通拒绝文本，不泄漏存在性、不抛异常。
    # 注意：audio_service 对「音频不存在」的 gRPC 错误经网关透传后是 HTTP 400 +
    # 业务文案（不是 404），因此这里按「普通失败文本」判定，不强制 NOT_FOUND 码。
    missing = run_action(gateway, context, 'detail', audio_id=99999999)
    check('不存在资源返回普通拒绝文本',
          (not missing.ok
           and ('不存在' in missing.content or '无权访问' in missing.content)
           and '99999999' not in missing.content
           and 'Traceback' not in missing.content),
          f'{missing.error_code}: {missing.content[:120]}')

    # 负例 2：权限不足 → 网关层拒绝，不回源
    limited = ToolInvocationContext(
        run_id='probe-run', session_id='probe-session', owner_id=0,
        tenant_id='', step_id='probe-step', permissions=('task:read',),
        idempotency_key='probe')
    denied = run_action(gateway, limited, 'list')
    check('权限不足在网关层拒绝且不泄漏',
          (not denied.ok and denied.error_code == PERMISSION_DENIED
           and '无权访问' in denied.content),
          f'{denied.error_code}: {denied.content}')

    # 负例 3：写工具仍不可执行
    from agent_service.application.tool_gateway import TOOL_NOT_ENABLED
    from shared.agent_tools.intent_tools import ENABLED_TOOLS
    disabled = 'audio_import' not in ENABLED_TOOLS and \
        'audio_annotate' not in ENABLED_TOOLS
    check('写工具未启用（M1 只读边界）', disabled,
          f'TOOL_NOT_ENABLED={TOOL_NOT_ENABLED}')

    print(f'\n结果：{len(CHECKS) - len(FAILURES)}/{len(CHECKS)} 项通过', flush=True)
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
