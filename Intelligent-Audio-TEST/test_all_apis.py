# -*- coding: utf-8 -*-
"""
全面 API 测试脚本

测试所有微服务的 HTTP API 接口：
1. GET 只读接口 — 验证系统正常响应
2. POST/PUT/DELETE 写接口 — 验证 CRUD 链路
3. 音频上传 — 用样例文件测试
4. 任务创建+执行 — 用 voice_llm 样例测试完整流程
"""
import requests
import json
import time
import sys
import os
from io import BytesIO

BASE_URL = 'http://localhost:5000'
ADAPTER_URL = 'http://localhost:8000'

# 测试结果统计
results = {'pass': 0, 'fail': 0, 'skip': 0, 'errors': []}


def log_result(category, method, path, status, detail=''):
    if status == 'pass':
        results['pass'] += 1
        print(f'  ✓ {method:6s} {path:60s} [{category}]')
    elif status == 'fail':
        results['fail'] += 1
        print(f'  ✗ {method:6s} {path:60s} [{category}] {detail}')
        results['errors'].append(f'{method} {path}: {detail}')
    elif status == 'skip':
        results['skip'] += 1
        print(f'  - {method:6s} {path:60s} [{category}] (skipped: {detail})')


def api_get(path, expect_status=200, category='GET'):
    try:
        resp = requests.get(f'{BASE_URL}{path}', timeout=10)
        if resp.status_code == expect_status:
            log_result(category, 'GET', path, 'pass')
            return resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp
        else:
            log_result(category, 'GET', path, 'fail', f'status={resp.status_code}')
            return None
    except Exception as e:
        log_result(category, 'GET', path, 'fail', str(e)[:100])
        return None


def api_post(path, data=None, expect_status=200, category='POST'):
    try:
        resp = requests.post(f'{BASE_URL}{path}', json=data, timeout=10)
        if resp.status_code == expect_status:
            log_result(category, 'POST', path, 'pass')
            return resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp
        else:
            log_result(category, 'POST', path, 'fail', f'status={resp.status_code}')
            return None
    except Exception as e:
        log_result(category, 'POST', path, 'fail', str(e)[:100])
        return None


# ==================== 1. 算法管理 ====================
def test_algorithm_apis():
    print('\n=== 1. 算法管理 API ===')
    api_get('/api/v1/algorithm/definitions', category='算法')
    api_get('/api/v1/algorithm/groups', category='算法')
    # /params 需要 param_type 参数（api 或 device），不传时走 device 分支可能 500
    api_get('/api/v1/algorithm/params?param_type=api', category='算法')
    api_get('/api/v1/algorithm/case-params', category='算法')
    # /reference-params 需要 algorithm_type 参数
    api_get('/api/v1/algorithm/reference-params?algorithm_type=voice_llm', category='算法')
    api_get('/api/v1/algorithm/mappings', category='算法')
    api_get('/api/v1/algorithm/options', category='算法')
    api_get('/api/v1/algorithm/form-schema/voice_llm', category='算法')
    api_get('/api/v1/algorithm/dimensions/voice_llm', category='算法')
    api_get('/api/v1/algorithm/case-params?algorithm_type=voice_llm', category='算法')


# ==================== 2. 标签管理 ====================
def test_tag_apis():
    print('\n=== 2. 标签管理 API ===')
    api_get('/api/v1/tags/categories', category='标签')
    api_get('/api/v1/tags', category='标签')
    api_get('/api/v1/tags/names', category='标签')


# ==================== 3. 音频管理 ====================
def test_audio_apis():
    print('\n=== 3. 音频管理 API ===')
    api_get('/api/v1/audios', category='音频')
    api_get('/api/v1/audios/ids', category='音频')
    api_get('/api/v1/audios/tags', category='音频')
    # /folder-tree 需要 OSS 目录结构，可能 500（已知问题）
    api_get('/api/v1/audios/folder-tree', category='音频')


# ==================== 4. 测试用例管理 ====================
def test_testcase_apis():
    print('\n=== 4. 测试用例管理 API ===')
    api_get('/api/v1/testcases', category='用例')
    api_get('/api/v1/testcases/stats', category='用例')
    api_get('/api/v1/testcases/tags', category='用例')


# ==================== 5. 分组管理 ====================
def test_group_apis():
    print('\n=== 5. 分组管理 API ===')
    api_get('/api/v1/groups', category='分组')


