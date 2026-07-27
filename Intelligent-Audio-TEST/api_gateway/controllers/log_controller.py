import os
import pandas as pd
import json
import glob
from flask import request, send_file
from shared.models.models import Log
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.clients.oss_client import oss
from api_gateway.schemas.log import LogItem, LogListData, LogRefreshData, LogRefreshRequest, LogMarkRequest, LogClearRequest, LogExportRequest, LogArchiveRequest, LogArchiveStatus, LogArchiveResult
from datetime import datetime, timezone, timedelta
from shared.utils.query_utils import now_cst
from sqlalchemy import func, or_
from flask_socketio import emit, join_room, leave_room


class LogFilterRegistry:
    """
    WebSocket 日志过滤器注册表（进程内单例）。
    保存每个 sid 的过滤器 {levels, modules, task_id, keyword}，供 _emit_websocket 做服务端过滤。
    同时维护 sid -> 房间集合，便于按 task 精准推送。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._filters = {}      # sid -> dict
            cls._instance._sid_task = {}     # sid -> task_id（订阅的任务）
        return cls._instance

    def set_filter(self, sid, filt):
        self._filters[sid] = filt or {}

    def get_filter(self, sid):
        return self._filters.get(sid)

    def remove(self, sid):
        self._filters.pop(sid, None)
        self._sid_task.pop(sid, None)

    def subscribe_task(self, sid, task_id):
        self._sid_task[sid] = task_id

    def unsubscribe_task(self, sid):
        self._sid_task.pop(sid, None)

    def match(self, log_data):
        """
        返回通过过滤器的 sid 列表。
        log_data 字段：level, module, task_id, content
        """
        level = (log_data.get('level') or '').upper()
        module = (log_data.get('module') or '').upper()
        content = log_data.get('content') or ''
        log_task_id = log_data.get('task_id')
        matched = []
        for sid, filt in self._filters.items():
            if not filt:
                matched.append(sid)
                continue
            levels = filt.get('levels')
            if levels:
                if level not in [l.upper() for l in levels]:
                    continue
            modules = filt.get('modules')
            if modules:
                if module not in [m.upper() for m in modules]:
                    continue
            kw = filt.get('keyword')
            if kw and kw not in content:
                continue
            ftid = filt.get('task_id')
            if ftid and str(log_task_id) != str(ftid):
                continue
            matched.append(sid)
        return matched


log_filter_registry = LogFilterRegistry()

class LogController:
    # 获取日志列表 (支持分页和高级过滤)
    @staticmethod
    def get_logs():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 50, type=int)
            level = request.args.get('level')
            module = request.args.get('module')
            category = request.args.get('category')
            keyword = request.args.get('keyword')
            content_include = request.args.get('content_include')
            content_exclude = request.args.get('content_exclude')
            start_time = request.args.get('start_time')
            end_time = request.args.get('end_time')
            mark = request.args.get('mark') # 'true' or 'false'
            device_id = request.args.get('device_id', type=int)
            task_id = request.args.get('task_id', type=int)
            api_id = request.args.get('api_id', type=int)
            test_case_id = request.args.get('test_case_id')
            # 处理额外的参数，避免传递到查询中
            thread_id = request.args.get('thread_id')
            algorithm_type = request.args.get('algorithm_type')

            query = Log.query
            
            if level:
                # 处理多个级别，如 "debug,info,error"
                if ',' in level:
                    levels = [l.strip().lower() for l in level.split(',')]
                    query = query.filter(func.lower(Log.level).in_(levels))
                else:
                    query = query.filter(func.lower(Log.level) == level.lower())
            if module:
                query = query.filter(func.lower(Log.module) == module.lower())
            if category and category != 'all':
                query = query.filter(func.lower(Log.category) == category.lower())
            if mark:
                query = query.filter_by(mark=mark)
            if device_id:
                query = query.filter_by(device_id=device_id)
            if task_id:
                query = query.filter_by(task_id=task_id)
            if api_id:
                query = query.filter_by(api_id=api_id)
            if test_case_id:
                query = query.filter_by(test_case_id=test_case_id)
            if thread_id:
                query = query.filter(Log.thread_id.like(f"%{thread_id}%"))
            if keyword:
                query = query.filter(Log.content.like(f"%{keyword}%"))
            if content_include:
                query = query.filter(Log.content.like(f"%{content_include}%"))
            if content_exclude:
                query = query.filter(~Log.content.like(f"%{content_exclude}%"))
            if start_time:
                try:
                    query = query.filter(Log.time >= datetime.fromisoformat(start_time))
                except ValueError:
                    pass  # 无效的时间格式，忽略该过滤条件
            if end_time:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_time))
                except ValueError:
                    pass  # 无效的时间格式，忽略该过滤条件
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(Log.algorithm_type == algorithm_type)

            pagination = query.order_by(Log.time.desc()).paginate(page=page, per_page=per_page, error_out=False)
            logs = pagination.items

            data = []
            for log in logs:
                data.append(
                    LogItem(
                        id=log.id,
                        time=log.time.isoformat(),
                        level=log.level,
                        category=log.category,
                        module=log.module,
                        source=log.source,
                        content=log.content,
                        mark=log.mark,
                        device_id=log.device_id,
                        task_id=log.task_id,
                        api_id=log.api_id,
                        test_case_id=log.test_case_id,
                        thread_id=log.thread_id,
                        algorithm_type=log.algorithm_type,
                    )
                )

            return success_response(
                LogListData(
                    items=data,
                    total=pagination.total,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    pages=pagination.pages,
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
            start_time = request.args.get('start_time')
            end_time = request.args.get('end_time')
            level = request.args.get('level')
            module = request.args.get('module')
            category = request.args.get('category')
            keyword = request.args.get('keyword')
            mark = request.args.get('mark')
            device_id = request.args.get('device_id', type=int)
            task_id = request.args.get('task_id', type=int)
            content_include = request.args.get('content_include')
            content_exclude = request.args.get('content_exclude')
            algorithm_type = request.args.get('algorithm_type')
            
            query = db.session.query(Log.level, func.count(Log.id))
            
            if level:
                # 处理多个级别，如 "debug,info,error"
                if ',' in level:
                    levels = [l.strip().lower() for l in level.split(',')]
                    query = query.filter(func.lower(Log.level).in_(levels))
                else:
                    query = query.filter(func.lower(Log.level) == level.lower())
            if module and module != 'all':
                query = query.filter(func.lower(Log.module) == module.lower())
            if category and category != 'all':
                query = query.filter(func.lower(Log.category) == category.lower())
            if mark:
                query = query.filter_by(mark=mark)
            if device_id:
                query = query.filter_by(device_id=device_id)
            if task_id:
                query = query.filter_by(task_id=task_id)
            if keyword:
                query = query.filter(Log.content.like(f"%{keyword}%"))
            if content_include:
                query = query.filter(Log.content.like(f"%{content_include}%"))
            if content_exclude:
                query = query.filter(~Log.content.like(f"%{content_exclude}%"))
            if start_time:
                try:
                    query = query.filter(Log.time >= datetime.fromisoformat(start_time))
                except ValueError:
                    pass  # 无效的时间格式，忽略该过滤条件
            if end_time:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_time))
                except ValueError:
                    pass  # 无效的时间格式，忽略该过滤条件
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(Log.algorithm_type == algorithm_type)
            
            from api_gateway.schemas.log import LogStatsData
            stats = query.group_by(Log.level).all()
            stats_dict = {level.lower(): count for level, count in stats}
            
            log_stats = LogStatsData(
                total=sum(stats_dict.values()) if stats_dict else 0,
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
        new_logs = Log.query.filter(Log.id > req.last_id).order_by(Log.id.asc()).limit(100).all()

        # 当前库内最大 id；若 last_id 大于它，说明增量基准已失效（日志被清/归档），前端应 reset
        db_max_id = db.session.query(func.max(Log.id)).scalar() or 0

        data_list = []
        for log in new_logs:
            data_list.append(
                LogItem(
                    id=log.id,
                    time=log.time.isoformat(),
                    level=log.level,
                    category=log.category,
                    module=log.module,
                    source=log.source,
                    content=log.content,
                    mark=log.mark,
                    device_id=log.device_id,
                    task_id=log.task_id,
                    api_id=log.api_id,
                    test_case_id=log.test_case_id,
                    thread_id=log.thread_id,
                    algorithm_type=log.algorithm_type,
                )
            )

        # 将 db_max_id / reset_required 放入 data，前端据此判断是否需要重置增量基准
        payload = LogRefreshData(
            items=data_list,
            count=len(data_list),
            new_count=len(data_list),
            last_id=data_list[-1].id if data_list else req.last_id,
        )
        payload_dict = payload.model_dump(by_alias=True, exclude_none=True)
        payload_dict['db_max_id'] = db_max_id
        if req.last_id > db_max_id:
            payload_dict['reset_required'] = True
        return success_response(payload_dict)

    # 标记日志
    @staticmethod
    def mark_logs():
        req = LogMarkRequest.model_validate(request.get_json())
        if not req.log_ids:
            return error_response("缺少必要参数: log_ids")
        
        try:
            Log.query.filter(Log.id.in_(req.log_ids)).update({"mark": req.mark}, synchronize_session=False)
            db.session.commit()
            return success_response(None, f"已为 {len(req.log_ids)} 条日志添加标记: {req.mark}")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 清除日志
    @staticmethod
    def clear_logs():
        req = LogClearRequest.model_validate(request.get_json() or {})
        
        try:
            query = Log.query
            if req.before_datetime:
                query = query.filter(Log.time < datetime.fromisoformat(req.before_datetime))
            
            if req.keep_marked:
                query = query.filter(or_(Log.mark.is_(None), Log.mark == ''))
            
            count = query.delete(synchronize_session=False)
            db.session.commit()
            return success_response({"deletedCount": count}, f"已成功清除 {count} 条历史日志")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 导出日志
    @staticmethod
    def export_logs():
        req = LogExportRequest.model_validate(request.get_json() or {})
        
        query = Log.query
        if req.log_ids:
            query = query.filter(Log.id.in_(req.log_ids))
        else:
            # 使用请求参数中的过滤条件
            level = request.args.get('level')
            module = request.args.get('module')
            if level: query = query.filter_by(level=level)
            if module: query = query.filter(db.func.lower(Log.module) == module.lower())
            
        logs = query.order_by(Log.time.desc()).all()
        
        export_data = []
        for log in logs:
            export_data.append({
                "ID": log.id,
                "Time": log.time.isoformat(),
                "Level": log.level,
                "Module": log.module,
                "Content": log.content,
                "Mark": log.mark or ""
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
        
        return send_file(file_path, as_attachment=True)

    # --- WebSocket 实时日志处理 ---

    @staticmethod
    def handle_connect():
        """处理 WebSocket 连接，初始化该 sid 的过滤器为空（接收全部日志）"""
        from flask_socketio import request as sio_request
        sid = getattr(sio_request, 'sid', None)
        if sid:
            log_filter_registry.set_filter(sid, {})
        log_not_emit('INFO', 'log_controller', f'Client connected to Log WebSocket sid={sid}', category='system')
        emit('status', {'type': 'STATUS', 'data': {'isMonitoring': True, 'message': 'Connected to Log Server'}})

    @staticmethod
    def handle_disconnect():
        """处理 WebSocket 断开连接，清理该 sid 的过滤器与任务订阅"""
        from flask_socketio import request as sio_request
        sid = getattr(sio_request, 'sid', None)
        if sid:
            log_filter_registry.remove(sid)
        log_not_emit('INFO', 'log_controller', f'Client disconnected from Log WebSocket sid={sid}', category='system')

    @staticmethod
    def handle_set_filter(data):
        """设置当前连接的日志过滤配置，服务端按此过滤再推送"""
        from flask_socketio import request as sio_request
        sid = getattr(sio_request, 'sid', None)
        if not sid:
            return
        # 规范化字段，缺失视为不过滤
        filt = {
            'levels': data.get('levels') or [],
            'modules': data.get('modules') or [],
            'keyword': data.get('keyword') or '',
            'task_id': data.get('task_id'),
        }
        log_filter_registry.set_filter(sid, filt)
        log_not_emit('INFO', 'log_controller', f'Filter updated sid={sid}: {filt}', category='system')
        emit('status', {'type': 'FILTER_APPLIED', 'data': filt})

    @staticmethod
    def handle_subscribe_task(data):
        """订阅指定 task 的日志房间。data: { "task_id": 123 }"""
        from flask_socketio import request as sio_request
        sid = getattr(sio_request, 'sid', None)
        if not sid:
            return
        task_id = data.get('task_id')
        if task_id is None:
            emit('status', {'type': 'ERROR', 'data': {'message': 'task_id required'}})
            return
        room = f'task_{task_id}'
        join_room(room)
        log_filter_registry.subscribe_task(sid, task_id)
        emit('status', {'type': 'SUBSCRIBED', 'data': {'task_id': task_id, 'room': room}})

    @staticmethod
    def handle_unsubscribe_task(data):
        """取消订阅 task 房间。"""
        from flask_socketio import request as sio_request
        sid = getattr(sio_request, 'sid', None)
        if not sid:
            return
        task_id = data.get('task_id')
        if task_id is not None:
            leave_room(f'task_{task_id}')
        log_filter_registry.unsubscribe_task(sid)
        emit('status', {'type': 'UNSUBSCRIBED', 'data': {'task_id': task_id}})

    @staticmethod
    def get_archive_status():
        try:
            # OSS: 列出 archives bucket 下各前缀的文件数
            task_keys = oss.list_objects('archives', prefix='tasks/')
            case_keys = oss.list_objects('archives', prefix='cases/')
            other_keys = oss.list_objects('archives', prefix='other/')

            task_count = len([k for k in task_keys if k.endswith('.json')])
            case_count = len([k for k in case_keys if k.endswith('.json')])
            other_count = len([k for k in other_keys if k.endswith('.json')])

            total_logs = db.session.query(func.count(Log.id)).scalar() or 0

            cutoff_date = now_cst() - timedelta(days=7)
            hot_logs = db.session.query(func.count(Log.id)).filter(Log.time >= cutoff_date).scalar() or 0
            cold_logs = total_logs - hot_logs

            return success_response({
                "total_logs": total_logs,
                "hot_logs": hot_logs,
                "cold_logs": cold_logs,
                "archive_dir": "oss://archives",
                "task_archives": task_count,
                "case_archives": case_count,
                "other_archives": other_count
            })
        except Exception as e:
            return error_response(f"获取归档状态失败: {str(e)}", code=500)

    @staticmethod
    def get_archived_logs():
        task_id = request.args.get('task_id', type=int)
        test_case_id = request.args.get('test_case_id')

        if not task_id and not test_case_id:
            return error_response("需要提供 task_id 或 test_case_id 参数", code=400)

        try:
            logs = []

            def load_oss_json_files(prefix):
                """从 OSS archives bucket 读取指定前缀下所有 JSON 文件"""
                result = []
                keys = oss.list_objects('archives', prefix=prefix)
                for key in keys:
                    if not key.endswith('.json'):
                        continue
                    try:
                        data = oss.download_bytes('archives', key)
                        result.extend(json.loads(data))
                    except Exception:
                        continue
                return result

            if task_id:
                if test_case_id:
                    # tasks/{task_id}/{case_id}/*.json
                    prefix = f'tasks/{task_id}/{test_case_id}/'
                    logs.extend(load_oss_json_files(prefix))
                else:
                    # tasks/{task_id}/*.json + tasks/{task_id}/*/*.json
                    prefix = f'tasks/{task_id}/'
                    keys = oss.list_objects('archives', prefix=prefix)
                    for key in keys:
                        if not key.endswith('.json'):
                            continue
                        try:
                            data = oss.download_bytes('archives', key)
                            logs.extend(json.loads(data))
                        except Exception:
                            continue

            if test_case_id and not task_id:
                prefix = f'cases/{test_case_id}/'
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

    @staticmethod
    def archive_logs():
        req = LogArchiveRequest.model_validate(request.get_json() or {})
        
        try:
            cutoff_date = now_cst() - timedelta(days=req.days)
            
            cold_logs_query = Log.query.filter(Log.time < cutoff_date)
            cold_count = cold_logs_query.count()
            
            if req.dry_run:
                return success_response({
                    "message": f"将归档 {cold_count} 条日志（{req.days}天前的数据）",
                    "cold_logs_count": cold_count,
                    "cutoff_date": cutoff_date.isoformat()
                })
            
            if cold_count == 0:
                return success_response(LogArchiveResult(
                    archived_count=0,
                    deleted_count=0,
                    archive_file=None,
                    remaining_count=db.session.query(func.count(Log.id)).scalar() or 0
                ), "没有需要归档的日志")
            
            # OSS: 归档到 archives bucket
            # 结构: tasks/{task_id}/{case_id}/{date}.json
            #       tasks/{task_id}/{date}.json
            #       cases/{case_id}/{date}.json
            #       other/{date}.json

            cold_logs = cold_logs_query.order_by(Log.time.asc()).all()

            task_case_logs = {}
            task_only_logs = {}
            case_only_logs = {}
            other_logs = {}
            
            for log in cold_logs:
                log_data = {
                    'id': log.id,
                    'time': log.time.isoformat() if log.time else None,
                    'level': log.level,
                    'category': log.category,
                    'module': log.module,
                    'source': log.source,
                    'content': log.content,
                    'mark': log.mark,
                    'device_id': log.device_id,
                    'task_id': log.task_id,
                    'test_case_id': log.test_case_id,
                    'api_id': log.api_id,
                    'thread_id': log.thread_id,
                    'algorithm_type': log.algorithm_type,
                    'created_at': log.created_at.isoformat() if log.created_at else None
                }
                
                log_date = (log.time or log.created_at or datetime.now()).strftime('%Y-%m-%d')
                
                if log.task_id and log.test_case_id:
                    key = (log.task_id, log.test_case_id, log_date)
                    if key not in task_case_logs:
                        task_case_logs[key] = []
                    task_case_logs[key].append(log_data)
                elif log.task_id:
                    key = (log.task_id, log_date)
                    if key not in task_only_logs:
                        task_only_logs[key] = []
                    task_only_logs[key].append(log_data)
                elif log.test_case_id:
                    key = (log.test_case_id, log_date)
                    if key not in case_only_logs:
                        case_only_logs[key] = []
                    case_only_logs[key].append(log_data)
                else:
                    if log_date not in other_logs:
                        other_logs[log_date] = []
                    other_logs[log_date].append(log_data)
            
            archived_count = 0

            def save_archive_oss(oss_key, logs):
                """上传归档到 OSS（合并已存在的）"""
                existing_logs = []
                if oss.exists('archives', oss_key):
                    try:
                        data = oss.download_bytes('archives', oss_key)
                        existing_logs = json.loads(data)
                    except Exception:
                        existing_logs = []
                existing_logs.extend(logs)
                existing_logs.sort(key=lambda x: x.get('time', '') or '')
                oss.upload_bytes(
                    json.dumps(existing_logs, ensure_ascii=False, indent=2).encode('utf-8'),
                    'archives', oss_key, content_type='application/json'
                )

            for (task_id, case_id, log_date), logs in task_case_logs.items():
                oss_key = f'tasks/{task_id}/{case_id}/{log_date}.json'
                save_archive_oss(oss_key, logs)
                archived_count += len(logs)

            for (task_id, log_date), logs in task_only_logs.items():
                oss_key = f'tasks/{task_id}/{log_date}.json'
                save_archive_oss(oss_key, logs)
                archived_count += len(logs)

            for (case_id, log_date), logs in case_only_logs.items():
                oss_key = f'cases/{case_id}/{log_date}.json'
                save_archive_oss(oss_key, logs)
                archived_count += len(logs)

            for log_date, logs in other_logs.items():
                oss_key = f'other/{log_date}.json'
                save_archive_oss(oss_key, logs)
                archived_count += len(logs)
            
            log_ids = [log.id for log in cold_logs]
            Log.query.filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            remaining_count = db.session.query(func.count(Log.id)).scalar() or 0
            
            return success_response(LogArchiveResult(
                archived_count=archived_count,
                deleted_count=len(log_ids),
                archive_file=None,
                remaining_count=remaining_count
            ), f"成功归档 {archived_count} 条日志 (任务用例: {len(task_case_logs)}, 任务: {len(task_only_logs)}, 用例: {len(case_only_logs)}, 其他: {len(other_logs)})")
            
        except Exception as e:
            db.session.rollback()
            return error_response(f"归档失败: {str(e)}", code=500)

    @staticmethod
    def download_archive(filename):
        try:
            # OSS: 在 archives bucket 中搜索匹配的文件
            all_keys = oss.list_objects('archives')
            matching_keys = [k for k in all_keys if k.endswith(f'/{filename}') or k == filename]

            if not matching_keys:
                return error_response("归档文件不存在", code=404)

            # 下载到临时文件再返回
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
            oss.download_file('archives', matching_keys[0], tmp.name)
            return send_file(tmp.name, as_attachment=True, download_name=filename)
        except Exception as e:
            return error_response(f"下载失败: {str(e)}", code=500)

    @staticmethod
    def delete_archive(filename):
        try:
            # OSS: 在 archives bucket 中搜索并删除
            all_keys = oss.list_objects('archives')
            matching_keys = [k for k in all_keys if k.endswith(f'/{filename}') or k == filename]

            if not matching_keys:
                return error_response("归档文件不存在", code=404)

            oss.delete('archives', matching_keys[0])
            return success_response(None, f"已删除归档文件: {filename}")
        except Exception as e:
            return error_response(f"删除失败: {str(e)}", code=500)
