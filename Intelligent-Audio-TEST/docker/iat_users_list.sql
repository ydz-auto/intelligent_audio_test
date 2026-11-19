\pset pager off
SELECT u.id,
       u.username,
       u.display_name,
       u.email,
       u.status,
       u.role_id,
       r.name AS role_name,
       u.oauth_provider,
       u.created_at,
       u.last_login_at
FROM users u
LEFT JOIN roles r ON r.id = u.role_id
ORDER BY u.id;
