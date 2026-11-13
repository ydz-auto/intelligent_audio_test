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
| GET  | /api/v1/agent/runs/{id}/approvals | 待审批提案（M0 空列表）|
| GET  | /api/v1/agent/runs/{id}/context-snapshots | 上下文压缩快照（调试模式可回放）|
| GET  | /api/v1/agent/skills | 当前用户可见 Skill（§4.2 规则 7）|
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from agent_service.config.config import Config
from agent_service.domain.model.entities import AgentRun, AgentSession
from agent_service.interfaces.api.dependencies import (
    Identity, get_container, get_identity,
)
from agent_service.interfaces.api.schemas import (
    CreateRunRequest, CreateRunResponse, CreateSessionRequest, RunResponse,
    SessionDetailResponse, SessionResponse, SkillResponse,
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
                identity: Identity = Depends(get_identity)):
    """当前用户可见的 Skill 列表（§11；权限 = Skill ∩ 用户权限）。

    INT-2453：同一响应附带当前用户可见的意图工具清单（31 个注册项，
    ``enabled`` 标明 M0 是否已实现），供前端展示与 Skill allowed-tools 对照。
    """
    from shared.agent_tools.intent_tools import ENABLED_TOOLS

    container = get_container(request)
    registry = container.skill_registry
    visible = registry.visible_for(identity.permissions)
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
        'items': [
            SkillResponse(
                name=skill.name, description=skill.description,
                version=skill.meta.version, owner=skill.meta.owner,
                allowed_tools=list(skill.meta.allowed_tools),
                permissions=list(skill.meta.permissions),
                budgets=dict(skill.meta.budgets),
            ).model_dump()
            for skill in visible
        ],
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
        'l1_tokens': registry.l1_tokens(identity.permissions),
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
