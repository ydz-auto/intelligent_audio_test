"""日志查询 Service。

P0-3 DDD 改造：所有 Log 读/聚合统计查询通过 gRPC 调用 task_service，
不再直连 task_service DB。
"""
import json
from datetime import datetime, timedelta

import pandas as pd
from fastapi.responses import FileResponse

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.utils.query_utils import now_cst
from shared.infrastructure.storage import storage
from api_gateway.schemas.log import (
    LogItem, LogListData, LogRefreshData, LogRefreshRequest,
    LogExportRequest, LogListQuery, LogStatsQuery, LogArchiveQuery, LogExportQuery,
)


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class LogQueryService:
    """日志查询读侧 Service（CQRS Query Side）。

    承载 LogController 中所有只读查询方法，保持原有逻辑不变。
    """

    # 获取日志列表 (支持分页和高级过滤)
    @staticmethod
    def get_logs():
        try:
            query = _parse_query_params(LogListQuery)

            # 通过 gRPC 查询 Log 列表（task_id/level/日期由服务端过滤，其余条件客户端过滤）
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            resp = task_data_service.list_logs(
                task_id=query.task_id,
                level=query.level.split(',')[0].strip() if query.level else None,
                page=query.page,
                per_page=query.per_page,
                start_date=query.start_time,
                end_date=query.end_time,
            )
            logs = resp.get('items') or []
            total = resp.get('total', 0)

            # 客户端过滤：gRPC ListLogs 仅支持 task_id/level/日期，其余条件在此过滤
            def _match(log):
                if query.module and (log.get('module') or '').lower() != query.module.lower():
                    return False
                if query.category and query.category != 'all' and (log.get('category') or '').lower() != query.category.lower():
                    return False
                if query.mark and log.get('mark') != query.mark:
                    return False
                if query.device_id and log.get('device_id') != query.device_id:
                    return False
                if query.api_id and log.get('api_id') != query.api_id:
                    return False
                if query.test_case_id and log.get('test_case_id') != query.test_case_id:
                    return False
                if query.thread_id and query.thread_id not in (log.get('thread_id') or ''):
                    return False
                content = log.get('content') or ''
                if query.keyword and query.keyword not in content:
                    return False
                if query.content_include and query.content_include not in content:
                    return False
                if query.content_exclude and query.content_exclude in content:
                    return False
                if query.algorithm_type and query.algorithm_type != 'all' and log.get('algorithm_type') != query.algorithm_type:
                    return False
                return True

            logs = [log for log in logs if _match(log)]

            data = []
            for log in logs:
                data.append(
                    LogItem(
                        id=log.get('id'),
                        time=log.get('time') or '',
                        level=log.get('level') or '',
                        category=log.get('category') or '',
                        module=log.get('module') or '',
                        source=log.get('source') or '',
                        content=log.get('content') or '',
                        mark=log.get('mark'),
                        device_id=log.get('device_id'),
                        task_id=log.get('task_id'),
                        api_id=log.get('api_id'),
                        test_case_id=log.get('test_case_id'),
                        thread_id=log.get('thread_id'),
                        algorithm_type=log.get('algorithm_type'),
                    )
                )

            return success_response(
                LogListData(
                    items=data,
                    total=total,
                    page=query.page,
                    per_page=query.per_page,
                    pages=(total + query.per_page - 1) // query.per_page if query.per_page else 1,
                )
            )
        except Exception as e:
            log_not_emit('ERROR', 'log_controller', f'Error in get_logs: {str(e)}', category='system')
            import traceback
            traceback.print_exc()
            return error_response(f"获取日志失败: {str(e)}", code=500)

    # 获取日志统计
    @staticmethod
    def get_stats():
        try:
            query = _parse_query_params(LogStatsQuery)

            # P0-3: 通过 gRPC 聚合查询日志统计
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            from api_gateway.schemas.log import LogStatsData
            stats_dict = task_data_service.get_log_stats(
                level=query.level,
                module=query.module if query.module != 'all' else None,
                category=query.category if query.category != 'all' else None,
                mark=query.mark,
                device_id=query.device_id,
                task_id=query.task_id,
                keyword=query.keyword,
                content_include=query.content_include,
                content_exclude=query.content_exclude,
                start_time=query.start_time,
                end_time=query.end_time,
                algorithm_type=query.algorithm_type if query.algorithm_type != 'all' else None,
            )

            log_stats = LogStatsData(
                total=stats_dict.get('total', 0),
                debug=stats_dict.get('debug', 0),
                info=stats_dict.get('info', 0),
                warning=stats_dict.get('warning', 0),
                error=stats_dict.get('error', 0),
                critical=stats_dict.get('critical', 0)
            )

            return success_response(log_stats)
        except Exception as e:
            log_not_emit('ERROR', 'log_controller', f'Error in get_stats: {str(e)}', category='system')
            import traceback
            traceback.print_exc()
            return error_response(f"获取日志统计失败: {str(e)}", code=500)

    # 刷新日志 (手动同步新日志)
    @staticmethod
    def refresh_logs():
        req = LogRefreshRequest.model_validate(request.get_json() or {})
        # P0-3: 通过 gRPC 增量查询日志
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        resp = task_data_service.list_logs_after_id(last_id=req.last_id, limit=100)
        new_logs = resp.get('items', [])
        db_max_id = resp.get('max_id', 0)

        data_list = []
        for log in new_logs:
            data_list.append(
                LogItem(
                    id=log.get('id'),
                    time=log.get('time') or '',
                    level=log.get('level') or '',
                    category=log.get('category') or '',
                    module=log.get('module') or '',
                    source=log.get('source') or '',
                    content=log.get('content') or '',
                    mark=log.get('mark'),
                    device_id=log.get('device_id'),
                    task_id=log.get('task_id'),
                    api_id=log.get('api_id'),
                    test_case_id=log.get('test_case_id'),
                    thread_id=log.get('thread_id'),
                    algorithm_type=log.get('algorithm_type'),
                )
            )

        # 将 db_max_id / reset_required 放入 data，前端据此判断是否需要重置增量基准
        payload = LogRefreshData(
            items=data_list,
            count=len(data_list),
            new_count=len(data_list),
            last_id=data_list[-1].id if data_list else req.last_id,
        )
        payload_dict = payload.model_dump(exclude_none=True)
        payload_dict['db_max_id'] = db_max_id
        if req.last_id > db_max_id:
            payload_dict['reset_required'] = True
        return success_response(payload_dict)

    # 导出日志
    @staticmethod
    def export_logs():
        import os
        req = LogExportRequest.model_validate(request.get_json() or {})
        query = _parse_query_params(LogExportQuery)

        # P0-3: 通过 gRPC 查询日志（按 id 列表或条件）
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        resp = task_data_service.get_logs_for_export(
            log_ids=req.log_ids if req.log_ids else None,
            level=query.level,
            module=query.module,
        )
        logs = resp.get('items', [])

        export_data = []
        for log in logs:
            export_data.append({
                "ID": log.get('id'),
                "Time": log.get('time') or '',
                "Level": log.get('level') or '',
                "Module": log.get('module') or '',
                "Content": log.get('content') or '',
                "Mark": log.get('mark') or ""
            })

        df = pd.DataFrame(export_data)
        export_dir = os.path.join(os.getcwd(), 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        filename = f"logs_export_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        file_path = ""

        if req.format == 'csv':
            file_path = os.path.join(export_dir, f"{filename}.csv")
            df.to_csv(file_path, index=False)
        elif req.format == 'json':
            file_path = os.path.join(export_dir, f"{filename}.json")
            df.to_json(file_path, orient='records', indent=4)
        elif req.format == 'txt':
            file_path = os.path.join(export_dir, f"{filename}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in export_data:
                    f.write(f"[{item['Time']}] {item['Level']} {item['Module']}: {item['Content']}\n")
        else: # Default Excel
            file_path = os.path.join(export_dir, f"{filename}.xlsx")
            df.to_excel(file_path, index=False)

        return FileResponse(file_path, headers={"Content-Disposition": "attachment"})

    # 获取归档状态
    @staticmethod
    def get_archive_status():
        try:
            # OSS: 列出 archives bucket 下各前缀的文件数
            task_keys = storage.list_objects('archives', prefix='tasks/')
            case_keys = storage.list_objects('archives', prefix='cases/')
            other_keys = storage.list_objects('archives', prefix='other/')

            task_count = len([k for k in task_keys if k.endswith('.json')])
            case_count = len([k for k in case_keys if k.endswith('.json')])
            other_count = len([k for k in other_keys if k.endswith('.json')])

            # P0-3: 通过 gRPC 查询日志总数
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            cutoff_date = now_cst() - timedelta(days=7)
            result = task_data_service.get_log_count(start_date=cutoff_date.isoformat())
            total_logs = result.get('total', 0)
            hot_logs = result.get('hot', 0)
            cold_logs = result.get('cold', 0)

            return success_response({
                "totalLogs": total_logs,
                "hotLogs": hot_logs,
                "coldLogs": cold_logs,
                "archiveDir": "oss://archives",
                "taskArchives": task_count,
                "caseArchives": case_count,
                "otherArchives": other_count
            })
        except Exception as e:
            return error_response(f"获取归档状态失败: {str(e)}", code=500)

    # 获取归档日志
    @staticmethod
    def get_archived_logs():
        query = _parse_query_params(LogArchiveQuery)

        if not query.task_id and not query.test_case_id:
            return error_response("需要提供 task_id 或 test_case_id 参数", code=400)

        try:
            logs = []

            def load_oss_json_files(prefix):
                """从存储 archives 类目读取指定前缀下所有 JSON 文件"""
                result = []
                keys = storage.list_objects('archives', prefix=prefix)
                for key in keys:
                    if not key.endswith('.json'):
                        continue
                    try:
                        data = storage.load_bytes(f'archives/{key}')
                        result.extend(json.loads(data))
                    except Exception:
                        continue
                return result

            if query.task_id:
                if query.test_case_id:
                    # tasks/{task_id}/{case_id}/*.json
                    prefix = f'tasks/{query.task_id}/{query.test_case_id}/'
                    logs.extend(load_oss_json_files(prefix))
                else:
                    # tasks/{task_id}/*.json + tasks/{task_id}/*/*.json
                    prefix = f'tasks/{query.task_id}/'
                    keys = storage.list_objects('archives', prefix=prefix)
                    for key in keys:
                        if not key.endswith('.json'):
                            continue
                        try:
                            data = storage.load_bytes(f'archives/{key}')
                            logs.extend(json.loads(data))
                        except Exception:
                            continue

            if query.test_case_id and not query.task_id:
                prefix = f'cases/{query.test_case_id}/'
                logs.extend(load_oss_json_files(prefix))

            logs.sort(key=lambda x: x.get('time', '') or '', reverse=True)

            items = []
            for log in logs:
                items.append(LogItem(
                    id=log.get('id', 0),
                    time=log.get('time', ''),
                    level=log.get('level', ''),
                    category=log.get('category', ''),
                    module=log.get('module', ''),
                    source=log.get('source', ''),
                    content=log.get('content', ''),
                    mark=log.get('mark'),
                    device_id=log.get('device_id'),
                    task_id=log.get('task_id'),
                    api_id=log.get('api_id'),
                    test_case_id=log.get('test_case_id'),
                    thread_id=log.get('thread_id'),
                    algorithm_type=log.get('algorithm_type'),
                ))

            return success_response({
                "items": items,
                "total": len(items),
                "source": "archive"
            })
        except Exception as e:
            return error_response(f"获取归档日志失败: {str(e)}", code=500)

    # 下载归档文件
    @staticmethod
    def download_archive(filename):
        try:
            # OSS: 在 archives bucket 中搜索匹配的文件
            all_keys = storage.list_objects('archives')
            matching_keys = [k for k in all_keys if k.endswith(f'/{filename}') or k == filename]

            if not matching_keys:
                return error_response("归档文件不存在", code=404)

            # 下载到临时文件再返回
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
            storage.load_file(f'archives/{matching_keys[0]}', tmp.name)
            return FileResponse(tmp.name, headers={"Content-Disposition": f"attachment; filename={filename}"})
        except Exception as e:
            return error_response(f"下载失败: {str(e)}", code=500)
