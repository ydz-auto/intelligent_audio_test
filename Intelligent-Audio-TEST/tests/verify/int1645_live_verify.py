# -*- coding: utf-8 -*-
"""INT-1645 验收实测：worktree 代码 + docker 真实库/rustfs（一次性容器内运行）。

覆盖卡面 §八.2 / §八.3：
- 存量用例（Windows 绝对路径 → oss://ref_params/...）第 1/2 轮 GET 非空；
- 四种失败口径（未登记轮 / 有轮无路径 / 对象缺失 / 内容空数组）；
- config.rounds camel 兜底；
- PUT 闭环（400 / 404 / 无路径轮建规范 key / 列 upsert 不动其它轮 / 不回写 config /
  幂等 / 写后 GET 一致 / legacy 路径归一化后写入）；
- 可见性非回归（私有用例非 owner 读 404、写 403）。

写入只用自建「接线测试_INT1645_验收_*」用例；脚本结束硬删用例行与写入对象。
"""
from __future__ import annotations

import json
import sys
import uuid
from concurrent import futures

CASE_STOCK = 'd2b8a465-9f48-46f6-9624-7702e9ae2145'
LEGACY_PREFIX = r'D:\00_static\static\ref_params'
NAME_PREFIX = '接线测试_INT1645_验收_'

_results = []


def check(name, cond, detail=''):
    _results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL ') + name + (f' | {detail}' if detail else ''), flush=True)


