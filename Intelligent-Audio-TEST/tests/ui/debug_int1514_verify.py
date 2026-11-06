# -*- coding: utf-8 -*-
"""INT-1514 真实库 / 真实链路的验收取证脚本（非 pytest）。

背景：:15000 docker 栈的 algorithm_service / api_gateway 镜像尚未包含
`ClearAlgorithmDefinitionDraft`（未部署未合并分支），无法在 docker 网关
端到端验证。本脚本改用「真实代码 + 真实依赖」的方式取证：

- 网关编排：worktree 内 api_gateway.AlgorithmCommandService（本卡改动）
- 算法定义写：docker task_service 旧 CRUD（宿主 53061，生产同路径，落主库）
- 草稿读写/清除：worktree 内 algorithm_service 以进程内 gRPC server
  （127.0.0.1:<临时端口>）跑真实 servicer，落主库 intelligent_audio_test
- 数据库：docker postgres 宿主 15432 / intelligent_audio_test

仅写 `itest1514_*` / `接线测试_INT1514_*` 测试数据，结尾（含异常）物理清理
并核对基线计数回到原值。

用法：
    python tests/ui/debug_int1514_verify.py
"""
import json
import os
import socket
import sys
import time
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


ALGO_PORT = _free_port()
DB_URL = os.environ.get(
    'INT1514_DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:15432/intelligent_audio_test',
)
os.environ['DATABASE_URL'] = DB_URL
os.environ['ALGORITHM_SERVICE_HOST'] = '127.0.0.1'
os.environ['ALGORITHM_SERVICE_GRPC_PORT'] = str(ALGO_PORT)
os.environ['TASK_SERVICE_HOST'] = '127.0.0.1'
os.environ.setdefault('TASK_SERVICE_GRPC_PORT', '53061')
os.environ.setdefault('GRPC_PORT', '53061')
os.environ.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
os.environ.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9000')
os.environ.setdefault('OSS_BUCKET_NAME', 'intelligent-audio-test')

RUN_ID = uuid.uuid4().hex[:8]
TYPES = {k: f'itest1514_{RUN_ID}_{k}' for k in ('t1', 't2', 't3', 't4', 't5', 't6')}
PREFIX = f'itest1514_{RUN_ID}%'

report = {'run_id': RUN_ID, 'algo_grpc_port': ALGO_PORT, 'steps': []}


def rec(step, ok, detail):
    report['steps'].append({'step': step, 'ok': bool(ok), 'detail': detail})
    print(f'[{"PASS" if ok else "FAIL"}] {step}: {detail}', flush=True)


