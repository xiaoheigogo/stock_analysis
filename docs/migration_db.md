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
pg_dump -h localhost -U postgres -d stock --no-owner --no-acl -F c -f stock_backup.dump
```

参数说明：
- `-F c`：压缩格式（custom format），体积小，恢复快
- `--no-owner`：跳过对象所有者，避免跨环境用户不匹配报错
- `--no-acl`：跳过权限（GRANT/REVOKE），同理

### 第二步 — 传输到 WSL

```powershell
# 在 Windows PowerShell 中执行
wsl cp stock_backup.dump /home/xiaohei/pyproject/stock_analysis/
```

或者复制到 Windows 用户目录，再从 WSL 挂载路径访问：
```powershell
copy stock_backup.dump C:\Users\<你的用户名>\
```
```bash
# 在 WSL 中
cp /mnt/c/Users/<你的用户名>/stock_backup.dump ~/
```

### 第三步 — 在本 WSL 中导入

先确保 PostgreSQL 服务已启动且 `stock` 数据库已创建：

```bash
sudo pg_ctlcluster 16 main start
sudo -u postgres createdb stock 2>/dev/null || echo "数据库已存在"
```

导入数据：

```bash
pg_restore -h localhost -U postgres -d stock --no-owner --role=postgres stock_backup.dump
```

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

- **不推荐**放在项目路径下（`.dump` 文件体积大，容易误提交到 git）
- **推荐**放到独立目录：`~/db_backups/`
- 如果必须放项目内，请加到 `.gitignore`：`echo "*.dump" >> .gitignore`

---

## 常见问题

### Q: pg_dump 提示 "pg_dump: error: connection to server failed"
A: 确认旧电脑 PostgreSQL 服务正在运行。Windows 服务列表中找到 `postgresql-x64-<版本>` 并启动。

### Q: pg_restore 提示 "role 'postgres' does not exist"
A: WSL 中 PostgreSQL 默认只有 `postgres` 角色。用 `--role=postgres` 即可。

### Q: 导入后中文乱码
A: 导出时数据库编码已是 UTF-8，正常不会乱码。如遇到，检查 `pg_restore` 额外加 `--encoding=UTF8`。

### Q: 旧电脑 PostgreSQL 已卸载，还能恢复数据吗？
A: 如果 `C:\Program Files\PostgreSQL\<版本>\data\` 目录还在，可以重新安装相同大版本的 PostgreSQL，用旧 data 目录替换新安装的 data 目录后启动，再导出。
