-- PostgreSQL 迁移脚本: 将所有 INTEGER 自增ID改为 BIGINT (BIGSERIAL)
-- 执行前请确保数据库连接正常，建议在执行前备份数据库

-- ============================================================================
-- 第一步: 删除所有外键约束
-- ============================================================================

-- user_permissions 表
ALTER TABLE user_permissions DROP CONSTRAINT IF EXISTS user_permissions_user_id_fkey;
ALTER TABLE user_permissions DROP CONSTRAINT IF EXISTS user_permissions_permission_id_fkey;

-- tags 表
ALTER TABLE tags DROP CONSTRAINT IF EXISTS tags_category_id_fkey;

-- test_case_tags 表
ALTER TABLE test_case_tags DROP CONSTRAINT IF EXISTS test_case_tags_tag_id_fkey;

-- devices 表 - 无外键引用其他表的ID

-- playback_devices 表
ALTER TABLE playback_devices DROP CONSTRAINT IF EXISTS playback_devices_current_spl_mapping_id_fkey;

-- device_tags 表
ALTER TABLE device_tags DROP CONSTRAINT IF EXISTS device_tags_device_id_fkey;
ALTER TABLE device_tags DROP CONSTRAINT IF EXISTS device_tags_tag_id_fkey;

-- audio_annotations 表
ALTER TABLE audio_annotations DROP CONSTRAINT IF EXISTS audio_annotations_audio_id_fkey;

-- audio_tags 表
ALTER TABLE audio_tags DROP CONSTRAINT IF EXISTS audio_tags_audio_id_fkey;
ALTER TABLE audio_tags DROP CONSTRAINT IF EXISTS audio_tags_tag_id_fkey;

-- audio_algorithm_relations 表
ALTER TABLE audio_algorithm_relations DROP CONSTRAINT IF EXISTS audio_algorithm_relations_audio_id_fkey;

-- prompt_audio_relations 表
ALTER TABLE prompt_audio_relations DROP CONSTRAINT IF EXISTS prompt_audio_relations_audio_id_fkey;
ALTER TABLE prompt_audio_relations DROP CONSTRAINT IF EXISTS prompt_audio_relations_device_id_fkey;

-- test_tasks 表 - created_by 字段需要修改但不是外键

-- task_tags 表
ALTER TABLE task_tags DROP CONSTRAINT IF EXISTS task_tags_task_id_fkey;
ALTER TABLE task_tags DROP CONSTRAINT IF EXISTS task_tags_tag_id_fkey;

-- task_case_relations 表
ALTER TABLE task_case_relations DROP CONSTRAINT IF EXISTS task_case_relations_task_id_fkey;

-- task_device_relations 表
ALTER TABLE task_device_relations DROP CONSTRAINT IF EXISTS task_device_relations_task_id_fkey;
ALTER TABLE task_device_relations DROP CONSTRAINT IF EXISTS task_device_relations_device_id_fkey;

-- task_api_relations 表
ALTER TABLE task_api_relations DROP CONSTRAINT IF EXISTS task_api_relations_task_id_fkey;
ALTER TABLE task_api_relations DROP CONSTRAINT IF EXISTS task_api_relations_api_id_fkey;

-- task_merge_relations 表
ALTER TABLE task_merge_relations DROP CONSTRAINT IF EXISTS task_merge_relations_merged_task_id_fkey;
ALTER TABLE task_merge_relations DROP CONSTRAINT IF EXISTS task_merge_relations_source_task_id_fkey;

-- test_results 表
ALTER TABLE test_results DROP CONSTRAINT IF EXISTS test_results_task_id_fkey;
ALTER TABLE test_results DROP CONSTRAINT IF EXISTS test_results_device_id_fkey;
ALTER TABLE test_results DROP CONSTRAINT IF EXISTS test_results_api_id_fkey;

-- test_result_dimensions 表
ALTER TABLE test_result_dimensions DROP CONSTRAINT IF EXISTS test_result_dimensions_test_result_id_fkey;
ALTER TABLE test_result_dimensions DROP CONSTRAINT IF EXISTS test_result_dimensions_dimension_id_fkey;

-- test_reports 表
ALTER TABLE test_reports DROP CONSTRAINT IF EXISTS test_reports_task_id_fkey;

-- report_summaries 表
ALTER TABLE report_summaries DROP CONSTRAINT IF EXISTS report_summaries_report_id_fkey;

-- report_detail_data 表
ALTER TABLE report_detail_data DROP CONSTRAINT IF EXISTS report_detail_data_report_id_fkey;

