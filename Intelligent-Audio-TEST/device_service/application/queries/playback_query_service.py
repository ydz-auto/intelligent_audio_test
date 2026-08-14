# -*- coding: utf-8 -*-
"""播放设备 Query 应用服务（读侧）

CQRS 拆分后的纯读操作服务，包含 get_all/get_one/scan。
- scan 仅读取物理设备列表并与已注册设备做差集，不更新设备状态，故归 query 侧。
- 方法签名和实现与原 playback_crud_service 完全一致。
"""
import logging

from device_service.domain.repositories import PlaybackRepositoryInterface, SPLRepositoryInterface

logger = logging.getLogger(__name__)


class PlaybackQueryService:
    """播放设备 Query 应用服务（读侧）"""

    def __init__(self, repo: PlaybackRepositoryInterface = None, spl_repo: SPLRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import playback_repository
            repo = playback_repository
        if spl_repo is None:
            from device_service.infrastructure.persistence.device_repository import spl_repository
            spl_repo = spl_repository
        self.repo = repo
        self.spl_repo = spl_repo

    @staticmethod
    def _get_physical_devices_via_grpc():
        """通过 ACL 仓储获取物理设备列表"""
        from device_service.infrastructure.acl.audio_service_acl_repository import audio_service_acl_repository
        return audio_service_acl_repository.get_physical_devices()

    # ========== 读操作 ==========

    def get_all(self, page: int = 1, per_page: int = 10, keyword: str = None,
                device_type: str = None) -> dict:
        """分页查询"""
        try:
            result = self.repo.list_playback_devices(
                page=page, per_page=per_page, keyword=keyword, device_type=device_type,
            )
            return {'success': True, 'message': 'Success', 'data': result, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, device_id: int) -> dict:
        """查询详情"""
        device = self.repo.get_playback_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}

        return {'success': True, 'message': 'Success', 'data': device.to_dict(), 'code': 200}

    def scan(self) -> dict:
        """扫描物理播放通道"""
        try:
            physical_devices = self._get_physical_devices_via_grpc()

            registered = self.repo.get_all_playback_devices()
            registered_keys = set([f'{d.device_unique_id}_{d.channel_index}' for d in registered])

            scanned_results = []
            for dev in physical_devices:
                key = f"{dev['unique_id']}_{dev['channel_index']}"
                if key not in registered_keys:
                    scanned_results.append({
                        'name': dev['name'],
                        'model': f"Hardware Channel ({dev['host_api']})",
                        'device_unique_id': dev['unique_id'],
                        'channel_index': dev['channel_index'],
                        'sample_rate': dev['sample_rate'],
                        'type': 'dry',
                        'status': 'online',
                    })

            return {
                'success': True,
                'message': f'成功扫描到 {len(scanned_results)} 个新通道',
                'data': scanned_results,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': f'扫描失败: {str(e)}', 'data': None, 'code': 400}


# 模块级实例
playback_query_service = PlaybackQueryService()
