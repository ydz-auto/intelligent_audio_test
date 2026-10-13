# OAuth 认证方案设计

> 本文档定义智能语音测试平台的 OAuth 认证方案（双模式：本地 OAuth + 华为云 OAuth）。
> 设计已于 2026-09-11 落地实现，实际代码路径与设计一致：
> - `api_gateway/middleware.py` — AuthMiddleware（JWT 解析 → request.state.user_id / role_id / permissions）
> - `api_gateway/routes/auth_bp.py` — 登录/回调/刷新/登出/me 5 个端点
> - `api_gateway/application/services/auth/` — auth_service / huawei_oauth / local_oauth / token_service / dependencies
> - `auth_service/` — DDD 四层骨架（domain + application + infrastructure + interfaces/grpc）
> 关联文档：[RBAC权限划分.md](./RBAC权限划分.md)、[DDD重构.md](./DDD重构.md)

---

## 九、认证与开发模式设计

### 1. 现状

| 维度 | 状态 |
|---|---|
| 认证流程 | **已实现** — AuthMiddleware（`api_gateway/middleware.py`）解析 JWT，通过 `AUTH_MODE` 控制（`off` / `dev` / `prod`） |
| OAuth 模型 | **已定义并实现** — User/OAuthClient/OAuthRefreshToken 表已建，RBAC 模型完整 |
| 华为云 OAuth 配置 | **Provider 已实现** — `api_gateway/application/services/auth/huawei_oauth.py`（授权码模式、token 换取、userinfo 获取）；配置项 `HW_OAUTH_*` 在 `.env` 中 |
| 开发模式/本地 OAuth | **已实现** — `api_gateway/application/services/auth/local_oauth.py`（本地登录验证 + JWT 签发） |
| RBAC | 模型已定义 + `api_gateway/application/services/auth/dependencies.py` 提供 `require_permission` 辅助函数 |

认证骨架（模型+表）+ 肌肉（AuthMiddleware、auth_bp 路由、auth_service、TokenService、OAuth Providers）已全部搭好。RBAC 路由层接入为可选优化。

### 2. 认证方案：华为云 OAuth + 开发模式本地 OAuth

#### 2.1 双模式认证架构

```
┌─────────────────────────────────────────────────────────┐
│                    api_gateway                           │
│                                                         │
│  请求 → CORSMiddleware → AuthMiddleware → 路由处理      │
│                              │                           │
│              ┌───────────────┼───────────────┐          │
│              ▼                               ▼          │
│     生产模式 (prod)                   开发模式 (dev)     │
│              │                               │          │
│  ┌───────────▼──────────┐     ┌──────────────▼───────┐  │
│  │ 华为云 OAuth         │     │ 本地 OAuth Server     │  │
│  │ (授权码模式)         │     │ (授权码模式, mock)    │  │
│  │                      │     │                       │  │
│  │ 1.重定向到华为云     │     │ 1.重定向到本地登录页  │  │
│  │ 2.华为云回调         │     │ 2.本地登录页          │  │
│  │ 3.换取 access_token  │     │ 3.回调                │  │
│  │ 4.获取用户信息       │     │ 4.签发本地 token       │  │
│  │ 5.签发内部 JWT       │     │ 5.签发内部 JWT        │  │
│  └──────────────────────┘     └───────────────────────┘  │
│              │                               │          │
│              └───────────┬───────────────────┘          │
│                          ▼                               │
│                 ┌────────────────┐                       │
│                 │  JWT 签发与校验  │                       │
│                 │  (本地, HS256)  │                       │
│                 └────────┬───────┘                       │
│                          │                               │
│                    注入 user_id                          │
│                    注入 permissions                      │
│                    注入 role_id                           │
│                          │                               │
│                     转发到下游微服务                       │
└─────────────────────────────────────────────────────────┘
```

#### 2.2 模式切换

通过环境变量 `AUTH_MODE` 控制：

