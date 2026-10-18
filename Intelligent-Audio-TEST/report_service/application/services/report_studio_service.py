# -*- coding: utf-8 -*-
"""Report Studio 应用服务（INT-673，设计文档 §15.4/§15.5）

CQRS 语义：
- 写侧：create_document / update_document / restore_version / create_export_job
  只写并自动落不可变版本快照（同一数据库事务），不发跨服务事件；
- 读侧：get_document / list_versions / get_chart_data / get_export_job /
  download_export 只读 ReadModel 与事实表，无写副作用。

服务端强制对象级权限（§15.8）：AUTH_MODE=off（user_id=None）时跳过归属校验，
开启认证后文档/图表/导出作业按 created_by 核验，跨账号不可读。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import threading
import uuid
from difflib import unified_diff
from typing import Any, Dict, List, Optional

from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
)
from shared.models.common_enums import (
    StudioExportFormat,
    StudioExportStatus,
    StudioSnapshotReason,
)
from report_service.config.config import Config

logger = logging.getLogger(__name__)


def _md5(*parts: Any) -> str:
    raw = '|'.join(str(p) for p in parts)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _new_id() -> str:
    return str(uuid.uuid4())


def _line_diff(left: str, right: str, max_lines: int = 12) -> List[str]:
    """逐行差异摘要（409 冲突信息用，非语义 diff）。"""
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    diff = list(unified_diff(left_lines, right_lines, lineterm='', n=1))[2:]
    if len(diff) > max_lines:
        diff = diff[:max_lines] + ['...']
    return diff


def _default_repo():
    from report_service.infrastructure.persistence.report_studio_repository import (
        ReportStudioRepositoryImpl,
    )
    return ReportStudioRepositoryImpl()


def _load_report(report_id: int):
    """读取报告聚合根（图表数据事实源；懒导入避免循环依赖）。"""
    from report_service.application.handlers.report_handlers import ReportQueryHandler
    from report_service.application.queries.report_queries import GetReportQuery
    return ReportQueryHandler().handle_get(GetReportQuery(report_id=int(report_id)))


class ReportStudioService:
    """Report Studio 应用服务（Query/Command 双侧的领域编排）。"""

    def __init__(self, repo=None):
        self._repo = repo

    @property
    def repo(self):
        if self._repo is None:
            self._repo = _default_repo()
        return self._repo

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _owner_check(doc) -> Optional[Dict[str, Any]]:
        """对象级权限校验：未认证/管理员放行，跨账号 403。"""
        user_id = get_current_user_id()
        if user_id is None or get_current_user_is_admin():
            return None
        if getattr(doc, 'created_by', None) is not None and int(doc.created_by) != int(user_id):
            return {'success': False, 'message': '无权访问该文档', 'data': None, 'code': 403}
        return None

    @staticmethod
    def _owner_check_export(job) -> Optional[Dict[str, Any]]:
        user_id = get_current_user_id()
        if user_id is None or get_current_user_is_admin():
            return None
        if getattr(job, 'created_by', None) is not None and int(job.created_by) != int(user_id):
            return {'success': False, 'message': '无权访问该导出作业', 'data': None, 'code': 403}
        return None

    @staticmethod
    def _doc_dict(doc, include_content: bool = True) -> Dict[str, Any]:
        data = {
            'doc_id': doc.doc_id,
            'report_id': doc.report_id,
            'title': doc.title,
            'current_version': doc.current_version,
            'etag': doc.etag_hash,
            'chart_refs': list(doc.chart_refs or []),
            'style_prefs': dict(doc.style_prefs or {}),
            'agent_session_id': doc.agent_session_id,
            'created_by': doc.created_by,
            'created_at': doc.created_at,
            'updated_at': doc.updated_at,
        }
        if include_content:
            data['markdown_content'] = doc.markdown_content
        return data

    @staticmethod
    def _version_dict(v) -> Dict[str, Any]:
        return {
            'id': v.id,
            'doc_id': v.doc_id,
            'version': v.version,
            'parent_version': v.parent_version,
            'snapshot_reason': v.snapshot_reason,
            'created_by': v.created_by,
            'created_at': v.created_at,
            'chart_specs': dict(v.chart_specs or {}),
        }

    # ------------------------------------------------------------------
    # 写侧：文档
    # ------------------------------------------------------------------

    def create_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        report_id = data.get('report_id')
        if not report_id:
            return {'success': False, 'message': '缺少 report_id', 'data': None, 'code': 400}
        # 校验报告存在（事实源复用报告 7 表）
        aggregate = _load_report(int(report_id))
        if aggregate is None:
            return {'success': False, 'message': '报告不存在', 'data': None, 'code': 404}

        doc_id = data.get('doc_id') or _new_id()
        title = data.get('title') or (getattr(aggregate, 'name', None) or f'报告 {report_id} 草稿')
        markdown = data.get('markdown_content') or ''
        chart_refs = [r for r in (data.get('chart_refs') or []) if isinstance(r, str)]
        style_prefs = dict(data.get('style_prefs') or {})
        agent_session_id = data.get('agent_session_id')
        created_by = get_current_user_id()
        etag = _md5(1, markdown)
        snapshot_reason = StudioSnapshotReason.AI_EDIT.value if agent_session_id \
            else StudioSnapshotReason.MANUAL_EDIT.value

        from report_service.domain.entities.report_studio import (
            ReportStudioDocument,
            ReportStudioVersion,
        )
        doc = ReportStudioDocument(
            doc_id=doc_id, report_id=int(report_id), title=str(title),
            markdown_content=markdown, chart_refs=chart_refs, style_prefs=style_prefs,
            current_version=1, etag_hash=etag, agent_session_id=agent_session_id,
            created_by=created_by,
        )
        version = ReportStudioVersion(
            id=0, doc_id=doc_id, version=1, markdown_content=markdown,
            chart_specs={'chart_refs': chart_refs}, parent_version=None,
            snapshot_reason=snapshot_reason, created_by=created_by,
        )
        try:
            self.repo.create_document(doc, version)
        except Exception as e:
            logger.exception('创建 Report Studio 文档失败')
            return {'success': False, 'message': f'创建文档失败: {e}', 'data': None, 'code': 500}
        return {'success': True, 'message': 'ok', 'data': self._doc_dict(doc), 'code': 0}

    # ------------------------------------------------------------------
    # 读侧：文档
    # ------------------------------------------------------------------

    def get_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        if not doc_id:
            return {'success': False, 'message': '缺少 doc_id', 'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied
        return {'success': True, 'message': 'ok', 'data': self._doc_dict(doc), 'code': 0}

    # ------------------------------------------------------------------
    # 写侧：编辑（乐观锁）
    # ------------------------------------------------------------------

    def update_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        expected_version = data.get('expected_version')
        if not doc_id or expected_version is None:
            return {'success': False, 'message': '缺少 doc_id 或 expected_version', 'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied

        markdown = data.get('markdown_content') or ''
        chart_refs = [r for r in (data.get('chart_refs') or []) if isinstance(r, str)]
        style_prefs = dict(data.get('style_prefs') or {})
        new_version = int(expected_version) + 1
        etag = _md5(new_version, markdown)

        from report_service.domain.entities.report_studio import ReportStudioVersion
        snapshot = ReportStudioVersion(
            id=0, doc_id=str(doc_id), version=new_version, markdown_content=markdown,
            chart_specs={'chart_refs': chart_refs},
            parent_version=int(expected_version),
            snapshot_reason=StudioSnapshotReason.MANUAL_EDIT.value,
            created_by=get_current_user_id(),
        )
        try:
            result = self.repo.update_document(
                str(doc_id), int(expected_version), markdown, chart_refs,
                style_prefs, etag, new_version, snapshot)
        except Exception as e:
            logger.exception('更新 Report Studio 文档失败')
            return {'success': False, 'message': f'更新文档失败: {e}', 'data': None, 'code': 500}
        if result is None:
            current = self.repo.get_document(str(doc_id))
            return {
                'success': False,
                'message': '版本冲突：他人已更新该文档',
                'data': {
                    'expected_version': int(expected_version),
                    'current_version': current.current_version if current else None,
                    'diff': _line_diff(markdown, current.markdown_content if current else ''),
                },
                'code': 409,
            }
        doc = self.repo.get_document(str(doc_id))
        return {'success': True, 'message': 'ok', 'data': self._doc_dict(doc), 'code': 0}

    # ------------------------------------------------------------------
    # 读侧：版本列表
    # ------------------------------------------------------------------

    def list_versions(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        if not doc_id:
            return {'success': False, 'message': '缺少 doc_id', 'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied
        versions = self.repo.list_versions(str(doc_id))
        return {'success': True, 'message': 'ok',
                'data': {'items': [self._version_dict(v) for v in versions],
                         'total': len(versions)}, 'code': 0}

    # ------------------------------------------------------------------
    # 写侧：版本恢复（新版本，不覆盖）
    # ------------------------------------------------------------------

    def restore_version(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        version = data.get('version')
        expected_version = data.get('expected_version')
        if not doc_id or version is None or expected_version is None:
            return {'success': False, 'message': '缺少 doc_id/version/expected_version',
                    'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied
        target = self.repo.get_version(str(doc_id), int(version))
        if target is None:
            return {'success': False, 'message': '历史版本不存在', 'data': None, 'code': 404}

        new_version = int(expected_version) + 1
        new_etag = _md5(new_version, target.markdown_content)
        try:
            result = self.repo.restore_version(
                str(doc_id), int(expected_version), target, new_version, new_etag)
        except Exception as e:
            logger.exception('恢复 Report Studio 文档版本失败')
            return {'success': False, 'message': f'恢复版本失败: {e}', 'data': None, 'code': 500}
        if result is None:
            current = self.repo.get_document(str(doc_id))
            return {
                'success': False,
                'message': '版本冲突：他人已更新该文档',
                'data': {'expected_version': int(expected_version),
                         'current_version': current.current_version if current else None},
                'code': 409,
            }
        doc = self.repo.get_document(str(doc_id))
        return {'success': True, 'message': 'ok', 'data': self._doc_dict(doc), 'code': 0}

    # ------------------------------------------------------------------
    # 读侧：图表数据
    # ------------------------------------------------------------------

    def get_chart_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        chart_id = data.get('chart_id')
        if not doc_id or not chart_id:
            return {'success': False, 'message': '缺少 doc_id 或 chart_id', 'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied
        spec = self.repo.get_chart_spec(str(doc_id), str(chart_id))
        if spec is None:
            return {'success': False, 'message': '图表不存在', 'data': None, 'code': 404}
        if spec.doc_id != str(doc_id):
            return {'success': False, 'message': '图表与文档不匹配', 'data': None, 'code': 403}

        aggregate = _load_report(int(spec.report_id))
        if aggregate is None:
            return {'success': False, 'message': '来源报告不存在', 'data': None, 'code': 404}
        metric_params = spec.metric_params or {}
        return {
            'success': True,
            'message': 'ok',
            'data': self._compute_chart_data(doc, spec, aggregate, metric_params),
            'code': 0,
        }

    @staticmethod
    def _compute_chart_data(doc, spec, aggregate, metric_params: Dict[str, Any]) -> Dict[str, Any]:
        """按当前报告事实 + ChartSpec 生成图表数据（服务端重新校验指标）。

        仅读取报告 7 表既有统计（full_summary.metric_data / summaries），
        不执行任何用户输入的 JS/SQL/URL 脚本。
        """
        wanted = [str(m) for m in (metric_params.get('metrics') or [])]
        group_by = metric_params.get('group_by') or 'category'

        # 总体指标：报告完整视图 metric_data（dict 单组或 list 多组）
        metrics = []
        full = aggregate.full_summary or {}
        metric_data = full.get('metric_data') or {}
        if isinstance(metric_data, dict):
            metric_data = [metric_data]
        for md in metric_data if isinstance(metric_data, list) else []:
            if not isinstance(md, dict):
                continue
            name = str(md.get('metric_name') or md.get('name') or 'overall')
            if wanted and name not in wanted:
                continue
            metrics.append({
                'name': name,
                'avg': float(md.get('avg') or 0.0),
                'min': float(md.get('min') or 0.0),
                'max': float(md.get('max') or 0.0),
                'std_dev': float(md.get('std_dev') or 0.0),
                'sample_count': int(md.get('sample_count') or 0),
            })

        # 分组维度（category/device 等）：优先 metric_data 行内 category 键，
        # 其次 summaries.metadata（报告摘要行不含 category 时归入「全部」）
        groups: Dict[str, Dict[str, Any]] = {}
        for md in metric_data if isinstance(metric_data, list) else []:
            if not isinstance(md, dict):
                continue
            name = str(md.get('metric_name') or md.get('name') or 'overall')
            if wanted and name not in wanted:
                continue
            gname = str(md.get(group_by) or md.get('category') or '全部')
            bucket = groups.setdefault(gname, {'name': gname, 'metrics': {}})
            bucket['metrics'][name] = float(md.get('avg') or 0.0)
        for s in (aggregate.summaries or []):
            if wanted and s.metric_name not in wanted:
                continue
            meta = dict(s.metadata or {})
            gname = str(meta.get(group_by) or meta.get('category') or '全部')
            bucket = groups.setdefault(gname, {'name': gname, 'metrics': {}})
            bucket['metrics'].setdefault(s.metric_name, s.metric_value)

        return {
            'chart_id': spec.chart_id,
            'doc_id': doc.doc_id,
            'report_id': spec.report_id,
            'title': f'{doc.title} 图表',
            'spec_version': spec.version,
            'metrics': metrics,
            'series': [
                {'name': g['name'], 'metrics': g['metrics']}
                for g in groups.values()
            ],
            'metric_params': metric_params,
        }

    # ------------------------------------------------------------------
    # 写侧：导出异步作业
    # ------------------------------------------------------------------

    def create_export_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get('doc_id')
        version = data.get('version')
        fmt = data.get('format')
        if not doc_id or version is None or not fmt:
            return {'success': False, 'message': '缺少 doc_id/version/format',
                    'data': None, 'code': 400}
        try:
            fmt_value = StudioExportFormat(fmt).value
        except ValueError:
            return {'success': False, 'message': f'不支持的导出格式: {fmt}',
                    'data': None, 'code': 400}
        doc = self.repo.get_document(str(doc_id))
        if doc is None:
            return {'success': False, 'message': '文档不存在', 'data': None, 'code': 404}
        denied = self._owner_check(doc)
        if denied:
            return denied
        # 固定文档版本：目标版本必须存在（允许导出当前版或任一历史版）
        target = self.repo.get_version(str(doc_id), int(version))
        if target is None:
            return {'success': False, 'message': f'文档版本 {version} 不存在',
                    'data': None, 'code': 404}

        theme = data.get('theme') or 'default'
        export_id = _new_id()
        from report_service.domain.entities.report_studio import ReportStudioExportJob
        job = ReportStudioExportJob(
            export_id=export_id, doc_id=str(doc_id), version=int(version),
            format=fmt_value, theme=str(theme), status=StudioExportStatus.PENDING.value,
            progress=0, created_by=get_current_user_id(),
        )
        try:
            self.repo.create_export_job(job)
        except Exception as e:
            logger.exception('创建导出作业失败')
            return {'success': False, 'message': f'创建导出作业失败: {e}',
                    'data': None, 'code': 500}

        # 后台线程渲染（作业记录持久化，线程退出不影响记录查询）
        t = threading.Thread(
            target=self._run_export_job, args=(export_id, fmt_value, theme),
            daemon=True, name=f'report-studio-export-{export_id[:8]}')
        t.start()
        return {'success': True, 'message': 'ok',
                'data': self._export_job_dict(job), 'code': 0}

    def _run_export_job(self, export_id: str, fmt: str, theme: str) -> None:
        """后台执行导出：渲染 → 写文件 → 更新作业状态。"""
        try:
            self.repo.update_export_job(
                export_id, status=StudioExportStatus.RUNNING.value, progress=10)
            job = self.repo.get_export_job(export_id)
            if job is None:
                return
            doc = self.repo.get_document(job.doc_id)
            if doc is None:
                self.repo.update_export_job(
                    export_id, status=StudioExportStatus.FAILED.value,
                    error='文档不存在', progress=100)
                return
            target = self.repo.get_version(job.doc_id, job.version) or doc
            markdown = target.markdown_content or doc.markdown_content

            export_dir = self._export_dir()
            os.makedirs(export_dir, exist_ok=True)
            if fmt == StudioExportFormat.MD.value:
                filename = f'{export_id}.md'
                content = markdown.encode('utf-8')
                mime = 'text/markdown'
            elif fmt == StudioExportFormat.HTML.value:
                filename = f'{export_id}.html'
                content = self._render_html(markdown, theme, doc.title).encode('utf-8')
                mime = 'text/html'
            else:
                # PPTX/PDF 属 S3 增强候选技术（§15.6），本卡落地 HTML/MD
                self.repo.update_export_job(
                    export_id, status=StudioExportStatus.FAILED.value,
                    error=f'格式 {fmt} 渲染为后续增强（S3），当前支持 html/md',
                    progress=100)
                return

            file_path = os.path.join(export_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(content)
            self.repo.update_export_job(
                export_id, status=StudioExportStatus.DONE.value,
                file_path=file_path, progress=100)
        except Exception as e:
            logger.exception('导出作业执行失败: %s', export_id)
            try:
                self.repo.update_export_job(
                    export_id, status=StudioExportStatus.FAILED.value,
                    error=str(e), progress=100)
            except Exception:
                logger.exception('更新导出作业失败状态失败')

    @staticmethod
    def _export_dir() -> str:
        base = getattr(Config, 'REPORT_STUDIO_EXPORT_DIR', None) or 'report_studio_exports'
        return os.path.abspath(base)

    @staticmethod
    def _render_html(markdown: str, theme: str, title: str) -> str:
        """最小 Markdown → HTML 渲染（受控输出，无脚本执行）。

        覆盖报告文档常用子集：标题/段落/粗斜体/列表/代码块/表格/分隔线。
        模型输出视为不可信内容，渲染为纯 HTML 文本节点。
        """
        import html
        lines = markdown.splitlines()
        out: List[str] = []
        i = 0
        in_code = False
        code_buf: List[str] = []
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith('```'):
                if not in_code:
                    in_code = True
                    code_buf = []
                else:
                    out.append('<pre><code>' + html.escape('\n'.join(code_buf)) + '</code></pre>')
                    in_code = False
                i += 1
                continue
            if in_code:
                code_buf.append(line)
                i += 1
                continue
            stripped = line.strip()
            if not stripped:
                out.append('<p></p>')
            elif stripped.startswith('### '):
                out.append(f'<h3>{html.escape(stripped[4:])}</h3>')
            elif stripped.startswith('## '):
                out.append(f'<h2>{html.escape(stripped[3:])}</h2>')
            elif stripped.startswith('# '):
                out.append(f'<h1>{html.escape(stripped[2:])}</h1>')
            elif stripped.startswith('- ') or stripped.startswith('* '):
                out.append(f'<li>{html.escape(stripped[2:])}</li>')
            elif stripped.startswith('|') and i + 1 < len(lines) \
                    and set(lines[i + 1].strip().replace('|', '').replace('-', '').replace(':', '').replace(' ', '')) == set():
                # 表格头 + 分隔行 → 简单表格
                header_cells = [c.strip() for c in stripped.strip('|').split('|')]
                i += 1
                body_rows = []
                while i + 1 < len(lines) and lines[i + 1].strip().startswith('|'):
                    body_rows.append([c.strip() for c in lines[i + 1].strip().strip('|').split('|')])
                    i += 1
                html_rows = '<thead><tr>' + ''.join(
                    f'<th>{html.escape(c)}</th>' for c in header_cells) + '</tr></thead>'
                html_body = ''
                for row in body_rows:
                    html_body += '<tr>' + ''.join(
                        f'<td>{html.escape(c)}</td>' for c in row) + '</tr>'
                out.append(f'<table>{html_rows}<tbody>{html_body}</tbody></table>')
            elif stripped == '---':
                out.append('<hr/>')
            else:
                text = html.escape(stripped)
                text = text.replace('**', '<strong>', 1).replace('**', '</strong>', 1)
                text = text.replace('__', '<em>', 1).replace('__', '</em>', 1)
                out.append(f'<p>{text}</p>')
            i += 1
        if in_code:
            out.append('<pre><code>' + html.escape('\n'.join(code_buf)) + '</code></pre>')
        theme_css = ('.report-studio-export{font-family:-apple-system,'
                     'Segoe UI,Roboto,sans-serif;max-width:860px;margin:0 auto;'
                     'padding:24px;line-height:1.6;}'
                     'table{border-collapse:collapse;width:100%;margin:8px 0;}'
                     'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}'
                     'pre{background:#f5f5f5;padding:10px;border-radius:4px;overflow-x:auto;}'
                     'code{background:#f5f5f5;padding:1px 4px;border-radius:3px;}')
        return (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"/>'
            f'<title>{html.escape(title)}</title><style>{theme_css}</style></head>'
            f'<body class="report-studio-export"><h1>{html.escape(title)}</h1>'
            f'<p class="export-theme">主题：{html.escape(theme)}</p>'
            + ''.join(out)
            + f'</body></html>'
        )

    @staticmethod
    def _export_job_dict(job) -> Dict[str, Any]:
        return {
            'export_id': job.export_id,
            'doc_id': job.doc_id,
            'version': job.version,
            'format': job.format,
            'theme': job.theme,
            'status': job.status,
            'progress': job.progress,
            'error': job.error,
            'created_by': job.created_by,
            'created_at': job.created_at,
            'updated_at': job.updated_at,
            # 下载引用：网关层据此拼接鉴权下载路径
            'download_ref': f'/api/v1/report-studio/exports/{job.export_id}/download',
        }

    # ------------------------------------------------------------------
    # 读侧：导出作业
    # ------------------------------------------------------------------

    def get_export_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        export_id = data.get('export_id')
        if not export_id:
            return {'success': False, 'message': '缺少 export_id', 'data': None, 'code': 400}
        job = self.repo.get_export_job(str(export_id))
        if job is None:
            return {'success': False, 'message': '导出作业不存在', 'data': None, 'code': 404}
        denied = self._owner_check_export(job)
        if denied:
            return denied
        return {'success': True, 'message': 'ok', 'data': self._export_job_dict(job), 'code': 0}

    def download_export(self, data: Dict[str, Any]) -> Dict[str, Any]:
        export_id = data.get('export_id')
        if not export_id:
            return {'success': False, 'message': '缺少 export_id', 'data': None, 'code': 400}
        job = self.repo.get_export_job(str(export_id))
        if job is None:
            return {'success': False, 'message': '导出作业不存在', 'data': None, 'code': 404}
        denied = self._owner_check_export(job)
        if denied:
            return denied
        if job.status != StudioExportStatus.DONE.value:
            return {'success': False, 'message': f'作业未完成（{job.status}）',
                    'data': None, 'code': 400}
        if not job.file_path or not os.path.exists(job.file_path):
            return {'success': False, 'message': '产物文件缺失', 'data': None, 'code': 404}
        try:
            with open(job.file_path, 'rb') as f:
                content = f.read()
        except OSError as e:
            return {'success': False, 'message': f'读取产物失败: {e}',
                    'data': None, 'code': 500}
        mime = 'text/html' if job.format == StudioExportFormat.HTML.value else 'text/markdown'
        filename = os.path.basename(job.file_path)
        return {
            'success': True, 'message': 'ok',
            'data': {
                'content_base64': base64.b64encode(content).decode('ascii'),
                'mime_type': mime,
                'filename': filename,
                'export_id': export_id,
            },
            'code': 0,
        }


report_studio_service = ReportStudioService()
