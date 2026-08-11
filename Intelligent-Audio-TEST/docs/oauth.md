
---

## 九、认证与开发模式设计

### 1. 现状

| 维度 | 状态 |
|---|---|
| 认证流程 | **未实现** — 无中间件、无依赖注入、无装饰器，所有 API 完全开放 |
| OAuth 模型 | **已定义** — User/OAuthClient/OAuthRefreshToken 表已建，RBAC 模型完整 |
| 华为云 OAuth 配置 | **未配置** — .env/config 中无 client_id、client_secret、redirect_uri |
| 开发模式/本地 OAuth | **未实现** — 无 skip-auth、mock-auth、dev-auth 机制 |
| RBAC | 模型已定义（Role/Permission/User.has_permission），但无任何调用点 |

认证"骨架"（模型+表）已搭好，"肌肉"（路由、service、中间件、token 签发与校验、配置）一行都还没写。

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

### 5. 实施计划

| 阶段 | 内容 | 优先级 |
|---|---|---|
| d9 | 认证骨架：AuthMiddleware + TokenService + auth_bp 路由 | d2-d7 完成后 |
| d10 | 开发模式 LocalOAuthProvider（本地登录页+JWT 签发） | d9 之后 |
| d11 | 华为云 OAuth Provider（授权码模式） | d10 之后 |
| d12 | RBAC 权限校验（路由层 require_permission） | d11 之后 |
| d13 | auth_service 微服务化（独立部署） | 视团队需要 |