# -*- coding: utf-8 -*-
"""软删除 + 部分唯一索引验证测试。

核心场景：删除记录（软删除）后，用相同的唯一键值重新创建记录，应成功。
迁移前旧 UniqueConstraint 会导致重新创建失败（唯一约束冲突）；
迁移后部分唯一索引 WHERE deleted = false 使软删除记录不参与唯一性检查。
"""
import time
import pytest
from tests.api.conftest import API_BASE


# ── 辅助 ──────────────────────────────────────────────────
def _unwrap(resp):
    body = resp.json()
    assert body.get('code') in (0, 200, 201) or body.get('success') is True, \
        f'API 返回失败: {resp.status_code} {body}'
    return body.get('data')


def _ts():
    return int(time.time() * 1000)


# ── Algorithm Groups ───────────────────────────────────────
class TestSoftDeleteRecreateAlgorithmGroups:
    """algorithm_groups: name 有部分唯一索引 WHERE deleted = false。"""

    def test_delete_then_recreate_same_name(self, api_client):
        name = f'_test_sd_group_{_ts()}'
        # 1. Create
        resp = api_client.post('/algorithm/groups', json={'name': name})
        data = _unwrap(resp)
        group_id = data.get('id')
        assert group_id is not None

        # 2. Delete (soft)
        resp = api_client.delete(f'/algorithm/groups/{group_id}')
        _unwrap(resp)

        # 3. Recreate with same name — 应成功
        resp = api_client.post('/algorithm/groups', json={'name': name})
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != group_id  # 新记录，不是旧记录复活

        # 4. Cleanup
        api_client.delete(f'/algorithm/groups/{new_id}')


