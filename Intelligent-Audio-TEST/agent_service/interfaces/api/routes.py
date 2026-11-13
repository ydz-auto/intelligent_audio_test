# -*- coding: utf-8 -*-
"""agent_service REST + SSE 路由（方案 §11）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/agent/sessions | 创建会话 |
| GET  | /api/v1/agent/sessions/{id} | 会话与最近消息 |
| POST | /api/v1/agent/sessions/{id}/runs | 发起 run（Idempotency-Key）|
| GET  | /api/v1/agent/runs/{id} | run 快照 |
| GET  | /api/v1/agent/runs/{id}/events?cursor= | SSE，支持 Last-Event-ID |
| POST | /api/v1/agent/runs/{id}/cancel | 取消 |
| GET  | /api/v1/agent/runs/{id}/approvals | 本 run 的审批单（待审批 + 已决）|
| POST | /api/v1/agent/approvals/{id}/decision | 批准 / 拒绝写操作提案 |
| GET  | /api/v1/agent/runs/{id}/context-snapshots | 上下文压缩快照（调试模式可回放）|
| GET  | /api/v1/agent/skills | 当前用户可见 Skill（§4.2 规则 7）|
"""
import json
import logging
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Header, HTTPException, Query, Request, Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from agent_service.application.skill_service import SkillDraftPayload
from agent_service.config.config import Config
from agent_service.domain.enums import (
    ApprovalDecision, SkillErrorCode, SkillScope, SkillStatus,
)
from agent_service.domain.exceptions import ApprovalExpired
from agent_service.domain.model.entities import AgentRun, AgentSession
from agent_service.interfaces.api.dependencies import (
    Identity, get_container, get_identity,
)
from agent_service.interfaces.api.schemas import (
    ApprovalDecisionRequest, ApprovalDecisionResponse, ApprovalResponse,
    CreateRunRequest, CreateRunResponse, CreateSessionRequest, RunResponse,
    SessionDetailResponse, SessionResponse, SkillDraftRequest,
    SkillForkRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------- serializers

def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _serialize_session(session: AgentSession) -> SessionResponse:
    return SessionResponse(
        id=session.id, owner_id=session.owner_id, tenant_id=session.tenant_id,
        title=session.title, active_skill=session.active_skill,
        model=session.model, created_at=_iso(session.created_at),
        updated_at=_iso(session.updated_at),
    )


def _serialize_run(run: AgentRun) -> RunResponse:
    return RunResponse(
        id=run.id, session_id=run.session_id, owner_id=run.owner_id,
        tenant_id=run.tenant_id, status=run.status.value, model=run.model,
        budget=run.budget or {}, token_in=run.token_in, token_out=run.token_out,
        error=run.error, created_at=_iso(run.created_at),
        started_at=_iso(run.started_at), finished_at=_iso(run.finished_at),
    )


def _sse_frame(event) -> str:
    payload = dict(event.payload or {})
    payload.update({
        'run_id': event.run_id,
        'sequence': event.sequence,
        'type': event.type.value,
        'timestamp': _iso(event.created_at),
    })
    data = json.dumps(payload, ensure_ascii=False)
    return (f'id: {event.sequence}\n'
            f'event: {event.type.value}\n'
            f'data: {data}\n\n')


# ---------------------------------------------------------------- routes

@router.post('/sessions', response_model=SessionResponse, status_code=201)
def create_session(payload: CreateSessionRequest, request: Request,
                   identity: Identity = Depends(get_identity)):
    container = get_container(request)
    session = container.run_service.create_session(
        owner_id=identity.user_id, tenant_id=identity.tenant_id,
        title=payload.title, active_skill=payload.active_skill,
        model=payload.model, permissions=identity.permissions,
    )
    return _serialize_session(session)


@router.get('/sessions/{session_id}', response_model=SessionDetailResponse)
def get_session(session_id: str, request: Request,
                identity: Identity = Depends(get_identity)):
    container = get_container(request)
    session = container.run_service.get_session(
        session_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    runs_repo = container.repositories['runs']
    runs = runs_repo.list_session_runs(session.id, Config.CONTEXT_MAX_RUNS)
    latest = runs[-1] if runs else None
    messages = container.assembler.recent_messages(
        session.id, latest, Config.CONTEXT_RECENT_MESSAGES)
    return SessionDetailResponse(
        session=_serialize_session(session), messages=messages,
        runs=[_serialize_run(run) for run in runs],
    )


@router.post('/sessions/{session_id}/runs', response_model=CreateRunResponse)
def create_run(session_id: str, payload: CreateRunRequest, request: Request,
               response: Response,
               idempotency_key: Optional[str] = Header(
                   default=None, alias='Idempotency-Key'),
               identity: Identity = Depends(get_identity)):
    container = get_container(request)
    run, created = container.run_service.create_run(
        session_id, owner_id=identity.user_id, tenant_id=identity.tenant_id,
        message=payload.message, idempotency_key=idempotency_key,
        permissions=identity.permissions, active_skill=payload.active_skill,
    )
    # INT-2453：只读 ToolGateway 以用户身份回源网关 REST。Authorization 只在
    # 进程内按 run 暂存（不落库 / 不进事件），run 结束或 TTL 到期即失效。
    container.credentials.put(run.id,
                              request.headers.get('Authorization'))
    if created:
        container.executor.submit(run.id)
        latest = container.repositories['runs'].get(run.id)
        if latest is not None:
            run = latest
    response.status_code = 201 if created else 200
    return CreateRunResponse(run=_serialize_run(run), created=created)


@router.get('/runs/{run_id}', response_model=RunResponse)
def get_run(run_id: str, request: Request,
            identity: Identity = Depends(get_identity)):
    container = get_container(request)
    run = container.run_service.get_run(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    return _serialize_run(run)


@router.get('/runs/{run_id}/events')
def stream_run_events(
        run_id: str, request: Request,
        cursor: int = Query(default=0, ge=0),
        last_event_id: Optional[str] = Header(default=None,
                                              alias='Last-Event-ID'),
        identity: Identity = Depends(get_identity)):
    container = get_container(request)
    # 先做归属校验：不存在 / 非本人一律 404（不泄漏存在性）
    container.run_service.get_run(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    start = cursor
    if last_event_id:
        try:
            start = max(start, int(last_event_id))
        except (TypeError, ValueError):
            pass

    def generate():
        for event in container.event_stream.iter_events(run_id, start):
            if event is None:
                yield ': keep-alive\n\n'
            else:
                yield _sse_frame(event)

    return StreamingResponse(
        generate(), media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@router.post('/runs/{run_id}/cancel', response_model=RunResponse)
def cancel_run(run_id: str, request: Request,
               identity: Identity = Depends(get_identity)):
    container = get_container(request)
    run = container.run_service.cancel_run(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    return _serialize_run(run)


@router.get('/runs/{run_id}/approvals')
def list_approvals(run_id: str, request: Request,
                   identity: Identity = Depends(get_identity)):
    container = get_container(request)
    items = container.run_service.list_approvals(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    return {'items': items}


@router.post('/approvals/{approval_id}/decision',
             response_model=ApprovalDecisionResponse)
def decide_approval(approval_id: str, payload: ApprovalDecisionRequest,
                    request: Request,
                    identity: Identity = Depends(get_identity)):
    """批准 / 拒绝一条写操作提案（§9.4）。

    - 只有 run 归属者本人能决策（越权 404，不泄漏存在性）；
    - 并发审批只有一个请求生效，另一个 409；
    - 过期单 409 且不执行，同时唤醒 run 把「过期」结果回灌模型；
    - 破坏性操作（DESTRUCTIVE）批准必须带 ``confirm=true``（二次确认），
      缺省 400 且不落决策（INT-2467）；
    - 决策本身不执行写操作：执行由 Loop 在恢复时按「实时权限 + 幂等键」
      完成（执行前重新校验权限与实时状态）。
    """
    container = get_container(request)
    try:
        decision = ApprovalDecision(payload.decision.strip().upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f'不支持的审批决议：{payload.decision}'
                   '（只能是 APPROVE / REJECT）')
    try:
        approval, run = container.run_service.decide_approval(
            approval_id, owner_id=identity.user_id,
            tenant_id=identity.tenant_id, decision=decision,
            permissions=identity.permissions, confirm=payload.confirm)
    except ApprovalExpired as exc:
        # 过期单不执行；让 run 继续，把「审批过期」作为工具结果回灌模型
        container.executor.submit(exc.run_id)
        raise
    # 审批后由 Loop 执行写操作，回源需要用户 Authorization：决策请求同样经
    # 网关鉴权，这里刷新 run 级凭据（只在进程内按 run 暂存，不落库）。
    container.credentials.put(run.id, request.headers.get('Authorization'))
    # 审批通过 / 拒绝都唤醒 run：结算本批写调用后继续（或收口）
    container.executor.submit(run.id)
    return ApprovalDecisionResponse(
        approval=ApprovalResponse(**approval),
        run_status=run.status.value)


@router.get('/runs/{run_id}/context-snapshots')
def list_context_snapshots(run_id: str, request: Request,
                           identity: Identity = Depends(get_identity)):
    """上下文压缩快照（§8.5）。

    归属校验与 GET /runs 一致：非本人 / 不存在一律 404。调试模式
    （``AGENT_CONTEXT_DEBUG``）下附带被裁消息 ID 与备忘，可据快照回放；
    非调试模式只给版本 / token / 层级等统计字段。
    """
    container = get_container(request)
    container.run_service.get_run(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    snapshots = container.repositories['snapshots'].list_by_run(run_id)
    debug = bool(getattr(container.compaction_settings, 'debug', False))
    items = []
    for snapshot in snapshots:
        item = {
            'id': snapshot.id,
            'version': snapshot.version,
            'token_count': snapshot.token_count,
            'level': snapshot.level.value,
            'dropped_count': len(snapshot.dropped_ids or []),
            'created_at': _iso(snapshot.created_at),
        }
        if debug:
            item['dropped_ids'] = list(snapshot.dropped_ids or [])
            item['memo'] = dict(snapshot.memo or {})
        items.append(item)
    return {'enabled': debug, 'items': items}


@router.get('/skills')
def list_skills(request: Request,
                scope: Optional[str] = Query(default=None),
                status: Optional[str] = Query(default=None),
                identity: Identity = Depends(get_identity)):
    """当前用户可见的 Skill 列表（§11；权限 = Skill ∩ 用户权限）。

    INT-2453：同一响应附带当前用户可见的意图工具清单（31 个注册项，
    ``enabled`` 标明 M0 是否已实现），供前端展示与 Skill allowed-tools 对照。

    INT-2549：合并自定义层（USER / TENANT）与平台层，支持 ``?scope=`` /
    ``?status=`` 过滤；被同名高层遮蔽的条目带 ``masked_by``。L1 只取生效项。
    """
    from shared.agent_tools.intent_tools import ENABLED_TOOLS

    container = get_container(request)
    registry = container.skill_registry
    service = getattr(container, 'skill_service', None)
    if service is None:
        raise HTTPException(status_code=503, detail='Skill 服务未就绪')
    views = service.list(
        owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions,
        scope=_skill_scope(scope), status=_skill_status(status))
    tools = []
    for descriptor in container.tool_gateway.all_tools():
        if not _granted(identity.permissions, descriptor.permissions):
            continue
        tools.append({
            'name': descriptor.name,
            'description': descriptor.description,
            'parameters': descriptor.parameters,
            'risk': descriptor.risk.value,
            'permissions': list(descriptor.permissions),
            'enabled': descriptor.name in ENABLED_TOOLS,
        })
    return {
        'items': [_skill_view_dict(view, include_issues=False)
                  for view in views],
        # 装载摘要（INT-2506）：装载总数与目录级 / 校验问题码，供看板与审计
        # 判断「Skill 层是否整体消失」，避免错挂载时接口仍然 200 全绿。
        'skills_count': len(registry.skills),
        'issues': [
            {
                'code': issue.code.value,
                'severity': issue.severity.value,
                'skill': issue.skill,
                'path': issue.path,
                'message': issue.message,
            }
            for issue in registry.issues
        ],
        'issues_count': len(registry.issues),
        'tools': tools,
        'tools_count': len(tools),
        'l1_tokens': registry.l1_tokens(
            identity.permissions, owner_id=identity.user_id,
            tenant_id=identity.tenant_id),
        'l1_budget_tokens': registry.l1_budget_tokens,
    }


def _granted(granted, required) -> bool:
    """权限 OR 语义；``*`` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


# ---------------------------------------------------------------- 自定义 Skill（INT-2549）

def _skill_service(request: Request):
    container = get_container(request)
    service = getattr(container, 'skill_service', None)
    if service is None:
        raise HTTPException(status_code=503, detail='Skill 服务未就绪')
    return service


def _skill_scope(raw: Optional[str]):
    if not raw:
        return None
    try:
        return SkillScope(raw.strip().upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={'code': SkillErrorCode.SKILL_VALIDATION_FAILED.value,
                    'message': f'不支持的 scope：{raw}'
                               '（只能是 PLATFORM / TENANT / USER）'})


def _skill_status(raw: Optional[str]):
    if not raw:
        return None
    try:
        return SkillStatus(raw.strip().upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={'code': SkillErrorCode.SKILL_STATUS_INVALID.value,
                    'message': f'不支持的 status：{raw}'
                               '（只能是 DRAFT / ACTIVE / DISABLED）'})


def _reject_identity_fields(payload) -> None:
    forbidden = payload.forbidden_identity_fields()
    if forbidden:
        raise HTTPException(
            status_code=400,
            detail={'code': SkillErrorCode.SKILL_VALIDATION_FAILED.value,
                    'message': ('请求体不得携带服务端身份字段：'
                                + '、'.join(forbidden)
                                + '（scope / owner_id / tenant_id 由服务端填写）')})


def _skill_view_dict(view, *, include_issues: bool = True) -> dict:
    payload = {
        'id': view.id,
        'scope': view.scope.value,
        'name': view.name,
        'description': view.description,
        'version': view.version,
        'status': view.status.value,
        'content_hash': view.content_hash,
        'masked_by': view.masked_by,
        'owner': view.owner,
        'owner_id': view.owner_id,
        'tenant_id': view.tenant_id,
        'created_by': view.created_by,
        'updated_at': _iso(view.updated_at),
        'allowed_tools': list(view.allowed_tools),
        'permissions': list(view.permissions),
        'budgets': dict(view.budgets),
    }
    if include_issues:
        payload['issues'] = [
            {'code': issue.code.value, 'severity': issue.severity.value,
             'field': issue.field, 'message': issue.message}
            for issue in view.issues
        ]
    return payload


def _draft_payload(payload) -> SkillDraftPayload:
    # None 原样透传（PUT 语义：未出现的字段不改）
    return SkillDraftPayload(
        name=payload.name, description=payload.description,
        frontmatter=(None if payload.frontmatter is None
                     else dict(payload.frontmatter)),
        body=payload.body,
        resources=(None if payload.resources is None
                   else dict(payload.resources)))


@router.post('/skills', status_code=201)
def create_skill(payload: SkillDraftRequest, request: Request,
                 identity: Identity = Depends(get_identity)):
    """新建草稿（在线编辑入口）。``scope`` / ``owner_id`` / ``tenant_id``
    由服务端按登录身份填，请求体携带一律 400。"""
    _reject_identity_fields(payload)
    service = _skill_service(request)
    view = service.create(
        _draft_payload(payload), owner_id=identity.user_id,
        tenant_id=identity.tenant_id, permissions=identity.permissions,
        created_by=identity.user_id)
    return _skill_view_dict(view)


@router.put('/skills/{skill_id}')
def update_skill(skill_id: str, payload: SkillDraftRequest, request: Request,
                 identity: Identity = Depends(get_identity)):
    """保存草稿（version +1）。ACTIVE Skill 保存后回到 DRAFT，需重新发布。"""
    _reject_identity_fields(payload)
    service = _skill_service(request)
    view = service.update(
        skill_id, _draft_payload(payload),
        owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions)
    return _skill_view_dict(view)


@router.delete('/skills/{skill_id}', status_code=204)
def delete_skill(skill_id: str, request: Request,
                 identity: Identity = Depends(get_identity)):
    """删除自定义 Skill（立即从 L1 / 激活候选消失；版本行保留供回放）。"""
    service = _skill_service(request)
    service.delete(skill_id, owner_id=identity.user_id,
                   tenant_id=identity.tenant_id)
    return Response(status_code=204)


@router.post('/skills/{skill_id}/publish')
def publish_skill(skill_id: str, request: Request,
                  identity: Identity = Depends(get_identity)):
    """发布门槛：≥3 条 golden tasks 且触发判定通过才 ACTIVE。"""
    service = _skill_service(request)
    result = service.publish(
        skill_id, owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions)
    return {
        'skill': _skill_view_dict(
            service.get(skill_id, owner_id=identity.user_id,
                        tenant_id=identity.tenant_id,
                        permissions=identity.permissions)),
        'gate': result.gate.to_dict(),
        'participates_in_trigger': result.participates_in_trigger,
    }


@router.post('/skills/{skill_id}/disable')
def disable_skill(skill_id: str, request: Request,
                  identity: Identity = Depends(get_identity)):
    """停用：立即从 L1 / 激活候选消失；在办 run 按快照继续。"""
    service = _skill_service(request)
    view = service.disable(skill_id, owner_id=identity.user_id,
                           tenant_id=identity.tenant_id)
    return _skill_view_dict(view)


@router.post('/skills/{skill_id}/fork', status_code=201)
def fork_skill(skill_id: str, payload: SkillForkRequest, request: Request,
               identity: Identity = Depends(get_identity)):
    """从内置 / 可见 Skill fork 出本人的草稿。"""
    _reject_identity_fields(payload)
    service = _skill_service(request)
    view = service.fork(
        skill_id, owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions, name=payload.name or '',
        description=payload.description or '')
    return _skill_view_dict(view)


@router.post('/skills/import', status_code=201)
async def import_skill(request: Request,
                       file: UploadFile = File(...),
                       identity: Identity = Depends(get_identity)):
    """zip 导入（根级 ``SKILL.md`` + references/scripts/assets）。"""
    service = _skill_service(request)
    data = await file.read()
    view = service.import_package(
        data, owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions)
    return _skill_view_dict(view)


@router.get('/skills/{skill_id}/export')
def export_skill(skill_id: str, request: Request,
                 identity: Identity = Depends(get_identity)):
    """导出 zip（根级 ``SKILL.md``，与本服务导入和平台包同一结构）。"""
    service = _skill_service(request)
    filename, data = service.export_package(
        skill_id, owner_id=identity.user_id, tenant_id=identity.tenant_id,
        permissions=identity.permissions)
    return Response(
        content=data, media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/skills/{skill_id}/versions')
def list_skill_versions(skill_id: str, request: Request,
                        identity: Identity = Depends(get_identity)):
    service = _skill_service(request)
    versions = service.versions(skill_id, owner_id=identity.user_id,
                                tenant_id=identity.tenant_id)
    return {
        'items': [
            {'version': item.version, 'content_hash': item.content_hash,
             'created_at': _iso(item.created_at),
             'created_by': item.created_by}
            for item in versions
        ],
    }


@router.get('/runs/{run_id}/skills')
def list_run_skills(run_id: str, request: Request,
                    identity: Identity = Depends(get_identity)):
    """run 的 Skill 版本快照 + 按版本表回放（Skill 后续修改不影响历史 run）。"""
    container = get_container(request)
    container.run_service.get_run(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)
    service = _skill_service(request)
    return {'items': service.replay(
        run_id, owner_id=identity.user_id, tenant_id=identity.tenant_id)}
