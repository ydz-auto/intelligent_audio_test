# -*- coding: utf-8 -*-
"""INT-1806 验收端到端夹具（产生事件方隔离进程，非产品代码）。

扮演 api_gateway：走真实审计写入器 → 真实 log handler emit → 真实
`BatchCreateLogs` gRPC → 服务端进程落审计文件（H4）。同时发一条同 category
的设备运维日志（H1 反例）与一条预览日志（D2）。

环境变量：
    E2E_SERVER_LOG_ROOT   服务端日志根（轮询审计文件落盘进度）
    E2E_EXPECT_AUDIT      本次期望新增的审计行数
"""
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'shared', 'proto'))


def _count_audit_lines(root):
    total = 0
    for dirpath, _, names in os.walk(os.path.join(root, 'audit')):
        for name in names:
            if name.endswith('.jsonl'):
                with open(os.path.join(dirpath, name), encoding='utf-8') as handle:
                    total += sum(1 for _ in handle)
    return total


def _wait_for(condition, timeout=60.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


def main():
    server_root = os.environ['E2E_SERVER_LOG_ROOT']
    expected = int(os.environ['E2E_EXPECT_AUDIT'])
    mode = os.environ.get('E2E_CLIENT_MODE', 'gateway')

    from shared.utils.log_handler import get_db_handler
    handler = get_db_handler()
    handler._batch_size = 1
    handler._batch_timeout = 0.1

    before = _count_audit_lines(server_root)

    if mode == 'device_host':
        # 宿主机 device_service 真实审计入口（H4：落盘方仍是 task_service）
        from device_service.application.services.device_monitor_service import (
            DeviceMonitorService,
        )
        DeviceMonitorService._log_alarm_triggered({
            'id': 7001,
            'rule_id': 3,
            'rule_name': '温度过高',
            'device_id': 55,
            'device_name': '设备55',
            'metric_type': 'temperature',
            'severity': 'critical',
            'trigger_value': 99,
            'threshold_value': 80,
        })
        from shared.utils.log_handler import log_not_emit
        log_not_emit('INFO', 'DeviceGroupCommand', 'group command dispatched',
                     category='device', source='backend', device_id=5)
        from shared.utils.testcase_helpers import log as common_log
        common_log('INFO', 'case preview step done', test_case_id='TC-9',
                   category='preview')
        ok = _wait_for(lambda: _count_audit_lines(server_root) >= before + expected)
        print(json.dumps({
            'audit_before': before,
            'audit_after': _count_audit_lines(server_root),
            'expected_new': expected,
            'reached': ok,
        }, ensure_ascii=False))
        if not ok:
            sys.exit(3)
        return

    from shared.models.common_enums import AuditEvent
    from api_gateway.application.services.device.device_audit import write_device_audit
    from api_gateway.application.services.visibility.visibility_audit import (
        write_visibility_audit,
    )
    from auth_service.application.services.auth_audit import write_auth_audit
    from report_service.application.services.benchmark_audit import write_benchmark_audit
    from shared.utils.log_handler import log_not_emit
    from shared.utils.testcase_helpers import log as common_log

    # 4 条真实审计事件（auth / benchmark / device / visibility）
    write_auth_audit(AuditEvent.AUTH_LOGIN, 'auth_login', {
        'operator_id': 369,
        'operator': '接线测试_admin',
        'target_id': 369,
        'target_type': 'user',
        'action': 'login',
        'result': 'success',
    })
    write_benchmark_audit(AuditEvent.BENCHMARK_RANKING_COMPUTED,
                          'benchmark_ranking', {
                              'operator_id': 42,
                              'operator': 'e2e_admin',
                              'target_id': 8,
                              'target_type': 'report',
                              'action': 'compute',
                          })
    write_device_audit(AuditEvent.DEVICE_ALARM_TRIGGERED, 'device_alarm', {
        'operator_id': 43,
        'operator': 'e2e_ops',
        'target_id': 55,
        'target_type': 'device',
        'device_id': 55,
        'action': 'alarm',
    })
    write_visibility_audit(AuditEvent.PRIVATE_RESOURCE_ACCESS,
                           'visibility_access', {
                               'operator_id': 44,
                               'operator': 'e2e_guest',
                               'target_id': 12,
                               'target_type': 'task',
                               'action': 'read',
                               'result': 'denied',
                           })

    # H1 反例：同 category='device' 但无 audit_event 的设备运维日志
    log_not_emit('INFO', 'DeviceGroupCommand', 'group command dispatched',
                 category='device', source='backend', device_id=5)
    # D2：test_case_id 有值、无 task_id 的预览日志
    common_log('INFO', 'case preview step done', test_case_id='TC-9',
               category='preview')

    ok = _wait_for(lambda: _count_audit_lines(server_root) >= before + expected)
    print(json.dumps({
        'audit_before': before,
        'audit_after': _count_audit_lines(server_root),
        'expected_new': expected,
        'reached': ok,
    }, ensure_ascii=False))
    if not ok:
        sys.exit(3)


if __name__ == '__main__':
    main()