| AUTH_MODE | 行为 | 适用场景 |
|---|---|---|
| `dev` | 本地 OAuth Server，自动创建测试用户，无需华为云 | 本地开发、单元测试 |
| `prod` | 华为云 OAuth，需配置 client_id/secret | 生产部署 |
| `off` | 完全跳过认证（当前行为） | 临时调试、过渡期 |

`.env.example` 补充配置项：

```bash
# ===== 认证配置 =====
# 认证模式: dev(本地OAuth) / prod(华为云OAuth) / off(无认证)
AUTH_MODE=dev

# JWT 配置
JWT_SECRET=your-jwt-secret-key-change-in-production
JWT_EXPIRE_HOURS=24
JWT_ALGORITHM=HS256

# 开发模式 - 本地 OAuth
DEV_OAUTH_CLIENT_ID=local_dev_client
DEV_OAUTH_CLIENT_SECRET=local_dev_secret
DEV_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
# 开发模式自动创建的默认用户
DEV_DEFAULT_USERNAME=dev_user
DEV_DEFAULT_PASSWORD=dev_password
DEV_DEFAULT_ROLE=admin

# 生产模式 - 华为云 OAuth
HW_OAUTH_CLIENT_ID=
HW_OAUTH_CLIENT_SECRET=
HW_OAUTH_REDIRECT_URI=http://your-domain/api/v1/auth/callback
# 华为云 OAuth 端点
HW_OAUTH_AUTHORIZE_URL=https://oauth.huaweicloud.com/oauth2/authorize
HW_OAUTH_TOKEN_URL=https://oauth.huaweicloud.com/oauth2/token
HW_OAUTH_USERINFO_URL=https://oauth.huaweicloud.com/oauth2/userinfo
```

#### 2.3 新增文件清单

```
api_gateway/
├── application/
│   └── services/
│       └── auth/
│           ├── __init__.py
│           ├── auth_service.py          # 认证核心服务（统一入口）
│           ├── huawei_oauth.py           # 华为云 OAuth Provider
│           ├── local_oauth.py           # 本地开发 OAuth Provider
│           └── token_service.py          # JWT 签发/校验/刷新
├── routes/
│   └── auth_bp.py                        # 认证路由（登录/回调/登出/刷新）
├── middleware.py                         # 改造：增加 AuthMiddleware
├── config/
│   └── config.py                          # 改造：增加认证配置项
└── domain/
    ├── entities/
    │   └── auth_entities.py              # AuthUser / TokenClaims
    └── value_objects/
        └── auth_value_objects.py         # OAuthProvider / TokenPayload / UserInfo
```

#### 2.4 认证流程详解

**生产模式（华为云 OAuth）**

```
前端                          网关                        华为云
  │                             │                            │
  │  GET /api/v1/auth/login     │                            │
  │ ──────────────────────────► │                            │
  │  302 → 华为云授权页          │                            │
  │ ◄────────────────────────  │                            │
  │                             │                            │
  │  浏览器跳转到华为云授权页     │                            │
  │  ──────────────────────────────────────────────────────► │
  │  用户在华为云登录并授权       │                            │
  │ ◄──────────────────────────────────────────────────────  │
  │  302 → /api/v1/auth/callback?code=xxx                   │
  │                             │                            │
  │  GET /api/v1/auth/callback  │                            │
  │   ?code=xxx&state=xxx       │                            │
  │ ──────────────────────────► │                            │
  │                             │  POST /oauth2/token        │
  │                             │   (code → access_token)   │
  │                             │ ─────────────────────────► │
  │                             │  {access_token}           │
  │                             │ ◄───────────────────────  │
  │                             │                            │
  │                             │  GET /oauth2/userinfo      │
  │                             │   (access_token → 用户信息) │
  │                             │ ─────────────────────────► │
  │                             │  {name,email,unionid,...} │
  │                             │ ◄───────────────────────  │
  │                             │                            │
  │                             │  查找/创建本地 User        │
  │                             │  签发 JWT (HS256)          │
  │                             │                            │
  │  200 {access_token, user}   │                            │
  │ ◄────────────────────────  │                            │
  │                             │                            │
  │  后续请求:                   │                            │
  │  Authorization: Bearer xxx  │                            │
  │ ──────────────────────────► │                            │
  │                             │  AuthMiddleware:           │
  │                             │  1. 解析 JWT               │
  │                             │  2. 注入 user_id/role_id   │
  │                             │  3. 注入 permissions       │
  │                             │  4. next() → 路由          │
```

