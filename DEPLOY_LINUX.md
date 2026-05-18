# KubeTrain2 Linux 服务器部署说明

本文档说明在 Linux 服务器上部署、启动、停止和排查 KubeTrain2 的常用步骤。示例默认项目目录为 `/opt/KubeTrain2`，后端端口为 `8010`，前端通过 Nginx 发布。

## 1. 目录与端口规划

| 项目 | 默认值 | 说明 |
|---|---:|---|
| 项目目录 | `/opt/KubeTrain2` | 上传后的 KubeTrain2 根目录 |
| 后端端口 | `8010` | Flask-SocketIO API 服务 |
| 前端访问端口 | `80` | Nginx 静态站点 |
| Agent 端口 | `8005` | 计算节点接收任务分发 |
| 数据库 | `kubetrain2` | MySQL 数据库名 |
| Redis | `redis://127.0.0.1:6379/0` | 任务队列与 Worker 注册 |

## 2. 安装系统依赖

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y nginx mysql-server redis-server curl git build-essential lsof
```

### CentOS / Rocky Linux

```bash
sudo dnf install -y nginx mysql-server redis curl git gcc gcc-c++ make lsof
sudo systemctl enable --now mysqld redis nginx
```

## 3. 准备 Python 与 Node.js

推荐使用已有的 conda 环境 `bs`。

```bash
conda create -n bs python=3.10 -y
conda run -n bs python --version
```

安装 Node.js 18+ 后检查版本：

```bash
node --version
npm --version
```

## 4. 放置项目文件

如果项目已上传到服务器，可移动或软链接到 `/opt/KubeTrain2`：

```bash
sudo mkdir -p /opt
sudo mv KubeTrain2 /opt/KubeTrain2
sudo chown -R $USER:$USER /opt/KubeTrain2
cd /opt/KubeTrain2
```

赋予脚本执行权限：

```bash
chmod +x scripts/*.sh
```

## 5. 初始化数据库

启动 MySQL 与 Redis：

```bash
sudo systemctl enable --now mysql || sudo systemctl enable --now mysqld
sudo systemctl enable --now redis-server || sudo systemctl enable --now redis
```

创建数据库并导入初始 SQL：

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS kubetrain2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p kubetrain2 < kubetrain2.sql
```

## 6. 配置后端环境变量

复制配置文件：

```bash
cp backend/.env.example backend/.env
vim backend/.env
```

建议至少修改以下项目：

```ini
FLASK_ENV=production
HOST=0.0.0.0
PORT=8010

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的数据库密码
DB_NAME=kubetrain2

REDIS_URL=redis://127.0.0.1:6379/0
SECRET_KEY=替换为随机长字符串
JWT_SECRET_KEY=替换为随机长字符串

SSH_HOST=192.168.171.3
SSH_USER=root
SSH_PASSWORD=如使用密码则填写
NFS_REMOTE_BASE=/data/kubetrain
NFS_MOUNT_PATH=/data

K8S_NAMESPACE=kubetrain
K8S_IN_CLUSTER=false
K8S_CONFIG_PATH=
TRAINING_IMAGE=kubetrain/pytorch-ddp:latest
IMAGE_PULL_POLICY=IfNotPresent
```

生产环境下 `SECRET_KEY`、`JWT_SECRET_KEY`、`DB_PASSWORD` 不能使用默认值，否则后端会拒绝启动。

## 7. 安装后端依赖

```bash
cd /opt/KubeTrain2
conda run -n bs pip install -r backend/requirements.txt
```

如果服务器上不使用 conda，也可以使用虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

## 8. 构建并发布前端

构建前端静态文件：

```bash
cd /opt/KubeTrain2
./scripts/start_frontend.sh build
```

安装 Nginx 配置：

```bash
sudo cp deploy/kubetrain2.nginx.conf /etc/nginx/conf.d/kubetrain2.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果项目目录不是 `/opt/KubeTrain2`，需要先修改 `deploy/kubetrain2.nginx.conf` 中的 `root` 路径。

## 9. 启动与停止后端

### 脚本方式

```bash
cd /opt/KubeTrain2
./scripts/start_backend.sh
./scripts/status.sh
```

停止后端：

```bash
cd /opt/KubeTrain2
./scripts/stop_backend.sh
```

查看日志：

```bash
tail -f /opt/KubeTrain2/logs/backend.log
```

### systemd 方式

先按实际部署用户和目录修改 `deploy/kubetrain2-backend.service`，然后安装：

```bash
sudo cp deploy/kubetrain2-backend.service /etc/systemd/system/kubetrain2-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now kubetrain2-backend
sudo systemctl status kubetrain2-backend
```

停止服务：

```bash
sudo systemctl stop kubetrain2-backend
```

## 10. 访问验证

后端健康检查：

```bash
curl http://127.0.0.1:8010/api/health
```

前端访问：

```bash
curl http://服务器IP/
```

浏览器访问：

```text
http://服务器IP/
```

默认账号：

```text
admin / admin123
```

## 11. 部署 Agent 计算节点

在计算节点上放置项目或至少复制 `agent/te_agent.py`。若使用完整项目目录：

```bash
cd /opt/KubeTrain2
chmod +x scripts/*.sh
conda run -n bs pip install requests
KUBETRAIN_SERVER=http://服务器IP:8010 ./scripts/start_agent.sh
```

也可以直接启动：

```bash
cd /opt/KubeTrain2
conda run -n bs python agent/te_agent.py --server http://服务器IP:8010 --agent-port 8005 --max-tasks 2
```

停止 Agent：

```bash
cd /opt/KubeTrain2
./scripts/stop_agent.sh
```

Agent systemd 方式：

```bash
sudo cp deploy/kubetrain2-agent.service /etc/systemd/system/kubetrain2-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now kubetrain2-agent
sudo systemctl status kubetrain2-agent
```

安装 systemd 服务前，需要将 `deploy/kubetrain2-agent.service` 中的 `KUBETRAIN_SERVER` 改为真实后端地址。

## 12. 开发模式前端

生产部署推荐 Nginx 静态发布。如果临时需要开发模式前端：

```bash
cd /opt/KubeTrain2
./scripts/start_frontend.sh dev
./scripts/stop_frontend.sh
```

开发模式默认端口为 `5173`，生产模式下前端由 Nginx 托管，通常不需要单独停止前端。

## 13. K3s / NFS / 镜像注意事项

如果使用 K8s 执行模式，需要确认：

```bash
kubectl get nodes
kubectl get ns kubetrain || kubectl create ns kubetrain
```

K3s 离线环境导入训练镜像时，应使用 `k8s.io` namespace：

```bash
sudo k3s ctr -n k8s.io images import /path/to/kubetrain-pytorch.tar
sudo k3s crictl images | grep kubetrain
```

为避免 K3s 重启后镜像丢失，可将镜像 tar 放到：

```bash
sudo mkdir -p /var/lib/rancher/k3s/agent/images/
sudo cp /path/to/kubetrain-pytorch.tar /var/lib/rancher/k3s/agent/images/
```

NFS 目录需要确保后端 SSH 用户可读写：

```bash
ssh root@192.168.171.3 "mkdir -p /data/kubetrain && chmod -R 777 /data/kubetrain"
```

## 14. 常用排查命令

查看整体状态：

```bash
cd /opt/KubeTrain2
./scripts/status.sh
```

查看端口：

```bash
ss -ltnp | grep -E '8010|5173|8005|80'
```

查看后端日志：

```bash
tail -n 200 /opt/KubeTrain2/logs/backend.log
```

查看 Nginx 日志：

```bash
sudo tail -n 100 /var/log/nginx/error.log
sudo tail -n 100 /var/log/nginx/access.log
```

检查 Redis：

```bash
redis-cli ping
```

检查 MySQL：

```bash
mysql -u root -p -e "SHOW DATABASES LIKE 'kubetrain2';"
```

## 15. 一组最小启动命令

```bash
cd /opt/KubeTrain2
chmod +x scripts/*.sh
conda run -n bs pip install -r backend/requirements.txt
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS kubetrain2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p kubetrain2 < kubetrain2.sql
cp backend/.env.example backend/.env
vim backend/.env
./scripts/start_frontend.sh build
sudo cp deploy/kubetrain2.nginx.conf /etc/nginx/conf.d/kubetrain2.conf
sudo nginx -t && sudo systemctl reload nginx
./scripts/start_backend.sh
./scripts/status.sh
```
