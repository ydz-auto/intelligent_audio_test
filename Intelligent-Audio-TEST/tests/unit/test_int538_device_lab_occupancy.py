# -*- coding: utf-8 -*-
"""INT-538（INT-493 拆分②）：设备/播放设备 lab_id/lab_name + 设备占用状态字段。

覆盖验收标准 1（单测）：
- DTO 序列化含新字段：DeviceItem / PlaybackDeviceItem 的 lab_id/lab_name
  有值与 null 两态；DeviceItem 的 occupied_status / occupied_task_id 可选
- task_service 占用聚合三态：pending/queued→occupied、running→testing、
  无活动行→null（不在返回映射中）；running 优先于 pending/queued；
  http_api/websocket_api 排除；device_ids / lab_id 过滤
- device_service 序列化补映射：_device_to_dict / _playback_to_dict 含
  lab_id/lab_name（有值/null 两态）
- device_service 列表 lab_id 过滤 + lab_name 经 laboratories 表解析回填
- api_gateway 组装时经 GetDeviceOccupancy RPC 注入占用态（失败降级 null）
"""
import os
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from shared.models import database  # noqa: E402
from shared.models.common_enums import DeviceOccupancyStatus  # noqa: E402

# 模型需在 fixture create_all 前注册进 Base.metadata（否则 sqlite 无表）
from api_gateway.schemas.device import DeviceItem  # noqa: E402,F401
from api_gateway.schemas.playback import PlaybackDeviceItem  # noqa: E402,F401
from device_service.infrastructure.persistence.models import (  # noqa: E402,F401
    Device,
    PlaybackDevice,
)
from task_service.infrastructure.persistence.models import (  # noqa: E402,F401
    TaskCase,
)


# ==================== sqlite 夹具 ====================