**开发模式（本地 OAuth）**

```
前端                          网关
  │                             │
  │  GET /api/v1/auth/login     │
  │ ──────────────────────────► │
  │  返回本地登录页 HTML         │
  │  (用户名/密码 表单)          │
  │ ◄────────────────────────  │
  │                             │
  │  POST /api/v1/auth/login    │
  │   {username, password}     │
  │ ──────────────────────────► │
  │                             │  LocalOAuth:              │
  │                             │  1. 查找/创建本地 User     │
  │                             │  2. 校验密码 (dev_password)│
  │                             │  3. 签发 JWT (HS256)      │
  │                             │                            │
  │  200 {access_token, user}   │
  │ ◄────────────────────────  │
  │                             │
  │  后续请求: 同生产模式         │
  │  Authorization: Bearer xxx  │
  │ ──────────────────────────► │
  │                             │  AuthMiddleware: 同生产模式 │
```

#### 2.5 认证中间件设计

```python
# api_gateway/middleware.py 改造

class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 - 双模式支持"""

    # 无需认证的路由前缀（白名单）
    PUBLIC_PATHS = [
        '/api/v1/auth/login',
        '/api/v1/auth/callback',
        '/api/v1/auth/register',  # 仅 dev 模式
        '/docs',
        '/openapi.json',
        '/redoc',
    ]

    async def dispatch(self, request, call_next):
        auth_mode = config.AUTH_MODE  # dev / prod / off

        # off 模式：完全跳过认证
        if auth_mode == 'off':
            # 注入默认开发用户
            request.state.user_id = 0
            request.state.role_id = 0
            request.state.permissions = []
            return await call_next(request)

        # 白名单路由：跳过认证
        path = request.url.path
        if any(path.startswith(p) for p in self.PUBLIC_PATHS):
            return await call_next(request)

        # 从 Header 提取 Bearer token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return _unauthorized('缺少认证令牌')

        token = auth_header[7:]

        # JWT 校验
        try:
            payload = TokenService.verify(token)
            request.state.user_id = payload['user_id']
            request.state.role_id = payload['role_id']
            request.state.permissions = payload['permissions']
            request.state.username = payload['username']
        except Exception as e:
            return _unauthorized(f'令牌无效: {e}')

        return await call_next(request)
```

> **设计期快照注记（2026-10-13 对齐，INT-189）**：上图 §2.5 为设计期草图，现行实现已演进——① 白名单扩展：`/auth/encryption-key`（INT-147/179 公钥下发）、`/auth/refresh`（INT-179 白名单化，路由自解析 Bearer）、`/auth/mode`（INT-180 启动自检）、`/auth/oauth`（INT-51）、`/health`、`/socket.io`；② 匹配语义：按**路径段边界**（`_is_public_path`：`path == p or path.startswith(p.rstrip('/') + '/')`）而非裸 `startswith`——防止 `/auth/oauth` 误伤 `/auth/oauth-providers` 这类共享字符串前缀的管理端路径。现行清单以 [RBAC权限划分.md](./RBAC权限划分.md) 6.3 节与 `api_gateway/middleware.py` 为准。

#### 2.6 认证服务设计

