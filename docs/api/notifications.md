# 通知

> v0.5.0 · 更新于 2026-08-13

告警生命周期中"新建 / 重开"事件触发多渠道通知。v0.5 内置两个全局通道：

| 通道 | 适用 | 配置项 |
|------|------|--------|
| Webhook | 通用 HTTP POST（可对接钉钉自定义机器人 / Slack / 企业微信等） | `WEBHOOK_URL` |
| Email | SMTP 邮件（HTML 格式） | `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` / `ALERT_EMAIL_TO` |

任一通道未配置则自动跳过。**关闭 / 自动恢复 / 持续触发**的告警**不通知**（避免噪音），仅"新建"和"重开"通知。

## Payload 格式

所有通道接收同一份 `AlertPayload`：

```json
{
  "alert_id": 42,
  "point_id": 1,
  "project_id": 1,
  "level": "warning",
  "value": 0.99,
  "threshold": 0.5,
  "message": "超阈值",
  "started_at": "2026-08-13T12:00:00+00:00",
  "device_code": "GW-001",
  "point_code": "ACC-X"
}
```

## Webhook 通道

```bash
# .env
WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx
WEBHOOK_HEADERS={"X-Custom":"v1"}
WEBHOOK_TIMEOUT_SECONDS=10
```

POST 请求体即 `AlertPayload`。响应码 2xx 视为成功，其他仅记日志不阻塞。

### 钉钉自定义机器人示例

```json
{
  "alert_id": 42,
  "level": "WARNING",
  "message": "超阈值",
  "value": 0.99,
  ...
}
```

钉钉默认 markdown 模式需要在 payload 外包一层（v0.7+ 可加 `DingTalkChannel` 自动包装）。当前 v0.5 通用 webhook 仅透传 JSON 字段。

## Email 通道

```bash
# .env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=xxxx
SMTP_USE_TLS=true
SMTP_FROM=alerts@example.com        # 默认等于 SMTP_USER
ALERT_EMAIL_TO=ops@example.com,admin@example.com
```

HTML 模板示例（warning 橙色、`#fd7e14`；danger 红色 `#dc3545`；info 蓝色 `#0d6efd`）：

```html
<h2 style="color: #fd7e14;">[SHM] 告警 WARNING</h2>
<table>
  <tr><td>告警 ID</td><td>#42</td></tr>
  <tr><td>项目</td><td>1</td></tr>
  <tr><td>设备 / 测点</td><td>GW-001 / ACC-X</td></tr>
  <tr><td>当前值</td><td style="color:#fd7e14;"><b>0.99</b></td></tr>
  <tr><td>阈值</td><td>0.5</td></tr>
  <tr><td>开始时间</td><td>2026-08-13T12:00:00+00:00</td></tr>
  <tr><td>说明</td><td>超阈值</td></tr>
</table>
```

## 触发与抑制

每次 `POST /data/ingest` 落库后，Celery `alerts` 队列消费 `_process_readings`：

1. 评估每条 reading vs `points.alert_rules`
2. 触发 → `trigger_alert`（含抑制窗口重开语义）
3. **created=True** 时（新建 / 重开） → 构造 `AlertPayload` → 并发 `dispatch_alert(payload)`
4. 关闭 / 自动恢复 → **不通知**

`created=False`（已有 open 告警被刷新 value/threshold）也**不通知**（v0.5 简化；v0.7+ 可加 value 显著变化时的通知策略）。

`AlertRule.suppress_seconds`（默认 60）控制抑制窗口：告警关闭后此时间内再次触发会**重开**同一条 alert（保留历史），不新建。0 表示不抑制。

## 故障隔离

`dispatch_alert` 使用 `asyncio.gather(..., return_exceptions=True)`：

- 通道 A 抛异常（webhook 502、smtp 超时）→ 记日志
- 通道 B 正常 → 继续发送
- 整个告警链路**不被任一通道阻塞**

## 未实现（v0.7+）

- 每项目通道配置（DB 表）
- 钉钉/企微/Slack/PagerDuty 专属 payload 包装
- 通知发送速率限制与去重
- 通知模板（jinja2）
- 邮件 HTML 富文本 + 链接到仪表盘
- 告警升级 / 抑制组合

## 相关 API

告警接口详见 [alerts.md](alerts.md)；WS 实时推送 `data:alert` 事件详见 [data.md](data.md)。