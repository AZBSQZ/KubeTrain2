# KubeTrain 2.0

容器化分布式 AI 训练平台 — 独立全栈系统，支持 K8s Job 与 Agent 两种执行模式。

## 功能模块

| 模块 | 说明 |
|---|---|
| 训练任务 | 创建/提交/监控训练任务，实时日志 + 指标图表，WebSocket 推送 |
| 数据集 | 版本化管理，SFTP 上传到 NFS，自动 zip 解压 |
| 算法 | 多版本脚本管理，直接粘贴代码或引用文件路径 |
| 模型仓库 | 训练完成自动注册，版本对比，生产版本标记 |
| 资源管理 | GPU/CPU/内存概览，资源配额，节点池管理 |
| K8s 集群 | 多集群管理，连通性测试，kubeconfig 注入 |
| Agent 节点 | Worker 注册/心跳，任务分发，实时状态 |
| 告警系统 | 告警规则，分级（critical/warning/info），确认/解决流程 |
| 用户管理 | JWT 认证，角色权限（admin/user/guest），资源配额绑定 |

## 目录结构

```
KubeTrain2/
├── backend/                    # Flask 后端 (port 8010)
│   ├── app/
│   │   ├── __init__.py        # Flask app factory + SocketIO
│   │   ├── api/               # REST API blueprints (16个)
│   │   │   ├── auth.py
│   │   │   ├── tasks.py
│   │   │   ├── datasets.py
│   │   │   ├── algorithms.py
│   │   │   ├── models.py
│   │   │   ├── model_groups.py
│   │   │   ├── logs.py
│   │   │   ├── metrics.py
│   │   │   ├── resources.py
│   │   │   ├── alerts.py
│   │   │   ├── node_pools.py
│   │   │   ├── workers.py
│   │   │   ├── clusters.py
│   │   │   └── tags.py
│   │   ├── models/            # SQLAlchemy ORM 模型 (13个)
│   │   ├── services/          # 核心服务层
│   │   │   ├── task_scheduler.py   # Redis 优先级队列调度
│   │   │   ├── task_watcher.py     # K8s Job 状态轮询
│   │   │   ├── log_collector.py    # Pod 日志采集 + 指标解析
│   │   │   ├── k8s_job_executor.py # K8s/Agent 任务执行
│   │   │   ├── k8s_client.py      # Kubernetes 客户端
│   │   │   ├── resource_manager.py # 节点资源同步
│   │   │   ├── worker_registry.py  # Redis Worker 注册表
│   │   │   └── alert_service.py   # 告警触发与推送
│   │   ├── websocket/         # SocketIO 事件处理
│   │   └── utils/             # datetime_helper 等工具
│   ├── config.py
│   ├── run.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # Vue3 + Vite 前端 (port 5173)
│   ├── src/
│   │   ├── api/index.js       # 所有 API 调用封装
│   │   ├── stores/auth.js     # Pinia 认证状态
│   │   ├── router/index.js    # Vue Router
│   │   ├── layouts/MainLayout.vue
│   │   └── views/             # 所有页面组件
│   ├── package.json
│   └── vite.config.js
├── agent/
│   └── te_agent.py            # 训练 Agent（部署到 Worker 节点）
├── kubetrain2.sql              # 数据库初始化 SQL
├── start.ps1                  # Windows 一键启动脚本
└── README.md
```

## 快速启动

### 1. 环境准备

```bash
# Python 环境
conda create -n bs python=3.10
conda activate bs
pip install -r backend/requirements.txt

# Node.js (v18+)
node --version
```

### 2. 数据库初始化

```sql
CREATE DATABASE IF NOT EXISTS kubetrain2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
mysql -u root -p kubetrain2 < kubetrain2.sql
```

### 3. 后端配置

复制并修改 `.env.example`：

```bash
cp backend/.env.example backend/.env
```

关键配置项：
```ini
DB_HOST=localhost
DB_PORT=3306
DB_NAME=kubetrain2
DB_USER=root
DB_PASSWORD=your_password
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key
SSH_HOST=192.168.171.3      # NFS 服务器 IP
SSH_USER=root
NFS_REMOTE_BASE=/data/kubetrain
```

### 4. 启动服务

**方式 A：PowerShell 一键启动**
```powershell
.\start.ps1 -All
```

**方式 B：手动启动**
```powershell
# 后端
cd backend
conda run -n bs python run.py

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

### 5. 访问

| 地址 | 说明 |
|---|---|
| http://localhost:5173 | 前端 UI |
| http://localhost:8010/api | 后端 API |
| http://localhost:8010/api/health | 健康检查 |

默认账号：`admin` / `admin123`

## 执行模式说明

| 模式 | 说明 | 适用场景 |
|---|---|---|
| `auto` | 自动选择（有 K8s 节点用 K8s，否则找 Agent） | 推荐 |
| `k8s` | 提交 Kubernetes Job | 有 K8s 集群 |
| `agent` | 分发给 te_agent.py 执行 | 裸机 / 无 K8s |

## 并行模式说明

| 模式 | 说明 |
|---|---|
| `single` | 单进程训练 |
| `ddp` | DistributedDataParallel（多 GPU / 多节点） |
| `fsdp` | FullyShardedDataParallel（大模型） |

## Agent 部署

在 Worker 节点上：
```bash
# 安装依赖
pip install requests torch

# 启动 Agent（指向后端地址）
python te_agent.py --backend http://master_ip:8010 --worker-id worker-01 --pool-id <pool_id>
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Flask + Flask-SocketIO + Flask-JWT-Extended |
| ORM | SQLAlchemy + Flask-Migrate |
| 数据库 | MySQL 8.0+ |
| 缓存/队列 | Redis |
| K8s 集成 | kubernetes Python SDK |
| SSH/SFTP | paramiko |
| 前端框架 | Vue 3 + Vite |
| UI 组件 | Element Plus |
| 状态管理 | Pinia |
| 图表 | ECharts |
| 实时通信 | Socket.IO |