```python
# api_gateway/application/services/auth/auth_service.py

class AuthService:
    """认证核心服务 - 统一入口"""

    @staticmethod
    def get_login_url() -> str:
        """获取登录 URL"""
        if config.AUTH_MODE == 'dev':
            return LocalOAuthProvider.get_login_url()
        elif config.AUTH_MODE == 'prod':
            return HuaweiOAuthProvider.get_login_url()
        else:
            raise ValueError(f'无效的认证模式: {config.AUTH_MODE}')

    @staticmethod
    def handle_callback(code: str, state: str) -> dict:
        """OAuth 回调处理"""
        # 1. 用 code 换取用户信息
        if config.AUTH_MODE == 'dev':
            user_info = LocalOAuthProvider.exchange_code_for_user(code)
        else:
            user_info = HuaweiOAuthProvider.exchange_code_for_user(code)

        # 2. 查找或创建本地用户
        user = AuthService._find_or_create_user(user_info)

        # 3. 获取用户权限
        permissions = AuthService._get_user_permissions(user)

        # 4. 签发 JWT
        token = TokenService.create_token(
            user_id=user.id,
            username=user.username,
            role_id=user.role_id,
            permissions=permissions,
        )

        return {
            'access_token': token,
            'token_type': 'Bearer',
            'expires_in': config.JWT_EXPIRE_HOURS * 3600,
            'user': {
                'id': user.id,
                'username': user.username,
                'role_id': user.role_id,
            }
        }

    @staticmethod
    def _find_or_create_user(user_info: dict) -> User:
        """根据 OAuth 用户信息查找或创建本地用户"""
        user = User.query.filter_by(
            oauth_provider=user_info['provider'],
            oauth_id=user_info['oauth_id'],
        ).first()

        if not user:
            user = User(
                username=user_info.get('username') or f"{user_info['provider']}_{user_info['oauth_id'][:8]}",
                oauth_provider=user_info['provider'],
                oauth_id=user_info['oauth_id'],
                oauth_unionid=user_info.get('unionid'),
                oauth_nickname=user_info.get('nickname'),
                oauth_avatar_url=user_info.get('avatar_url'),
                role_id=user_info.get('role_id', 2),  # 默认普通用户
            )
            db.session.add(user)
            db.session.commit()
        else:
            # 更新昵称/头像
            user.oauth_nickname = user_info.get('nickname', user.oauth_nickname)
            user.oauth_avatar_url = user_info.get('avatar_url', user.oauth_avatar_url)
            user.last_login_at = datetime.now()
            user.last_login_ip = user_info.get('login_ip')
            db.session.commit()

        return user


# api_gateway/application/services/auth/huawei_oauth.py

class HuaweiOAuthProvider:
    """华为云 OAuth Provider"""

    @staticmethod
    def get_login_url() -> str:
        """构造华为云授权 URL"""
        params = {
            'client_id': config.HW_OAUTH_CLIENT_ID,
            'redirect_uri': config.HW_OAUTH_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid profile',
            'state': AuthService._generate_state(),
        }
        return f"{config.HW_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_user(code: str) -> dict:
        """用授权码换取用户信息"""
        # 1. code → access_token
        token_resp = httpx.post(config.HW_OAUTH_TOKEN_URL, json={
            'client_id': config.HW_OAUTH_CLIENT_ID,
            'client_secret': config.HW_OAUTH_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': config.HW_OAUTH_REDIRECT_URI,
        })
        token_resp.raise_for_status()
        access_token = token_resp.json()['access_token']

        # 2. access_token → 用户信息
        user_resp = httpx.get(
            config.HW_OAUTH_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()

        return {
            'provider': 'huawei',
            'oauth_id': user_data.get('sub'),
            'unionid': user_data.get('unionid'),
            'nickname': user_data.get('name'),
            'avatar_url': user_data.get('picture'),
            'username': user_data.get('preferred_username'),
        }


# api_gateway/application/services/auth/local_oauth.py

class LocalOAuthProvider:
    """本地开发 OAuth Provider"""

    @staticmethod
    def get_login_url() -> str:
        """返回本地登录页 URL"""
        return '/api/v1/auth/login'

    @staticmethod
    def handle_login_form() -> HTMLResponse:
        """返回本地登录 HTML 表单"""
        return HTMLResponse(f"""
        <html><body>
        <h2>开发模式 - 本地登录</h2>
        <form method="POST" action="/api/v1/auth/login">
          <input name="username" placeholder="用户名" value="{config.DEV_DEFAULT_USERNAME}"/>
          <input name="password" type="password" placeholder="密码" value="{config.DEV_DEFAULT_PASSWORD}"/>
          <button type="submit">登录</button>
        </form>
        </body></html>
        """)

    @staticmethod
    def verify_credentials(username: str, password: str) -> dict:
        """校验本地凭据"""
        if username == config.DEV_DEFAULT_USERNAME and password == config.DEV_DEFAULT_PASSWORD:
            return {
                'provider': 'local_dev',
                'oauth_id': f'dev_{username}',
                'nickname': username,
                'username': username,
                'role_id': 1,  # dev 模式给 admin 角色
            }
        raise ValueError('开发模式凭据错误')


# api_gateway/application/services/auth/token_service.py

class TokenService:
    """JWT 签发与校验"""

    @staticmethod
    def create_token(user_id, username, role_id, permissions) -> str:
        payload = {
            'user_id': user_id,
            'username': username,
            'role_id': role_id,
            'permissions': permissions,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=config.JWT_EXPIRE_HOURS),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

    @staticmethod
    def verify(token: str) -> dict:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])

    @staticmethod
    def refresh(token: str) -> str:
        payload = TokenService.verify(token)
        return TokenService.create_token(
            user_id=payload['user_id'],
            username=payload['username'],
            role_id=payload['role_id'],
            permissions=payload['permissions'],
        )
```

