#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统计缓存刷新脚本

用于初始化或刷新首页统计数据缓存。
可在系统启动时或数据变更后运行，确保首页统计数据显示正确。
"""
import sys
import os

# 添加 backend 目录到 Python 路径
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# 尝试从项目根目录添加路径（如果在 backend 目录下运行）
project_root = os.path.dirname(backend_path)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.models.database import db
from backend.models.models import StatsCache
from backend.utils.stats_cache import refresh_stats_cache
from app import create_app


def init_stats_cache():
    """
    初始化统计缓存

    如果缓存不存在则创建，存在则刷新
    """
    print("正在初始化统计缓存...")

    try:
        result = refresh_stats_cache()

        if result:
            cache_entry = db.session.query(StatsCache).filter(
                StatsCache.cache_key == 'home_stats'
            ).first()

            if cache_entry and cache_entry.cache_value:
                cache_data = cache_entry.cache_value
                print("\n✅ 统计缓存初始化成功！")
                print("\n当前统计数据：")
                print(f"  测试用例: {cache_data.get('testCases', {}).get('total', 0)} 个")
                print(f"  用例分组: {cache_data.get('testCases', {}).get('groups', 0)} 个")
                print(f"  测试任务: {cache_data.get('tasks', {}).get('total', 0)} 个")
                print(f"  评估指标: {cache_data.get('dimensions', 0)} 个")
                print(f"  音频文件: {cache_data.get('audioFiles', {}).get('total', 0)} 个")
                print(f"  在线设备: {cache_data.get('devices', {}).get('online', 0)} 个")
                print(f"  API服务: {cache_data.get('apis', {}).get('online', 0)} 个")
                print(f"\n更新时间: {cache_data.get('updatedAt', '未知')}")
                return True
            else:
                print("❌ 缓存更新后未找到缓存条目")
                return False
        else:
            print("❌ 统计缓存刷新失败")
            return False

    except Exception as e:
        print(f"❌ 初始化统计缓存时出错: {str(e)}")
        return False


def clear_stats_cache():
    """
    清空统计缓存
    """
    print("正在清空统计缓存...")

    try:
        deleted = db.session.query(StatsCache).filter(
            StatsCache.cache_key == 'home_stats'
        ).delete()

        db.session.commit()
        print(f"✅ 已删除 {deleted} 条缓存记录")
        return True

    except Exception as e:
        print(f"❌ 清空缓存时出错: {str(e)}")
        return False


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='统计缓存管理脚本')
    parser.add_argument('--init', action='store_true', help='初始化/刷新统计缓存')
    parser.add_argument('--clear', action='store_true', help='清空统计缓存')
    parser.add_argument('--force', action='store_true', help='强制刷新（先清空再创建）')

    args = parser.parse_args()

    if not any([args.init, args.clear, args.force]):
        parser.print_help()
        print("\n示例:")
        print("  python init_stats_cache.py --init    # 初始化统计缓存")
        print("  python init_stats_cache.py --clear   # 清空统计缓存")
        print("  python init_stats_cache.py --force   # 强制刷新（先清空后创建）")
        return

    app = create_app()
    with app.app_context():
        if args.clear or args.force:
            clear_stats_cache()
            if args.clear:
                return

        if args.init or args.force:
            init_stats_cache()


if __name__ == '__main__':
    main()
