#!/usr/bin/env python3
"""
验证所有测试用例都关联了音频
"""
import sys
import os

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))

from backend.app import create_app
from backend.models.models import TestCase, TestCaseAudio, Audio

def verify_test_case_audio():
    """验证所有测试用例都关联了音频"""
    app = create_app()
    
    with app.app_context():
        print("=== 验证所有测试用例都关联了音频 ===")
        
        # 查询所有未删除的测试用例
        test_cases = TestCase.query.filter_by(deleted=False).all()
        total_cases = len(test_cases)
        
        print(f"总共有 {total_cases} 个测试用例:")
        
        all_linked = True
        for case in test_cases:
            # 查询该用例关联的音频
            case_audios = TestCaseAudio.query.filter_by(test_case_id=case.id).all()
            
            if not case_audios:
                print(f"❌ 错误: 测试用例 '{case.name}' (ID: {case.id}) 未关联任何音频!")
                all_linked = False
            else:
                # 查询音频详情
                audio_names = []
                for ca in case_audios:
                    audio = db.session.get(Audio, ca.audio_id)
                    if audio:
                        audio_names.append(f"'{audio.name}' (ID: {audio.id})")
                    else:
                        audio_names.append(f"音频ID: {ca.audio_id} (已删除)")
                
                audio_str = ', '.join(audio_names)
                print(f"✅ 测试用例 '{case.name}' (ID: {case.id}) 关联了 {len(case_audios)} 个音频: {audio_str}")
        
        print("\n=== 验证结果 ===")
        if all_linked:
            print(f"🎉 所有 {total_cases} 个测试用例都已成功关联到音频!")
        else:
            print(f"❌ 存在未关联音频的测试用例，需要修复!")
        
        return all_linked

if __name__ == "__main__":
    verify_test_case_audio()
