\pset pager off
SELECT id, file_path, regexp_replace(file_path, '^.*[\\/]static[\\/]audios[\\/]', 'oss://audios/') AS new_path FROM audios LIMIT 5;
SELECT id, reference_params::text FROM test_cases WHERE reference_params::text LIKE '%ref_params%' LIMIT 2;
SELECT id, result_data_path, replace(result_data_path, '\', '/') AS normalized FROM test_results WHERE result_data_path IS NOT NULL AND result_data_path NOT LIKE 'oss://%' LIMIT 5;
