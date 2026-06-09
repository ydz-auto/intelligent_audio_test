import sqlite3
import json
from datetime import datetime
from ..config import config

class TaskModel:
    @staticmethod
    def get_db_connection():
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db():
        with open(config.SCHEMA_PATH, 'r', encoding='utf-8') as f:
            schema = f.read()
        
        with TaskModel.get_db_connection() as conn:
            conn.executescript(schema)
            conn.commit()

    @staticmethod
    def create_task(task_id, task_type='wer', source_lang=None, target_lang=None, translate_direct=None, 
                    asr_ref=None, asr_result=None, task_params=None, endpoints=None, endpoint_url=None):
        import json
        with TaskModel.get_db_connection() as conn:
            conn.execute(
                'INSERT INTO tasks (task_id, task_type, source_lang, target_lang, translate_direct, asr_ref, asr_result, task_params, status, endpoints, endpoint_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (task_id, task_type, source_lang, target_lang, translate_direct, asr_ref, asr_result, 
                 json.dumps(task_params) if task_params else None, 'pending', 
                 json.dumps(endpoints) if endpoints else None, endpoint_url)
            )
            conn.commit()
        return task_id

    @staticmethod
    def get_task(task_id):
        with TaskModel.get_db_connection() as conn:
            task = conn.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,)).fetchone()
            if task:
                task_dict = dict(task)
                if task_dict.get('task_params'):
                    task_dict['task_params'] = json.loads(task_dict['task_params'])
                return task_dict
            return None

    @staticmethod
    def update_task_status(task_id, status, started_at=None, completed_at=None, result=None, error_msg=None):
        query = 'UPDATE tasks SET status = ?'
        params = [status]
        
        if started_at:
            query += ', started_at = ?'
            params.append(started_at)
        if completed_at:
            query += ', completed_at = ?'
            params.append(completed_at)
        if result:
            query += ', result = ?'
            params.append(json.dumps(result))
        if error_msg:
            query += ', error_msg = ?'
            params.append(error_msg)
            
        query += ' WHERE task_id = ?'
        params.append(task_id)
        
        with TaskModel.get_db_connection() as conn:
            conn.execute(query, tuple(params))
            conn.commit()

    @staticmethod
    def delete_task(task_id):
        with TaskModel.get_db_connection() as conn:
            cursor = conn.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def get_pending_tasks():
        with TaskModel.get_db_connection() as conn:
            tasks = conn.execute("SELECT * FROM tasks WHERE status = 'pending' AND endpoint_url IS NULL").fetchall()
            result = []
            for t in tasks:
                task_dict = dict(t)
                if task_dict.get('task_params'):
                    task_dict['task_params'] = json.loads(task_dict['task_params'])
                result.append(task_dict)
            return result

    # 端点配置管理方法
    @staticmethod
    def create_endpoint(url, name=None, capabilities=None, task_types=None, max_process=1):
        with TaskModel.get_db_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO endpoints (url, name, capabilities, task_types, max_process, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                (url, name, json.dumps(capabilities) if capabilities else None, 
                 json.dumps(task_types) if task_types else None, max_process, datetime.now().isoformat())
            )
            conn.commit()
        return url

    @staticmethod
    def get_endpoint(url):
        with TaskModel.get_db_connection() as conn:
            endpoint = conn.execute('SELECT * FROM endpoints WHERE url = ?', (url,)).fetchone()
            if endpoint:
                endpoint_dict = dict(endpoint)
                # 解析JSON字段
                if endpoint_dict.get('capabilities'):
                    endpoint_dict['capabilities'] = json.loads(endpoint_dict['capabilities'])
                if endpoint_dict.get('task_types'):
                    endpoint_dict['task_types'] = json.loads(endpoint_dict['task_types'])
                return endpoint_dict
            return None

    @staticmethod
    def update_endpoint(url, name=None, capabilities=None, task_types=None, max_process=None):
        query = 'UPDATE endpoints SET updated_at = ?' 
        params = [datetime.now().isoformat()]
        
        if name is not None:
            query += ', name = ?'
            params.append(name)
        if capabilities is not None:
            query += ', capabilities = ?'
            params.append(json.dumps(capabilities))
        if task_types is not None:
            query += ', task_types = ?'
            params.append(json.dumps(task_types))
        if max_process is not None:
            query += ', max_process = ?'
            params.append(max_process)
        
        query += ' WHERE url = ?'
        params.append(url)
        
        with TaskModel.get_db_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def delete_endpoint(url):
        with TaskModel.get_db_connection() as conn:
            cursor = conn.execute('DELETE FROM endpoints WHERE url = ?', (url,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def get_all_endpoints():
        with TaskModel.get_db_connection() as conn:
            endpoints = conn.execute('SELECT * FROM endpoints').fetchall()
            result = []
            for ep in endpoints:
                ep_dict = dict(ep)
                if ep_dict.get('capabilities'):
                    ep_dict['capabilities'] = json.loads(ep_dict['capabilities'])
                if ep_dict.get('task_types'):
                    ep_dict['task_types'] = json.loads(ep_dict['task_types'])
                result.append(ep_dict)
            return result

    @staticmethod
    def update_endpoint_concurrency(url, task_type, max_process):
        """更新指定端点对特定任务类型的并发限制"""
        with TaskModel.get_db_connection() as conn:
            # 先获取现有配置
            endpoint = conn.execute('SELECT capabilities FROM endpoints WHERE url = ?', (url,)).fetchone()
            if endpoint:
                capabilities = json.loads(endpoint['capabilities']) if endpoint['capabilities'] else {}
            else:
                capabilities = {}
            
            # 更新并发限制
            capabilities[task_type] = capabilities.get(task_type, {})
            capabilities[task_type]['max_process'] = max_process
            
            # 更新数据库
            conn.execute(
                'UPDATE endpoints SET capabilities = ?, updated_at = ? WHERE url = ?',
                (json.dumps(capabilities), datetime.now().isoformat(), url)
            )
            conn.commit()
            return True
        return False
