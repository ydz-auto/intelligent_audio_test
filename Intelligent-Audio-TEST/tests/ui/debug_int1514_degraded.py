# -*- coding: utf-8 -*-
"""INT-1514 版本错配降级取证：网关新代码 + docker :15000 现役旧 algorithm_service。

场景：本次修复需要 api_gateway 与 algorithm_service 同版本部署。镜像升级存在
先后窗口，先升网关、算法服务仍旧版时，ClearAlgorithmDefinitionDraft 返回
UNIMPLEMENTED，网关必须「只记 warning、发布结果照常成功」。

本脚本用 docker 现役服务（task_service 53061 / algorithm_service 53067）验这
条降级路径；预期发布 200、草稿快照保留（未升级侧不清）。测试数据 itest1514_*
前缀，结尾物理清理。
"""
import json
import os
import sys
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

os.environ['DATABASE_URL'] = os.environ.get(
    'INT1514_DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:15432/intelligent_audio_test',
)
os.environ['ALGORITHM_SERVICE_HOST'] = '127.0.0.1'
os.environ['ALGORITHM_SERVICE_GRPC_PORT'] = '53067'  # docker 现役（未升级）
os.environ['TASK_SERVICE_HOST'] = '127.0.0.1'
os.environ.setdefault('TASK_SERVICE_GRPC_PORT', '53061')
os.environ.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
os.environ.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9000')
os.environ.setdefault('OSS_BUCKET_NAME', 'intelligent-audio-test')

RUN_ID = uuid.uuid4().hex[:8]
T = f'itest1514_{RUN_ID}_degraded'
report = {'run_id': RUN_ID, 'steps': []}


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

    def cleanup():
        session.execute(text("delete from algorithm_definition_drafts where algorithm_type like 'itest1514%'"))
        session.execute(text("delete from algorithm_definitions where type like 'itest1514%'"))
        session.commit()

    stale_defs = scalar("select count(*) from algorithm_definitions where type like 'itest1514%'")
    stale_drafts = scalar("select count(*) from algorithm_definition_drafts where algorithm_type like 'itest1514%'")
    cleanup()
    base_defs = scalar('select count(*) from algorithm_definitions')
    base_drafts = scalar('select count(*) from algorithm_definition_drafts')
    rec('baseline', True, {'stale_definitions': stale_defs, 'stale_drafts': stale_drafts,
                           'definitions': base_defs, 'drafts': base_drafts})

    from shared.proto import algorithm_service_pb2 as pb
    from shared.clients.grpc_clients import get_algorithm_definition_service_stub
    stub = get_algorithm_definition_service_stub()

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
            raise ValueError(method)
        finally:
            gw.request = old

    try:
        body, code = call_gw('create', {'type': T, 'name': '接线测试_INT1514_降级'})
        rec('create', code == 200 and body.get('success'), {'code': code, 'type': T})

        saved = stub.SaveAlgorithmDefinitionDraft(
            pb.SaveAlgorithmDefinitionDraftRequest(
                data=json.dumps({'algorithm_type': T, 'name': '接线测试_INT1514_降级草稿'})
            ),
            timeout=30,
        )
        rec('save_draft_on_old_service', saved.success, {'success': saved.success})

        # 旧 algorithm_service 无 ClearAlgorithmDefinitionDraft → 网关应降级
        body, code = call_gw('update', {'name': '接线测试_INT1514_降级发布'}, algo_type=T)
        ok_pub = code == 200 and body.get('success')
        draft_left = scalar(
            'select count(*) from algorithm_definition_drafts where algorithm_type = :t', t=T
        )
        def_name = scalar('select name from algorithm_definitions where type = :t', t=T)
        rec('publish_degrades_gracefully', ok_pub and draft_left == 1,
            {'publish_code': code, 'publish_success': body.get('success'),
             'draft_rows_kept': draft_left, 'definition_name': def_name})
    finally:
        cleanup()
        rec('cleanup', scalar('select count(*) from algorithm_definitions where type like :p', p='itest1514%') == 0
            and scalar('select count(*) from algorithm_definition_drafts where algorithm_type like :p', p='itest1514%') == 0
            and scalar('select count(*) from algorithm_definitions') == base_defs
            and scalar('select count(*) from algorithm_definition_drafts') == base_drafts,
            {'definitions': scalar('select count(*) from algorithm_definitions'),
             'drafts': scalar('select count(*) from algorithm_definition_drafts')})

    passed = all(s['ok'] for s in report['steps'])
    report['result'] = 'PASS' if passed else 'FAIL'
    print('\n' + json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
