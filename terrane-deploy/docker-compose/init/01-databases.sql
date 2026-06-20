-- Terrane 出厂初始化:创建双库(前台 terrane_main / 后台 terrane_admin)。
-- 只在 PostgreSQL 首次初始化(数据目录为空)时执行一次。扩展(age / vector)在各服务的 Alembic
-- 迁移内 CREATE EXTENSION;此处仅建库。
SELECT 'CREATE DATABASE terrane_main'  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'terrane_main')\gexec
SELECT 'CREATE DATABASE terrane_admin' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'terrane_admin')\gexec
