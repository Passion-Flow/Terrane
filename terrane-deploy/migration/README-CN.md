# Terrane 备份 / 迁移(docker-compose 部署)

把一台 Terrane 整机搬到新服务器,或做日常灾备。脚本在 `Scripts/`。

> 适用于 docker-compose **自带数据库**部署(默认即是,脚本用 `docker compose exec postgres pg_dump` 导库)。
> 若你改用了**外部数据库**,数据库备份由你的 PG 侧负责;本脚本只需备 `license` 卷 + `.env`(KEK),
> 数据库部分用你 DBA 的 dump/恢复流程。

## 备份(旧服务器,在 docker-compose 部署目录内)

```bash
bash migration/Scripts/backup-terrane.sh           # 热备份(不停服,适合演练/日常)
bash migration/Scripts/backup-terrane.sh --final    # 终备份(停应用层冻结写入,正式割接当天)
```
产物 `terrane-migration-<时间戳>.tar.gz`,含:**双库 dump**(terrane_main + terrane_admin)、**License 卷**(active.forge + install_id)、**.env**(含 KEK)、SHA256 校验清单。

> ⚠ 整包含 KEK 与全部数据,只走加密通道(scp/sftp)传输,落地后尽快删中转副本。

## 恢复(新服务器)

前置:装好 Docker+Compose;解压同版本部署包并 `cd` 进 `docker-compose/`;配好镜像仓库登录。

```bash
scp terrane-migration-*.tar.gz user@new-host:/path/terrane-deploy/docker-compose/
# 新服务器:
bash migration/Scripts/restore-terrane.sh /path/terrane-migration-<时间戳>.tar.gz
```
脚本会:校验 → 落 .env → 起 PG → 恢复双库 → 恢复 License 卷 → 起全栈 → 等健康。

## 验证清单(切流量前必过)

1. 后台能登(用改密后的超管账号),前台知识库 / 记忆 / 对话历史数据都在。
2. License 状态 `active`(后台 License 卡片)。
3. 模型渠道在、Chat 能正常回答。

## 关键铁律

- **KEK 必须逐字一致**:新机 `.env` 的 `TERRANE_KEK` 与旧机相同,否则 SMTP/2FA/凭据密文解不开。
- **验证全过前不要关旧服务器、不要切 DNS/流量**。
- License 因部署指纹变化掉证:正常,后台用激活码**重激活**即可(install_id 已随卷迁移,多数情况无感)。
- 卷名假设为默认 `terrane_license`;若 compose project 名不同(`docker volume ls` 查),按实际卷名调脚本。
