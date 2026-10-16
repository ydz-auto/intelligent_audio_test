# -*- coding: utf-8 -*-
"""api_gateway 基础设施层 —— 实验室资源计数/子资源列表聚合读模型（INT-493/INT-537 拆分①）

实验室 counts 经 gRPC 聚合 device_service（ListDevices）/ audio_service
（ListPlaybackDevices）/ task_service（ListTestCases），单服务不可用计数容错为 0
（同 HomeStatsReadModel 模式）。

lab_id 过滤为拆分②③ RPC 新增参数（device/playback DTO 补 lab_id + list RPC 增
lab_id 过滤为拆分②；用例 lab 过滤含通用用例为拆分③）。本读模型以
``_supports_lab_id`` 探测 RPC 是否已支持 lab_id：
- 计数路径：RPC 未支持时容错为 0（避免把全库总数当成本实验室计数）；
- 子资源列表路径：RPC 未支持时退化为无过滤透传（路由骨架语义），随②③合入自动生效。
"""
import inspect

# 子资源列表默认分页（对齐各 List RPC 默认 per_page）
_DEFAULT_PER_PAGE = 10


class LaboratoryResourceReadModel:
    """实验室资源计数聚合 + 子资源列表（gRPC 透传）。"""

    # ---- RPC 能力探测 ----

    @staticmethod
    def _supports_lab_id(method) -> bool:
        """探测 List RPC 代理方法是否已支持 lab_id 参数（拆分②③是否合入）。"""
        try:
            return 'lab_id' in inspect.signature(method).parameters
        except (TypeError, ValueError):
            return False

    # ---- 计数聚合（容错为 0）----

    @staticmethod
    def _devices_total(lab_id: int) -> int:
        try:
            from api_gateway.infrastructure.grpc_proxies import device_config_service
            if not LaboratoryResourceReadModel._supports_lab_id(device_config_service.get_all):
                return 0  # 拆分② RPC lab_id 过滤未就绪：容错为 0
            resp = device_config_service.get_all(page=1, per_page=1, lab_id=lab_id)
            if not resp or not resp.get('success'):
                return 0
            data = resp.get('data') or {}
            return int(data.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _playback_devices_total(lab_id: int) -> int:
        try:
            from api_gateway.infrastructure.grpc_proxies import playback_config_service
            if not LaboratoryResourceReadModel._supports_lab_id(playback_config_service.get_all):
                return 0  # 拆分② RPC lab_id 过滤未就绪：容错为 0
            resp = playback_config_service.get_all(page=1, per_page=1, lab_id=lab_id)
            if not resp or not resp.get('success'):
                return 0
            data = resp.get('data') or {}
            return int(data.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _test_cases_total(lab_id: int) -> int:
        try:
            from api_gateway.infrastructure.grpc_proxies import testcase_config_service
            if not LaboratoryResourceReadModel._supports_lab_id(testcase_config_service.list_testcases):
                return 0  # 拆分③ RPC lab_id 过滤未就绪：容错为 0
            resp = testcase_config_service.list_testcases(page=1, per_page=1, lab_id=lab_id)
            if not resp or not resp.get('success'):
                return 0
            data = resp.get('data') or {}
            return int(data.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def counts(lab_id: int) -> dict:
        """实验室三资源计数：{device_count, playback_device_count, test_case_count}。"""
        return {
            'device_count': LaboratoryResourceReadModel._devices_total(lab_id),
            'playback_device_count': LaboratoryResourceReadModel._playback_devices_total(lab_id),
            'test_case_count': LaboratoryResourceReadModel._test_cases_total(lab_id),
        }

    # ---- 子资源列表（RPC 未支持 lab_id 时退化为无过滤透传）----

    @staticmethod
    def list_devices(lab_id: int, page: int = 1, per_page: int = _DEFAULT_PER_PAGE,
                     keyword: str = '') -> dict:
        try:
            from api_gateway.infrastructure.grpc_proxies import device_config_service
            kwargs = {'page': int(page or 1), 'per_page': int(per_page or _DEFAULT_PER_PAGE),
                      'keyword': keyword or ''}
            if LaboratoryResourceReadModel._supports_lab_id(device_config_service.get_all):
                kwargs['lab_id'] = lab_id
            resp = device_config_service.get_all(**kwargs)
            if not resp or not resp.get('success'):
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
            return resp.get('data') or {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
        except Exception:
            return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

    @staticmethod
    def list_playback_devices(lab_id: int, page: int = 1, per_page: int = _DEFAULT_PER_PAGE,
                              keyword: str = '') -> dict:
        try:
            from api_gateway.infrastructure.grpc_proxies import playback_config_service
            kwargs = {'page': int(page or 1), 'per_page': int(per_page or _DEFAULT_PER_PAGE),
                      'keyword': keyword or ''}
            if LaboratoryResourceReadModel._supports_lab_id(playback_config_service.get_all):
                kwargs['lab_id'] = lab_id
            resp = playback_config_service.get_all(**kwargs)
            if not resp or not resp.get('success'):
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
            return resp.get('data') or {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
        except Exception:
            return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

    @staticmethod
    def list_test_cases(lab_id: int, page: int = 1, per_page: int = _DEFAULT_PER_PAGE,
                        algorithm_type: str = '') -> dict:
        try:
            from api_gateway.infrastructure.grpc_proxies import testcase_config_service
            kwargs = {'page': int(page or 1), 'per_page': int(per_page or _DEFAULT_PER_PAGE),
                      'algorithm_type': algorithm_type or ''}
            if LaboratoryResourceReadModel._supports_lab_id(testcase_config_service.list_testcases):
                kwargs['lab_id'] = lab_id
            resp = testcase_config_service.list_testcases(**kwargs)
            if not resp or not resp.get('success'):
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
            return resp.get('data') or {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
        except Exception:
            return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
