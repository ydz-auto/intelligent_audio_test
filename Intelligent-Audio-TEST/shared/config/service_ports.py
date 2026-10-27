"""服务端口注册表 — 集中管理所有微服务端口，避免散落硬编码"""

# HTTP 服务端口（来源：各服务 config/config.py 与 app.py 中 os.environ.get 默认值）
API_GATEWAY_PORT = 5000
TASK_SERVICE_HTTP_PORT = 5001
E2E_TEST_HTTP_PORT = 5002
API_TEST_HTTP_PORT = 5003
EVALUATION_SERVICE_HTTP_PORT = 5004
REPORT_SERVICE_HTTP_PORT = 5006
ALGORITHM_SERVICE_HTTP_PORT = 5007
AUTH_SERVICE_HTTP_PORT = 5009
TRANSFER_AGENT_HTTP_PORT = 5010

# gRPC 服务端口（来源：各服务 grpc/server.py 默认参数与 BaseConfig）
# INT-901：Windows 排除端口段 50060-50159（WinError 10013）gRPC 无法绑定，
# 全部迁出到 510xx（510xx 空闲且不与 parallel 栈 535xx 冲突）；e2e/audio/device 5005x 与 report 51068 不受影响。
E2E_TEST_GRPC_PORT = 50051
AUDIO_SERVICE_GRPC_PORT = 50052
DEVICE_SERVICE_GRPC_PORT = 50053
ALGORITHM_SERVICE_GRPC_PORT = 51067
REPORT_SERVICE_GRPC_PORT = 51068
AUTH_SERVICE_GRPC_PORT = 51069
TASK_SERVICE_GRPC_PORT = 51061
API_TEST_SERVICE_GRPC_PORT = 51071
EVALUATION_SERVICE_GRPC_PORT = 51091
TRANSFER_AGENT_GRPC_PORT = 51101

# Mock 替身服务端口（INT-137/INT-182：mock_services 独立替身，仅联调/验收/回归用；
# MOCK_SERVICES_ENABLED=true 时由 run_all.py 可选启动，默认关闭、不进生产编排与镜像）
MOCK_THIRD_PARTY_EVAL_HTTP_PORT = 5099
MOCK_REALTIME_API_WS_PORT = 5098
MOCK_EVAL_SERVER_HTTP_PORT = 5097
# INT-1169/1176：被测 API 单轮协议 DUT mock（api_adapter_service 删除后替代），
# 实现 /health + /api/create_task + /api/get_status + /api/get_final_result +
# /api/delete_task + /chat（voice_llm 多轮会话）
MOCK_DUT_API_HTTP_PORT = 5096
# INT-2079（A4）：被测 API WS 请求-响应式 mock（websocket + streaming=false 冒烟）
MOCK_WS_REQUEST_RESPONSE_API_PORT = 5095

# 基础设施端口
REDIS_PORT = 6379
POSTGRESQL_PORT = 5432
RUSTFS_PORT = 9000

# 前端端口（来源：frontend/vite.config.ts）
FRONTEND_PORT = 6173
# 前端开发端口（run_all.py / stop_all.py 用 --port 覆盖 vite.config.ts 的 6173 为 5173）
FRONTEND_DEV_PORT = 5173
# RustFS 控制台端口（rustfs server --console-address :9001）
RUSTFS_CONSOLE_PORT = 9001