#### 2.7 认证路由设计

```python
# api_gateway/routes/auth_bp.py

router = APIRouter(prefix='/api/v1/auth', tags=['认证'])

@router.get('/login')
def login():
    """登录入口 - 重定向到 OAuth"""
    url = AuthService.get_login_url()
    if config.AUTH_MODE == 'dev':
        return LocalOAuthProvider.handle_login_form()
    return RedirectResponse(url)

@router.post('/login')
def login_submit(username: str = Form(...), password: str = Form(...)):
    """开发模式本地登录"""
    if config.AUTH_MODE != 'dev':
        raise HTTPException(403, '开发模式才支持本地登录')
    user_info = LocalOAuthProvider.verify_credentials(username, password)
    user = AuthService._find_or_create_user(user_info)
    permissions = AuthService._get_user_permissions(user)
    token = TokenService.create_token(user.id, user.username, user.role_id, permissions)
    return {'access_token': token, 'token_type': 'Bearer', 'user': {...}}

@router.get('/callback')
def callback(code: str = Query(...), state: str = Query(...)):
    """OAuth 回调"""
    result = AuthService.handle_callback(code, state)
    return result

@router.post('/refresh')
def refresh_token(request: Request):
    """刷新 token"""
    token = request.headers.get('Authorization', '')[7:]
    new_token = TokenService.refresh(token)
    return {'access_token': new_token, 'token_type': 'Bearer'}

@router.post('/logout')
def logout(request: Request):
    """登出"""
    # JWT 是无状态的，前端删除即可
    # 如需强制失效，可将 token 加入黑名单（Redis）
    return {'message': '已登出'}

@router.get('/me')
def me(request: Request):
    """获取当前用户信息"""
    return {
        'user_id': request.state.user_id,
        'username': request.state.username,
        'role_id': request.state.role_id,
        'permissions': request.state.permissions,
    }
```