def main() -> int:
    import grpc
    from shared.infrastructure.grpc_interceptors import (
        ServerDbScopeInterceptor, ServerUserContextInterceptor,
    )
    from shared.proto import task_service_pb2 as pb
    from shared.proto import task_service_pb2_grpc as pbg
    from task_service.interfaces.grpc.testcase_config import TestCaseConfigServiceServicer

    port = '127.0.0.1:51990'
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        interceptors=[ServerUserContextInterceptor(), ServerDbScopeInterceptor()],
    )
    pbg.add_TestCaseConfigServiceServicer_to_server(TestCaseConfigServiceServicer(), server)
    server.add_insecure_port(port)
    server.start()
    channel = grpc.insecure_channel(port)
    stub = pbg.TestCaseConfigServiceStub(channel)

    def get(tc_id, rnd, meta=()):
        resp = stub.GetTestCaseRefParams(
            pb.GetTestCaseRefParamsRequest(tc_id=tc_id, round_number=rnd), metadata=meta)
        return resp, (json.loads(resp.data) if resp.data else {})

    def put(tc_id, rnd, payload, meta=()):
        resp = stub.UpdateTestCaseRefParams(
            pb.UpdateTestCaseRefParamsRequest(
                tc_id=tc_id, round_number=rnd,
                data=json.dumps(payload, ensure_ascii=False),
            ), metadata=meta)
        return resp, (json.loads(resp.data) if resp.data else {})

    created_ids = []
    written_paths = []

    try:
        from shared.models.database import get_db_session, init_db
        from task_service.infrastructure.persistence.models.testcase_models import TestCase

        init_db(pool_size=5)
        db = get_db_session()

        def new_case(tag, config, ref_params=None, visibility='shared', owner=None):
            cid = str(uuid.uuid4())
            row = TestCase(
                id=cid, name=NAME_PREFIX + tag, config=config,
                reference_params=ref_params, visibility=visibility,
                created_by_user_id=owner,
            )
            db.add(row)
            db.commit()
            created_ids.append(cid)
            return cid

        # ---------- 1. 存量用例：Windows 绝对路径经归一化读到对象 ----------
        for rnd in (1, 2):
            resp, data = get(CASE_STOCK, rnd)
            check(f'存量用例 round={rnd} GET 200',
                  resp.success, resp.message)
            check(f'存量用例 round={rnd} path 归一化',
                  data.get('referenceParamsPath') == f'oss://ref_params/{CASE_STOCK}/round_{rnd}.json',
                  str(data.get('referenceParamsPath')))
            check(f'存量用例 round={rnd} 内容非空',
                  isinstance(data.get('referenceParams'), list) and len(data['referenceParams']) > 0,
                  f"n={len(data.get('referenceParams') or [])}")
            check(f'存量用例 round={rnd} roundNumber',
                  data.get('roundNumber') == rnd, str(data.get('roundNumber')))

        # ---------- 2. 未登记轮次 ----------
        resp, _ = get(CASE_STOCK, 9)
        check('未登记轮次 → 404「未找到第 9 轮」',
              (not resp.success) and resp.message == '未找到第 9 轮', resp.message)

        # ---------- 3. 有轮无路径 ----------
        cid_no_path = new_case('无路径', {'rounds': [{'round_number': 1}, {'round_number': 2}]})
        resp, _ = get(cid_no_path, 1)
        check('有轮无路径 → 404「第 1 轮未生成参考参数」',
              (not resp.success) and resp.message == '第 1 轮未生成参考参数', resp.message)

        # ---------- 4. 有路径但对象不存在（不得 200 空列表） ----------
        ghost = str(uuid.uuid4())
        cid_missing = new_case('对象缺失', {'rounds': [{'round_number': 1}]},
                               ref_params=[{'round_number': 1,
                                            'reference_params_path': f'{LEGACY_PREFIX}\\{ghost}\\round_1.json'}])
        resp, data = get(cid_missing, 1)
        check('对象缺失 → 失败且不是 200 空列表',
              (not resp.success) and data.get('referenceParams') is None, resp.message)
        check('对象缺失 → 消息带原始路径与归一化路径',
              '参考参数文件读取失败' in resp.message
              and ghost in resp.message and f'oss://ref_params/{ghost}/round_1.json' in resp.message,
              resp.message)

        # ---------- 5. 内容为空数组 → 200 [] ----------
        from shared.infrastructure.storage import storage
        cid_empty = new_case('空数组', {'rounds': [{'round_number': 1}]},
                             ref_params=[{'round_number': 1,
                                          'reference_params_path': f'oss://ref_params/{ghost}_empty/round_1.json'}])
        written_paths.append(storage.save_bytes(b'[]', 'ref_params', f'{ghost}_empty/round_1.json',
                                                content_type='application/json'))
        resp, data = get(cid_empty, 1)
        check('空数组对象 → 200 []', resp.success and data.get('referenceParams') == [],
              f"{resp.message} {data.get('referenceParams')}")

        # ---------- 6. config.rounds camel 兜底 ----------
        cid_camel = new_case('config兜底', {
            'rounds': [{'roundNumber': 1,
                        'referenceParamsPath': f'oss://ref_params/{ghost}_camel/round_1.json'}],
        })
        written_paths.append(storage.save_bytes(
            json.dumps([{'code': 'camel_ref', 'value': '1'}]).encode('utf-8'),
            'ref_params', f'{ghost}_camel/round_1.json', content_type='application/json'))
        resp, data = get(cid_camel, 1)
        check('仅 config.rounds（camel roundNumber + path）→ 200 兜底成功',
              resp.success and len(data.get('referenceParams') or []) == 1, resp.message)

        # ---------- 7. PUT：缺字段 / 非数组 → 400 ----------
        resp, _ = put(cid_no_path, 1, {})
        check('PUT 缺 referenceParams → 400', (not resp.success) and '缺少 referenceParams' in resp.message,
              resp.message)
        resp, _ = put(cid_no_path, 1, {'referenceParams': {'a': 1}})
        check('PUT 非数组 → 400', (not resp.success) and '必须为数组' in resp.message, resp.message)

        # ---------- 8. PUT：未知轮 → 404 ----------
        resp, _ = put(cid_no_path, 7, {'referenceParams': []})
        check('PUT 未知轮 → 404「未找到第 7 轮」',
              (not resp.success) and resp.message == '未找到第 7 轮', resp.message)

        # ---------- 9. PUT 无路径轮：建规范 key + 列 upsert + 不回写 config ----------
        written_paths.append(storage.save_bytes(
            json.dumps([{'code': 'r1_ref', 'value': 'x'}]).encode('utf-8'),
            'ref_params', f'{cid_no_path}/round_1.json', content_type='application/json'))
        row = db.query(TestCase).filter(TestCase.id == cid_no_path).one()
        row.reference_params = [{'round_number': 1,
                                 'reference_params_path': f'oss://ref_params/{cid_no_path}/round_1.json'}]
        db.commit()

        params_v2 = [{'code': 'r2_ref', 'value': 'y'}, {'code': 'r2_other', 'value': 'z'}]
        resp, put_data = put(cid_no_path, 2, {'referenceParams': params_v2})
        check('PUT 无路径轮 → 200 规范路径',
              resp.success and put_data.get('referenceParamsPath') == f'oss://ref_params/{cid_no_path}/round_2.json',
              f"{resp.message} {put_data.get('referenceParamsPath')}")
        check('PUT 返回内容保留入参 code/value',
              [(p.get('code'), p.get('value')) for p in (put_data.get('referenceParams') or [])]
              == [(p['code'], p['value']) for p in params_v2],
              str(put_data.get('referenceParams')))
        written_paths.append(put_data.get('referenceParamsPath'))

        db.expire_all()
        row = db.query(TestCase).filter(TestCase.id == cid_no_path).one()
        col = row.reference_params or []
        check('PUT 后列内新增 round 2 规范路径',
              {'round_number': 2, 'reference_params_path': f'oss://ref_params/{cid_no_path}/round_2.json'} in col,
              json.dumps(col, ensure_ascii=False))
        check('PUT 后其它轮条目不变',
              {'round_number': 1, 'reference_params_path': f'oss://ref_params/{cid_no_path}/round_1.json'} in col,
              json.dumps(col, ensure_ascii=False))
        check('PUT 后按轮次升序',
              [e.get('round_number') for e in col] == sorted(e.get('round_number') for e in col),
              str([e.get('round_number') for e in col]))
        check('PUT 不回写 config.rounds 路径键',
              all(not any(k in r for k in ('reference_params_path', 'referenceParamsPath'))
                  for r in row.config.get('rounds', []))
              and all('round_number' in r for r in row.config.get('rounds', [])),
              json.dumps(row.config, ensure_ascii=False))

        resp_get, get_data = get(cid_no_path, 2)
        check('PUT 后 GET 与 PUT 返回一致',
              resp_get.success and get_data.get('referenceParams') == put_data.get('referenceParams'),
              f"{resp_get.message} {get_data.get('referenceParams')}")

        resp2, data2 = put(cid_no_path, 2, {'referenceParams': params_v2})
        check('重复 PUT 幂等（路径不变）',
              resp2.success and data2.get('referenceParamsPath') == put_data.get('referenceParamsPath'),
              str(data2.get('referenceParamsPath')))

        # ---------- 10. PUT legacy Windows 路径 → 归一化写入 + 列更新 ----------
        cid_legacy = new_case('legacy写', {'rounds': [{'round_number': 1}]},
                              ref_params=[{'round_number': 1,
                                           'reference_params_path': f'{LEGACY_PREFIX}\\{ghost}_legacy\\round_1.json'}])
        resp, put_legacy = put(cid_legacy, 1, {'referenceParams': [{'code': 'legacy_ref', 'value': '1'}]})
        expect_legacy = f'oss://ref_params/{ghost}_legacy/round_1.json'
        check('PUT legacy 路径 → 归一化规范路径',
              resp.success and put_legacy.get('referenceParamsPath') == expect_legacy,
              f"{resp.message} {put_legacy.get('referenceParamsPath')}")
        written_paths.append(expect_legacy)
        db.expire_all()
        row = db.query(TestCase).filter(TestCase.id == cid_legacy).one()
        check('PUT legacy 后列内路径已更新为规范路径',
              [e.get('reference_params_path') for e in (row.reference_params or [])] == [expect_legacy],
              json.dumps(row.reference_params, ensure_ascii=False))
        resp_get, get_legacy = get(cid_legacy, 1)
        check('PUT legacy 后 GET 一致',
              resp_get.success and get_legacy.get('referenceParams') == put_legacy.get('referenceParams'),
              f"{resp_get.message} {get_legacy.get('referenceParams')}")

        # ---------- 11. 可见性非回归：私有用例非 owner ----------
        owner = 987654321
        non_owner = ([('x-user-id', '123456789')])
        cid_private = new_case('私有', {'rounds': [{'round_number': 1}]},
                               visibility='private', owner=owner)
        resp, _ = get(cid_private, 1, meta=non_owner)
        check('私有用例非 owner 读 → 404 未找到测试用例',
              (not resp.success) and resp.message == '未找到测试用例', resp.message)
        resp, _ = put(cid_private, 1, {'referenceParams': []}, meta=non_owner)
        check('私有用例非 owner 写 → 403 资源不存在或无权访问',
              (not resp.success) and resp.message == '资源不存在或无权访问', resp.message)
        resp, _ = get(cid_private, 1, meta=[('x-user-id', str(owner))])
        check('私有用例 owner 读 → 有轮无路径口径（未生成）',
              (not resp.success) and resp.message == '第 1 轮未生成参考参数', resp.message)

        # ---------- 12. 列表 / 详情里的参考参数字段不受影响（gRPC 侧 snake_case） ----------
        detail = stub.GetTestCaseDetail(pb.GetTestCaseDetailRequest(tc_id=CASE_STOCK))
        detail_data = json.loads(detail.data) if detail.data else {}
        check('详情 reference_params 字段仍在且为列真值',
              detail.success and isinstance(detail_data.get('reference_params'), list)
              and len(detail_data['reference_params']) == 2,
              f"{detail.message} {json.dumps(detail_data.get('reference_params'), ensure_ascii=False)}")
        lst = stub.ListTestCases(pb.ListTestCasesRequest(page=1, per_page=5))
        lst_data = json.loads(lst.data) if lst.data else {}
        items = lst_data.get('items') or lst_data.get('list') or []
        check('列表项仍带 reference_params 字段',
              lst.success and bool(items) and all('reference_params' in it for it in items),
              f"{lst.message} n={len(items)}")

        # ---------- 13. 库内残留自检 ----------
        db.expire_all()
        left = db.query(TestCase).filter(TestCase.name.like(NAME_PREFIX + '%')).count()
        check('自建用例数为本脚本创建数', left == len(created_ids), f'{left}/{len(created_ids)}')

    finally:
        # 清理：写入对象 + 自建用例行
        try:
            from shared.infrastructure.storage import storage as _st
            for p in written_paths:
                if p:
                    try:
                        _st.delete(p)
                    except Exception as exc:
                        print(f'[cleanup] 删除对象失败 {p}: {exc}', file=sys.stderr, flush=True)
        except Exception as exc:
            print(f'[cleanup] 存储清理异常: {exc}', file=sys.stderr, flush=True)
        try:
            from shared.models.database import get_db_session
            from task_service.infrastructure.persistence.models.testcase_models import TestCase
            db = get_db_session()
            if created_ids:
                db.query(TestCase).filter(TestCase.id.in_(created_ids)).delete(synchronize_session=False)
                db.commit()
            left = db.query(TestCase).filter(TestCase.id.in_(created_ids)).count() if created_ids else 0
            print(f'[cleanup] 自建用例残留={left}', flush=True)
        except Exception as exc:
            print(f'[cleanup] 用例清理异常: {exc}', file=sys.stderr, flush=True)
        server.stop(0)

    failed = [r for r in _results if not r[1]]
    print(f'\n===== {len(_results) - len(failed)}/{len(_results)} passed =====', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