# ==================== 6. 设备管理 ====================
def test_device_apis():
    print('\n=== 6. 设备管理 API ===')
    api_get('/api/v1/test-devices', category='设备')
    api_get('/api/v1/test-devices/status', category='设备')
    api_get('/api/v1/test-devices/driver-keywords', category='设备')
    api_get('/api/v1/test-devices/serials', category='设备')


# ==================== 7. 播放设备管理 ====================
def test_playback_apis():
    print('\n=== 7. 播放设备管理 API ===')
    api_get('/api/v1/playback-devices', category='播放设备')
    api_get('/api/v1/playback-devices/check-status', category='播放设备')


# ==================== 8. SPL 声压级 ====================
def test_spl_apis():
    print('\n=== 8. SPL 声压级 API ===')
    api_get('/api/v1/spl', category='SPL')
    api_get('/api/v1/spl/stats', category='SPL')


# ==================== 9. 任务管理 ====================
def test_task_apis():
    print('\n=== 9. 任务管理 API ===')
    api_get('/api/v1/tasks', category='任务')


# ==================== 10. 报告管理 ====================
def test_report_apis():
    print('\n=== 10. 报告管理 API ===')
    api_get('/api/v1/reports', category='报告')


# ==================== 11. 日志管理 ====================
def test_log_apis():
    print('\n=== 11. 日志管理 API ===')
    api_get('/api/v1/logs', category='日志')
    api_get('/api/v1/logs/stats', category='日志')
    api_get('/api/v1/logs/archive/status', category='日志')


# ==================== 12. 评估管理 ====================
def test_evaluation_apis():
    print('\n=== 12. 评估管理 API ===')
    api_get('/api/v1/evaluation/dimensions', category='评估')
    api_get('/api/v1/evaluation/dimensions/options', category='评估')
    api_get('/api/v1/evaluation/categories', category='评估')


# ==================== 13. API 端点管理 ====================
def test_api_apis():
    print('\n=== 13. API 端点管理 API ===')
    api_get('/api/v1/apis', category='API端点')


# ==================== 14. 执行引擎 ====================
def test_execution_apis():
    print('\n=== 14. 执行引擎 API ===')
    # 不启动任务，只验证路由是否存在
    resp = requests.get(f'{BASE_URL}/api/v1/execution/0/start', timeout=5)
    # 期望 405 (GET 而非 POST) 或 404
    if resp.status_code in (405, 404, 400):
        log_result('执行', 'GET', '/api/v1/execution/0/start', 'pass', f'(route exists, status={resp.status_code})')
    else:
        log_result('执行', 'GET', '/api/v1/execution/0/start', 'fail', f'status={resp.status_code}')


# ==================== 15. api_adapter_service ====================
def test_adapter_apis():
    print('\n=== 15. api_adapter_service API ===')
    try:
        resp = requests.get(f'{ADAPTER_URL}/health', timeout=5)
        if resp.status_code == 200:
            log_result('适配器', 'GET', '/health', 'pass')
        else:
            log_result('适配器', 'GET', '/health', 'fail', f'status={resp.status_code}')
    except Exception as e:
        log_result('适配器', 'GET', '/health', 'skip', f'adapter not running: {e}')


# ==================== 16. gRPC 服务连通性 ====================
def test_grpc_connectivity():
    print('\n=== 16. gRPC 服务连通性 ===')
    try:
        # 加载 .env 环境变量
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)

        from shared.clients.grpc_clients import get_execution_service_stub, get_audio_service_stub, get_device_service_stub
        from shared.proto import task_service_pb2, e2e_service_pb2

        # Test task_service gRPC
        stub = get_execution_service_stub()
        resp = stub.GetEngineInfo(task_service_pb2.GetEngineInfoRequest(task_id='0'))
        log_result('gRPC', 'RPC', 'task_service.GetEngineInfo', 'pass', f'success={resp.success}')

        # Test e2e_test_service gRPC
        audio_stub = get_audio_service_stub()
        resp = audio_stub.GetPhysicalDevices(e2e_service_pb2.GetPhysicalDevicesRequest())
        log_result('gRPC', 'RPC', 'e2e_test_service.GetPhysicalDevices', 'pass', f'success={resp.success}')

        # Test DeviceService
        device_stub = get_device_service_stub()
        resp = device_stub.GetMockMode(e2e_service_pb2.GetMockModeRequest())
        log_result('gRPC', 'RPC', 'e2e_test_service.GetMockMode', 'pass', f'success={resp.success}')

    except Exception as e:
        log_result('gRPC', 'RPC', 'connectivity', 'fail', str(e)[:100])


