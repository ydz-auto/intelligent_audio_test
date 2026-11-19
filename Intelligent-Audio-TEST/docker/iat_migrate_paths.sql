\set ON_ERROR_STOP on
\pset pager off

BEGIN;

UPDATE audios
SET file_path = replace(
        regexp_replace(file_path, '^.*[\\/]static[\\/]audios[\\/]', 'oss://audios/'),
        '\', '/')
WHERE file_path LIKE '%static%audios%';

UPDATE test_cases
SET reference_params = replace(
        regexp_replace(reference_params::text, '"[^"]*static\\\\ref_params\\\\', '"oss://ref_params/', 'g'),
        '\\', '/')::json
WHERE reference_params::text LIKE '%ref_params%';

UPDATE report_cases
SET reference_params = replace(
        regexp_replace(reference_params::text, '"[^"]*static\\\\ref_params\\\\', '"oss://ref_params/', 'g'),
        '\\', '/')::json
WHERE reference_params::text LIKE '%ref_params%';

UPDATE test_results
SET result_data_path = 'oss://' || replace(result_data_path, '\', '/')
WHERE result_data_path LIKE 'case_result%';

UPDATE test_results
SET result_data_path = replace(result_data_path, '\', '/')
WHERE result_data_path LIKE 'oss://%';

UPDATE test_results
SET algorithm_result = replace(
        regexp_replace(algorithm_result::text, '"[^"]*case_result\\\\', '"oss://case_result/', 'g'),
        '\\', '/')::json
WHERE algorithm_result IS NOT NULL AND algorithm_result::text LIKE '%case_result%';

UPDATE dimensions
SET api_url = 'http://eval_server:8888'
WHERE api_url IS NOT NULL AND api_url <> '';

COMMIT;

SELECT count(*) AS audios_total,
       count(*) FILTER (WHERE file_path LIKE 'oss://audios/%') AS audios_oss
FROM audios;

SELECT count(*) AS cases_with_ref,
       count(*) FILTER (WHERE reference_params::text LIKE '%oss://ref_params/%') AS cases_ref_oss
FROM test_cases
WHERE reference_params::text LIKE '%ref_params%';

SELECT count(*) AS results_total,
       count(*) FILTER (WHERE result_data_path LIKE 'oss://%') AS results_oss
FROM test_results
WHERE result_data_path IS NOT NULL AND result_data_path <> '';

SELECT DISTINCT api_url FROM dimensions WHERE api_url IS NOT NULL AND api_url <> '';

SELECT id, file_path FROM audios LIMIT 2;
SELECT id, reference_params::text FROM test_cases WHERE reference_params::text LIKE '%oss://ref_params/%' LIMIT 1;
SELECT id, result_data_path FROM test_results WHERE result_data_path LIKE 'oss://%' LIMIT 2;