> **设计期快照注记（2026-10-13 对齐，INT-189）**：上图 §2.7 路由草图为设计期快照，`POST /auth/login`（login_submit）现行契约已演进——① 请求体**双格式兼容**（INT-179）：表单编码 `application/x-www-form-urlencoded` 为前端契约（`frontend/src/infrastructure/api/authApi.ts` 以 URLSearchParams 提交），JSON body 亦可（经 RequestAdapterMiddleware 预解析进 `request.state._json_body` 兜底）；② INT-147：密码 RSA 加密传输——加密开关开启时仅接受 `password_encrypted` / `encryption_key_id`（明文 `password` 被忽略，无明文回退），公钥经 `/auth/encryption-key`（或 `/auth/login/encryption-key`）登录前下发；③ 401 以 error code 区分语义（INT-188：加密载荷无效 `AUTH_ENCRYPTION_INVALID` / 凭证错误 `AUTH_CREDENTIALS_INVALID`）。白名单现状：`/auth/login`、`/auth/callback`、`/auth/register`（仅 dev）、`/auth/encryption-key`、`/auth/refresh`、`/auth/mode`、`/auth/oauth` 在 `AuthMiddleware.PUBLIC_PATHS` 内（见 [RBAC权限划分.md](./RBAC权限划分.md) 6.3 节），`/auth/logout`、`/auth/me` 须鉴权。现行实现以 `api_gateway/routes/auth_bp.py` 为准。

> **设计补记（2026-10-13，INT-245）：密码加密双 padding 降级设计**。① 根因：前端 `passwordEncryption.ts` 用 WebCrypto `crypto.subtle`（RSA-OAEP-SHA256），该 API 仅存在于安全上下文（https 或 localhost）；通过 `http://<LAN-IP>:5173` 访问时 `subtle` 为 undefined → `rsaOaepEncrypt` 失败 → 登录报"登录加密初始化失败"。旧 V9.7.10 用 jsencrypt（纯 JS，PKCS1v15，任何上下文可用）无此问题；INT-156 升级 WebCrypto 时未覆盖 http+IP 部署形态。② 方案：后端 RSA 密钥**成对独立**——主密钥（`AUTH_RSA_KEY_PATH`，kid → OAEP-SHA256）+ 降级密钥（`AUTH_RSA_FALLBACK_KEY_PATH`，kid → PKCS1v15，对齐旧库 jsencrypt 基线）；`PasswordEncryptionService.decrypt_password` 按 `encryption_key_id` 归属分派算法（**kid 即算法绑定**），交叉/未知 kid 一律拒绝；`/auth/login/encryption-key`（及 `/auth/encryption-key` 别名）响应增加 `fallback: {kid, public_key}`。③ 前端：`encryptPassword` 按上下文二选一——subtle 可用 → WebCrypto OAEP 主路径（**不回退**）；不可用（http+IP 非安全上下文）→ 动态 `import('jsencrypt')` 走 PKCS1v15 + 降级 kid；降级密钥未下发或加密失败仍收敛 `PasswordEncryptionUnavailableError`。④ 明文兜底保持禁止（INT-179/188 语义不变）。现行实现以 `api_gateway/application/services/auth/password_encryption.py` 与 `frontend/src/utils/passwordEncryption.ts` 为准。

### 3. auth_service 微服务化

认证逻辑初期可保留在网关 application/services/auth/，后续按 DDD 演进下沉为独立微服务：

```
auth_service/                          # 建议新增
├── domain/
│   ├── entities/
│   │   └── user.py                    # User 聚合根
│   │   └── oauth_client.py            # OAuthClient 实体
│   ├── value_objects/
│   │   └── token.py                   # TokenPayload / JWTClaims
│   │   └── credential.py             # OAuthCredential / PasswordHash
│   ├── services/
│   │   └── login_service.py           # 领域服务：认证逻辑
│   └── events/
│       └── user_logged_in.py          # 领域事件
├── application/
│   ├── commands/
│   │   ├── login_command.py           # LoginCommand / LoginHandler
│   │   └── refresh_token_command.py   # RefreshTokenCommand / Handler
│   └── queries/
│       └── user_permissions_query.py  # GetUserPermissions
├── infrastructure/
│   ├── persistence/
│   │   └── user_repository.py         # UserRepository
│   └── oauth/
│       ├── huawei_provider.py         # 华为云 OAuth Provider
│       └── local_provider.py          # 本地开发 OAuth Provider
└── interfaces/
    ├── grpc/
    │   └── servicers.py              # ValidateToken / GetUserPermissions
    └── api/
        └── routes.py                  # HTTP 路由
```

