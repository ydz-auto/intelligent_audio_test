"""
首页统计信息控制器 (Home Stats Controller)

提供首页统计数据接口，包括测试用例数、任务数、设备数和音频文件数等。
支持缓存机制以提升性能。
"""
from flask import Blueprint, request
from sqlalchemy import func, desc
from backend.models.database import db
from backend.models.models import TestCase, Task, Device, TestCaseGroup, StatsCache
from backend.schemas.home import HomeStatsDetails, HomeStatsRefreshRequest
from backend.utils.web.response import success_response, error_response
from backend.utils.report.stats_cache import refresh_stats_cache

home_bp = Blueprint('home', __name__)


@home_bp.route('/stats/details', methods=['GET'])
def get_stats_details():
    """
    获取首页统计详细信息（使用缓存）

    返回更详细的统计数据
    """
    try:
        cache_entry = db.session.query(StatsCache).filter(
            StatsCache.cache_key == 'home_stats'
        ).first()

        if cache_entry and cache_entry.cache_value:
            stats_data = HomeStatsDetails(**cache_entry.cache_value)
            return success_response(data=stats_data)

        refresh_stats_cache()

        cache_entry = db.session.query(StatsCache).filter(
            StatsCache.cache_key == 'home_stats'
        ).first()

        if cache_entry:
            stats_data = HomeStatsDetails(**cache_entry.cache_value)
            return success_response(data=stats_data)

        return success_response(data=HomeStatsDetails())

    except Exception as e:
        return error_response(message=f"获取统计详情失败: {str(e)}")


@home_bp.route('/stats/refresh', methods=['POST'])
def refresh_stats():
    """
    手动刷新统计缓存

    当数据发生变化时调用此接口更新缓存
    """
    try:
        req = HomeStatsRefreshRequest.model_validate(request.get_json() or {})
        refresh_stats_cache()
        return success_response(message="统计缓存已刷新")
    except Exception as e:
        return error_response(message=f"刷新统计缓存失败: {str(e)}")


@home_bp.route('/stats/summary', methods=['GET'])
def get_stats_summary():
    """
    获取首页汇总统计信息（用于展示最新数据，不使用缓存）

    返回:
        - recentTasks: 最近的任务
        - topGroups: 用例数量最多的分组
        - deviceStatus: 设备状态概览
    """
    try:
        recent_tasks = db.session.query(Task).filter(
            Task.deleted == False
        ).order_by(
            desc(Task.created_at)
        ).limit(5).all()

        top_groups = db.session.query(
            TestCaseGroup,
            func.count(TestCase.id).label('case_count')
        ).outerjoin(TestCase, db.and_(
            TestCase.deleted == False,
            TestCase.group_id == TestCaseGroup.id
        )).group_by(TestCaseGroup.id).order_by(
            desc('case_count')
        ).limit(5).all()

        from backend.schemas.home import RecentTaskItem, TopGroupItem, DeviceStatus, HomeStatsSummary
        recent_tasks_data = []
        for task in recent_tasks:
            recent_tasks_data.append(
                RecentTaskItem(
                    id=task.id,
                    name=task.name,
                    type=task.type,
                    status=task.status,
                    algorithm_type=task.algorithm_type,
                    total_cases=task.total_cases,
                    completed_cases=task.completed_cases,
                    created_at=task.created_at.isoformat() if task.created_at else None
                )
            )

        top_groups_data = []
        for group, case_count in top_groups:
            top_groups_data.append(
                TopGroupItem(
                    id=group.id,
                    name=group.name,
                    case_count=case_count
                )
            )

        device_status = DeviceStatus(
            online=db.session.query(func.count(Device.id)).filter(
                Device.status == 'online',
                Device.deleted == False
            ).scalar() or 0,
            offline=db.session.query(func.count(Device.id)).filter(
                Device.status == 'offline',
                Device.deleted == False
            ).scalar() or 0
        )

        summary = HomeStatsSummary(
            recentTasks=recent_tasks_data,
            topGroups=top_groups_data,
            deviceStatus=device_status
        )

        return success_response(data=summary)

    except Exception as e:
        return error_response(message=f"获取汇总统计失败: {str(e)}")
