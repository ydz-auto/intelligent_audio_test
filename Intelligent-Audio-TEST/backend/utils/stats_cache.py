"""
统计缓存刷新工具

提供自动刷新统计缓存的功能，在数据变化时调用。
"""
from flask import Blueprint
from sqlalchemy import func
from backend.models.database import db
from backend.models.models import TestCase, Task, Device, Audio, PlaybackDevice, API, Report, TestCaseGroup, Dimension
from datetime import datetime, timezone, timedelta

stats_cache_bp = Blueprint('stats_cache', __name__)


def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))


def refresh_stats_cache():
    """
    刷新统计缓存

    在数据增删改后调用此函数更新缓存
    """
    try:
        test_cases_count = db.session.query(func.count(TestCase.id)).filter(
            TestCase.deleted == False
        ).scalar() or 0

        test_case_groups_count = db.session.query(func.count(TestCaseGroup.id)).scalar() or 0

        tasks_count = db.session.query(func.count(Task.id)).filter(
            Task.deleted == False
        ).scalar() or 0

        tasks_completed = db.session.query(func.count(Task.id)).filter(
            Task.deleted == False,
            Task.status == 'completed'
        ).scalar() or 0

        tasks_running = db.session.query(func.count(Task.id)).filter(
            Task.deleted == False,
            Task.status == 'running'
        ).scalar() or 0

        tasks_failed = db.session.query(func.count(Task.id)).filter(
            Task.deleted == False,
            Task.status == 'failed'
        ).scalar() or 0

        devices_online = db.session.query(func.count(Device.id)).filter(
            Device.status == 'online',
            Device.deleted == False
        ).scalar() or 0

        devices_offline = db.session.query(func.count(Device.id)).filter(
            Device.status == 'offline',
            Device.deleted == False
        ).scalar() or 0

        audio_dry_count = db.session.query(func.count(Audio.id)).filter(
            Audio.audio_type == 'dry',
            Audio.deleted == False
        ).scalar() or 0

        audio_noise_count = db.session.query(func.count(Audio.id)).filter(
            Audio.audio_type == 'noise',
            Audio.deleted == False
        ).scalar() or 0

        audio_prompt_count = db.session.query(func.count(Audio.id)).filter(
            Audio.audio_type == 'prompt',
            Audio.deleted == False
        ).scalar() or 0

        audio_files_count = db.session.query(func.count(Audio.id)).filter(
            Audio.deleted == False
        ).scalar() or 0

        audio_total_duration = db.session.query(func.coalesce(func.sum(Audio.duration), 0)).filter(
            Audio.deleted == False
        ).scalar() or 0

        audio_dry_duration = db.session.query(func.coalesce(func.sum(Audio.duration), 0)).filter(
            Audio.audio_type == 'dry',
            Audio.deleted == False
        ).scalar() or 0

        audio_noise_duration = db.session.query(func.coalesce(func.sum(Audio.duration), 0)).filter(
            Audio.audio_type == 'noise',
            Audio.deleted == False
        ).scalar() or 0

        audio_prompt_duration = db.session.query(func.coalesce(func.sum(Audio.duration), 0)).filter(
            Audio.audio_type == 'prompt',
            Audio.deleted == False
        ).scalar() or 0

        playback_devices_count = db.session.query(func.count(PlaybackDevice.id)).scalar() or 0

        apis_online = db.session.query(func.count(API.id)).filter(
            API.status == 'online',
            API.deleted == False
        ).scalar() or 0

        apis_offline = db.session.query(func.count(API.id)).filter(
            API.status == 'offline',
            API.deleted == False
        ).scalar() or 0

        reports_count = db.session.query(func.count(Report.id)).scalar() or 0

        dimensions_count = db.session.query(func.count(Dimension.id)).filter(
            Dimension.deleted == False
        ).scalar() or 0

        dimensions_with_endpoints = db.session.query(func.count(Dimension.id)).filter(
            Dimension.deleted == False,
            Dimension.api_endpoints != None,
            Dimension.api_endpoints != '[]'
        ).scalar() or 0

        dimensions_endpoints_total = 0
        dimensions_data = db.session.query(Dimension.api_endpoints).filter(
            Dimension.deleted == False,
            Dimension.api_endpoints != None,
            Dimension.api_endpoints != '[]'
        ).all()
        for api_endpoints, in dimensions_data:
            if api_endpoints and isinstance(api_endpoints, list):
                dimensions_endpoints_total += len(api_endpoints)

        cache_value = {
            'test_cases': {
                'total': test_cases_count,
                'groups': test_case_groups_count
            },
            'tasks': {
                'total': tasks_count,
                'completed': tasks_completed,
                'running': tasks_running,
                'failed': tasks_failed
            },
            'devices': {
                'online': devices_online,
                'offline': devices_offline,
                'total': devices_online + devices_offline
            },
            'audio_files': {
                'total': audio_files_count,
                'dry': audio_dry_count,
                'noise': audio_noise_count,
                'prompt': audio_prompt_count,
                'duration': {
                    'total': audio_total_duration,
                    'dry': audio_dry_duration,
                    'noise': audio_noise_duration,
                    'prompt': audio_prompt_duration
                }
            },
            'playback_devices': playback_devices_count,
            'apis': {
                'online': apis_online,
                'offline': apis_offline,
                'total': apis_online + apis_offline
            },
            'reports': reports_count,
            'dimensions': {
                'total': dimensions_count,
                'with_endpoints': dimensions_with_endpoints,
                'endpoints': dimensions_endpoints_total
            },
            'updated_at': utc8now().isoformat()
        }

        from backend.models.models import StatsCache
        cache_entry = db.session.query(StatsCache).filter(
            StatsCache.cache_key == 'home_stats'
        ).first()

        if cache_entry:
            cache_entry.cache_value = cache_value
            cache_entry.updated_at = utc8now()
        else:
            cache_entry = StatsCache(
                cache_key='home_stats',
                cache_value=cache_value
            )
            db.session.add(cache_entry)

        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        print(f"刷新统计缓存失败: {str(e)}")
        return False