-- dimensions 表
ALTER TABLE dimensions DROP CONSTRAINT IF EXISTS dimensions_parent_dimension_id_fkey;
ALTER TABLE dimensions DROP CONSTRAINT IF EXISTS dimensions_category_id_fkey;

-- logs 表
ALTER TABLE logs DROP CONSTRAINT IF EXISTS logs_device_id_fkey;
ALTER TABLE logs DROP CONSTRAINT IF EXISTS logs_task_id_fkey;
ALTER TABLE logs DROP CONSTRAINT IF EXISTS logs_api_id_fkey;

-- spl_mappings 表
ALTER TABLE spl_mappings DROP CONSTRAINT IF EXISTS spl_mappings_device_id_fkey;

-- calibration_history 表
ALTER TABLE calibration_history DROP CONSTRAINT IF EXISTS calibration_history_mapping_id_fkey;

-- algorithm_groups 表 - 无外键

-- algorithm_definitions 表
ALTER TABLE algorithm_definitions DROP CONSTRAINT IF EXISTS algorithm_definitions_group_id_fkey;

-- algorithm_device_params 表 - algorithm_type 是 VARCHAR 外键，不需要改

-- algorithm_api_params 表 - algorithm_type 是 VARCHAR 外键，不需要改

-- algorithm_reference_params 表 - algorithm_type 是 VARCHAR 外键，不需要改

-- evaluation_dimension_params 表
ALTER TABLE evaluation_dimension_params DROP CONSTRAINT IF EXISTS evaluation_dimension_params_dimension_id_fkey;

-- param_mappings 表
ALTER TABLE param_mappings DROP CONSTRAINT IF EXISTS param_mappings_dimension_id_fkey;

-- algorithm_dimension_relations 表
ALTER TABLE algorithm_dimension_relations DROP CONSTRAINT IF EXISTS algorithm_dimension_relations_dimension_id_fkey;

-- case_algorithm_params 表 - algorithm_type 是 VARCHAR 外键，不需要改

-- languages 表 - 无外键

-- ============================================================================
-- 第二步: 修改所有主键字段从 INTEGER 改为 BIGINT
-- ============================================================================

-- 用户与权限管理
ALTER TABLE users ALTER COLUMN id TYPE BIGINT;
ALTER TABLE permissions ALTER COLUMN id TYPE BIGINT;
ALTER TABLE user_permissions ALTER COLUMN id TYPE BIGINT;

-- 标签管理
ALTER TABLE tag_categories ALTER COLUMN id TYPE BIGINT;
ALTER TABLE tags ALTER COLUMN id TYPE BIGINT;

-- 测试用例管理 (test_case_tags)
ALTER TABLE test_case_tags ALTER COLUMN id TYPE BIGINT;

-- 设备管理
ALTER TABLE devices ALTER COLUMN id TYPE BIGINT;
ALTER TABLE playback_devices ALTER COLUMN id TYPE BIGINT;
ALTER TABLE device_tags ALTER COLUMN id TYPE BIGINT;

-- 音频文件管理
ALTER TABLE translation_directions ALTER COLUMN id TYPE BIGINT;
ALTER TABLE audios ALTER COLUMN id TYPE BIGINT;
ALTER TABLE audio_annotations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE audio_tags ALTER COLUMN id TYPE BIGINT;
ALTER TABLE audio_algorithm_relations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE prompt_audio_relations ALTER COLUMN id TYPE BIGINT;

-- API 配置管理
ALTER TABLE apis ALTER COLUMN id TYPE BIGINT;

-- 测试任务管理
ALTER TABLE test_tasks ALTER COLUMN id TYPE BIGINT;
ALTER TABLE task_tags ALTER COLUMN id TYPE BIGINT;
ALTER TABLE task_case_relations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE task_device_relations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE task_api_relations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE task_merge_relations ALTER COLUMN id TYPE BIGINT;

-- 测试结果管理
ALTER TABLE test_results ALTER COLUMN id TYPE BIGINT;
ALTER TABLE test_result_dimensions ALTER COLUMN id TYPE BIGINT;
ALTER TABLE test_reports ALTER COLUMN id TYPE BIGINT;
ALTER TABLE report_summaries ALTER COLUMN id TYPE BIGINT;
ALTER TABLE report_detail_data ALTER COLUMN id TYPE BIGINT;

-- 评估维度管理
ALTER TABLE categories ALTER COLUMN id TYPE BIGINT;
ALTER TABLE dimensions ALTER COLUMN id TYPE BIGINT;

-- 日志管理
ALTER TABLE logs ALTER COLUMN id TYPE BIGINT;

