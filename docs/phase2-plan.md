# Phase 2：产品化上线

> 创建日期：2026-04-29 | 状态：设计完成，Phase 1 完成后实施

## 0. 前置条件

Phase 1 已完成：
- 至少一种模型训练完成，方向准确率 ≥ 55%
- 预测管线可用，推荐系统不再 fallback 随机数
- Web 前端展示真实预测结果

---

## 1. 目标

从"本地能跑的工具"升级为"用户可以访问的在线服务"，具备完整的用户体系和付费能力，支持每日自动数据更新和模型迭代。

---

## 2. 功能模块

### 2.1 用户系统

| 功能 | 说明 |
|------|------|
| 注册/登录 | 手机号 + 验证码（首选），或邮箱 + 密码 |
| JWT 鉴权 | 无状态 Token，7 天过期 + refresh token 机制 |
| 角色管理 | 普通用户 / 会员 / 管理员 |
| 个人信息 | 修改密码、绑定微信、推送偏好设置 |

### 2.2 会员体系

| 等级 | 价格（参考） | 权益 |
|------|------------|------|
| 免费 | ¥0 | 每日 1 次查询 + TOP-3 推荐 |
| 基础会员 | ¥29/月 或 ¥199/年 | 无限查询 + TOP-10 推荐 + 1 支个股盯盘 |
| 高级会员 | ¥59/月 或 ¥399/年 | 全部功能 + 5 支个股盯盘 + 数据导出 + 历史回测 |

**支付方式**：
- 微信支付（JSAPI 支付，H5 内唤起）
- 支付宝（网页支付）

### 2.3 每日自动化

```
cron 调度 (每天 17:30 收盘后)
  ├── 数据更新：python main.py update --all
  ├── 数据清洗：python main.py clean --incremental
  ├── 模型评估：如果新交易日 > 30 天未重训，触发训练
  ├── 批量预测：python main.py predict
  └── 推荐生成：保存到 DB，前端读取
```

技术方案：
- WSL 内 `cron` 定时任务
- 或 Python 的 `APScheduler`，集成到 FastAPI 进程中
- Phase 3 迁移到云端后用 Linux cron / K8s CronJob

### 2.4 盯盘提醒

用户可以设置关注的个股和提醒条件：

| 提醒类型 | 触发条件 |
|------|---------|
| 涨跌幅提醒 | 当日涨跌幅超过 ±X% |
| 模型信号提醒 | 模型预测方向发生变化 |
| 价格突破提醒 | 突破 MA5/MA10/MA20 |
| 推荐上榜提醒 | 个股进入当日 TOP-N 推荐 |

推送方式：
- Web 端：站内通知（右上角红点）
- 未来小程序：微信订阅消息

技术方案：WebSocket 实时推送 + 数据库存储通知历史。

---

## 3. 数据库扩展

Phase 1 的 3 张表基础上新增：

```sql
-- 用户表
users (id, phone, email, password_hash, nickname, avatar, role, status, created_at)

-- 会员订单
membership_orders (id, user_id, plan, amount, pay_method, pay_status, start_date, end_date, created_at)

-- 盯盘设置
watchlist (id, user_id, ts_code, alert_config JSONB, enabled, created_at)

-- 通知记录
notifications (id, user_id, type, title, content, is_read, created_at)

-- 每日推荐快照（避免每次请求重新预测）
daily_recommendations (id, trade_date, ts_code, predicted_return, confidence, risk_score, rank, created_at)
```

---

## 4. 技术选型

| 组件 | 方案 | 原因 |
|------|------|------|
| 鉴权 | `python-jose` + `passlib[bcrypt]` | 轻量 JWT，FastAPI 原生集成 |
| 微信支付 | `wechatpy` | Python 微信 SDK，支持支付 + 小程序 |
| 定时任务 | `APScheduler` | 进程内调度，无需外挂 cron |
| 实时推送 | FastAPI WebSocket | 框架内置，无需额外组件 |
| 验证码 | 阿里云短信 / 腾讯云短信 | 国内用户优先 |
| 支付回调 | FastAPI webhook endpoint | 接收微信/支付宝异步通知 |

---

## 5. 架构图

```
                         ┌──────────────────────┐
                         │    Nginx (反向代理)    │
                         │    HTTPS + 静态资源    │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │    FastAPI 应用        │
                         │  ┌─────────────────┐  │
                         │  │ 用户模块         │  │
                         │  │ 会员模块         │  │
                         │  │ 预测模块 (Phase1)│  │
                         │  │ 盯盘模块         │  │
                         │  │ 推荐模块         │  │
                         │  ├─────────────────┤  │
                         │  │ APScheduler      │  │
                         │  │ WebSocket Hub    │  │
                         │  └─────────────────┘  │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             ┌──────────┐  ┌──────────┐  ┌──────────────┐
             │PostgreSQL│  │  Redis   │  │ 第三方服务     │
             │ 业务数据  │  │ 缓存/会话 │  │ 短信/支付回调  │
             └──────────┘  └──────────┘  └──────────────┘
```

Redis 用途：
- 验证码 5 分钟过期
- 免费用户每日查询次数限制
- 每日推荐结果缓存（减少 DB 查询）
- WebSocket 连接状态维护

---

## 6. 部署方案

### 6.1 Phase 2 阶段：单机部署

```
WSL / 云服务器 (2C4G 起步)
├── PostgreSQL 16
├── Redis 7
├── FastAPI (uvicorn, 4 workers)
├── Nginx（HTTPS 反代 + 静态文件）
└── APScheduler（每日数据更新）
```

### 6.2 Phase 3 阶段：容器化

```
Docker Compose
├── app (FastAPI)
├── db (PostgreSQL)
├── redis (Redis)
├── nginx (Nginx)
└── scheduler (APScheduler 独立容器)
```

---

## 7. 安全清单

| 项目 | 措施 |
|------|------|
| 密码存储 | bcrypt 加盐哈希 |
| API 鉴权 | JWT + 过期 + refresh token |
| SQL 注入 | psycopg2 参数化查询（已有） |
| XSS | 前端输出转义 + CSP header |
| HTTPS | Nginx + Let's Encrypt 免费证书 |
| 支付安全 | 微信/支付宝 SDK 签名验证 + 回调验签 |
| 频率限制 | Redis 令牌桶，免费用户限速 |
| 敏感配置 | `.env` 文件，不提交到 git |

---

## 8. 时间估算

| 模块 | 预计耗时 |
|------|---------|
| 用户系统（注册/登录/JWT） | 3 天 |
| 会员 + 微信支付接入 | 5 天（含微信审核等待） |
| 每日自动化（APScheduler + 流程串联） | 2 天 |
| 盯盘提醒（WebSocket + 通知） | 3 天 |
| 前端改版（个人中心/会员页/支付页） | 3 天 |
| 部署上线（Nginx + HTTPS + 域名） | 1 天 |
| 测试 + 修 Bug | 2 天 |
| **合计** | **约 19 天** |

---

## 9. 下一步

Phase 2 完成后进入 **Phase 3：多维分析增强**：
- 基本面数据接入（PE/PB/ROE/营收）
- 舆情分析（新闻情感 + 龙虎榜 + 资金流向）
- 回测引擎（历史策略验证 + 绩效报告）
- 微信小程序
- 云端部署 + CI/CD
