\pset pager off
\d audios
SELECT id, file_path FROM audios LIMIT 3;
SELECT id, result_data_path FROM test_results LIMIT 3;
SELECT id, source_file_path FROM report_studio_documents LIMIT 3;
SELECT id, file_path FROM report_studio_export_jobs LIMIT 3;
SELECT id, final_path FROM transfer_records LIMIT 3;
SELECT id, stored_path FROM upload_chunks LIMIT 3;
SELECT id, relative_path FROM upload_files LIMIT 3;
SELECT id, field_path FROM algorithm_reference_params LIMIT 5;
SELECT id, api_url FROM apis LIMIT 5;
SELECT id, url FROM benchmark_sources LIMIT 5;
SELECT id, oauth_avatar_url FROM users LIMIT 3;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '%test%';
