# -*- coding: utf-8 -*-
"""INT-1645 网关层 404 状态映射实测：真实 gRPC 打到 docker task_service（旧代码）。"""
import json, sys

def main():
    from api_gateway.application.services.testcase import testcase_query_service as qs
    from api_gateway.application.services.testcase import testcase_command_service as cs

    case = 'd2b8a465-9f48-46f6-9624-7702e9ae2145'
    body, http_code = qs.TestCaseQueryService.get_ref_params(case, 1)
    print('GET body=', json.dumps(body, ensure_ascii=False), 'http_code=', http_code, flush=True)
    ok1 = (http_code == 404 and int(body.get('code', 0)) == 404)

    from types import SimpleNamespace
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(SimpleNamespace(
        state=SimpleNamespace(_json_body={'referenceParams': []}),
        query_params={}, method='PUT', headers={}))
    body2, http_code2 = cs.TestCaseCommandService.update_ref_params(case, 1)
    print('PUT body=', json.dumps(body2, ensure_ascii=False), 'http_code=', http_code2, flush=True)
    ok2 = (http_code2 == 404 and int(body2.get('code', 0)) == 404)

    print(('PASS' if ok1 and ok2 else 'FAIL') + ' 网关 GET/PUT 404 映射：HTTP 状态与 body code 同为 404', flush=True)
    return 0 if (ok1 and ok2) else 1

if __name__ == '__main__':
    sys.exit(main())