# ── Algorithm Device Params ───────────────────────────────
class TestSoftDeleteRecreateAlgorithmDeviceParams:
    """algorithm_device_params: (algorithm_type, param_code, direction) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_devparam_{_ts()}'
        param_code = '_test_param_sd'
        payload = {
            'algorithmType': algo_type,
            'paramCode': param_code,
            'paramName': 'Test SD Param',
            'paramType': 'text',
            'direction': 'input',
            'uiOrder': 1,
        }
        # 1. Create
        resp = api_client.post('/algorithm/params', json=payload)
        data = _unwrap(resp)
        param_id = data.get('id')
        assert param_id is not None

        # 2. Delete
        api_client.delete(f'/algorithm/params/{param_id}')

        # 3. Recreate same key — 应成功
        resp = api_client.post('/algorithm/params', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != param_id

        # 4. Cleanup
        api_client.delete(f'/algorithm/params/{new_id}')


# ── Algorithm API Params ──────────────────────────────────
class TestSoftDeleteRecreateAlgorithmApiParams:
    """algorithm_api_params: (algorithm_type, param_code, direction) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_apiparam_{_ts()}'
        param_code = '_test_api_param_sd'
        payload = {
            'algorithmType': algo_type,
            'paramCode': param_code,
            'paramName': 'Test SD API Param',
            'paramType': 'text',
            'direction': 'input',
            'uiOrder': 1,
        }
        # 通过 /algorithm/params 创建（路由根据 direction 自动判断表）
        resp = api_client.post('/algorithm/params', json=payload)
        data = _unwrap(resp)
        param_id = data.get('id')
        assert param_id is not None

        api_client.delete(f'/algorithm/params/{param_id}')

        resp = api_client.post('/algorithm/params', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != param_id

        api_client.delete(f'/algorithm/params/{new_id}')


# ── Algorithm Reference Params ────────────────────────────
class TestSoftDeleteRecreateReferenceParams:
    """algorithm_reference_params: (algorithm_type, code) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_ref_{_ts()}'
        code = '_test_ref_code_sd'
        payload = {
            'algorithmType': algo_type,
            'code': code,
            'name': 'Test SD Ref',
            'type': 'text',
        }
        resp = api_client.post('/algorithm/reference-params', json=payload)
        data = _unwrap(resp)
        ref_id = data.get('id')
        assert ref_id is not None

        api_client.delete(f'/algorithm/reference-params/{ref_id}')

        resp = api_client.post('/algorithm/reference-params', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != ref_id

        api_client.delete(f'/algorithm/reference-params/{new_id}')


# ── Algorithm Dimension Relations ─────────────────────────
class TestSoftDeleteRecreateDimensionRelations:
    """algorithm_dimension_relations: (algorithm_type, dimension_id) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_dimrel_{_ts()}'
        payload = {
            'algorithmType': algo_type,
            'dimensionId': 999,
            'isDefault': False,
            'weight': 1.0,
        }
        resp = api_client.post('/algorithm/dimension-relations', json=payload)
        data = _unwrap(resp)
        rel_id = data.get('id')
        assert rel_id is not None

        api_client.delete(f'/algorithm/dimension-relations/{rel_id}')

        resp = api_client.post('/algorithm/dimension-relations', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != rel_id

        api_client.delete(f'/algorithm/dimension-relations/{new_id}')


# ── Algorithm Case Params ─────────────────────────────────
class TestSoftDeleteRecreateCaseParams:
    """case_algorithm_params: (algorithm_type, param_code) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_case_{_ts()}'
        param_code = '_test_case_param_sd'
        payload = {
            'algorithmType': algo_type,
            'paramCode': param_code,
            'paramName': 'Test SD Case Param',
            'paramType': 'text',
            'uiOrder': 1,
            'scope': 'common',
        }
        resp = api_client.post('/algorithm/case-params', json=payload)
        data = _unwrap(resp)
        param_id = data.get('id')
        assert param_id is not None

        api_client.delete(f'/algorithm/case-params/{param_id}')

        resp = api_client.post('/algorithm/case-params', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != param_id

        api_client.delete(f'/algorithm/case-params/{new_id}')


# ── Algorithm Mappings ────────────────────────────────────
class TestSoftDeleteRecreateMappings:
    """param_mappings: (algorithm_type, source, source_param, dimension_id) 部分唯一索引。"""

    def test_delete_then_recreate_same_key(self, api_client):
        algo_type = f'_test_sd_mapping_{_ts()}'
        payload = {
            'algorithmType': algo_type,
            'sourceType': 'device',
            'sourceParam': '_test_source_sd',
            'sourceDirection': 'output',
            'dimensionId': 888,
            'targetParam': '_test_target_sd',
            'transformType': 'none',
        }
        resp = api_client.post('/algorithm/mappings', json=payload)
        data = _unwrap(resp)
        mapping_id = data.get('id')
        assert mapping_id is not None

        api_client.delete(f'/algorithm/mappings/{mapping_id}')

        resp = api_client.post('/algorithm/mappings', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != mapping_id

        api_client.delete(f'/algorithm/mappings/{new_id}')


# ── Playback Devices ──────────────────────────────────────
class TestSoftDeleteRecreatePlaybackDevices:
    """playback_devices: (device_unique_id, channel_index) 部分唯一索引 WHERE is_deleted = 0。

    删除后用相同 device_unique_id + channel_index 重建，应成功（直接新建，不恢复）。
    """

    def test_delete_then_recreate_same_key(self, api_client):
        unique_id = f'_test_sd_pb_{_ts()}'
        payload = {
            'name': '_test_sd_playback',
            'model': 'TestSpeaker',
            'deviceType': 'speaker',
            'sampleRate': 48000,
            'deviceUniqueId': unique_id,
            'channelIndex': 0,
        }
        # 1. Create
        resp = api_client.post('/playback-devices', json=payload)
        data = _unwrap(resp)
        device_id = data.get('id')
        assert device_id is not None

        # 2. Delete (soft)
        api_client.delete(f'/playback-devices/{device_id}')

        # 3. Recreate same key — 应成功（直接新建，软删记录不参与唯一索引）
        resp = api_client.post('/playback-devices', json=payload)
        data = _unwrap(resp)
        new_id = data.get('id')
        assert new_id is not None
        assert new_id != device_id  # 新记录，不是旧记录复活

        # 4. Cleanup
        api_client.delete(f'/playback-devices/{new_id}')


# ── Audio Algorithm Relations ─────────────────────────────
class TestSoftDeleteRecreateAudioAlgorithmRelations:
    """audio_algorithm_relations: (audio_id, algorithm_type) 部分唯一索引 WHERE deleted = false。

    audio_algorithm_relations 采用"全量软删 + 重建"模式：PUT /audios/{id}/algorithms
    会先软删所有旧关联，再创建新的。连续两次 PUT 同一算法不应报唯一约束冲突。
    需要已有 audio + task，因此用数据库直接插入 audio 记录。
    """

    def test_repeated_set_algorithms_no_conflict(self, api_client):
        import psycopg2
        ts = _ts()
        algo_type = f'_test_sd_algo_{ts}'

        # 1. 直接在数据库插入 audio 记录（绕过 upload/register 的 taskId 依赖）
        conn = psycopg2.connect(
            host='localhost', port=5432,
            dbname='intelligent_audio_test',
            user='intelligent_audio_test',
            password='intelligent_audio_test666',
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audios (name, file_path, size, duration, format, md5, "
                    "deleted, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, false, now(), now()) RETURNING id",
                    (f'_test_sd_audio_{ts}', f'/tmp/test_sd_{ts}.wav',
                     1000, 1.0, 'wav', f'test_md5_{ts}')
                )
                audio_id = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        try:
            algorithms_payload = {'algorithms': [
                {'algorithm_type': algo_type, 'is_primary': False, 'weight': 1.0},
            ]}

            # 2. First set — create relation
            resp = api_client.put(f'/audios/{audio_id}/algorithms', json=algorithms_payload)
            _unwrap(resp)

            # 3. Second set — soft delete old + create new
            #    部分唯一索引 WHERE deleted = false 使旧软删关联不冲突
            resp = api_client.put(f'/audios/{audio_id}/algorithms', json=algorithms_payload)
            _unwrap(resp)

            # 4. Third set — 再次设置，验证多次软删+重建不冲突
            resp = api_client.put(f'/audios/{audio_id}/algorithms', json=algorithms_payload)
            _unwrap(resp)
        finally:
            # 5. Cleanup: 删除 audio（级联清理 relations）
            conn = psycopg2.connect(
                host='localhost', port=5432,
                dbname='intelligent_audio_test',
                user='intelligent_audio_test',
                password='intelligent_audio_test666',
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM audio_algorithm_relations WHERE audio_id = %s", (audio_id,))
                    cur.execute("DELETE FROM audios WHERE id = %s", (audio_id,))
                conn.commit()
            finally:
                conn.close()
