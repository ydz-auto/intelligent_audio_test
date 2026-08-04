"""首页统计服务"""
from api_gateway.infrastructure.request_adapter import request
from sqlalchemy import func, desc
from shared.models.database import db
from shared.models.models import TestCase, Task, Device, TestCaseGroup, StatsCache
from api_gateway.schemas.home import HomeStatsDetails, HomeStatsRefreshRequest
from shared.utils.response import success_response, error_response
from shared.utils.report.stats_cache import refresh_stats_cache


class HomeService:
    """首页统计服务"""

    @staticmethod
    def get_stats_details():
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

    @staticmethod
    def refresh_stats():
        try:
            req = HomeStatsRefreshRequest.model_validate(request.get_json() or {})
            refresh_stats_cache()
            return success_response(message="统计缓存已刷新")
        except Exception as e:
            return error_response(message=f"刷新统计缓存失败: {str(e)}")

    @staticmethod
    def get_stats_summary():
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

            from api_gateway.schemas.home import RecentTaskItem, TopGroupItem, DeviceStatus, HomeStatsSummary
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
