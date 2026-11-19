\pset pager off
\x on
\d test_cases
SELECT * FROM test_cases LIMIT 1;
\d test_results
SELECT * FROM test_results LIMIT 1;
\d algorithm_reference_params
SELECT * FROM algorithm_reference_params LIMIT 1;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '%ref%';
SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' AND column_name ILIKE '%ref%param%';
SELECT DISTINCT substring(file_path from 1 for 90) AS prefix FROM audios LIMIT 12;
