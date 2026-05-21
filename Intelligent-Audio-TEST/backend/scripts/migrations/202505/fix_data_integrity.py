"""
数据完整性检查和修复脚本

检查并清理外键引用不一致的数据
"""
import os
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

def check_and_clean_integrity():
    config = get_db_config()
    
    print("=" * 60)
    print("数据完整性检查与修复")
    print("=" * 60)
    
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cursor = conn.cursor()
    
    checks = [
        {
            'name': 'task_case_relations -> test_tasks',
            'table': 'task_case_relations',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'task_tags -> test_tasks',
            'table': 'task_tags',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'task_device_relations -> test_tasks',
            'table': 'task_device_relations',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'task_api_relations -> test_tasks',
            'table': 'task_api_relations',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'task_merge_relations -> test_tasks (merged)',
            'table': 'task_merge_relations',
            'fk_column': 'merged_task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'task_merge_relations -> test_tasks (source)',
            'table': 'task_merge_relations',
            'fk_column': 'source_task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'test_results -> test_tasks',
            'table': 'test_results',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'test_reports -> test_tasks',
            'table': 'test_reports',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'logs -> test_tasks',
            'table': 'logs',
            'fk_column': 'task_id',
            'ref_table': 'test_tasks',
            'ref_column': 'id'
        },
        {
            'name': 'user_permissions -> users',
            'table': 'user_permissions',
            'fk_column': 'user_id',
            'ref_table': 'users',
            'ref_column': 'id'
        },
        {
            'name': 'user_permissions -> permissions',
            'table': 'user_permissions',
            'fk_column': 'permission_id',
            'ref_table': 'permissions',
            'ref_column': 'id'
        },
        {
            'name': 'tags -> tag_categories',
            'table': 'tags',
            'fk_column': 'category_id',
            'ref_table': 'tag_categories',
            'ref_column': 'id'
        },
        {
            'name': 'test_case_tags -> tags',
            'table': 'test_case_tags',
            'fk_column': 'tag_id',
            'ref_table': 'tags',
            'ref_column': 'id'
        },
        {
            'name': 'device_tags -> devices',
            'table': 'device_tags',
            'fk_column': 'device_id',
            'ref_table': 'devices',
            'ref_column': 'id'
        },
        {
            'name': 'device_tags -> tags',
            'table': 'device_tags',
            'fk_column': 'tag_id',
            'ref_table': 'tags',
            'ref_column': 'id'
        },
        {
            'name': 'audio_annotations -> audios',
            'table': 'audio_annotations',
            'fk_column': 'audio_id',
            'ref_table': 'audios',
            'ref_column': 'id'
        },
        {
            'name': 'audio_tags -> audios',
            'table': 'audio_tags',
            'fk_column': 'audio_id',
            'ref_table': 'audios',
            'ref_column': 'id'
        },
        {
            'name': 'audio_tags -> tags',
            'table': 'audio_tags',
            'fk_column': 'tag_id',
            'ref_table': 'tags',
            'ref_column': 'id'
        },
        {
            'name': 'audio_algorithm_relations -> audios',
            'table': 'audio_algorithm_relations',
            'fk_column': 'audio_id',
            'ref_table': 'audios',
            'ref_column': 'id'
        },
        {
            'name': 'prompt_audio_relations -> audios',
            'table': 'prompt_audio_relations',
            'fk_column': 'audio_id',
            'ref_table': 'audios',
            'ref_column': 'id'
        },
        {
            'name': 'prompt_audio_relations -> devices',
            'table': 'prompt_audio_relations',
            'fk_column': 'device_id',
            'ref_table': 'devices',
            'ref_column': 'id'
        },
        {
            'name': 'test_results -> devices',
            'table': 'test_results',
            'fk_column': 'device_id',
            'ref_table': 'devices',
            'ref_column': 'id'
        },
        {
            'name': 'test_results -> apis',
            'table': 'test_results',
            'fk_column': 'api_id',
            'ref_table': 'apis',
            'ref_column': 'id'
        },
        {
            'name': 'test_result_dimensions -> test_results',
            'table': 'test_result_dimensions',
            'fk_column': 'test_result_id',
            'ref_table': 'test_results',
            'ref_column': 'id'
        },
        {
            'name': 'test_result_dimensions -> dimensions',
            'table': 'test_result_dimensions',
            'fk_column': 'dimension_id',
            'ref_table': 'dimensions',
            'ref_column': 'id'
        },
        {
            'name': 'report_summaries -> test_reports',
            'table': 'report_summaries',
            'fk_column': 'report_id',
            'ref_table': 'test_reports',
            'ref_column': 'id'
        },
        {
            'name': 'report_detail_data -> test_reports',
            'table': 'report_detail_data',
            'fk_column': 'report_id',
            'ref_table': 'test_reports',
            'ref_column': 'id'
        },
        {
            'name': 'dimensions -> dimensions (parent)',
            'table': 'dimensions',
            'fk_column': 'parent_dimension_id',
            'ref_table': 'dimensions',
            'ref_column': 'id'
        },
        {
            'name': 'dimensions -> categories',
            'table': 'dimensions',
            'fk_column': 'category_id',
            'ref_table': 'categories',
            'ref_column': 'id'
        },
        {
            'name': 'logs -> devices',
            'table': 'logs',
            'fk_column': 'device_id',
            'ref_table': 'devices',
            'ref_column': 'id'
        },
        {
            'name': 'logs -> apis',
            'table': 'logs',
            'fk_column': 'api_id',
            'ref_table': 'apis',
            'ref_column': 'id'
        },
        {
            'name': 'spl_mappings -> playback_devices',
            'table': 'spl_mappings',
            'fk_column': 'device_id',
            'ref_table': 'playback_devices',
            'ref_column': 'id'
        },
        {
            'name': 'calibration_history -> spl_mappings',
            'table': 'calibration_history',
            'fk_column': 'mapping_id',
            'ref_table': 'spl_mappings',
            'ref_column': 'id'
        },
        {
            'name': 'playback_devices -> spl_mappings',
            'table': 'playback_devices',
            'fk_column': 'current_spl_mapping_id',
            'ref_table': 'spl_mappings',
            'ref_column': 'id'
        },
        {
            'name': 'algorithm_definitions -> algorithm_groups',
            'table': 'algorithm_definitions',
            'fk_column': 'group_id',
            'ref_table': 'algorithm_groups',
            'ref_column': 'id'
        },
        {
            'name': 'evaluation_dimension_params -> dimensions',
            'table': 'evaluation_dimension_params',
            'fk_column': 'dimension_id',
            'ref_table': 'dimensions',
            'ref_column': 'id'
        },
        {
            'name': 'param_mappings -> dimensions',
            'table': 'param_mappings',
            'fk_column': 'dimension_id',
            'ref_table': 'dimensions',
            'ref_column': 'id'
        },
        {
            'name': 'algorithm_dimension_relations -> dimensions',
            'table': 'algorithm_dimension_relations',
            'fk_column': 'dimension_id',
            'ref_table': 'dimensions',
            'ref_column': 'id'
        },
    ]
    
    total_invalid = 0
    
    for check in checks:
        sql = f"""
        SELECT COUNT(*) FROM {check['table']} t
        WHERE t.{check['fk_column']} IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM {check['ref_table']} r 
            WHERE r.{check['ref_column']} = t.{check['fk_column']}
        )
        """
        cursor.execute(sql)
        count = cursor.fetchone()[0]
        
        if count > 0:
            print(f"⚠ {check['name']}: 发现 {count} 条无效引用")
            
            delete_sql = f"""
            DELETE FROM {check['table']} t
            WHERE t.{check['fk_column']} IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM {check['ref_table']} r 
                WHERE r.{check['ref_column']} = t.{check['fk_column']}
            )
            """
            cursor.execute(delete_sql)
            print(f"  已删除 {count} 条无效记录")
            total_invalid += count
        else:
            print(f"✓ {check['name']}: 数据完整")
    
    cursor.close()
    conn.close()
    
    print("=" * 60)
    print(f"总计清理: {total_invalid} 条无效记录")
    print("数据完整性修复完成!")
    print("=" * 60)

if __name__ == '__main__':
    check_and_clean_integrity()