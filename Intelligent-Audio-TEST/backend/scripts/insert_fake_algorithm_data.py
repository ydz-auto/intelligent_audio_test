# -*- coding: utf-8 -*-
"""
插入算法配置假数据
"""

import os
import sys
import json

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

from sqlalchemy import create_engine, text
engine = create_engine(f'sqlite:///{db_path}')


def insert_fake_data():
    """插入假数据"""
    with engine.connect() as conn:
        # 检查并插入算法分组
        result = conn.execute(text("SELECT COUNT(*) FROM algorithm_groups"))
        if result.fetchone()[0] == 0:
            groups = [
                ('翻译', '机器翻译算法，支持多语言互译', 'translate', 1),
                ('语音识别', '语音识别算法，将语音转换为文本', 'speech', 2),
                ('声纹识别', '声纹识别算法，识别说话人身份', 'voiceprint', 3),
                ('语音合成', '语音合成算法，将文本转换为语音', 'tts', 4),
            ]
            
            for name, description, icon, order in groups:
                conn.execute(text("""
                    INSERT INTO algorithm_groups (name, description, icon, display_order, deleted)
                    VALUES (:name, :description, :icon, :order, 0)
                """), {'name': name, 'description': description, 'icon': icon, 'order': order})
            
            print("算法分组插入完成")
        else:
            print("算法分组已存在，跳过插入")
        
        # 检查并插入算法定义
        result = conn.execute(text("SELECT COUNT(*) FROM algorithm_definitions"))
        if result.fetchone()[0] == 0:
            algorithms = [
                ('translation', '机器翻译', 1, '多语言机器翻译服务', 'online', 1),
                ('asr', '语音识别(ASR)', 2, '自动语音识别服务', 'online', 2),
                ('speaker_recognition', '说话人识别', 3, '说话人身份识别服务', 'online', 3),
                ('tts', '语音合成(TTS)', 4, '文本转语音合成服务', 'online', 4),
                ('asr_eval', 'ASR评估', None, 'ASR识别准确率评估', 'online', 5),
            ]
            
            for type_code, name, group_id, description, status, order in algorithms:
                conn.execute(text("""
                    INSERT INTO algorithm_definitions (type, name, group_id, description, status, display_order, deleted)
                    VALUES (:type, :name, :group_id, :description, :status, :order, 0)
                """), {'type': type_code, 'name': name, 'group_id': group_id, 
                       'description': description, 'status': status, 'order': order})
            
            print("算法定义插入完成")
        else:
            print("算法定义已存在，跳过插入")
        
        # 检查并插入算法参数
        result = conn.execute(text("SELECT COUNT(*) FROM algorithm_params"))
        if result.fetchone()[0] == 0:
            params = [
                # 翻译参数
                ('translation', 'source_language', '源语言', 'select', True, 'zh', 'languages', 'code', 'name', 'basic', 1),
                ('translation', 'target_language', '目标语言', 'select', True, 'en', 'languages', 'code', 'name', 'basic', 2),
                ('translation', 'model', '翻译模型', 'select', False, 'default', 'translation_models', 'value', 'label', 'model', 3),
                
                # ASR参数
                ('asr', 'language', '语言', 'select', True, 'zh', 'languages', 'code', 'name', 'basic', 1),
                ('asr', 'model', '识别模型', 'select', False, 'default', 'asr_models', 'value', 'label', 'model', 2),
                ('asr', 'use_itn', '使用ITN', 'switch', False, 'true', None, None, None, 'advanced', 3),
                ('asr', 'use_punc', '使用标点', 'switch', False, 'true', None, None, None, 'advanced', 4),
                
                # 说话人识别参数
                ('speaker_recognition', 'language', '语言', 'select', True, 'zh', 'languages', 'code', 'name', 'basic', 1),
                ('speaker_recognition', 'threshold', '相似度阈值', 'slider', False, '0.5', None, None, None, 'advanced', 2),
                ('speaker_recognition', 'enrollment_num', '注册音频数量', 'number', False, '3', None, None, None, 'basic', 3),
                
                # TTS参数
                ('tts', 'language', '语言', 'select', True, 'zh', 'languages', 'code', 'name', 'basic', 1),
                ('tts', 'voice', '音色', 'select', True, 'default', 'voices', 'value', 'label', 'basic', 2),
                ('tts', 'speed', '语速', 'slider', False, '1.0', None, None, None, 'advanced', 3),
                ('tts', 'pitch', '音调', 'slider', False, '1.0', None, None, None, 'advanced', 4),
                ('tts', 'volume', '音量', 'slider', False, '1.0', None, None, None, 'advanced', 5),
                
                # ASR评估参数
                ('asr_eval', 'language', '语言', 'select', True, 'zh', 'languages', 'code', 'name', 'basic', 1),
                ('asr_eval', 'ref_text', '参考文本', 'textarea', True, None, None, None, None, 'basic', 2),
            ]
            
            for p in params:
                conn.execute(text("""
                    INSERT INTO algorithm_params 
                    (algorithm_type, param_code, param_name, param_type, required, default_value, 
                     options_source, options_field, options_label_field, ui_group, ui_order, deleted)
                    VALUES (:algorithm_type, :param_code, :param_name, :param_type, :required, :default_value,
                            :options_source, :options_field, :options_label_field, :ui_group, :ui_order, 0)
                """), {
                    'algorithm_type': p[0], 'param_code': p[1], 'param_name': p[2], 'param_type': p[3],
                    'required': p[4], 'default_value': p[5], 'options_source': p[6], 
                    'options_field': p[7], 'options_label_field': p[8], 'ui_group': p[9], 'ui_order': p[10]
                })
            
            print("算法参数插入完成")
        else:
            print("算法参数已存在，跳过插入")
        
        conn.commit()
        print("\n假数据插入完成!")


if __name__ == '__main__':
    insert_fake_data()