@pytest.fixture()
def sqlite_db():
    """进程级 sqlite 库：绑定全局 engine + 建表（对齐 test_benchmark_acceptance_t27）。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


def _create_laboratories(session):
    """创建 laboratories 表（INT-655 起由 device_service Laboratory PO 经 create_all 建表；
    此处仅为测试数据直插，status 显式补默认值满足 PO NOT NULL）。"""
    session.execute(text(
        "CREATE TABLE IF NOT EXISTS laboratories ("
        " id INTEGER PRIMARY KEY, code VARCHAR(50) UNIQUE NOT NULL,"
        " name VARCHAR(100) NOT NULL, status VARCHAR(20) DEFAULT 'active',"
        " deleted BOOLEAN DEFAULT FALSE)"
    ))
    session.execute(text(
        "INSERT INTO laboratories (id, code, name, status, deleted) "
        "VALUES (1, 'L1', 'A楼101', 'active', FALSE)"
    ))
    session.execute(text(
        "INSERT INTO laboratories (id, code, name, status, deleted) "
        "VALUES (2, 'L2', 'B楼201', 'active', FALSE)"
    ))
    session.commit()


# ==================== 网关 DTO 序列化（验收 1） ====================

def test_device_item_lab_occupancy_fields_present():
    """DeviceItem 含 lab_id/lab_name/occupied_status/occupied_task_id 有值态。"""
    item = DeviceItem.model_validate({
        'id': 1,
        'name': 'phone-1',
        'lab_id': 2,
        'lab_name': 'B楼201',
        'occupied_status': DeviceOccupancyStatus.TESTING.value,
        'occupied_task_id': 42,
    })
    assert item.lab_id == 2
    assert item.lab_name == 'B楼201'
    assert item.occupied_status == 'testing'
    assert item.occupied_task_id == 42


def test_device_item_lab_occupancy_fields_null():
    """DeviceItem 缺省态：lab/占用字段均为 null（未绑定/无占用）。"""
    item = DeviceItem.model_validate({'id': 1, 'name': 'phone-1'})
    assert item.lab_id is None
    assert item.lab_name is None
    assert item.occupied_status is None
    assert item.occupied_task_id is None


def test_playback_device_item_lab_fields():
    """PlaybackDeviceItem 含 lab_id/lab_name 有值态 + null 态。"""
    item = PlaybackDeviceItem.model_validate({
        'id': 1,
        'name': 'playback-1',
        'lab_id': 1,
        'lab_name': 'A楼101',
    })
    assert item.lab_id == 1
    assert item.lab_name == 'A楼101'

    empty = PlaybackDeviceItem.model_validate({'id': 2, 'name': 'playback-2'})
    assert empty.lab_id is None
    assert empty.lab_name is None


# ==================== task_service 占用聚合（验收 1） ====================

def test_get_device_occupancy_three_states(sqlite_db):
    """占用三态：running→testing、pending/queued→occupied、无活动行→null。"""
    from task_service.infrastructure.persistence.task_repository import task_repository
    session = database.get_db_session()

    rows = [
        # (device_id, device_type, execution_status, task_id, case_id, lab_id)
        ('1', 'physical', 'running', 10, 'case-r1', None),
        ('2', 'physical', 'pending', 20, 'case-p1', None),
        ('3', 'physical', 'queued', 30, 'case-q1', None),
        # 无活动行：completed 不计入
        ('4', 'physical', 'completed', 40, 'case-d1', None),
        # 非物理设备排除
        ('5', 'http_api', 'running', 50, 'case-h1', None),
        # 空 device_id 忽略
        (None, 'physical', 'running', 60, 'case-n1', None),
    ]
    for device_id, device_type, exec_status, task_id, case_id, lab_id in rows:
        session.add(TaskCase(
            device_id=device_id,
            device_type=device_type,
            execution_status=exec_status,
            task_id=task_id,
            test_case_id=case_id,
            lab_id=lab_id,
        ))
    session.commit()

    result = task_repository.get_device_occupancy()
    assert result['1']['occupied_status'] == DeviceOccupancyStatus.TESTING.value
    assert result['1']['task_id'] == 10
    assert result['1']['case_id'] == 'case-r1'
    assert result['2']['occupied_status'] == DeviceOccupancyStatus.OCCUPIED.value
    assert result['3']['occupied_status'] == DeviceOccupancyStatus.OCCUPIED.value
    # 无活动行/非物理/空 device_id 均不在返回映射（DTO 层 null）
    assert '4' not in result
    assert '5' not in result


def test_get_device_occupancy_running_priority(sqlite_db):
    """同设备 pending 与 running 并存 → testing（running 优先）。"""
    from task_service.infrastructure.persistence.task_repository import task_repository
    session = database.get_db_session()
    session.add(TaskCase(device_id='1', device_type='physical',
                         execution_status='pending', task_id=10, test_case_id='c1'))
    session.add(TaskCase(device_id='1', device_type='physical',
                         execution_status='running', task_id=11, test_case_id='c2'))
    session.commit()

    result = task_repository.get_device_occupancy()
    assert result['1']['occupied_status'] == DeviceOccupancyStatus.TESTING.value
    assert result['1']['task_id'] == 11  # running 行优先


def test_get_device_occupancy_filters(sqlite_db):
    """device_ids / lab_id 过滤均生效；int 入参自动转字符串匹配 String 列。"""
    from task_service.infrastructure.persistence.task_repository import task_repository
    session = database.get_db_session()
    session.add(TaskCase(device_id='1', device_type='physical',
                         execution_status='running', task_id=10, test_case_id='c1', lab_id=1))
    session.add(TaskCase(device_id='2', device_type='physical',
                         execution_status='running', task_id=20, test_case_id='c2', lab_id=2))
    session.add(TaskCase(device_id='3', device_type='physical',
                         execution_status='running', task_id=30, test_case_id='c3', lab_id=1))
    session.commit()

    # 网关侧传 int 设备 ID（设备 DTO id 为 int），repo 需转字符串匹配 String 列
    by_ids = task_repository.get_device_occupancy(device_ids=[1, 3])
    assert set(by_ids.keys()) == {'1', '3'}

    by_lab = task_repository.get_device_occupancy(lab_id=1)
    assert set(by_lab.keys()) == {'1', '3'}


# ==================== device_service 序列化补映射（验收 1） ====================

def test_device_serializer_lab_fields(sqlite_db):
    """_device_to_dict / _playback_to_dict 含 lab_id/lab_name（有值 + null 两态）。"""
    from device_service.infrastructure.persistence._device_serializers import (
        _device_to_dict, _playback_to_dict,
    )
    session = database.get_db_session()
    session.add(Device(
        id=1, name='phone-1', model='M1', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        lab_id=1, status='online',
    ))
    session.add(Device(
        id=2, name='phone-2', model='M2', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        status='online',
    ))
    session.add(PlaybackDevice(
        id=1, name='pb-1', model='PM', device_type='dry', sample_rate=48000,
        device_unique_id='u1', lab_id=2, status='online',
    ))
    session.add(PlaybackDevice(
        id=2, name='pb-2', model='PM', device_type='dry', sample_rate=48000,
        device_unique_id='u2', status='online',
    ))
    session.commit()

    dev1 = session.query(Device).filter_by(id=1).first()
    dev2 = session.query(Device).filter_by(id=2).first()
    pb1 = session.query(PlaybackDevice).filter_by(id=1).first()
    pb2 = session.query(PlaybackDevice).filter_by(id=2).first()

    d1 = _device_to_dict(dev1, lab_name='A楼101')
    assert d1['lab_id'] == 1
    assert d1['lab_name'] == 'A楼101'
    d2 = _device_to_dict(dev2)
    assert d2['lab_id'] is None
    assert d2['lab_name'] is None

    p1 = _playback_to_dict(pb1, lab_name='B楼201')
    assert p1['lab_id'] == 2
    assert p1['lab_name'] == 'B楼201'
    p2 = _playback_to_dict(pb2)
    assert p2['lab_id'] is None
    assert p2['lab_name'] is None


def test_device_list_lab_filter_and_lab_name(sqlite_db):
    """device_service 列表 lab_id 过滤 + lab_name 经 laboratories 表解析回填。"""
    from device_service.infrastructure.persistence.device_repository import (
        device_repository, playback_repository,
    )
    session = database.get_db_session()
    _create_laboratories(session)

    session.add(Device(
        id=1, name='phone-1', model='M1', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        lab_id=1, status='online',
    ))
    session.add(Device(
        id=2, name='phone-2', model='M2', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        lab_id=2, status='online',
    ))
    session.add(Device(
        id=3, name='phone-3', model='M3', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        status='online',  # 未绑定实验室
    ))
    session.commit()

    result = device_repository.list_devices(lab_id=1, page=1, per_page=10)
    assert result['total'] == 1
    assert result['items'][0]['id'] == 1
    assert result['items'][0]['lab_id'] == 1
    assert result['items'][0]['lab_name'] == 'A楼101'

    all_result = device_repository.list_devices(page=1, per_page=10)
    assert all_result['total'] == 3
    by_id = {item['id']: item for item in all_result['items']}
    assert by_id[1]['lab_name'] == 'A楼101'
    assert by_id[2]['lab_name'] == 'B楼201'
    assert by_id[3]['lab_name'] is None  # 未绑定

    # 播放设备同样透出 lab_name
    session.add(PlaybackDevice(
        id=1, name='pb-1', model='PM', device_type='dry', sample_rate=48000,
        device_unique_id='u1', lab_id=1, status='online',
    ))
    session.commit()
    pb_result = playback_repository.list_playback_devices(lab_id=1, page=1, per_page=10)
    assert pb_result['total'] == 1
    assert pb_result['items'][0]['lab_id'] == 1
    assert pb_result['items'][0]['lab_name'] == 'A楼101'


def test_device_get_one_entity_lab_fields(sqlite_db):
    """设备详情路径（get_device → entity.to_dict）透出 lab_id/lab_name（有值/null 两态）。"""
    from device_service.infrastructure.persistence.device_repository import (
        device_repository, playback_repository,
    )
    session = database.get_db_session()
    _create_laboratories(session)
    session.add(Device(
        id=1, name='phone-1', model='M1', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        lab_id=1, status='online',
    ))
    session.add(Device(
        id=2, name='phone-2', model='M2', type='phone', system='Android',
        system_version='13', app_name='app', app_version='1.0',
        status='online',
    ))
    session.add(PlaybackDevice(
        id=1, name='pb-1', model='PM', device_type='dry', sample_rate=48000,
        device_unique_id='u1', lab_id=1, status='online',
    ))
    session.commit()

    dev = device_repository.get_device(1)
    data = dev.to_dict()
    assert data['lab_id'] == 1
    assert data['lab_name'] == 'A楼101'

    dev2 = device_repository.get_device(2)
    data2 = dev2.to_dict()
    assert data2['lab_id'] is None
    assert data2['lab_name'] is None

    pb = playback_repository.get_playback_device(1)
    pb_data = pb.to_dict()
    assert pb_data['lab_id'] == 1
    assert pb_data['lab_name'] == 'A楼101'


# ==================== 集成冒烟：真实 gRPC 传输 + 真实 servicer + sqlite（验收 3 静态层） ====================

def test_get_device_occupancy_grpc_roundtrip(sqlite_db):
    """GetDeviceOccupancy 经真实 gRPC in-process 通道往返：三态 + 序列化。"""
    import json as _json
    from concurrent import futures

    import grpc

    from shared.proto import task_service_pb2 as task_pb
    from shared.proto import task_service_pb2_grpc as task_grpc
    from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

    session = database.get_db_session()
    session.add(TaskCase(device_id='1', device_type='physical',
                         execution_status='running', task_id=10, test_case_id='c1'))
    session.add(TaskCase(device_id='2', device_type='physical',
                         execution_status='pending', task_id=20, test_case_id='c2'))
    session.add(TaskCase(device_id='3', device_type='http_api',
                         execution_status='running', task_id=30, test_case_id='c3'))
    session.commit()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    task_grpc.add_TaskDataServiceServicer_to_server(TaskDataServiceServicer(), server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    try:
        with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
            stub = task_grpc.TaskDataServiceStub(channel)
            resp = stub.GetDeviceOccupancy(
                task_pb.GetDeviceOccupancyRequest(data='{}'), timeout=10)
            assert resp.success is True
            payload = _json.loads(resp.data)
            assert payload['1']['occupied_status'] == 'testing'
            assert payload['2']['occupied_status'] == 'occupied'
            assert '3' not in payload  # 非物理设备排除

            # device_ids 过滤经真实序列化往返
            resp2 = stub.GetDeviceOccupancy(
                task_pb.GetDeviceOccupancyRequest(
                    data=_json.dumps({'device_ids': [1]})), timeout=10)
            payload2 = _json.loads(resp2.data)
            assert set(payload2.keys()) == {'1'}
    finally:
        server.stop(0)


# ==================== api_gateway 占用注入（验收 1） ====================

def test_gateway_inject_occupancy(monkeypatch):
    """网关经 GetDeviceOccupancy RPC 注入占用态；无占用行置 null。"""
    import sys
    import types

    from api_gateway.application.services.device.device_query_service import DeviceQueryService

    fake_occupancy = {
        '1': {'occupied_status': 'testing', 'task_id': 10, 'case_id': 'c1'},
        '3': {'occupied_status': 'occupied', 'task_id': 30, 'case_id': 'c3'},
    }

    class _FakeTaskData:
        def get_device_occupancy(self, device_ids=None, lab_id=None):
            return fake_occupancy

    # 替换 sys.modules 中的 task_data_proxies 模块（_inject_occupancy 在函数体内懒导入）
    fake_mod = types.ModuleType('api_gateway.infrastructure.grpc_proxies.task_data_proxies')
    fake_mod.task_data_service = _FakeTaskData()
    monkeypatch.setitem(sys.modules, 'api_gateway.infrastructure.grpc_proxies.task_data_proxies', fake_mod)

    items = [
        {'id': 1, 'name': 'd1'},
        {'id': 2, 'name': 'd2'},
        {'id': 3, 'name': 'd3'},
    ]
    DeviceQueryService._inject_occupancy(items)
    assert items[0]['occupied_status'] == 'testing'
    assert items[0]['occupied_task_id'] == 10
    assert items[1]['occupied_status'] is None
    assert items[1]['occupied_task_id'] is None
    assert items[2]['occupied_status'] == 'occupied'
    assert items[2]['occupied_task_id'] == 30


def test_gateway_inject_occupancy_rpc_failure(monkeypatch):
    """GetDeviceOccupancy RPC 失败时占用字段保持 null（可选注入不阻塞列表）。"""
    import sys
    import types

    from api_gateway.application.services.device.device_query_service import DeviceQueryService

    class _FakeTaskData:
        def get_device_occupancy(self, device_ids=None, lab_id=None):
            # 模拟 gRPC 失败：proxy 降级返回 {}（_grpc_call default_return）
            return {}

    fake_mod = types.ModuleType('api_gateway.infrastructure.grpc_proxies.task_data_proxies')
    fake_mod.task_data_service = _FakeTaskData()
    monkeypatch.setitem(sys.modules, 'api_gateway.infrastructure.grpc_proxies.task_data_proxies', fake_mod)

    items = [{'id': 1, 'name': 'd1'}]
    DeviceQueryService._inject_occupancy(items)
    assert items[0]['occupied_status'] is None
    assert items[0]['occupied_task_id'] is None
