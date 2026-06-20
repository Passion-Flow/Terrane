-- 出厂初始化:创建双库(前台 terrane_main / 后台 terrane_admin)。扩展在各自迁移内 CREATE EXTENSION。
SELECT 'CREATE DATABASE terrane_main'  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='terrane_main')\gexec
SELECT 'CREATE DATABASE terrane_admin' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='terrane_admin')\gexec