def main():
    from sqlalchemy import text
    from shared.models.database import init_db, get_db_session

    init_db()
    session = get_db_session()

    def scalar(sql, **kw):
        return session.execute(text(sql), kw).scalar()

    def pref_defs():
        return scalar("select count(*) from algorithm_definitions where type like :p", p=PREFIX)

    def pref_drafts():
        return scalar("select count(*) from algorithm_definition_drafts where algorithm_type like :p", p=PREFIX)

    def draft_rows(algo_type):
        return session.execute(
            text('select algorithm_type, snapshot from algorithm_definition_drafts where algorithm_type = :t'),
            {'t': algo_type},
        ).fetchall()

    def def_row(algo_type):
        return session.execute(
            text('select name, deleted from algorithm_definitions where type = :t'),
            {'t': algo_type},
        ).fetchall()

    def cleanup():
        """物理清理本卡测试前缀（含历次中断残留）。"""
        session.execute(text("delete from algorithm_definition_drafts where algorithm_type like 'itest1514%'"))
        session.execute(text("delete from algorithm_definitions where type like 'itest1514%'"))
        session.commit()

    # 预清理：上一次中断留下的 itest1514_* 行（测试前缀，仅本卡使用）
    stale_defs = scalar("select count(*) from algorithm_definitions where type like 'itest1514%'")
    stale_drafts = scalar("select count(*) from algorithm_definition_drafts where algorithm_type like 'itest1514%'")
    cleanup()
    rec('preclean', True, {'stale_definitions': stale_defs, 'stale_drafts': stale_drafts})

    base_defs = scalar('select count(*) from algorithm_definitions')
    base_drafts = scalar('select count(*) from algorithm_definition_drafts')
    report['baseline'] = {'definitions': base_defs, 'drafts': base_drafts}
    rec('baseline', True, report['baseline'])

    # ---- 进程内 algorithm_service gRPC server（真实 servicer + 主库）----
    from algorithm_service.interfaces.grpc.server import start_grpc_server
    server = start_grpc_server(port=ALGO_PORT)
    time.sleep(0.5)

    from shared.proto import algorithm_service_pb2 as pb
    from shared.clients.grpc_clients import get_algorithm_definition_service_stub
    stub = get_algorithm_definition_service_stub()

    # 宿主 -> 进程内 server 首连偶发 stall（Windows gRPC 冷启动），重试预热
    warmed, attempts = False, 0
    for attempts in range(1, 4):
        try:
            stub.GetAlgorithmDefinitionDraft(
                pb.GetAlgorithmDefinitionDraftRequest(algorithm_type='itest1514__warmup__none'),
                timeout=20,
            )
            warmed = True
            break
        except Exception as e:  # noqa: BLE001
            print(f'  warmup attempt {attempts} failed: {e}', flush=True)
            time.sleep(1)
    rec('warmup', warmed, {'attempts': attempts})

    def save_draft(algo_type, name):
        return stub.SaveAlgorithmDefinitionDraft(
            pb.SaveAlgorithmDefinitionDraftRequest(
                data=json.dumps({'algorithm_type': algo_type, 'name': name})
            ),
            timeout=30,
        )

    def get_draft(algo_type):
        resp = stub.GetAlgorithmDefinitionDraft(
            pb.GetAlgorithmDefinitionDraftRequest(algorithm_type=algo_type), timeout=30
        )
        data = json.loads(resp.data) if resp.data else {}
        return resp.success, (data.get('name') if data else None), data

    def clear_draft(algo_type):
        resp = stub.ClearAlgorithmDefinitionDraft(
            pb.ClearAlgorithmDefinitionDraftRequest(algorithm_type=algo_type), timeout=30
        )
        data = json.loads(resp.data) if resp.data else {}
        return resp.success, data

    import api_gateway.application.services.algorithm.algorithm_command_service as gw

    class _Req:
        def __init__(self, payload):
            self._payload = payload

        def get_json(self):
            return self._payload

    def call_gw(method, payload=None, algo_type=None):
        old = gw.request
        gw.request = _Req(payload or {})
        try:
            if method == 'create':
                return gw.AlgorithmCommandService.create_algorithm()
            if method == 'update':
                return gw.AlgorithmCommandService.update_algorithm(algo_type)
            if method == 'delete':
                return gw.AlgorithmCommandService.delete_algorithm(algo_type)
            if method == 'bulk':
                return gw.AlgorithmCommandService.bulk_delete()
            raise ValueError(method)
        finally:
            gw.request = old

    try:
        # ==================== 用例 1：发布后清草稿 ====================
        t1 = TYPES['t1']
        body, code = call_gw('create', {'type': t1, 'name': '接线测试_INT1514_发布A'})
        rec('1a.create', code == 200 and body.get('success'), {'code': code, 'type': t1})

        resp = save_draft(t1, '接线测试_INT1514_草稿态A')
        ok_save = resp.success
        ok_get, name, _ = get_draft(t1)
        rec('1b.save_draft', ok_save and ok_get and name == '接线测试_INT1514_草稿态A',
            {'saved': ok_save, 'draft_name': name, 'db_rows': len(draft_rows(t1))})

        body, code = call_gw('update', {'name': '接线测试_INT1514_发布态B'}, algo_type=t1)
        ok_pub = code == 200 and body.get('success')
        ok_get, name, data = get_draft(t1)
        ok_rows = len(draft_rows(t1)) == 0
        detail_name = (def_row(t1) or [(None,)])[0][0]
        rec('1c.publish_clears_draft',
            ok_pub and ok_get and name is None and ok_rows and detail_name == '接线测试_INT1514_发布态B',
            {'publish_code': code, 'draft_name': name, 'draft_rows': len(draft_rows(t1)),
             'definition_name': detail_name})

        # 幂等：再清一次
        ok_again, payload = clear_draft(t1)
        rec('1d.clear_idempotent', ok_again and payload.get('cleared') is False,
            {'success': ok_again, 'payload': payload})

        # ==================== 用例 2：删除后清草稿 ====================
        t2 = TYPES['t2']
        body, code = call_gw('create', {'type': t2, 'name': '接线测试_INT1514_删除1'})
        save_draft(t2, '接线测试_INT1514_删前草稿')
        before = len(draft_rows(t2))
        body, code = call_gw('delete', algo_type=t2)
        ok_del = code == 200 and body.get('success')
        after = len(draft_rows(t2))
        deleted_flag = (def_row(t2) or [(None, None)])[0][1]
        rec('2.delete_clears_draft', ok_del and before == 1 and after == 0,
            {'delete_code': code, 'draft_before': before, 'draft_after': after,
             'definition_soft_deleted': deleted_flag})

        # ==================== 用例 3：批量删除只清被删类型 ====================
        for key, label in (('t3', '批量A'), ('t4', '批量B'), ('t5', '批量保留')):
            call_gw('create', {'type': TYPES[key], 'name': f'接线测试_INT1514_{label}'})
            save_draft(TYPES[key], f'接线测试_INT1514_{label}_草稿')
        body, code = call_gw('bulk', {'algorithm_types': [TYPES['t3'], TYPES['t4']]})
        ok_bulk = code == 200 and body.get('success')
        d3, d4, d5 = len(draft_rows(TYPES['t3'])), len(draft_rows(TYPES['t4'])), len(draft_rows(TYPES['t5']))
        rec('3.bulk_delete_clears_only_deleted', ok_bulk and d3 == 0 and d4 == 0 and d5 == 1,
            {'bulk_code': code, 't3_drafts': d3, 't4_drafts': d4, 'kept_t5_drafts': d5})

        # ==================== 用例 4：发布失败保留草稿 ====================
        t6 = TYPES['t6']
        call_gw('create', {'type': t6, 'name': '接线测试_INT1514_失败发布'})
        save_draft(t6, '接线测试_INT1514_失败前草稿')
        body, code = call_gw('update', {'name': ''}, algo_type=t6)  # 校验失败
        ok_fail = code == 400 or body.get('success') is False
        kept = len(draft_rows(t6))
        ok_get, name, _ = get_draft(t6)
        rec('4.publish_failure_keeps_draft', ok_fail and kept == 1 and name == '接线测试_INT1514_失败前草稿',
            {'update_code': code, 'draft_rows': kept, 'draft_name': name})
    finally:
        # ==================== 清理（异常也执行）====================
        cleanup()
        end_defs = scalar('select count(*) from algorithm_definitions')
        end_drafts = scalar('select count(*) from algorithm_definition_drafts')
        leftover_defs = pref_defs()
        leftover_drafts = pref_drafts()
        report['cleanup'] = {'definitions_before': base_defs, 'definitions_after': end_defs,
                             'drafts_before': base_drafts, 'drafts_after': end_drafts,
                             'leftover_definitions': leftover_defs, 'leftover_drafts': leftover_drafts}
        rec('5.cleanup',
            leftover_defs == 0 and leftover_drafts == 0
            and end_defs == base_defs and end_drafts == base_drafts,
            report['cleanup'])
        server.stop(0)

    passed = all(s['ok'] for s in report['steps'])
    report['result'] = 'PASS' if passed else 'FAIL'
    print('\n' + json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