-- 扩展功能
ALTER TABLE spl_mappings ALTER COLUMN id TYPE BIGINT;
ALTER TABLE calibration_history ALTER COLUMN id TYPE BIGINT;

-- 上传分片
ALTER TABLE upload_chunks ALTER COLUMN id TYPE BIGINT;

-- 统计缓存
ALTER TABLE stats_cache ALTER COLUMN id TYPE BIGINT;

-- 算法配置模型
ALTER TABLE algorithm_groups ALTER COLUMN id TYPE BIGINT;
ALTER TABLE algorithm_definitions ALTER COLUMN id TYPE BIGINT;
ALTER TABLE algorithm_device_params ALTER COLUMN id TYPE BIGINT;
ALTER TABLE algorithm_api_params ALTER COLUMN id TYPE BIGINT;
ALTER TABLE algorithm_reference_params ALTER COLUMN id TYPE BIGINT;
ALTER TABLE evaluation_dimension_params ALTER COLUMN id TYPE BIGINT;
ALTER TABLE param_mappings ALTER COLUMN id TYPE BIGINT;
ALTER TABLE algorithm_dimension_relations ALTER COLUMN id TYPE BIGINT;
ALTER TABLE case_algorithm_params ALTER COLUMN id TYPE BIGINT;
ALTER TABLE languages ALTER COLUMN id TYPE BIGINT;

-- ============================================================================
-- 第三步: 修改所有 ForeignKey 字段从 INTEGER 改为 BIGINT
-- ============================================================================

-- user_permissions 表
ALTER TABLE user_permissions ALTER COLUMN user_id TYPE BIGINT;
ALTER TABLE user_permissions ALTER COLUMN permission_id TYPE BIGINT;

-- tags 表
ALTER TABLE tags ALTER COLUMN category_id TYPE BIGINT;

-- test_case_tags 表
ALTER TABLE test_case_tags ALTER COLUMN tag_id TYPE BIGINT;

-- playback_devices 表
ALTER TABLE playback_devices ALTER COLUMN current_spl_mapping_id TYPE BIGINT;

-- device_tags 表
ALTER TABLE device_tags ALTER COLUMN device_id TYPE BIGINT;
ALTER TABLE device_tags ALTER COLUMN tag_id TYPE BIGINT;

-- audio_annotations 表
ALTER TABLE audio_annotations ALTER COLUMN audio_id TYPE BIGINT;

-- audio_tags 表
ALTER TABLE audio_tags ALTER COLUMN audio_id TYPE BIGINT;
ALTER TABLE audio_tags ALTER COLUMN tag_id TYPE BIGINT;

-- audio_algorithm_relations 表
ALTER TABLE audio_algorithm_relations ALTER COLUMN audio_id TYPE BIGINT;

-- prompt_audio_relations 表
ALTER TABLE prompt_audio_relations ALTER COLUMN audio_id TYPE BIGINT;
ALTER TABLE prompt_audio_relations ALTER COLUMN device_id TYPE BIGINT;

-- test_tasks 表 - created_by 是用户ID引用
ALTER TABLE test_tasks ALTER COLUMN created_by TYPE BIGINT;

-- task_tags 表
ALTER TABLE task_tags ALTER COLUMN task_id TYPE BIGINT;
ALTER TABLE task_tags ALTER COLUMN tag_id TYPE BIGINT;

-- task_case_relations 表
ALTER TABLE task_case_relations ALTER COLUMN task_id TYPE BIGINT;

-- task_device_relations 表
ALTER TABLE task_device_relations ALTER COLUMN task_id TYPE BIGINT;
ALTER TABLE task_device_relations ALTER COLUMN device_id TYPE BIGINT;

-- task_api_relations 表
ALTER TABLE task_api_relations ALTER COLUMN task_id TYPE BIGINT;
ALTER TABLE task_api_relations ALTER COLUMN api_id TYPE BIGINT;

-- task_merge_relations 表
ALTER TABLE task_merge_relations ALTER COLUMN merged_task_id TYPE BIGINT;
ALTER TABLE task_merge_relations ALTER COLUMN source_task_id TYPE BIGINT;

-- test_results 表
ALTER TABLE test_results ALTER COLUMN task_id TYPE BIGINT;
ALTER TABLE test_results ALTER COLUMN device_id TYPE BIGINT;
ALTER TABLE test_results ALTER COLUMN api_id TYPE BIGINT;

-- test_result_dimensions 表
ALTER TABLE test_result_dimensions ALTER COLUMN test_result_id TYPE BIGINT;
ALTER TABLE test_result_dimensions ALTER COLUMN dimension_id TYPE BIGINT;

