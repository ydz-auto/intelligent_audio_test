#!/usr/bin/env python3
"""
添加测试用例数据，确保关联到音频表中的音频
"""
import sys
import os
import json
from datetime import datetime

# Add the project root directory to Python path (test-task-managerV12231730)
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))

from backend.app import create_app
from backend.models.database import db
from backend.models.models import (
    Audio, TestCase, TestCaseGroup, TestCaseAudio
)

def add_test_case_data():
    """添加测试用例数据，确保关联到音频"""
    # Create app context to access database
    app = create_app()
    
    with app.app_context():
        print("=== 音频数据检查 ===")
        # 查询所有未删除的音频
        audios = Audio.query.filter_by(deleted=False).all()
        print(f"总共有 {len(audios)} 个音频文件:")
        
        # 按类型分组音频
        audio_by_type = {}
        for audio in audios:
            print(f"  ID: {audio.id}, 名称: {audio.name}, 类型: {audio.audio_type}")
            if audio.audio_type not in audio_by_type:
                audio_by_type[audio.audio_type] = []
            audio_by_type[audio.audio_type].append(audio)
        
        # 确保至少有音频可用
        if not audios:
            print("错误: 数据库中没有可用音频，请先添加音频数据!")
            return
        
        print("\n=== 现有测试用例分组 ===")
        # 查询所有测试用例分组
        groups = TestCaseGroup.query.all()
        print(f"总共有 {len(groups)} 个测试用例分组:")
        for group in groups:
            print(f"  ID: {group.id}, 名称: {group.name}")
        
        # 如果没有分组，创建一个默认分组
        if not groups:
            default_group = TestCaseGroup(
                id="default",
                name="默认分组",
                description="默认测试用例分组"
            )
            db.session.add(default_group)
            db.session.commit()
            groups = [default_group]
            print("\n已创建默认测试用例分组")
        
        print("\n=== 现有测试用例 ===")
        # 查询所有未删除的测试用例
        existing_cases = TestCase.query.filter_by(deleted=False).all()
        print(f"总共有 {len(existing_cases)} 个测试用例:")
        
        # 添加测试用例数据
        print("\n=== 添加测试用例数据 ===")
        
        # 准备测试用例数据，确保每个用例都关联到音频
        test_cases_data = [
            {
                "name": "基础API测试用例",
                "description": "测试基础API功能",
                "group_id": groups[0].id,
                "audio_type": "dry",
                "test_type": "api",
                "config": {"param1": "value1", "param2": "value2"}
            },
            {
                "name": "E2E测试用例",
                "description": "端到端测试用例",
                "group_id": groups[0].id,
                "audio_type": "dry",
                "test_type": "e2e",
                "config": {"param1": "value1", "param2": "value2"}
            },
            {
                "name": "噪音环境测试",
                "description": "在噪音环境下测试",
                "group_id": groups[0].id,
                "audio_type": "dry",
                "test_type": "api",
                "config": {"param1": "value1", "param2": "value2"}
            }
        ]
        
        added_count = 0
        for case_data in test_cases_data:
            # 检查是否已有同名用例
            existing_case = TestCase.query.filter_by(
                name=case_data["name"],
                deleted=False
            ).first()
            
            if existing_case:
                print(f"跳过: 测试用例 '{case_data['name']}' 已存在")
                continue
            
            # 获取对应类型的音频
            audio_type = case_data["audio_type"]
            if audio_type not in audio_by_type or not audio_by_type[audio_type]:
                # 如果没有对应类型的音频，使用任意音频
                audio = audios[0]
            else:
                audio = audio_by_type[audio_type][0]
            
            # 创建测试用例
            test_case = TestCase(
                id=f"case_{int(datetime.utcnow().timestamp())}_{added_count}",
                name=case_data["name"],
                description=case_data["description"],
                config=case_data["config"],
                group_id=case_data["group_id"]
            )
            db.session.add(test_case)
            db.session.commit()
            
            # 创建测试用例与音频的关联
            test_case_audio = TestCaseAudio(
                test_case_id=test_case.id,
                audio_id=audio.id,
                test_type=case_data["test_type"],
                spl=70.0,  # 默认声压级
                playback_device_id=None,
                play_order=0
            )
            db.session.add(test_case_audio)
            db.session.commit()
            
            print(f"已添加: 测试用例 '{test_case.name}' 关联到音频 '{audio.name}'")
            added_count += 1
        
        print(f"\n总共添加了 {added_count} 个测试用例")
        
        # 检查所有用例是否都关联了音频
        print("\n=== 验证所有用例都关联了音频 ===")
        all_cases = TestCase.query.filter_by(deleted=False).all()
        for case in all_cases:
            case_audios = TestCaseAudio.query.filter_by(test_case_id=case.id).all()
            if not case_audios:
                print(f"警告: 测试用例 '{case.name}' 未关联任何音频!")
                # 为未关联音频的用例添加关联
                audio = audios[0]  # 使用第一个音频
                test_case_audio = TestCaseAudio(
                    test_case_id=case.id,
                    audio_id=audio.id,
                    test_type="api",
                    spl=70.0,
                    playback_device_id=None,
                    play_order=0
                )
                db.session.add(test_case_audio)
                db.session.commit()
                print(f"已修复: 为测试用例 '{case.name}' 添加了音频关联")
        
        print("\n=== 完成 ===")
        print("所有测试用例都已关联到音频!")

if __name__ == "__main__":
    add_test_case_data()
