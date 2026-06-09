# 评估维度服务 (WER/SER Calculator Service)

一个基于 Flask 的 WER（Word Error Rate）和 SER（Sentence Error Rate）计算服务，支持本地处理、分布式调度和动态并发控制。

## 功能特性

- **WER 计算**：支持中英文混合文本的词错误率计算
- **SER 计算**：支持句子错误率计算
- **本地/远程处理**：支持本地处理和分发到远程 Worker 节点
- **两层并发控制**：
  - 本地并发：限制单个服务实例同时处理的任务数量
  - 远程端点并发：限制分发到各远程节点的任务数量
- **动态配置**：支持通过 API 动态调整端点的并发限制，无需重启服务
- **健康检查**：提供健康检查端点，便于监控服务状态
- **模块化设计**：采用 MVC 架构，便于扩展和维护

## 技术栈

- Python 3.9+
- Flask 3.0.0+
- NumPy 1.26.0+

## 项目结构

```
wer/
├── app/                    # 应用模块
│   ├── app.py             # 应用创建和初始化
│   ├── config.py          # 配置信息
│   ├── controllers/       # API 控制器
│   │   ├── api.py         # 任务管理 API
│   │   └── health.py      # 健康检查 API
│   ├── database/          # 数据库相关
│   │   ├── schema.sql     # 数据库表结构
│   │   └── wer_tasks.db   # SQLite 数据库文件
│   ├── models/            # 数据模型
│   │   └── task.py        # 任务和端点模型
│   ├── services/          # 业务逻辑
│   │   ├── remote_service.py   # 远程服务调用
│   │   ├── task_service.py     # 任务管理
│   │   └── wer_calculator.py   # WER/SER 计算核心逻辑
│   └── utils/             # 工具函数
│       ├── concurrency.py      # 并发控制
│       ├── decorators.py       # 装饰器
│       └── responses.py        # 响应格式化
├── app.py                 # 主应用入口
├── API_DOC.md             # API 接口文档（详细）
├── README.md              # 项目说明文档
└── requirements.txt       # 依赖列表
```

## 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd wer
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置服务**
   - 修改 `app/config.py` 文件中的配置项
   - 可配置服务名称、端口、本地并发限制等

## 运行服务

### 启动服务
```bash
python app.py
```

### 配置说明

在 `app/config.py` 中可以配置：

```python
class Config:
    # Flask settings
    DEBUG = True
    PORT = 5001
    HOST = '0.0.0.0'
    
    # Local concurrency control
    LOCAL_MAX_CONCURRENCY = 10
    
    # Task settings (per-task-type concurrency in worker mode)
    CONCURRENCY_LIMITS = {
        'wer': 2,
        'ser': 1
    }
```

## 文档结构

本项目有两份文档：

| 文档 | 内容 | 读者 |
|------|------|------|
| **README.md** | 项目简介、安装、运行、快速开始 | 所有用户 |
| **API_DOC.md** | 完整的 API 接口规范、请求/响应示例、错误码说明 | API 开发者 |

建议先阅读 README 了解项目概况，再查阅 API_DOC 获取详细的接口文档。

## 快速开始

### 1. 创建本地任务

```bash
curl -X POST http://localhost:5001/api/create_task \
  -H "Content-Type: application/json" \
  -d '{
    "asr_ref": "今天天气不错",
    "asr_result": "今天天气不措",
    "task_type": "wer"
  }'
```

### 2. 检查任务状态

```bash
curl http://localhost:5001/api/get_status/{task_id}
```

### 3. 获取评估结果

```bash
curl http://localhost:5001/api/get_final_result/{task_id}
```

## 分布式调度

### 配置远程端点

```bash
# 创建端点配置
curl -X POST http://localhost:5001/api/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://localhost:5002",
    "name": "worker-1",
    "capabilities": {
      "wer": {"max_process": 5},
      "ser": {"max_process": 3}
    }
  }'
```

### 创建分布式任务

```bash
curl -X POST http://localhost:5001/api/create_task \
  -H "Content-Type: application/json" \
  -d '{
    "asr_ref": "今天天气不错",
    "asr_result": "今天天气不措",
    "task_type": "wer",
    "endpoints": [{"endpoint": "http://localhost:5002"}]
  }'
```

### 动态调整并发限制

```bash
# 调整 WER 任务的最大并发数
curl -X PUT "http://localhost:5001/api/endpoints/http://localhost:5002/concurrency/wer" \
  -H "Content-Type: application/json" \
  -d '{"max_process": 10}'
```

### 查看并发状态

```bash
curl http://localhost:5001/api/status
```

## API 文档

详细的 API 接口文档请参考 [API_DOC.md](API_DOC.md)，包含：

- 所有 API 端点的详细说明
- 请求/响应示例
- 错误码说明
- 并发控制机制
- 调用流程示例

## 测试

运行项目根目录下的测试文件：

```bash
python test_wer.py       # 测试 WER 计算
python test_ser.py       # 测试 SER 计算
python test_api.py       # 测试 API 接口
python test_health.py    # 测试健康检查
python test_concurrency.py  # 测试并发控制
```

## 开发说明

1. **添加新功能**：在 `app/services/` 目录下添加新的服务模块
2. **修改配置**：在 `app/config.py` 文件中修改配置项
3. **扩展 API**：在 `app/controllers/api.py` 中添加新的路由
4. **数据库变更**：修改 `app/database/schema.sql` 并重新初始化数据库

## 部署建议

- **生产环境**：建议使用 Gunicorn 或 uWSGI 等生产级 WSGI 服务器部署
- **监控**：使用健康检查端点 `/health` 和状态查询端点 `/api/status` 监控服务状态
- **分布式部署**：高并发场景下使用多 Worker 节点分担压力
- **动态调整**：根据实际负载通过 API 动态调整并发限制

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