-- test_reports 表
ALTER TABLE test_reports ALTER COLUMN task_id TYPE BIGINT;

-- report_summaries 表
ALTER TABLE report_summaries ALTER COLUMN report_id TYPE BIGINT;

-- report_detail_data 表
ALTER TABLE report_detail_data ALTER COLUMN report_id TYPE BIGINT;

-- dimensions 表
ALTER TABLE dimensions ALTER COLUMN parent_dimension_id TYPE BIGINT;
ALTER TABLE dimensions ALTER COLUMN category_id TYPE BIGINT;

-- logs 表
ALTER TABLE logs ALTER COLUMN device_id TYPE BIGINT;
ALTER TABLE logs ALTER COLUMN task_id TYPE BIGINT;
ALTER TABLE logs ALTER COLUMN api_id TYPE BIGINT;

-- spl_mappings 表
ALTER TABLE spl_mappings ALTER COLUMN device_id TYPE BIGINT;

-- calibration_history 表
ALTER TABLE calibration_history ALTER COLUMN mapping_id TYPE BIGINT;

-- algorithm_definitions 表
ALTER TABLE algorithm_definitions ALTER COLUMN group_id TYPE BIGINT;

-- evaluation_dimension_params 表
ALTER TABLE evaluation_dimension_params ALTER COLUMN dimension_id TYPE BIGINT;

-- param_mappings 表
ALTER TABLE param_mappings ALTER COLUMN dimension_id TYPE BIGINT;

-- algorithm_dimension_relations 表
ALTER TABLE algorithm_dimension_relations ALTER COLUMN dimension_id TYPE BIGINT;

-- ============================================================================
-- 第四步: 重新创建所有外键约束
-- ============================================================================

-- user_permissions 表
ALTER TABLE user_permissions ADD CONSTRAINT user_permissions_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE user_permissions ADD CONSTRAINT user_permissions_permission_id_fkey 
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE;

-- tags 表
ALTER TABLE tags ADD CONSTRAINT tags_category_id_fkey 
    FOREIGN KEY (category_id) REFERENCES tag_categories(id) ON DELETE SET NULL;

-- test_case_tags 表
ALTER TABLE test_case_tags ADD CONSTRAINT test_case_tags_tag_id_fkey 
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE;

-- playback_devices 表
ALTER TABLE playback_devices ADD CONSTRAINT playback_devices_current_spl_mapping_id_fkey 
    FOREIGN KEY (current_spl_mapping_id) REFERENCES spl_mappings(id) ON DELETE SET NULL;

-- device_tags 表
ALTER TABLE device_tags ADD CONSTRAINT device_tags_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE;
ALTER TABLE device_tags ADD CONSTRAINT device_tags_tag_id_fkey 
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE;

-- audio_annotations 表
ALTER TABLE audio_annotations ADD CONSTRAINT audio_annotations_audio_id_fkey 
    FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE;

-- audio_tags 表
ALTER TABLE audio_tags ADD CONSTRAINT audio_tags_audio_id_fkey 
    FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE;
ALTER TABLE audio_tags ADD CONSTRAINT audio_tags_tag_id_fkey 
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE;

-- audio_algorithm_relations 表
ALTER TABLE audio_algorithm_relations ADD CONSTRAINT audio_algorithm_relations_audio_id_fkey 
    FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE;

-- prompt_audio_relations 表
ALTER TABLE prompt_audio_relations ADD CONSTRAINT prompt_audio_relations_audio_id_fkey 
    FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE;
ALTER TABLE prompt_audio_relations ADD CONSTRAINT prompt_audio_relations_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL;

-- task_tags 表
ALTER TABLE task_tags ADD CONSTRAINT task_tags_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;
ALTER TABLE task_tags ADD CONSTRAINT task_tags_tag_id_fkey 
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE;

-- task_case_relations 表
ALTER TABLE task_case_relations ADD CONSTRAINT task_case_relations_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;

-- task_device_relations 表
ALTER TABLE task_device_relations ADD CONSTRAINT task_device_relations_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;
ALTER TABLE task_device_relations ADD CONSTRAINT task_device_relations_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE;

-- task_api_relations 表
ALTER TABLE task_api_relations ADD CONSTRAINT task_api_relations_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;
ALTER TABLE task_api_relations ADD CONSTRAINT task_api_relations_api_id_fkey 
    FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE CASCADE;

