"""API Gateway 领域配置"""
import os
from shared.infrastructure.config import BaseConfig, _get_int


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5000))
    # 本地音频上传临时存储路径（分片上传、合并、转码中间文件）
    AUDIO_STORAGE_PATH = os.environ.get(
        'AUDIO_STORAGE_PATH',
        os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios')
    )

    # WSGI 线程池上限（Werkzeug ThreadedWSGIServer monkey-patch）
    # 100 并发用户场景下，并发 HTTP 请求约 30-40，其余为 WebSocket 长连接
    # None = 使用默认值 40；可通过环境变量 WSGI_MAX_THREADS 覆盖
    WSGI_MAX_THREADS = int(os.environ.get('WSGI_MAX_THREADS', 40))

    # ===== 认证配置 =====
    # 认证模式: dev(本地OAuth) / prod(华为云OAuth) / off(无认证)
    AUTH_MODE = os.environ.get('AUTH_MODE', 'off')

    # 自助注册开关（INT-51）：关闭后 POST /api/v1/auth/register 返回 403
    AUTH_REGISTRATION_ENABLED = os.environ.get(
        'AUTH_REGISTRATION_ENABLED', 'true').strip().lower() in (
        '1', 'true', 'yes', 'on')

    # OAuth state 防伪签名有效期（秒）：授权跳转到回调的最长间隔
    OAUTH_STATE_TTL_SECONDS = int(os.environ.get('OAUTH_STATE_TTL_SECONDS', '600'))

    # OAuth 绑定票据有效期（秒）：intent=bind 回调回前端票据的完成窗口（INT-147）
    OAUTH_BIND_TICKET_TTL_SECONDS = int(
        os.environ.get('OAUTH_BIND_TICKET_TTL_SECONDS', '300'))

    # ===== 登录密码 RSA 加密传输（INT-147 对齐旧库安全基线）=====
    # false 时 /auth/login、/auth/register 接受明文 password 字段（灰度回退）
    AUTH_PASSWORD_ENCRYPTION_ENABLED = os.environ.get(
        'AUTH_PASSWORD_ENCRYPTION_ENABLED', 'true').strip().lower() in (
        '1', 'true', 'yes', 'on')
    # RSA 私钥 PEM 持久化路径（不存在时自动生成；务必纳入备份）
    AUTH_RSA_KEY_PATH = os.environ.get(
        'AUTH_RSA_KEY_PATH',
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            'data', 'auth_key.pem'))
    # 降级 RSA 私钥路径（INT-245：非安全上下文 http+IP 前端 WebCrypto
    # 不可用 → jsencrypt PKCS1v15；与主密钥成对独立，kid 即算法绑定）
    AUTH_RSA_FALLBACK_KEY_PATH = os.environ.get(
        'AUTH_RSA_FALLBACK_KEY_PATH',
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            'data', 'auth_key_fallback.pem'))

    # 自定义 OAuth 提供方回调基址（authorize redirect_uri 由它 + slug 拼接）
    OAUTH_REDIRECT_BASE = os.environ.get(
        'OAUTH_REDIRECT_BASE', 'http://localhost:8000')

    # JWT 配置
    JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret-change-in-production')
    JWT_EXPIRE_HOURS = int(os.environ.get('JWT_EXPIRE_HOURS', '24'))
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

    # 开发模式 - 本地 OAuth
    DEV_OAUTH_CLIENT_ID = os.environ.get('DEV_OAUTH_CLIENT_ID', 'local_dev_client')
    DEV_OAUTH_CLIENT_SECRET = os.environ.get('DEV_OAUTH_CLIENT_SECRET', 'local_dev_secret')
    DEV_OAUTH_REDIRECT_URI = os.environ.get(
        'DEV_OAUTH_REDIRECT_URI', 'http://localhost:8000/api/v1/auth/callback'
    )
    DEV_DEFAULT_USERNAME = os.environ.get('DEV_DEFAULT_USERNAME', 'dev_user')
    DEV_DEFAULT_PASSWORD = os.environ.get('DEV_DEFAULT_PASSWORD', 'dev_password')
    DEV_DEFAULT_ROLE = os.environ.get('DEV_DEFAULT_ROLE', 'admin')

    # 生产模式 - 华为云 OAuth
    HW_OAUTH_CLIENT_ID = os.environ.get('HW_OAUTH_CLIENT_ID', '')
    HW_OAUTH_CLIENT_SECRET = os.environ.get('HW_OAUTH_CLIENT_SECRET', '')
    HW_OAUTH_REDIRECT_URI = os.environ.get(
        'HW_OAUTH_REDIRECT_URI', 'http://localhost:8000/api/v1/auth/callback'
    )
    HW_OAUTH_AUTHORIZE_URL = os.environ.get(
        'HW_OAUTH_AUTHORIZE_URL', 'https://oauth.huaweicloud.com/oauth2/authorize'
    )
    HW_OAUTH_TOKEN_URL = os.environ.get(
        'HW_OAUTH_TOKEN_URL', 'https://oauth.huaweicloud.com/oauth2/token'
    )
    HW_OAUTH_USERINFO_URL = os.environ.get(
        'HW_OAUTH_USERINFO_URL', 'https://oauth.huaweicloud.com/oauth2/userinfo'
    )

    # ===== 报告分享（INT-971）=====
    # 分享链接拼接用公开 origin（请求 base URL 不可用时回退；
    # 形态与前端路由 /report/:reportId?share= 一致）
    PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'http://localhost:5000')

    # ===== MCP 自转发基址（INT-1150）=====
    # MCP tools/call 把调用转发回网关自身 REST 端点时使用的内部基址。
    # 必须服务端配置，不得跟随客户端 Host 头 —— 已认证调用者把网关当跳板
    # 向内网任意地址发注册表内工具路径请求属认证 SSRF（审计打回 P2）。
    # 空 = 回退网关自身监听地址 http://127.0.0.1:{PORT}；部署在反向代理/
    # 容器网络后如需显式指定内部入口，设 MCP_SELF_FORWARD_BASE
    # （如 http://api_gateway:5000）。
    MCP_SELF_FORWARD_BASE = os.environ.get('MCP_SELF_FORWARD_BASE', '')

    # ===== 报告对比（INT-1406）=====
    # 跨任务大结果集同步聚合的 GenerateCompareReport gRPC 调用显式超时（秒）。
    # 客户端默认 deadline 为 60s（GRPC_CLIENT_DEADLINE_SECONDS），跨任务大结果集
    # 同步聚合实测 >60s → DEADLINE_EXCEEDED → 网关 400；此配置显式放宽该调用。
    GRPC_REPORT_COMPARE_TIMEOUT_SECONDS: int = _get_int(
        'GRPC_REPORT_COMPARE_TIMEOUT_SECONDS', 600)

    @classmethod
    def validate(cls):
        """启动校验必填项 + AUTH_MODE 枚举合法性（INT-180：非法取值启动即自曝，
        杜绝拼错的模式静默落入 JWT 强制态）"""
        super().validate()
        from shared.constants.auth_mode import normalize_auth_mode
        from shared.infrastructure.config import ConfigValidationError
        try:
            normalize_auth_mode(cls.AUTH_MODE)
        except ValueError as exc:
            raise ConfigValidationError(str(exc)) from exc


# 兼容旧代码中的 GatewayConfig 引用
GatewayConfig = Config
