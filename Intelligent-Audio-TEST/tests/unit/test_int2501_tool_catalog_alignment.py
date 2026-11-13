# -*- coding: utf-8 -*-
"""INT-2501：platform_contract 接口前缀 / 意图工具权限码对齐事实源。

卡面两条缺陷的回归锚点：

1. ``ENDPOINT_PREFIXES`` 只列网关真实注册的前缀，不再返回不存在的
   ``/api/v1/trash``；回收站按「各实体路由下的 restore / purge 动作」表述。
2. 意图工具声明的权限码必须出自 RBAC 事实源（``seed_rbac.PERMISSIONS``）
   或同能力 MCP 工具实际使用的码；M0 暂未定码的 driver_propose 在 INT-2467
   启用时改用 ``device:update``（驱动属于设备接入能力，发布仍走单独审批），
   「待规格」白名单随之清空。记忆工具（INT-2490）只要求登录：记忆域没有
   RBAC 权限码，隔离由服务端按身份构造路径 + 审批保证。
"""
import ast
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_gateway.app as gateway_app
from shared.agent_tools import contract, intent_tools, mcp_registry

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# 「待规格」白名单：RBAC 里确实还没有对应权限码，等需求规划师定码（INT-2501）
# INT-2490：memory_write 改为只要求登录（permissions 为空），从名单移出。
_PENDING_PERMISSION_SPEC = set()

# 本卡按 RBAC / MCP 事实源改正的 7 个预留工具
# INT-2468：tag_group_manage 启用后补批量打标要用的 testcase:update / :delete。
_EXPECTED_PERMISSIONS = {
    'audio_import': {'audio:upload'},
    'audio_annotate': {'audio:update'},
    'tag_group_manage': {'tag:create', 'tag:update', 'tag:delete',
                         'group:create', 'group:update', 'group:delete',
                         'testcase:update', 'testcase:delete'},
    'evaluation_manage': {'evaluation:dim_manage',
                          'evaluation:category_manage',
                          'evaluation:execute', 'evaluation:share'},
    'algorithm_manage': {'algorithm:definition_manage',
                         'algorithm:param_manage'},
    'device_control': {'device:control'},
    # 物理域 + 数字域按动作收窄（INT-2467）：工具级声明是并集
    'spl_calibrate': {'spl:create', 'spl:update', 'spl:delete',
                      'spl:test_tone', 'digital_spl:create',
                      'digital_spl:update', 'digital_spl:delete'},
    'driver_propose': {'device:update'},
    # INT-2471：Studio 导出是写权限码（不是只读 report:read）
    'report_export': {'report:studio:export'},
    'dashboard_query': {'home:read'},
}


def _rbac_codes():
    """从 RBAC 种子脚本读权限码全集（静态解析，不连库）。"""
    path = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202608',
                        'seed_rbac.py')
    with open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                getattr(node.targets[0], 'id', '') == 'PERMISSIONS':
            return {ast.literal_eval(elt)[0] for elt in node.value.elts}
    raise AssertionError('seed_rbac.PERMISSIONS 未找到')


def _gateway_paths():
    """网关 OpenAPI 路径表。

    新版 FastAPI 把 include_router 包装成 _IncludedRouter，app.routes 不再
    扁平列出子路由，用 OpenAPI paths 断言最稳定（同 INT-787 做法）。
    """
    return list(gateway_app.app.openapi()['paths'])


# ---------------------------------------------------------------- 接口前缀

def test_endpoint_prefixes_are_real_registered_routes():
    paths = _gateway_paths()
    for entry in contract.ENDPOINT_PREFIXES:
        prefix = entry['prefix']
        assert any(p == prefix or p.startswith(prefix + '/') for p in paths), \
            f'{prefix}（{entry["domain"]}）不是网关真实注册的前缀'


def test_no_phantom_trash_prefix():
    prefixes = [e['prefix'] for e in contract.ENDPOINT_PREFIXES]
    assert '/api/v1/trash' not in prefixes
    assert not any('trash' in p for p in prefixes)
    # 网关侧也确实没有 /trash 端点（回收站是各实体路由的动作）
    assert not any('trash' in p for p in _gateway_paths())


def test_trash_documented_as_entity_actions():
    conventions = [c for c in contract.CONVENTIONS if '回收站' in c]
    assert conventions, '回收站口径不应只靠已删除的前缀条目承载'
    line = conventions[0]
    assert '/restore' in line and '/purge' in line

    result = intent_tools.platform_contract('回收站', 'conventions')
    assert any('/restore' in c and '/purge' in c for c in result['conventions'])


# ---------------------------------------------------------------- 权限码

def test_mcp_tool_permissions_all_exist_in_rbac():
    rbac = _rbac_codes()
    declared = set()
    for tool in mcp_registry.TOOLS:
        declared.update(tool['permissions'])
    assert declared - rbac == set(), \
        f'MCP 工具声明了 RBAC 不存在的权限码：{sorted(declared - rbac)}'


def test_intent_tool_permissions_all_exist_in_rbac():
    rbac = _rbac_codes()
    for tool in intent_tools.INTENT_TOOLS:
        unknown = sorted(set(tool.permissions) - rbac)
        if tool.name in _PENDING_PERMISSION_SPEC:
            # 待规格项：确认 RBAC 里仍然没有该码，且工具未启用（fail-closed）
            assert unknown, f'{tool.name} 已有真实码，请从待规格名单移出'
            assert tool.enabled is False, tool.name
            continue
        assert unknown == [], \
            f'{tool.name} 声明了 RBAC 里不存在的权限码：{unknown}'


def test_pending_permission_spec_is_exactly_the_known_tools():
    rbac = _rbac_codes()
    pending = {t.name for t in intent_tools.INTENT_TOOLS
               if set(t.permissions) - rbac}
    assert pending == _PENDING_PERMISSION_SPEC


def test_fixed_tools_use_fact_source_permission_codes():
    rbac = _rbac_codes()
    # INT-2461 启用 dashboard_query（首页只读）；INT-2469 启用 evaluation_manage
    # （M2 写工具，权限码补上可见性分享 evaluation:share）；INT-2467 启用
    # 音频 / 设备 / SPL 写与驱动提案；INT-2468 启用用例 / 标签 / 任务写意图；
    # INT-2470 启用算法写意图（定义 / 参数 / 参考参数 / 映射 / 导入 / 热重载）；
    # INT-2471 启用报告写 / Studio 编排（report_generate / report_export）
    enabled_later = {'dashboard_query', 'evaluation_manage', 'audio_import',
                     'audio_annotate', 'device_control', 'spl_calibrate',
                     'driver_propose', 'testcase_write', 'tag_group_manage',
                     'task_run', 'algorithm_manage', 'report_generate',
                     'report_export'}
    for name, expected in _EXPECTED_PERMISSIONS.items():
        tool = intent_tools.INTENT_TOOL_BY_NAME[name]
        assert set(tool.permissions) == expected, name
        assert set(tool.permissions) <= rbac, name
        # 本卡（INT-2501）只改码，不动启用状态；后续卡启用需在此显式登记
        assert tool.enabled is (name in enabled_later), name


def test_platform_contract_reports_aligned_permissions():
    result = intent_tools.platform_contract('audio_import')
    assert result['tool']['permissions'] == ['audio:upload']

    result = intent_tools.platform_contract('dashboard_query')
    assert result['tool']['permissions'] == ['home:read']
