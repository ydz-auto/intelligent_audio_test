import os
import pandas as pd
import json
import glob
from flask import request, send_file
from backend.models.models import Log
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.schemas.log import LogItem, LogListData, LogRefreshData, LogRefreshRequest, LogMarkRequest, LogClearRequest, LogExportRequest, LogArchiveRequest, LogArchiveStatus, LogArchiveResult
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, or_
from flask_socketio import emit

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
            print(f"Error in get_logs: {str(e)}")
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
            
            from backend.schemas.log import LogStatsData
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
            print(f"Error in get_stats: {str(e)}")
            import traceback
            traceback.print_exc()
            return error_response(f"获取日志统计失败: {str(e)}", code=500)

    # 刷新日志 (手动同步新日志)
    @staticmethod
    def refresh_logs():
        req = LogRefreshRequest.model_validate(request.get_json() or {})
        new_logs = Log.query.filter(Log.id > req.last_id).order_by(Log.id.asc()).limit(100).all()
        
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
            
        return success_response(
            LogRefreshData(
                items=data_list,
                count=len(data_list),
                new_count=len(data_list),
                last_id=data_list[-1].id if data_list else req.last_id,
            )
        )

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
        """处理 WebSocket 连接"""
        # 可以添加 JWT 校验逻辑
        print("Client connected to Log WebSocket")
        emit('status', {'type': 'STATUS', 'data': {'isMonitoring': True, 'message': 'Connected to Log Server'}})

    @staticmethod
    def handle_disconnect():
        """处理 WebSocket 断开连接"""
        print("Client disconnected from Log WebSocket")

    @staticmethod
    def handle_set_filter(data):
        """设置日志过滤配置"""
        # data: { "levels": ["error"], "modules": ["TASK"] }
        # 实际应用中，过滤器状态应保存在 session 或连接上下文中
        print(f"Filter updated: {data}")
        emit('status', {'type': 'FILTER_APPLIED', 'data': data})

    @staticmethod
    def log_and_emit(level, module, content, category='system', source='backend', task_id=None, device_id=None, api_id=None, test_case_id=None, **kwargs):
        try:
            from backend.utils.log_handler import log_and_emit as handler_log_and_emit
            handler_log_and_emit(level, module, content, category, source, task_id, device_id, api_id, test_case_id, **kwargs)
        except Exception as e:
            import sys
            print(f"Error in log_controller.log_and_emit: {str(e)}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    @staticmethod
    def get_archive_status():
        try:
            archive_dir = os.path.join(os.getcwd(), 'archives')
            
            task_files = []
            case_files = []
            other_files = []
            
            task_dir = os.path.join(archive_dir, 'tasks')
            case_dir = os.path.join(archive_dir, 'cases')
            other_dir = os.path.join(archive_dir, 'other')
            
            if os.path.exists(task_dir):
                task_files = [os.path.basename(f) for f in glob.glob(os.path.join(task_dir, 'task_*.json'))]
            if os.path.exists(case_dir):
                case_files = [os.path.basename(f) for f in glob.glob(os.path.join(case_dir, 'case_*.json'))]
            if os.path.exists(other_dir):
                other_files = [os.path.basename(f) for f in glob.glob(os.path.join(other_dir, 'other_*.json'))]
            
            total_logs = db.session.query(func.count(Log.id)).scalar() or 0
            
            cutoff_date = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=7)
            hot_logs = db.session.query(func.count(Log.id)).filter(Log.time >= cutoff_date).scalar() or 0
            cold_logs = total_logs - hot_logs
            
            return success_response({
                "total_logs": total_logs,
                "hot_logs": hot_logs,
                "cold_logs": cold_logs,
                "archive_dir": archive_dir,
                "task_archives": len(task_files),
                "case_archives": len(case_files),
                "other_archives": len(other_files)
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
            archive_dir = os.path.join(os.getcwd(), 'archives')
            logs = []
            
            if task_id:
                archive_path = os.path.join(archive_dir, 'tasks', f"task_{task_id}.json")
                if os.path.exists(archive_path):
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        logs = json.load(f)
            
            if test_case_id:
                archive_path = os.path.join(archive_dir, 'cases', f"case_{test_case_id}.json")
                if os.path.exists(archive_path):
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        case_logs = json.load(f)
                        logs.extend(case_logs)
            
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
            cutoff_date = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=req.days)
            
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
            
            archive_dir = os.path.join(os.getcwd(), 'archives')
            task_dir = os.path.join(archive_dir, 'tasks')
            case_dir = os.path.join(archive_dir, 'cases')
            other_dir = os.path.join(archive_dir, 'other')
            
            for d in [archive_dir, task_dir, case_dir, other_dir]:
                if not os.path.exists(d):
                    os.makedirs(d)
            
            cold_logs = cold_logs_query.order_by(Log.time.asc()).all()
            
            task_logs = {}
            case_logs = {}
            other_logs = []
            
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
                
                if log.task_id:
                    if log.task_id not in task_logs:
                        task_logs[log.task_id] = []
                    task_logs[log.task_id].append(log_data)
                elif log.test_case_id:
                    if log.test_case_id not in case_logs:
                        case_logs[log.test_case_id] = []
                    case_logs[log.test_case_id].append(log_data)
                else:
                    other_logs.append(log_data)
            
            archived_count = 0
            
            for task_id, logs in task_logs.items():
                archive_path = os.path.join(task_dir, f"task_{task_id}.json")
                existing_logs = []
                if os.path.exists(archive_path):
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        existing_logs = json.load(f)
                
                existing_logs.extend(logs)
                existing_logs.sort(key=lambda x: x.get('time', '') or '')
                
                with open(archive_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                archived_count += len(logs)
            
            for case_id, logs in case_logs.items():
                archive_path = os.path.join(case_dir, f"case_{case_id}.json")
                existing_logs = []
                if os.path.exists(archive_path):
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        existing_logs = json.load(f)
                
                existing_logs.extend(logs)
                existing_logs.sort(key=lambda x: x.get('time', '') or '')
                
                with open(archive_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                archived_count += len(logs)
            
            if other_logs:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                archive_path = os.path.join(other_dir, f"other_{timestamp}.json")
                with open(archive_path, 'w', encoding='utf-8') as f:
                    json.dump(other_logs, f, ensure_ascii=False, indent=2)
                archived_count += len(other_logs)
            
            log_ids = [log.id for log in cold_logs]
            Log.query.filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            remaining_count = db.session.query(func.count(Log.id)).scalar() or 0
            
            return success_response(LogArchiveResult(
                archived_count=archived_count,
                deleted_count=len(log_ids),
                archive_file=None,
                remaining_count=remaining_count
            ), f"成功归档 {archived_count} 条日志 (任务: {len(task_logs)}, 用例: {len(case_logs)}, 其他: {len(other_logs)})")
            
        except Exception as e:
            db.session.rollback()
            return error_response(f"归档失败: {str(e)}", code=500)

    @staticmethod
    def download_archive(filename):
        try:
            archive_dir = os.path.join(os.getcwd(), 'archives')
            
            for subdir in ['', 'tasks', 'cases', 'other']:
                file_path = os.path.join(archive_dir, subdir, filename)
                if os.path.exists(file_path):
                    if not os.path.abspath(file_path).startswith(os.path.abspath(archive_dir)):
                        return error_response("非法的文件路径", code=400)
                    return send_file(file_path, as_attachment=True)
            
            return error_response("归档文件不存在", code=404)
        except Exception as e:
            return error_response(f"下载失败: {str(e)}", code=500)

    @staticmethod
    def delete_archive(filename):
        try:
            archive_dir = os.path.join(os.getcwd(), 'archives')
            
            for subdir in ['', 'tasks', 'cases', 'other']:
                file_path = os.path.join(archive_dir, subdir, filename)
                if os.path.exists(file_path):
                    if not os.path.abspath(file_path).startswith(os.path.abspath(archive_dir)):
                        return error_response("非法的文件路径", code=400)
                    os.remove(file_path)
                    return success_response(None, f"已删除归档文件: {filename}")
            
            return error_response("归档文件不存在", code=404)
        except Exception as e:
            return error_response(f"删除失败: {str(e)}", code=500)
