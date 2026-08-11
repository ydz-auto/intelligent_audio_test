"""API Test Service 客户端"""
import requests

class APITestClient:
    def __init__(self, host, port=5003):
        self.base_url = f'http://{host}:{port}/internal'
    
    def start_task(self, task_id, case_ids, api_ids):
        r = requests.post(f'{self.base_url}/tasks/start',
            json={'task_id': task_id, 'case_ids': case_ids, 'api_ids': api_ids}, timeout=30)
        return r.json()
    
    def stop_task(self, task_id):
        r = requests.post(f'{self.base_url}/tasks/{task_id}/stop', timeout=10)
        return r.json()
    
    def get_task_status(self, task_id):
        r = requests.get(f'{self.base_url}/tasks/{task_id}/status', timeout=10)
        return r.json()
    
    def health_check(self):
        try:
            r = requests.get(f'{self.base_url}/health', timeout=5)
            return {'healthy': r.status_code == 200}
        except Exception:
            return {'healthy': False}
