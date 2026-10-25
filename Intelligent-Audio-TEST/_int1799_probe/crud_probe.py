# -*- coding: utf-8 -*-
"""INT-1799 真实 Postgres（隔离库副本）探针：API CRUD 两新列读写 + 筛选 + 拒绝规则。

用法（DATABASE_URL 指向 int1799_verify，apis 表已由迁移脚本 --apply 过）：
    DATABASE_URL=postgresql://...@localhost:15432/int1799_verify \
        python _int1799_probe/crud_probe.py
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

assert os.environ.get('DATABASE_URL'), '必须由调用方注入 DATABASE_URL'

from shared.models.database import init_db  # noqa: E402

init_db()

from api_test_service.application import api_crud_service as mod  # noqa: E402
from api_test_service.application.api_crud_service import APICrudService  # noqa: E402

# 出域副作用：事件总线 / stats 缓存属于网关侧，与本卡无关，置空以便单点取证
mod.APICrudService._publish_config_changed = staticmethod(lambda *a, **k: None)
mod.refresh_stats_cache = lambda: None

RESULTS = []


def _rec(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' :: ' + detail)


def _mk(name, **extra):
    payload = {'name': name, 'meta': {'environment': 'int1799probe'}}
    payload.update(extra)
    return APICrudService.create(payload)


def run():
    # ① 新建缺省 → http / false
    r = _mk('int1799-default')
    _rec('create_default', r['code'] == 201, f"code={r['code']} msg={r['message']}")
    default_id = (r.get('data') or {}).get('id')
    detail = APICrudService.get_one(default_id)['data']
    _rec('create_default_readback',
         detail.get('protocol') == 'http' and detail.get('streaming') is False,
         f"protocol={detail.get('protocol')!r} streaming={detail.get('streaming')!r}")
    _rec('read_has_no_device_type', 'device_type' not in detail,
         f"keys含device_type={'device_type' in detail}")

    # ② 新建 websocket + 流式 → 201
    r = _mk('int1799-ws', protocol='websocket', streaming=True)
    _rec('create_websocket_streaming', r['code'] == 201,
         f"code={r['code']} msg={r['message']}")
    ws_id = (r.get('data') or {}).get('id')
    detail = APICrudService.get_one(ws_id)['data']
    _rec('create_websocket_readback',
         detail.get('protocol') == 'websocket' and detail.get('streaming') is True,
         f"protocol={detail.get('protocol')!r} streaming={detail.get('streaming')!r}")

    # ③ 未上线组合 → 400
    for proto, streaming in (('grpc', False), ('sse', True), ('http', True),
                             ('websocket', False)):
        r = _mk(f'int1799-bad-{proto}-{streaming}', protocol=proto, streaming=streaming)
        _rec(f'create_reject_{proto}_{str(streaming).lower()}',
             r['code'] == 400 and '实现未上线' in r['message'],
             f"code={r['code']} msg={r['message']}")

    # ④ 旧前端只传 device_type → 400
    r = _mk('int1799-legacy', device_type='websocket_api')
    _rec('create_reject_device_type',
         r['code'] == 400 and 'device_type 已废弃' in r['message'],
         f"code={r['code']} msg={r['message']}")

    # ⑤ 更新：http+false → websocket+true 放行；只改一维 → 400
    r = APICrudService.update(default_id, {'streaming': True})
    _rec('update_single_dim_rejected',
         r['code'] == 400 and '实现未上线' in r['message'],
         f"code={r['code']} msg={r['message']}")
    r = APICrudService.update(default_id, {'protocol': 'websocket', 'streaming': True})
    ok = r['code'] == 200
    detail = APICrudService.get_one(default_id)['data']
    _rec('update_both_dims_allowed',
         ok and detail.get('protocol') == 'websocket' and detail.get('streaming') is True,
         f"code={r['code']} -> protocol={detail.get('protocol')!r} "
         f"streaming={detail.get('streaming')!r}")
    # 回到 http+false，供筛选用例
    APICrudService.update(default_id, {'protocol': 'http', 'streaming': False})

    # ⑥ 列表筛选（真实库 WHERE）
    all_rows = APICrudService.get_all(page=1, per_page=500)
    total = all_rows['data']['total']
    ws_rows = APICrudService.get_all(page=1, per_page=500, protocol='websocket',
                                     streaming=True)['data']
    http_rows = APICrudService.get_all(page=1, per_page=500, protocol='http')['data']
    bad_proto = APICrudService.get_all(page=1, per_page=500, protocol='ftp')
    _rec('filter_websocket_true',
         ws_rows['total'] >= 1 and all(
             i['protocol'] == 'websocket' and i['streaming'] is True
             for i in ws_rows['items']),
         f"total={ws_rows['total']} / 全库 {total}")
    _rec('filter_http_protocol',
         http_rows['total'] == total - ws_rows['total'],
         f"http={http_rows['total']} ws={ws_rows['total']} all={total}")
    _rec('filter_illegal_protocol_400', bad_proto['code'] == 400
         if 'code' in bad_proto else False,
         f"code={bad_proto.get('code')} msg={bad_proto.get('message')}")

    # ⑦ 直接查库确认落库值（不经服务读侧序列化）
    from shared.models.database import get_db_session
    from api_test_service.infrastructure.persistence.models.api_models import API
    s = get_db_session()
    row = s.query(API).filter(API.id == ws_id).first()
    _rec('db_columns_persisted',
         row is not None and row.protocol == 'websocket' and row.streaming is True
         and row.device_type == 'http_api',
         f"protocol={getattr(row, 'protocol', None)!r} "
         f"streaming={getattr(row, 'streaming', None)!r} "
         f"device_type(未写列默认)={getattr(row, 'device_type', None)!r}")
    s.remove()

    # ⑧ 清理探针行（软删，隔离库专属）
    for api_id in (default_id, ws_id):
        APICrudService.delete(api_id)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print('\n===== SUMMARY %d/%d passed =====' % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print('FAILED: ' + ', '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(run())
