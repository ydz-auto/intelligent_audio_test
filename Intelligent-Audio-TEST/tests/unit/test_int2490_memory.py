# -*- coding: utf-8 -*-
"""INT-2490 文件式长期记忆：隔离 / 路径穿越 / 审批占位 / 敏感扫描 / 注入 / 无向量。

验收锚点（卡面可测标准 1–6、8）：
1. 隔离：A 的 memory_search 查不到 B；跨租户同样为空且无「存在但无权」提示；
2. 路径穿越：``../../other`` / 绝对路径 / 软链（Windows 用 junction）全部拒绝；
3. 审批：未审批不落盘；批准后文件内容 == 预演；拒绝无副作用；
4. 敏感信息：Key / 密码 / token 拦截，PII 脱敏，审计无明文；
5. 注入：会话摘要只含偏好 + 项目规则，token ≤ 配置上限；
6. 无向量依赖：requirements / 代码中不出现向量库或 embedding，检索走 rg。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.memory_service import (
    MemoryService, MemoryServiceSettings,
)
from agent_service.domain.enums import MemoryScope, MemorySection, SensitiveRuleAction
from agent_service.domain.exceptions import (
    MemoryPathRejected, MemorySensitiveRejected,
)
from agent_service.domain.model.memory import summary_lines
from agent_service.domain.services.token_estimator import estimate_tokens
from agent_service.infrastructure.memory import (
    FileMemoryStore, MemoryStoreSettings, RipgrepSearcher, load_sensitive_rules,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_RULES_PATH = os.path.join(_REPO_ROOT, 'agent_service', 'config',
                           'memory_sensitive_rules.json')


def _rules():
    return load_sensitive_rules(_RULES_PATH)


@pytest.fixture()
def skills_root(tmp_path):
    """一份最小 skills 目录：references 可检索，SKILL.md 不参与。"""
    root = tmp_path / 'skills'
    refs = root / 'demo' / 'references'
    refs.mkdir(parents=True)
    (refs / 'guide.md').write_text('任务查询先看 groups，再做报告导出。\n',
                                   encoding='utf-8')
    (root / 'demo' / 'SKILL.md').write_text(
        '---\nname: demo\ndescription: d\n---\n任务查询正文不该被检索\n',
        encoding='utf-8')
    return root


@pytest.fixture()
def store(tmp_path, skills_root):
    return FileMemoryStore(MemoryStoreSettings(
        root=str(tmp_path / 'memory'), skills_root=str(skills_root),
        sensitive_rules=_rules()))


def _approve(store, tenant, owner, section, content, project_id=None):
    proposal = store.create_proposal(
        tenant_id=tenant, owner_id=owner, section=section, content=content,
        project_id=project_id)
    store.approve(tenant_id=tenant, owner_id=owner,
                  approval_id=proposal.approval_id)
    return proposal


def _make_link(link: Path, target: Path) -> bool:
    """建目录链接：优先软链；Windows 无权限时退 mklink /J（junction）。"""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except OSError:
        pass
    if sys.platform.startswith('win'):
        result = subprocess.run(
            ['cmd', '/c', 'mklink', '/J', str(link), str(target)],
            capture_output=True, check=False)
        return result.returncode == 0
    return False


# ---------------------------------------------------------------- 1. 隔离

def test_search_is_isolated_between_users_and_tenants(store):
    _approve(store, 't1', 1, MemorySection.USER_PROFILE, '偏好中文回答')
    _approve(store, 't1', 2, MemorySection.USER_PROFILE, '偏好英文回答')

    mine = store.search(tenant_id='t1', owner_id=1, query='中文',
                        scope=MemoryScope.USER)
    assert mine.count == 1
    assert mine.hits[0].path == 'user_profile.md'
    assert '偏好中文回答' in mine.hits[0].snippet

    # 同租户他人 / 跨租户同 owner：都为空，且不泄漏「存在但无权」
    for tenant, owner in (('t1', 2), ('t2', 1), ('t2', 9)):
        other = store.search(tenant_id=tenant, owner_id=owner, query='中文',
                             scope=MemoryScope.USER)
        assert other.count == 0
        assert other.to_payload() == {
            'scope': 'USER', 'count': 0, 'truncated': False, 'items': []}


def test_project_scope_only_sees_that_project(store):
    _approve(store, 't1', 1, MemorySection.PROJECT_MEMORY, '项目甲规则 A',
             project_id='alpha')
    _approve(store, 't1', 1, MemorySection.PROJECT_MEMORY, '项目乙规则 B',
             project_id='beta')
    alpha = store.search(tenant_id='t1', owner_id=1, query='规则',
                         scope=MemoryScope.PROJECT, project_id='alpha')
    assert alpha.count == 1
    assert alpha.hits[0].path == 'projects/alpha/project_memory.md'
    assert 'B' not in alpha.hits[0].snippet


def test_skill_references_are_read_only_shared_knowledge(store):
    result = store.search(tenant_id='t1', owner_id=1, query='任务查询',
                          scope=MemoryScope.SKILL_REFERENCES)
    paths = [hit.path for hit in result.hits]
    assert paths == ['demo/references/guide.md']
    # 不接收写入：skill references 没有写入区段
    with pytest.raises(MemoryPathRejected):
        store.create_proposal(tenant_id='t1', owner_id=1,
                              section=MemorySection.PROJECT_MEMORY,
                              content='x', project_id='demo/references')


# ---------------------------------------------------------------- 2. 路径穿越

@pytest.mark.parametrize('bad_project', [
    '../../other', '..', '.', '/etc/passwd', 'C:/Windows', '~root',
    'a/../../b', 'a\\..\\b', 'alpha/beta',
])
def test_path_traversal_project_id_rejected(store, bad_project):
    with pytest.raises(MemoryPathRejected):
        store.create_proposal(
            tenant_id='t1', owner_id=1,
            section=MemorySection.PROJECT_MEMORY, content='越界写入',
            project_id=bad_project)


def test_path_traversal_reason_is_recorded_in_audit(tmp_path, store):
    service = MemoryService(
        store, audit_path=str(tmp_path / 'audit'))
    with pytest.raises(MemoryPathRejected):
        service.propose_write(
            tenant_id='t1', owner_id=1, section='PROJECT_MEMORY',
            content='越界写入', project_id='../../other')
    lines = (tmp_path / 'audit' / 't1.jsonl').read_text(
        encoding='utf-8').strip().splitlines()
    payload = json.loads(lines[-1])
    assert payload['decision'] == 'deny'
    assert payload['result_code'] == 'MEMORY_PATH_REJECTED'
    assert '越界' not in json.dumps(payload, ensure_ascii=False)


def test_symlink_or_junction_project_dir_rejected(store, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    projects = tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '1' / 'projects'
    projects.mkdir(parents=True)
    link = projects / 'evil'
    if not _make_link(link, outside):
        pytest.skip('当前环境不支持创建目录链接（软链 / junction 均失败）')
    with pytest.raises(MemoryPathRejected):
        store.create_proposal(tenant_id='t1', owner_id=1,
                              section=MemorySection.PROJECT_MEMORY,
                              content='逃逸写入', project_id='evil')
    assert not (outside / 'project_memory.md').exists()


def test_invalid_tenant_is_rejected(store):
    with pytest.raises(MemoryPathRejected):
        store.search(tenant_id='../t2', owner_id=1, query='x',
                     scope=MemoryScope.USER)


def test_junction_tenant_dir_rejected(store, tmp_path):
    """租户目录被替换成链接时，连目录初始化都不能逃逸到根目录外。"""
    outside = tmp_path / 'outside_tenant'
    outside.mkdir()
    tenants = tmp_path / 'memory' / 'tenants'
    tenants.mkdir(parents=True)
    link = tenants / 't-evil'
    if not _make_link(link, outside):
        pytest.skip('当前环境不支持创建目录链接（软链 / junction 均失败）')
    with pytest.raises(MemoryPathRejected):
        store.search(tenant_id='t-evil', owner_id=1, query='x',
                     scope=MemoryScope.USER)
    with pytest.raises(MemoryPathRejected):
        store.create_proposal(tenant_id='t-evil', owner_id=1,
                              section=MemorySection.USER_PROFILE,
                              content='逃逸')
    assert not (outside / 'users').exists()


# ---------------------------------------------------------------- 3. 审批占位

def test_write_requires_approval_and_matches_preview(store, tmp_path):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.PROJECT_MEMORY,
        content='项目规则：报告导出前必须核对任务 ID', project_id='alpha')
    target = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '1'
              / 'projects' / 'alpha' / 'project_memory.md')
    assert proposal.status.value == 'PENDING'
    assert not target.exists(), '审批前不得落盘'
    assert '报告导出前必须核对任务 ID' in proposal.preview

    approved = store.approve(tenant_id='t1', owner_id=1,
                             approval_id=proposal.approval_id)
    assert approved.status.value == 'APPROVED'
    assert target.read_text(encoding='utf-8') == proposal.preview


def test_rejected_write_has_no_side_effects(store, tmp_path):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.PROJECT_MEMORY,
        content='不该落盘的规则', project_id='alpha')
    rejected = store.reject(tenant_id='t1', owner_id=1,
                            approval_id=proposal.approval_id)
    assert rejected.status.value == 'REJECTED'
    target = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '1'
              / 'projects' / 'alpha' / 'project_memory.md')
    assert not target.exists()
    assert store.pending_proposals(tenant_id='t1', owner_id=1) == ()


def test_approve_is_scoped_to_owner_and_tenant(store):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.USER_PROFILE,
        content='只属于 u1')
    from agent_service.domain.exceptions import MemoryProposalNotFound
    with pytest.raises(MemoryProposalNotFound):
        store.approve(tenant_id='t1', owner_id=2,
                      approval_id=proposal.approval_id)
    with pytest.raises(MemoryProposalNotFound):
        store.approve(tenant_id='t2', owner_id=1,
                      approval_id=proposal.approval_id)


def test_approve_detects_concurrent_file_change(store, tmp_path):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.USER_PROFILE,
        content='第一条')
    target = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '1'
              / 'user_profile.md')
    target.write_text(target.read_text(encoding='utf-8') + '- 外部写入\n',
                      encoding='utf-8')
    from agent_service.domain.exceptions import MemoryProposalConflict
    with pytest.raises(MemoryProposalConflict):
        store.approve(tenant_id='t1', owner_id=1,
                      approval_id=proposal.approval_id)


# ---------------------------------------------------------------- 4. 敏感信息

def test_sensitive_credentials_blocked_without_proposal(store):
    with pytest.raises(MemorySensitiveRejected) as info:
        store.create_proposal(
            tenant_id='t1', owner_id=1, section=MemorySection.USER_PROFILE,
            content='以后用 password: hunter2 登录平台')
    assert 'password_assignment' in str(info.value)
    assert 'hunter2' not in str(info.value)
    assert store.pending_proposals(tenant_id='t1', owner_id=1) == ()


def test_pii_is_redacted_before_proposal(store):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.USER_PROFILE,
        content='联系人邮箱 me@example.com，手机 13800138000')
    assert 'me@example.com' not in proposal.preview
    assert '13800138000' not in proposal.preview
    assert '[已脱敏]' in proposal.preview
    assert {f.rule for f in proposal.sensitive} >= {'email_pii',
                                                    'cn_mobile_pii'}


def test_audit_has_no_memory_body(tmp_path, store):
    service = MemoryService(store, audit_path=str(tmp_path / 'audit'))
    service.propose_write(tenant_id='t1', owner_id=1, section='USER_PROFILE',
                          content='偏好中文回答，不要长篇')
    service.search(tenant_id='t1', owner_id=1, query='偏好')
    raw = (tmp_path / 'audit' / 't1.jsonl').read_text(encoding='utf-8')
    for line in raw.strip().splitlines():
        payload = json.loads(line)
        assert set(payload) >= {'ts', 'action', 'tool', 'run_id', 'tenant_id',
                                'owner_id', 'args_hash', 'decision',
                                'result_code', 'reason', 'rules'}
        assert len(payload['args_hash']) == 64
    assert '偏好中文回答' not in raw
    actions = {json.loads(line)['action'] for line in raw.splitlines()}
    assert actions == {'memory_write', 'memory_search'}


# ---------------------------------------------------------------- 5. 注入

def test_summary_contains_only_preferences_and_project_rules(store):
    _approve(store, 't1', 1, MemorySection.USER_PROFILE, '偏好中文回答')
    _approve(store, 't1', 1, MemorySection.PROJECT_MEMORY, '项目规则：先查任务',
             project_id='alpha')
    # 话题细节不进摘要（会话备忘由 INT-2454 snapshot 管，本卡不注入）
    _approve(store, 't1', 1, MemorySection.TOPIC, '话题细节：某个很长的排查过程',
             project_id='alpha')

    summary = store.summary(tenant_id='t1', owner_id=1, max_tokens=600)
    assert '偏好中文回答' in summary
    assert '项目规则：先查任务' in summary
    assert '话题细节' not in summary
    assert summary.startswith('## 长期记忆摘要')


def test_summary_respects_token_budget(store):
    for index in range(200):
        _approve(store, 't1', 1, MemorySection.USER_PROFILE,
                 f'偏好条目 {index}：' + '很长的偏好描述' * 10)
    summary = store.summary(tenant_id='t1', owner_id=1, max_tokens=80)
    assert summary
    assert estimate_tokens(summary) <= 80
    # 细节仍可通过 memory_search 取到（注入裁剪不影响检索）
    hits = store.search(tenant_id='t1', owner_id=1, query='偏好条目',
                        scope=MemoryScope.USER, limit=20)
    assert hits.count > 0


def test_summary_is_empty_without_memory(store):
    assert store.summary(tenant_id='t9', owner_id=99, max_tokens=600) == ''


# ---------------------------------------------------------------- 6. 无向量 / rg

def test_no_vector_or_embedding_dependencies():
    requirements = Path(_REPO_ROOT) / 'requirements.txt'
    text = requirements.read_text(encoding='utf-8').lower()
    for banned in ('faiss', 'chromadb', 'sentence-transformers', 'milvus',
                   'pinecone', 'qdrant', 'pgvector', 'annoy', 'hnswlib'):
        assert banned not in text, banned
    banned_imports = ('faiss', 'chromadb', 'sentence_transformers', 'milvus',
                      'pinecone', 'qdrant', 'annoy', 'hnswlib', 'openai.embeddings')
    scanned = 0
    for base in (Path(_REPO_ROOT) / 'agent_service',
                 Path(_REPO_ROOT) / 'shared' / 'agent_tools'):
        for path in base.rglob('*.py'):
            code = path.read_text(encoding='utf-8', errors='replace')
            for banned in banned_imports:
                assert banned not in code, f'{path}: {banned}'
            scanned += 1
    assert scanned > 20


def test_search_uses_rg_with_fixed_strings(monkeypatch, store, skills_root):
    captured = {}

    class _Done:
        returncode = 0
        stdout = (json.dumps({
            'type': 'match',
            'data': {'path': {'text': str(skills_root / 'demo' / 'references'
                                          / 'guide.md')},
                     'lines': {'text': '任务查询先看 groups\n'},
                     'line_number': 1},
        }) + '\n').encode('utf-8')
        stderr = b''

    def fake_run(command, **kwargs):
        captured['command'] = list(command)
        captured['kwargs'] = kwargs
        return _Done()

    monkeypatch.setattr('agent_service.infrastructure.memory.rg_search.'
                        'subprocess.run', fake_run)
    result = store.search(tenant_id='t1', owner_id=1, query='任务查询',
                          scope=MemoryScope.SKILL_REFERENCES)
    assert result.count == 1
    command = captured['command']
    assert command[0] == 'rg'
    assert '--fixed-strings' in command
    assert '--json' in command
    assert str(skills_root) in command
    assert any(glob for glob in command if 'references' in str(glob))


def test_rg_missing_reports_backend_unavailable(monkeypatch, store):
    # 先建用户树，否则空目录会直接返回空结果、根本不会调 rg
    _approve(store, 't1', 1, MemorySection.USER_PROFILE, '偏好一')

    def boom(*args, **kwargs):
        raise FileNotFoundError('rg')

    monkeypatch.setattr('agent_service.infrastructure.memory.rg_search.'
                        'subprocess.run', boom)
    from agent_service.domain.exceptions import MemoryBackendUnavailable
    with pytest.raises(MemoryBackendUnavailable):
        store.search(tenant_id='t1', owner_id=1, query='偏好',
                     scope=MemoryScope.USER)
    searcher = RipgrepSearcher('rg-custom')
    assert searcher.build_command('/tmp', 'q')[0] == 'rg-custom'


# ---------------------------------------------------------------- 元数据 / 规则

def test_metadata_counts_without_content(store):
    _approve(store, 't1', 1, MemorySection.USER_PROFILE, '偏好一')
    _approve(store, 't1', 1, MemorySection.PROJECT_MEMORY, '规则一',
             project_id='alpha')
    _approve(store, 't1', 1, MemorySection.TOPIC, '话题一', project_id='alpha')
    payload = store.metadata(tenant_id='t1', owner_id=1).to_payload()
    assert payload['user_profile_count'] == 1
    assert payload['project_count'] == 1
    assert payload['topic_file_count'] == 1
    assert payload['quota_bytes'] > 0
    assert payload['updated_at']
    assert '偏好一' not in json.dumps(payload, ensure_ascii=False)


def test_sensitive_rules_are_configurable(tmp_path):
    from agent_service.infrastructure.memory import SensitiveRule, SensitiveScanner
    scanner = SensitiveScanner([SensitiveRule(
        name='custom_secret', pattern=r'ZZZ-\d+',
        action=SensitiveRuleAction.BLOCK)])
    outcome = scanner.scan('bad ZZZ-123')
    assert outcome.blocked
    assert outcome.rules == ('custom_secret',)
    assert scanner.scan('clean text').blocked is False


def test_written_entry_is_single_bullet(store, tmp_path):
    proposal = store.create_proposal(
        tenant_id='t1', owner_id=1, section=MemorySection.USER_PROFILE,
        content='第一行\n第二行')
    store.approve(tenant_id='t1', owner_id=1,
                  approval_id=proposal.approval_id)
    content = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '1'
               / 'user_profile.md').read_text(encoding='utf-8')
    assert '- 第一行\n  第二行' in content
    assert summary_lines(content) == ['- 第一行']


def test_service_summary_caps_at_inject_limit(tmp_path, store):
    for index in range(100):
        _approve(store, 't1', 1, MemorySection.USER_PROFILE,
                 f'{index} ' + 'x' * 80)
    service = MemoryService(store, settings=MemoryServiceSettings(
        inject_max_tokens=60), audit_path=str(tmp_path / 'audit'))
    summary = service.system_summary(tenant_id='t1', owner_id=1)
    assert summary
    assert estimate_tokens(summary) <= 60
