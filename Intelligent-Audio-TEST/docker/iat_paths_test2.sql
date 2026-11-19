\pset pager off
SELECT regexp_replace(reference_params::text, '"[^"]*static\\\\ref_params\\\\', '"oss://ref_params/', 'g') AS r1 FROM test_cases WHERE reference_params::text LIKE '%ref_params%' LIMIT 1;
SELECT replace(regexp_replace(reference_params::text, '"[^"]*static\\\\ref_params\\\\', '"oss://ref_params/', 'g'), '\\', '/') AS r2 FROM test_cases WHERE reference_params::text LIKE '%ref_params%' LIMIT 1;
SELECT regexp_replace(algorithm_result::text, '"[^"]*case_result\\\\', '"oss://case_result/', 'g') AS a1 FROM test_results WHERE algorithm_result::text LIKE '%case_result\\\\%' LIMIT 1;
SELECT replace(regexp_replace(algorithm_result::text, '"[^"]*case_result\\\\', '"oss://case_result/', 'g'), '\\', '/') AS a2 FROM test_results WHERE algorithm_result::text LIKE '%case_result\\\\%' LIMIT 1;
SELECT regexp_replace(reference_params::text, '"[^"]*static\\\\ref_params\\\\', '"oss://ref_params/', 'g') AS rc1 FROM report_cases WHERE reference_params::text LIKE '%ref_params%' LIMIT 1;
