#!/usr/bin/env python3
"""
检查数据库中的音频数据
"""
import sys
import os
# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath('.'))

from models.database import db
from models.models import Audio, TestCase, TestCaseGroup, TestCaseAudio

def check_audio_data():
    """检查音频数据"""
    print("=== 音频数据检查 ===")
    
    # 查询所有音频
    audios = Audio.query.filter_by(deleted=False).all()
    print(f"总共有 {len(audios)} 个音频文件:")
    for audio in audios:
        print(f"  ID: {audio.id}, 名称: {audio.name}, 类型: {audio.audio_type}, 时长: {audio.duration:.2f}s")
    
    print("\n=== 测试用例分组检查 ===")
    # 查询所有测试用例分组
    groups = TestCaseGroup.query.all()
    print(f"总共有 {len(groups)} 个测试用例分组:")
    for group in groups:
        print(f"  ID: {group.id}, 名称: {group.name}")
    
    print("\n=== 现有测试用例检查 ===")
    # 查询所有测试用例
    test_cases = TestCase.query.filter_by(deleted=False).all()
    print(f"总共有 {len(test_cases)} 个测试用例:")
    for test_case in test_cases:
        # 查询关联的音频
        case_audios = TestCaseAudio.query.filter_by(test_case_id=test_case.id).all()
        audio_count = len(case_audios)
        print(f"  ID: {test_case.id}, 名称: {test_case.name}, 关联音频数: {audio_count}")
        if audio_count > 0:
            for ca in case_audios:
                audio = db.session.get(Audio, ca.audio_id)
                print(f"    - 音频ID: {ca.audio_id}, 名称: {audio.name if audio else '未知'}")

if __name__ == "__main__":
    check_audio_data()
