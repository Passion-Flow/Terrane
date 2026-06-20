# Terrane Webhook 事件目录（webhook.md §2 规范）

信封：`{event_id(uuid), event_type, occurred_at(ISO8601 UTC), workspace_id, data}`；签名头 `X-Terrane-Signature: HMAC-SHA256(secret, body)` + `X-Terrane-Timestamp`（±5min 防重放）；重试指数退避 5 次→DLQ；event_id 幂等键。

| Event Type | 触发时机 | data 要点 |
|------------|---------|-----------|
| `ingest.completed` | 源摄入编译完成（管线⑦后） | kb_id, source_id, pages_touched, spent_tokens |
| `ingest.failed` | 摄入失败（含降级失败） | kb_id, source_id, stage, error_code |
| `agent.task_completed` | Agent 运行产物就绪 | task_id, run_id, pages_written[], diff_url |
| `agent.task_failed` | Agent 运行失败/被预算暂停 | task_id, run_id, reason |
| `lint.report_ready` | 体检报告生成 | kb_id, report_id, counts{contradiction,orphan,stale,...} |
| `memory.recall` | 记忆唤回（日批聚合后，可订阅） | user_id, memory_ids[], trigger_source_id |
| `budget.threshold` | 预算达 80% | scope(ws/kb), budget_id, spent, limit |
| `budget.exhausted` | 预算 100%（自动任务暂停） | 同上 + paused_tasks[] |
| `quota.storage_full` | 存储硬配额触顶（拒新摄入） | workspace_id, used_bytes, limit_bytes |
| `kb.shared` | 共享邀请发出 | kb_id, invitee_user_id, role |
| `kb.deleted` | 库硬删除完成 | kb_id（元数据，内容已不可恢复） |
| `export.completed` | 导出包就绪 | kb_id, export_job_id, download_expires_at |
| `license.expiring` | License 到期前 30/7 天 | days_left, expire_at |
| `user.created` / `workspace.created` | B 端基线事件 | — |

订阅管理：后台 Settings › Webhooks（端点 CRUD/secret 轮换/事件勾选/投递历史+手动重投）。