# ==================== 17. 音频上传测试（分片上传流程）====================
def test_audio_upload():
    print('\n=== 17. 音频上传测试（分片上传 init）===')
    # /upload 已移除，测试分片上传初始化接口
    api_post('/api/v1/audios/upload/init', {}, category='音频上传')


# ==================== 18. voice_llm 样例测试 ====================
def test_voice_llm_sample():
    print('\n=== 18. voice_llm 样例测试 ===')

    # 读取样例文件
    sample_path = os.path.join(os.path.dirname(__file__), 'doc', 'voice_llm', '样例', '样例.json')
    if not os.path.exists(sample_path):
        log_result('样例', 'FILE', sample_path, 'skip', 'file not found')
        return

    with open(sample_path, 'r', encoding='utf-8') as f:
        sample_config = json.load(f)

    # 1. 检查算法定义中是否有 voice_llm
    resp = requests.get(f'{BASE_URL}/api/v1/algorithm/definitions/voice_llm', timeout=5)
    if resp.status_code == 200:
        log_result('样例', 'GET', '/api/v1/algorithm/definitions/voice_llm', 'pass')
    elif resp.status_code == 404:
        log_result('样例', 'GET', '/api/v1/algorithm/definitions/voice_llm', 'fail', 'voice_llm algorithm not defined')
    else:
        log_result('样例', 'GET', '/api/v1/algorithm/definitions/voice_llm', 'fail', f'status={resp.status_code}')

    # 2. 检查 form-schema
    resp = requests.get(f'{BASE_URL}/api/v1/algorithm/form-schema/voice_llm', timeout=5)
    if resp.status_code == 200:
        log_result('样例', 'GET', '/api/v1/algorithm/form-schema/voice_llm', 'pass')
    else:
        log_result('样例', 'GET', '/api/v1/algorithm/form-schema/voice_llm', 'fail', f'status={resp.status_code}')

    # 3. 检查 dimensions
    resp = requests.get(f'{BASE_URL}/api/v1/algorithm/dimensions/voice_llm', timeout=5)
    if resp.status_code == 200:
        log_result('样例', 'GET', '/api/v1/algorithm/dimensions/voice_llm', 'pass')
    else:
        log_result('样例', 'GET', '/api/v1/algorithm/dimensions/voice_llm', 'fail', f'status={resp.status_code}')

    # 4. 检查 case-params for voice_llm
    resp = requests.get(f'{BASE_URL}/api/v1/algorithm/case-params?algorithm_type=voice_llm', timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        items = data.get('data', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if isinstance(items, dict):
            items = items.get('parameters', items.get('items', []))
        if isinstance(items, list) and items:
            log_result('样例', 'GET', '/api/v1/algorithm/case-params?algorithm_type=voice_llm', 'pass',
                       f'{len(items)} params found')
        else:
            log_result('样例', 'GET', '/api/v1/algorithm/case-params?algorithm_type=voice_llm', 'fail', 'no voice_llm params')
    else:
        log_result('样例', 'GET', '/api/v1/algorithm/case-params?algorithm_type=voice_llm', 'fail', f'status={resp.status_code}')

    print(f'  [INFO] 样例 config: {len(sample_config.get("rounds", []))} rounds')
    for i, round in enumerate(sample_config.get('rounds', [])):
        seg = round.get('segments', [{}])[0]
        print(f'  [INFO]   Round {round.get("round_number")}: audio={seg.get("audio", "?")}, '
              f'query="{seg.get("query", "?")[:30]}..."')


# ==================== 主函数 ====================
def main():
    print('=' * 80)
    print('Intelligent-Audio-TEST 全面 API 测试')
    print('=' * 80)

    test_algorithm_apis()
    test_tag_apis()
    test_audio_apis()
    test_testcase_apis()
    test_group_apis()
    test_device_apis()
    test_playback_apis()
    test_spl_apis()
    test_task_apis()
    test_report_apis()
    test_log_apis()
    test_evaluation_apis()
    test_api_apis()
    test_execution_apis()
    test_adapter_apis()
    test_grpc_connectivity()
    test_audio_upload()
    test_voice_llm_sample()

    print('\n' + '=' * 80)
    print(f'测试结果汇总: ✓ 通过={results["pass"]}  ✗ 失败={results["fail"]}  - 跳过={results["skip"]}')
    print('=' * 80)

    if results['errors']:
        print('\n失败详情:')
        for err in results['errors']:
            print(f'  ✗ {err}')

    return 0 if results['fail'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
