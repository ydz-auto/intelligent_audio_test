\pset pager off
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (column_name ILIKE '%url%' OR column_name ILIKE '%path%')
ORDER BY table_name, column_name;
SELECT DISTINCT api_url FROM dimensions WHERE api_url IS NOT NULL AND api_url <> '';
SELECT id, file_path FROM audios LIMIT 5;
SELECT id, file_path FROM testcases LIMIT 5;
