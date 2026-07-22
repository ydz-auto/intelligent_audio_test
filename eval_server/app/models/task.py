# -*- coding: utf-8 -*-
"""基于文件的任务与端点存储（替代 SQLite）。

任务文件按日分文件夹存放，一个 task_id 一个 JSON 文件：
    database/tasks/2026-06-25/task_xxx.json

端点配置统一存放在：
    database/endpoints.json
"""

import os
import json
import threading
from datetime import datetime
from ..config import config


class TaskModel:
    _lock = threading.Lock()          # 任务文件读写锁
    _endpoint_lock = threading.Lock() # 端点文件读写锁

    # ------------------------------------------------------------------
    #  内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_dirs():
        """确保存储目录存在"""
        os.makedirs(config.TASKS_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(config.ENDPOINTS_FILE), exist_ok=True)

    @staticmethod
    def _get_today_dir():
        """获取今日文件夹路径，不存在则创建"""
        today = datetime.now().strftime('%Y-%m-%d')
        dir_path = os.path.join(config.TASKS_DIR, today)
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    @staticmethod
    def _get_task_path(eval_task_id):
        """在所有日文件夹中查找任务文件，返回路径或 None"""
        if not os.path.exists(config.TASKS_DIR):
            return None
        for day_folder in sorted(os.listdir(config.TASKS_DIR), reverse=True):
            day_path = os.path.join(config.TASKS_DIR, day_folder)
            if not os.path.isdir(day_path):
                continue
            task_path = os.path.join(day_path, f'{eval_task_id}.json')
            if os.path.exists(task_path):
                return task_path
        return None

    @staticmethod
    def _write_json(filepath, data):
        """原子写入 JSON：先写 .tmp 再 rename，防止写一半崩溃"""
        tmp_path = f'{filepath}.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    @staticmethod
    def _read_json(filepath):
        """读取 JSON 文件"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    # ------------------------------------------------------------------
    #  初始化
    # ------------------------------------------------------------------

    @staticmethod
    def init_db():
        """初始化存储目录（替代原 SQLite init_db）"""
        TaskModel._ensure_dirs()
        if not os.path.exists(config.ENDPOINTS_FILE):
            TaskModel._write_json(config.ENDPOINTS_FILE, [])

    # ------------------------------------------------------------------
    #  任务 CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def create_task(eval_task_id, task_type='wer', source_lang=None, target_lang=None,
                    translate_direct=None, asr_ref=None, asr_hyp=None,
                    task_params=None, endpoints=None, endpoint_url=None, task_id=None):
        """创建任务文件，状态固定为 pending"""
        today_dir = TaskModel._get_today_dir()
        task_path = os.path.join(today_dir, f'{eval_task_id}.json')
        task_data = {
            'eval_task_id': eval_task_id,
            'task_id': task_id,
            'task_type': task_type,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct,
            'asr_ref': asr_ref,
            'asr_hyp': asr_hyp,
            'task_params': task_params,
            'status': 'pending',
            'result': None,
            'error_msg': None,
            'endpoints': endpoints,
            'endpoint_url': endpoint_url,
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
        }
        with TaskModel._lock:
            TaskModel._write_json(task_path, task_data)
        return eval_task_id

    @staticmethod
    def get_task(eval_task_id):
        """按 eval_task_id 读取任务，返回 dict 或 None"""
        with TaskModel._lock:
            task_path = TaskModel._get_task_path(eval_task_id)
            if not task_path:
                return None
            return TaskModel._read_json(task_path)

    @staticmethod
    def update_task_status(eval_task_id, status, started_at=None, completed_at=None,
                           result=None, error_msg=None):
        """更新任务状态及可选字段"""
        with TaskModel._lock:
            task_path = TaskModel._get_task_path(eval_task_id)
            if not task_path:
                return False
            task_data = TaskModel._read_json(task_path)
            task_data['status'] = status
            if started_at is not None:
                task_data['started_at'] = started_at
            if completed_at is not None:
                task_data['completed_at'] = completed_at
            if result is not None:
                task_data['result'] = result
            if error_msg is not None:
                task_data['error_msg'] = error_msg
            TaskModel._write_json(task_path, task_data)
            return True

    @staticmethod
    def delete_task(eval_task_id):
        """删除任务文件"""
        with TaskModel._lock:
            task_path = TaskModel._get_task_path(eval_task_id)
            if not task_path:
                return False
            os.remove(task_path)
            return True

    @staticmethod
    def get_pending_tasks():
        """扫描所有日文件夹，返回 status=pending 且 endpoint_url 为空的本地任务"""
        result = []
        with TaskModel._lock:
            if not os.path.exists(config.TASKS_DIR):
                return result
            for day_folder in sorted(os.listdir(config.TASKS_DIR), reverse=True):
                day_path = os.path.join(config.TASKS_DIR, day_folder)
                if not os.path.isdir(day_path):
                    continue
                for filename in os.listdir(day_path):
                    if not filename.endswith('.json'):
                        continue
                    filepath = os.path.join(day_path, filename)
                    try:
                        task_data = TaskModel._read_json(filepath)
                        if task_data.get('status') == 'pending' and not task_data.get('endpoint_url'):
                            result.append(task_data)
                    except (json.JSONDecodeError, OSError):
                        continue
        return result

    @staticmethod
    def reset_processing_tasks():
        """服务重启后将所有 processing 状态的任务重置为 pending，避免任务永久卡死"""
        count = 0
        with TaskModel._lock:
            if not os.path.exists(config.TASKS_DIR):
                return 0
            for day_folder in sorted(os.listdir(config.TASKS_DIR), reverse=True):
                day_path = os.path.join(config.TASKS_DIR, day_folder)
                if not os.path.isdir(day_path):
                    continue
                for filename in os.listdir(day_path):
                    if not filename.endswith('.json'):
                        continue
                    filepath = os.path.join(day_path, filename)
                    try:
                        task_data = TaskModel._read_json(filepath)
                        if task_data.get('status') == 'processing':
                            task_data['status'] = 'pending'
                            task_data['started_at'] = None
                            TaskModel._write_json(filepath, task_data)
                            count += 1
                    except (json.JSONDecodeError, OSError):
                        continue
        return count

    # ------------------------------------------------------------------
    #  端点配置 CRUD（统一存放在 endpoints.json）
    # ------------------------------------------------------------------

    @staticmethod
    def _load_endpoints():
        if not os.path.exists(config.ENDPOINTS_FILE):
            return []
        return TaskModel._read_json(config.ENDPOINTS_FILE)

    @staticmethod
    def _save_endpoints(endpoints):
        TaskModel._write_json(config.ENDPOINTS_FILE, endpoints)

    @staticmethod
    def create_endpoint(url, name=None, capabilities=None, task_types=None, max_process=1):
        """创建或覆盖端点配置"""
        with TaskModel._endpoint_lock:
            endpoints = TaskModel._load_endpoints()
            # 同 URL 覆盖
            endpoints = [ep for ep in endpoints if ep.get('url') != url]
            endpoints.append({
                'url': url,
                'name': name,
                'capabilities': capabilities,
                'task_types': task_types,
                'max_process': max_process,
                'updated_at': datetime.now().isoformat(),
            })
            TaskModel._save_endpoints(endpoints)
        return url

    @staticmethod
    def get_endpoint(url):
        with TaskModel._endpoint_lock:
            for ep in TaskModel._load_endpoints():
                if ep.get('url') == url:
                    return ep
            return None

    @staticmethod
    def update_endpoint(url, name=None, capabilities=None, task_types=None, max_process=None):
        with TaskModel._endpoint_lock:
            endpoints = TaskModel._load_endpoints()
            for ep in endpoints:
                if ep.get('url') == url:
                    if name is not None:
                        ep['name'] = name
                    if capabilities is not None:
                        ep['capabilities'] = capabilities
                    if task_types is not None:
                        ep['task_types'] = task_types
                    if max_process is not None:
                        ep['max_process'] = max_process
                    ep['updated_at'] = datetime.now().isoformat()
                    TaskModel._save_endpoints(endpoints)
                    return True
            return False

    @staticmethod
    def delete_endpoint(url):
        with TaskModel._endpoint_lock:
            endpoints = TaskModel._load_endpoints()
            filtered = [ep for ep in endpoints if ep.get('url') != url]
            if len(filtered) < len(endpoints):
                TaskModel._save_endpoints(filtered)
                return True
            return False

    @staticmethod
    def get_all_endpoints():
        with TaskModel._endpoint_lock:
            return TaskModel._load_endpoints()

    @staticmethod
    def update_endpoint_concurrency(url, task_type, max_process):
        """更新指定端点对特定任务类型的并发限制"""
        with TaskModel._endpoint_lock:
            endpoints = TaskModel._load_endpoints()
            for ep in endpoints:
                if ep.get('url') == url:
                    capabilities = ep.get('capabilities') or {}
                    capabilities.setdefault(task_type, {})
                    capabilities[task_type]['max_process'] = max_process
                    ep['capabilities'] = capabilities
                    ep['updated_at'] = datetime.now().isoformat()
                    TaskModel._save_endpoints(endpoints)
                    return True
            return False