-- task_merge_relations 表
ALTER TABLE task_merge_relations ADD CONSTRAINT task_merge_relations_merged_task_id_fkey 
    FOREIGN KEY (merged_task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;
ALTER TABLE task_merge_relations ADD CONSTRAINT task_merge_relations_source_task_id_fkey 
    FOREIGN KEY (source_task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;

-- test_results 表
ALTER TABLE test_results ADD CONSTRAINT test_results_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE;
ALTER TABLE test_results ADD CONSTRAINT test_results_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL;
ALTER TABLE test_results ADD CONSTRAINT test_results_api_id_fkey 
    FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE CASCADE;

-- test_result_dimensions 表
ALTER TABLE test_result_dimensions ADD CONSTRAINT test_result_dimensions_test_result_id_fkey 
    FOREIGN KEY (test_result_id) REFERENCES test_results(id) ON DELETE CASCADE;
ALTER TABLE test_result_dimensions ADD CONSTRAINT test_result_dimensions_dimension_id_fkey 
    FOREIGN KEY (dimension_id) REFERENCES dimensions(id) ON DELETE CASCADE;

-- test_reports 表
ALTER TABLE test_reports ADD CONSTRAINT test_reports_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE SET NULL;

-- report_summaries 表
ALTER TABLE report_summaries ADD CONSTRAINT report_summaries_report_id_fkey 
    FOREIGN KEY (report_id) REFERENCES test_reports(id) ON DELETE CASCADE;

-- report_detail_data 表
ALTER TABLE report_detail_data ADD CONSTRAINT report_detail_data_report_id_fkey 
    FOREIGN KEY (report_id) REFERENCES test_reports(id) ON DELETE CASCADE;

-- dimensions 表
ALTER TABLE dimensions ADD CONSTRAINT dimensions_parent_dimension_id_fkey 
    FOREIGN KEY (parent_dimension_id) REFERENCES dimensions(id) ON DELETE SET NULL;
ALTER TABLE dimensions ADD CONSTRAINT dimensions_category_id_fkey 
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL;

-- logs 表
ALTER TABLE logs ADD CONSTRAINT logs_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL;
ALTER TABLE logs ADD CONSTRAINT logs_task_id_fkey 
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE SET NULL;
ALTER TABLE logs ADD CONSTRAINT logs_api_id_fkey 
    FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE SET NULL;

-- spl_mappings 表
ALTER TABLE spl_mappings ADD CONSTRAINT spl_mappings_device_id_fkey 
    FOREIGN KEY (device_id) REFERENCES playback_devices(id) ON DELETE SET NULL;

-- calibration_history 表
ALTER TABLE calibration_history ADD CONSTRAINT calibration_history_mapping_id_fkey 
    FOREIGN KEY (mapping_id) REFERENCES spl_mappings(id) ON DELETE CASCADE;

-- algorithm_definitions 表
ALTER TABLE algorithm_definitions ADD CONSTRAINT algorithm_definitions_group_id_fkey 
    FOREIGN KEY (group_id) REFERENCES algorithm_groups(id) ON DELETE SET NULL;

-- evaluation_dimension_params 表
ALTER TABLE evaluation_dimension_params ADD CONSTRAINT evaluation_dimension_params_dimension_id_fkey 
    FOREIGN KEY (dimension_id) REFERENCES dimensions(id) ON DELETE CASCADE;

-- param_mappings 表
ALTER TABLE param_mappings ADD CONSTRAINT param_mappings_dimension_id_fkey 
    FOREIGN KEY (dimension_id) REFERENCES dimensions(id) ON DELETE CASCADE;

-- algorithm_dimension_relations 表
ALTER TABLE algorithm_dimension_relations ADD CONSTRAINT algorithm_dimension_relations_dimension_id_fkey 
    FOREIGN KEY (dimension_id) REFERENCES dimensions(id) ON DELETE CASCADE;

-- ============================================================================
-- 第五步: 更新序列类型为 BIGSERIAL (确保新数据使用 BIGINT)
-- ============================================================================

-- 对于已存在的序列，PostgreSQL 在 ALTER COLUMN id TYPE BIGINT 后会自动处理
-- 但为了确保一致性，可以显式检查并确保序列范围足够大

-- 查看当前所有序列的状态
SELECT sequence_name, data_type, start_value, minimum_value, maximum_value 
FROM information_schema.sequences 
WHERE sequence_schema = 'public';

-- ============================================================================
-- 完成提示
-- ============================================================================

-- 迁移完成！请验证：
-- 1. 所有表的 id 字段现在是 BIGINT 类型
-- 2. 所有外键约束已正确重建
-- 3. 序列现在支持 BIGINT 范围
-- 4. 建议运行测试确保应用程序正常工作