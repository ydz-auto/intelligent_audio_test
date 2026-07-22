# -*- coding: utf-8 -*-
"""
algorithm_params field_value 数字转字符串迁移脚本

将数据库中已有的 algorithm_params 中的数字格式 field_value 转为字符串格式
例如: {"field_value": 1} -> {"field_value": "1"}

使用方法:
    python migrate_algorithm_params_to_string.py
"""
import os
import json
import psycopg2


def get_db_config():
    db_user = os.environ.get('DB_USER', 'intelligent_audio_test')
    db_password = os.environ.get('DB_PASSWORD', 'intelligent_audio_test666')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'intelligent_audio_test')
    
    return {
        'host': db_host,
        'port': db_port,
        'database': db_name,
        'user': db_user,
        'password': db_password
    }


def convert_field_value_to_string(params):
    """
    将 algorithm_params 或 reference_params 中的 field_value 数字转为字符串
    
    Args:
        params: 参数列表
        
    Returns:
        转换后的参数列表，如果无需转换返回 None
    """
    if not params:
        return None
    
    if not isinstance(params, list):
        return None
    
    converted = []
    has_change = False
    
    for item in params:
        if isinstance(item, dict):
            new_item = item.copy()
            field_value = new_item.get('field_value', new_item.get('fieldValue'))
            if field_value is not None and isinstance(field_value, (int, float)):
                new_item['field_value'] = str(field_value)
                if 'fieldValue' in new_item:
                    new_item['fieldValue'] = str(field_value)
                has_change = True
            converted.append(new_item)
        else:
            converted.append(item)
    
    if has_change:
        return converted
    return None


def migrate_algorithm_params():
    """
    迁移 test_cases 表中的 algorithm_params 字段
    """
    config = get_db_config()
    
    print("=" * 60)
    print("algorithm_params field_value 数字转字符串迁移")
    print("=" * 60)
    
    conn = psycopg2.connect(**config)
    conn.autocommit = False
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, name, algorithm_params 
            FROM test_cases 
            WHERE deleted = false 
            AND algorithm_params IS NOT NULL
        """)
        
        rows = cursor.fetchall()
        total_count = len(rows)
        updated_count = 0
        
        print(f"\n找到 {total_count} 个测试用例")
        print("-" * 60)
        
        for row in rows:
            tc_id = row[0]
            tc_name = row[1]
            original_params = row[2]
            
            if not original_params:
                continue
            
            converted_params = convert_field_value_to_string(original_params)
            
            if converted_params is not None:
                cursor.execute("""
                    UPDATE test_cases 
                    SET algorithm_params = %s 
                    WHERE id = %s
                """, (json.dumps(converted_params, ensure_ascii=False), tc_id))
                
                updated_count += 1
                param_str = json.dumps(converted_params, ensure_ascii=False)[:100]
                print(f"  [{tc_id[:8]}] {tc_name[:30]}: {param_str}...")
        
        if updated_count > 0:
            conn.commit()
            print("-" * 60)
            print(f"已更新 {updated_count} 个测试用例的 algorithm_params")
        else:
            print("-" * 60)
            print("无需更新，所有 field_value 已为字符串格式")
        
        print("=" * 60)
        print("迁移完成!")
        print("=" * 60)
        
    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    migrate_algorithm_params()