**其他微服务获取用户权限的方式**：

- 方案 A（轻量）：网关解析 JWT 后，在 gRPC metadata 中传递 `user_id` / `permissions`，下游微服务直接信任
- 方案 B（安全）：下游微服务通过 gRPC 调用 `auth_service.ValidateToken` / `GetUserPermissions` 自行验证

### 4. RBAC 权限校验

认证中间件将 `permissions` 注入 `request.state`，路由层可按需校验：

```python
# 网关路由层权限校验（按需使用）
@router.post('/tasks')
def create_task(request: Request):
    require_permission(request, 'task:create')
    return to_response(TaskCommandService.create(request))

# 辅助函数
def require_permission(request: Request, perm: str):
    permissions = request.state.permissions or []
    if perm not in permissions:
        raise HTTPException(403, f'缺少权限: {perm}')
```

### 5. 实施状态

| 阶段 | 内容 | 优先级（原） | 状态 |
|---|---|---|---|
| d9 | 认证骨架：AuthMiddleware + TokenService + auth_bp 路由 | d2-d7 完成后 | ✅ **已实现** |
| d10 | 开发模式 LocalOAuthProvider（本地登录页+JWT 签发） | d9 之后 | ✅ **已实现** |
| d11 | 华为云 OAuth Provider（授权码模式） | d10 之后 | ✅ **已实现** |
| d12 | RBAC 权限校验（路由层 require_permission） | d11 之后 | ✅ **已实现** |
| d13 | auth_service 微服务化（独立部署） | 视团队需要 | ⚠️ DDD 四层已建 + run_all.py 已纳入启动；docker-compose 未含，需按需补充 |

### 6. 前端构建期注入（VITE_AUTH_MODE，INT-181）

前端登录跳转行为压在构建期变量 `VITE_AUTH_MODE` 上（Vite 构建时把 `import.meta.env.VITE_AUTH_MODE` 静态替换进产物，运行期不可改）。生产构建**必须显式注入**，未注入时构建期守卫（`frontend/vite.config.ts`）显式报错退出——不存在静默默认 `off`。

取值（与后端 `AUTH_MODE` 保持一致，合法值单一来源：`frontend/src/domain/enums.ts` 的 `AuthMode`）：

| VITE_AUTH_MODE | 行为 | 适用场景 |
|---|---|---|
| `off` | 无 token 直接放行（向后兼容，后端须同置 `AUTH_MODE=off`） | 临时调试、过渡期 |
| `dev` | 本地 OAuth 登录跳转 | 联调环境 |
| `prod` | 正式 OAuth 登录跳转（未登录访问受保护路由跳登录页） | 生产部署 |

注入方式（按构建通道二选一）：

```bash
# 宿主机 / CI 直构（dist 由外部 nginx 托管）
VITE_AUTH_MODE=prod npm run build

# Docker 镜像构建（docker/Dockerfile.frontend，compose 服务 frontend 已强制校验）
docker compose build frontend                     # 须先 export VITE_AUTH_MODE=prod
docker build -f docker/Dockerfile.frontend --build-arg VITE_AUTH_MODE=prod ..
```

注意：
- 仅「显式注入」被认可——`frontend/.env*` 文件值不作为生产构建依据（`.env.production` 已不提供默认值）。
- 注入值必须与后端 `api_gateway` 的 `AUTH_MODE` 一致，两者不一致会出现前端跳登录而后端不放 token（或反向）的错配。
- 取值非法（不在 `off|dev|prod` 内）同样构建失败。