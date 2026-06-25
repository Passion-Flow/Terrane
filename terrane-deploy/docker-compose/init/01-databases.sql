-- Terrane factory init: create the two databases (front-end terrane_main / admin terrane_admin).
-- Runs only once, on PostgreSQL's first initialization (empty data directory). The extensions
-- (age / vector) are created via CREATE EXTENSION inside each service's Alembic migration; this file
-- only creates the databases.
SELECT 'CREATE DATABASE terrane_main'  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'terrane_main')\gexec
SELECT 'CREATE DATABASE terrane_admin' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'terrane_admin')\gexec
