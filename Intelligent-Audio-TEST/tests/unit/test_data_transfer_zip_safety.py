# -*- coding: utf-8 -*-
"""任务数据导入导出 —— ZIP 安全与包结构单测（防 zip-slip / 版本门禁 / roundtrip）"""
import json
import os
import zipfile

import pytest

# zip_io 经包 __init__ 引入 storage（BaseConfig 在 import 时读环境变量），测试环境补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.constants.data_transfer import (
    SUPPORTED_MANIFEST_VERSIONS,
    TransferTable,
)
from task_service.domain.services.data_transfer import (
    ManifestError,
    build_manifest,
    validate_manifest,
)
from task_service.infrastructure.transfer.zip_io import (
    build_zip,
    iter_file_entries,
    read_db_tables,
    read_manifest,
    safe_zip_entry_name,
)


class TestZipEntryNameSafety:
    def test_valid_names_pass(self):
        assert safe_zip_entry_name('db/test_tasks.json', ['db/']) == 'db/test_tasks.json'
        assert safe_zip_entry_name('files/case_results/2/c/dev/x.json', ['files/']) == \
            'files/case_results/2/c/dev/x.json'

    def test_zip_slip_rejected(self):
        for bad in ('../evil.json', 'db/../../evil.json', '/abs/evil.json',
                    'db\\evil.json', 'files/./../x'):
            with pytest.raises(ValueError):
                safe_zip_entry_name(bad, ['db/', 'files/', 'meta/'])

    def test_outside_allowed_prefix_rejected(self):
        with pytest.raises(ValueError):
            safe_zip_entry_name('other/x.json', ['db/', 'files/', 'meta/'])


class TestManifestValidation:
    def test_valid_manifest_passes(self):
        manifest = build_manifest(
            task_rows=[{'id': 1, 'name': 'A', 'type': 'api', 'status': 'completed'}],
            result_rows=[{'id': 9, 'task_id': 1}],
            dimension_count=4, report_count=1, file_count=2, total_file_size=128,
        )
        assert manifest['version'] in SUPPORTED_MANIFEST_VERSIONS
        assert manifest['stats']['taskCount'] == 1
        assert manifest['stats']['resultCount'] == 1
        assert manifest['tasks'][0]['resultCount'] == 1
        out = validate_manifest(manifest)
        assert out['options']['includeRefParams'] is True

    def test_version_mismatch_rejected(self):
        with pytest.raises(ManifestError):
            validate_manifest({'version': '9.9', 'tasks': []})

    def test_missing_version_rejected(self):
        with pytest.raises(ManifestError):
            validate_manifest({'tasks': []})

    def test_missing_tasks_rejected(self):
        with pytest.raises(ManifestError):
            validate_manifest({'version': '1.0'})

    def test_none_manifest_rejected(self):
        with pytest.raises(ManifestError):
            validate_manifest(None)


def _write_sample_zip(path):
    db_tables = {table.value: [] for table in TransferTable}
    db_tables['test_tasks'] = [{'id': 1, 'name': 'A'}]
    manifest = build_manifest(
        task_rows=[{'id': 1, 'name': 'A', 'type': 'api', 'status': 'completed'}],
        result_rows=[], dimension_count=0, report_count=0,
        file_count=1, total_file_size=3,
    )
    file_entries = iter([('case_results/1/c1/dev1/result_data.json', b'abc')])
    count = build_zip(str(path), db_tables, manifest, file_entries,
                      dimensions_snapshot=[{'id': 1, 'name': 'dim'}])
    return count, manifest


class TestZipRoundtrip:
    def test_build_then_read(self, tmp_path):
        zip_path = tmp_path / 'export.zip'
        file_count, manifest = _write_sample_zip(zip_path)
        assert file_count == 1

        assert read_manifest(str(zip_path))['stats']['taskCount'] == \
            manifest['stats']['taskCount']

        tables = read_db_tables(str(zip_path))
        assert set(tables) == {t.value for t in TransferTable}
        assert tables['test_tasks'] == [{'id': 1, 'name': 'A'}]

        entries = list(iter_file_entries(str(zip_path), 'files/case_results'))
        assert entries == [('1/c1/dev1/result_data.json', b'abc')]

    def test_reader_rejects_slip_entry(self, tmp_path):
        """打包侧恶意构造 ../ 条目时，读取/迭代侧必须拒绝（防 zip-slip）"""
        zip_path = tmp_path / 'evil.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('files/case_results/../../evil.json', b'x')
        with pytest.raises(ValueError):
            list(iter_file_entries(str(zip_path), 'files/case_results'))

    def test_read_manifest_missing(self, tmp_path):
        zip_path = tmp_path / 'empty.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('other.json', '{}')
        with pytest.raises(ValueError):
            read_manifest(str(zip_path))

    def test_db_json_non_array_rejected(self, tmp_path):
        zip_path = tmp_path / 'bad_db.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', json.dumps({'version': '1.0', 'tasks': []}))
            zf.writestr('db/test_tasks.json', json.dumps({'id': 1}))
        with pytest.raises(ValueError):
            read_db_tables(str(zip_path))
