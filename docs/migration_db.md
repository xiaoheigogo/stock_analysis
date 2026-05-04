# 数据库迁移指南

从旧电脑（Windows PostgreSQL）迁移数据到新电脑（WSL PostgreSQL）。

## 环境概览

| 环境 | 系统 | PostgreSQL |
|------|------|------------|
| 旧电脑 | Windows 10/11 | 独立安装 |
| 新电脑 WSL | Ubuntu 24.04 | `sudo apt install postgresql` 安装 |

## 方式一：pg_dump 导出/导入（推荐，保留历史数据）

### 第一步 — 在旧 Windows 电脑上导出

打开 PowerShell 或 CMD，进入 PostgreSQL bin 目录（默认路径 `C:\Program Files\PostgreSQL\<版本>\bin\`）：

```powershell
pg_dump -h localhost -U postgres -d stock --no-owner --no-acl -F p -f stock_backup.sql
```

参数说明：
- `-F p`：纯 SQL 格式（`plain`），跨版本兼容，避免 custom format 版本不匹配问题
- `--no-owner`：跳过对象所有者，避免跨环境用户不匹配报错
- `--no-acl`：跳过权限（GRANT/REVOKE），同理

> **为什么不用 `-F c`？** custom format 与 pg_dump 版本绑定。旧电脑 PG17 → WSL PG16 会报 `unsupported version (1.16)`。纯 SQL 无此问题。

### 第二步 — 传输到 WSL

推荐放到独立备份目录：

```powershell
# 在 Windows PowerShell 中执行
wsl mkdir -p /home/xiaohei/db_backups
wsl cp stock_backup.sql /home/xiaohei/db_backups/
```

或者先复制到 Windows 用户目录，再从 WSL 挂载路径访问：
```powershell
copy stock_backup.sql C:\Users\<你的用户名>\
```
```bash
cp /mnt/c/Users/<你的用户名>/stock_backup.sql ~/db_backups/
```

### 第三步 — 在本 WSL 中导入

先确保 PostgreSQL 服务已启动且 `stock` 数据库已创建：

```bash
sudo pg_ctlcluster 16 main start
sudo -u postgres createdb stock 2>/dev/null || echo "数据库已存在"
```

导入数据（纯 SQL 用 `psql`，不是 `pg_restore`）：

```bash
psql -h localhost -U postgres -d stock -f ~/db_backups/stock_backup.sql
```

> 导入时会看到 `transaction_timeout`、`relation already exists`、`multiple primary keys` 等报错，**均可忽略**——分别是 PG17 特有参数不兼容和表结构已存在的提示，数据（COPY 行）正常导入。

验证导入结果：

```bash
source venv38/bin/activate
python test_db_connection.py
```

---

## 方式二：重新拉取（不需要历史数据）

如果旧数据不重要，直接用项目的数据管道重拉，完全重建：

```bash
source venv38/bin/activate

# 建表
python -m utils.tables

# 全量拉取数据
python main.py update --all
```

---

## 导出文件存放建议

- **不推荐**放在项目路径下（备份文件体积大，容易误提交到 git）
- **推荐**放到独立目录：`~/db_backups/`
- 如果必须放项目内，请加到 `.gitignore`：`echo "*.sql" >> .gitignore`

---

## 从 Windows DBeaver 连接 WSL PostgreSQL

1. 修改 PostgreSQL 监听地址（默认仅 `localhost`，外部工具无法连接）：

```bash
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/16/main/postgresql.conf
echo "host    all             all             172.29.0.0/16          scram-sha-256" | sudo tee -a /etc/postgresql/16/main/pg_hba.conf
sudo pg_ctlcluster 16 main restart
```

2. DBeaver 连接参数：

| 字段 | 值 |
|------|-----|
| Host | `localhost`（WSL2 自动转发） |
| Port | `5432` |
| Database | `stock` |
| User | `postgres` |
| Password | `123456` |

---

## 常见问题

### Q: pg_dump 提示 "pg_dump: error: connection to server failed"
A: 确认旧电脑 PostgreSQL 服务正在运行。Windows 服务列表中找到 `postgresql-x64-<版本>` 并启动。

### Q: pg_restore 报 "unsupported version (1.16) in file header"
A: 旧电脑 PG17 的 custom format 与 WSL PG16 不兼容。用 `-F p`（纯 SQL）重新导出即可跨版本迁移。

### Q: 导入时报 "unrecognized configuration parameter 'transaction_timeout'"
A: PG17 的参数在 PG16 中不存在，可忽略，不影响数据导入。

### Q: 导入时报 "relation already exists" / "multiple primary keys"
A: WSL 中已建过同名表，报错可忽略，COPY 数据正常写入。

### Q: pg_restore 提示 "role 'postgres' does not exist"
A: WSL 中 PostgreSQL 默认只有 `postgres` 角色。用 `--role=postgres` 即可。

### Q: DBeaver 连接报 "Connection refused"
A: PostgreSQL 默认仅监听 `localhost`。需要修改 `listen_addresses = '*'` 并添加 `pg_hba.conf` 允许规则（见上文 DBeaver 连接章节）。

### Q: 导入后中文乱码
A: 导出时数据库编码已是 UTF-8，正常不会乱码。如遇到，检查 `pg_restore` 额外加 `--encoding=UTF8`。

### Q: 旧电脑 PostgreSQL 已卸载，还能恢复数据吗？
A: 如果 `C:\Program Files\PostgreSQL\<版本>\data\` 目录还在，可以重新安装相同大版本的 PostgreSQL，用旧 data 目录替换新安装的 data 目录后启动，再导出。
