# -*- coding: utf-8 -*-
"""UI 自动化测试层 conftest（INT-260）。

门禁三件套（与 tests/api 实机口径对齐并加固）：
1. RUN_LIVE_STACK=1 显式纳入 —— 默认整目录 skip，UI 实机用例不参与日常回归；
2. 隔离库守卫 —— /health 的 database 必须等于 intelligent_audio_test_test，
   指向共享业务库直接 FAIL（负责人数据零污染红线；UI 用例有写操作）；
3. 引导自举 —— 隔离库 RBAC 种子（seed_rbac.py 幂等重播）+ admin 账号
   （空库首注册即 admin 角色），全部用例共享。

INT-363 served-mode 前置条件：认证链路用例（test_ui_01 表单登录跳转/
登出、test_ui_02 未登录重定向）断言路由守卫弹回行为，仅在 served
VITE_AUTH_MODE != off 时有意义——off 模式守卫对未登录全放行（向后
兼容语义）。并行隔离栈（方式 A）由 launcher 进程 env 固定注入
AUTH_MODE/VITE_AUTH_MODE=dev（vite 进程 env 优先级高于 .env* 文件，
不受 .env.development=off / .env.local=dev 文件级优先级冲突影响），
恒一致；served=off 时此类用例显式 skip 并标注前置条件，不静默失败
污染回归判据。

失败取证：call 阶段失败自动落 截图 + console 日志 + page source 到
tests/ui/artifacts/<用例名>/（issue 验收口径：缺陷卡直接引用）。
"""
import json
import os
import sys

import httpx
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants.database import ISOLATED_TEST_DB_NAME  # noqa: E402

from tests.ui.pages.base_page import BasePage, ARTIFACTS_DIR  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402
from tests.ui.utils import bootstrap  # noqa: E402

# 127.0.0.1 直连（INT-102：localhost 解析 ::1 误连；服务端仅绑 IPv4）
FRONTEND_BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5173')
API_ROOT = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5000')

# 认证链路用例模块（INT-363 served-mode 前置条件适用范围）
AUTH_GATED_MODULES = ('test_ui_01_login.py', 'test_ui_02_navigation.py')

# 账号口径：.env DEV_DEFAULT_*（本地开发默认 admin/admin123）；测试不改账号
UI_USERNAME = os.environ.get('UI_TEST_USERNAME', 'admin')
UI_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'admin123')

# 浏览器二进制沿用 e2e_tests/selenium 既有基建（Selenium Manager 联网下载卡死规避）
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
CHROMEDRIVER = os.environ.get(
    'UI_CHROMEDRIVER',
    os.path.join(PROJECT_ROOT, 'e2e_tests', 'selenium', 'drivers',
                 'chromedriver-win32', 'chromedriver.exe'))


def _chrome_major() -> int:
    """读取本机 Chrome 主版本（Windows 注册表 BLBeacon；读不到返回 0）。"""
    if os.name != 'nt':
        return 0
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int((winreg.QueryValueEx(k, 'version')[0]).split('.')[0])
    except Exception:
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
                return int((winreg.QueryValueEx(k, 'version')[0]).split('.')[0])
        except Exception:
            return 0


def _resolve_chromedriver() -> str:
    """驱动解析：显式 env → Selenium 缓存同主版本最新 → 仓库 e2e_tests 既有 →
    空串（Selenium Manager 自行解析）。仓库自带 152 与本机 Chrome 154 漂移时
    自动升到缓存驱动，避免版本不匹配硬失败。"""
    if os.environ.get('UI_CHROMEDRIVER'):
        return os.environ['UI_CHROMEDRIVER']
    chrome_major = _chrome_major()
    candidates = []
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                candidates.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    if chrome_major:
        same = [exe for ver, exe in candidates if ver and ver[0] == chrome_major]
        if same:
            return max(same)
    for _, exe in sorted(candidates, reverse=True):
        return exe
    return CHROMEDRIVER if os.path.isfile(CHROMEDRIVER) else ''

_HTTPOPTS = dict(timeout=5, trust_env=False)

# 驱动注册表：会话内唯一 Chrome，供失败取证钩子取用
_DRIVER_REF = {'driver': None, 'page': None}


# ── 门禁 1：默认 skip，RUN_LIVE_STACK=1 显式纳入 ─────────────
@pytest.fixture(scope='session', autouse=True)
def _live_stack_gate():
    if os.environ.get('RUN_LIVE_STACK', '') != '1':
        pytest.skip('RUN_LIVE_STACK!=1：UI 实机用例不参与默认回归（tests/ui/README.md）')


# ── 门禁 2：隔离库守卫 ───────────────────────────────────────
@pytest.fixture(scope='session', autouse=True)
def _isolated_db_guard(_live_stack_gate):
    """栈必须在线且已切隔离测试库；指向共享业务库 → 整会话 FAIL。"""
    try:
        r = httpx.get(f'{API_ROOT}/health', **_HTTPOPTS)
    except Exception as exc:
        pytest.fail(f'UI 门禁：网关不可达（{API_ROOT}/health: {exc}）。'
                    '请先以隔离库起栈：python run_all.py --test-db', pytrace=False)
    if r.status_code != 200:
        pytest.fail(f'UI 门禁：/health 返回 {r.status_code}，栈未就绪。', pytrace=False)
    body = r.json() if 'json' in r.headers.get('content-type', '') else {}
    if body.get('version') != 'V9.7.31':
        pytest.fail(f"UI 门禁：同端口疑似非 V9.7.31 网关（version={body.get('version')!r}），"
                    '拒绝误连。', pytrace=False)
    db_name = body.get('database', '')
    if db_name != ISOLATED_TEST_DB_NAME:
        pytest.fail(
            'UI 门禁（INT-260 隔离库口径）：当前栈 database='
            f"{db_name or '(未上报)'}，不是隔离测试库 '{ISOLATED_TEST_DB_NAME}'。"
            'UI 用例含写操作，禁止对共享业务库执行；请以 '
            '`python run_all.py --test-db` 重启栈后再跑。', pytrace=False)
    return db_name


# ── INT-363：served 认证模式探测与认证链路用例前置条件 ───────
def _served_vite_auth_mode() -> str:
    """读 vite dev server 模块图里实际注入的 VITE_AUTH_MODE（浏览器同源）。

    vite dev 下 enums.ts 顶部被静态替换为 `import.meta.env = {...}` 单行，
    其中 VITE_AUTH_MODE 即 served 值；读不到（前端未起/结构变更）回空串。
    """
    try:
        r = httpx.get(f'{FRONTEND_BASE}/src/domain/enums.ts', **_HTTPOPTS)
        r.raise_for_status()
    except Exception:
        return ''
    for line in r.text.splitlines():
        if 'import.meta.env' in line and 'VITE_AUTH_MODE' in line:
            try:
                return line.split('"VITE_AUTH_MODE":')[1].split('"')[1]
            except IndexError:
                return ''
    return ''


def pytest_collection_modifyitems(config, items):
    """INT-363：served VITE_AUTH_MODE=off 时，认证链路用例显式 skip。

    仅对 AUTH_GATED_MODULES 生效（session 级探测一次）；off 模式路由守卫
    对未登录全放行，登录跳转/登出/未登录重定向断言无前提，属环境前置
    不满足而非产品缺陷。并行隔离栈恒为 dev（launcher 注入），此分支
    只在共享栈方式 B 且未注入 VITE_AUTH_MODE 时触发。
    """
    gated = [it for it in items
             if os.path.basename(str(it.fspath)) in AUTH_GATED_MODULES]
    if not gated:
        return
    served = _served_vite_auth_mode()
    if served != 'off':
        if served == '':
            print(f'[UI-CONFTEST][WARN] {FRONTEND_BASE} 未起或读取不到 served '
                  'VITE_AUTH_MODE；认证链路用例前置条件未验证，盲跑。')
        return
    skip = pytest.mark.skip(
        reason='served VITE_AUTH_MODE=off：路由守卫对未登录全放行，认证链路'
               '用例（登录跳转/登出/未登录重定向）无断言前提（INT-363 口径）。'
               '请以并行隔离栈跑门禁（python tests/ui/run_gate.py，launcher '
               '固定注入 dev/dev），或以 VITE_AUTH_MODE=dev 重启共享栈前端。')
    for it in gated:
        it.add_marker(skip)


# ── 门禁 3：隔离库引导（RBAC 种子 + admin 账号）──────────────
@pytest.fixture(scope='session', autouse=True)
def _bootstrap_isolated_db(_isolated_db_guard):
    url = bootstrap.isolated_db_url()
    if not bootstrap.roles_seeded(url):
        bootstrap.seed_rbac(url)
    api = ApiClient(API_ROOT)
    try:
        api.login(UI_USERNAME, UI_PASSWORD)
    except Exception:
        # 空库首注册 → admin 角色（auth_service _FIRST_USER_ROLE_NAME 逻辑）
        api.register(UI_USERNAME, UI_PASSWORD)
        api.login(UI_USERNAME, UI_PASSWORD)


# ── 会话级登录态（API 登录，一次取 token 全会话复用）─────────
@pytest.fixture(scope='session')
def api_client(_bootstrap_isolated_db) -> ApiClient:
    api = ApiClient(API_ROOT)
    api.login(UI_USERNAME, UI_PASSWORD)
    return api


@pytest.fixture(scope='session')
def login_state(api_client) -> dict:
    return {'token': api_client.token, 'user': api_client.user}


# ── 会话级 Chrome 驱动 ───────────────────────────────────────
@pytest.fixture(scope='session')
def driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    # console 日志取证（失败钩子读取）
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    drv_path = _resolve_chromedriver()
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    _DRIVER_REF['driver'] = drv
    yield drv
    _DRIVER_REF['driver'] = None
    try:
        drv.quit()
    except Exception:
        pass


# ── 页面对象（函数级）：默认已注入登录态 ─────────────────────
@pytest.fixture()
def page(driver, login_state) -> BasePage:
    pg = BasePage(driver, FRONTEND_BASE)
    _DRIVER_REF['page'] = pg
    pg.inject_login_state(login_state['token'], login_state['user'])
    yield pg


@pytest.fixture()
def login_page(driver) -> 'object':
    from tests.ui.pages.login_page import LoginPage
    lp = LoginPage(driver, FRONTEND_BASE)
    _DRIVER_REF['page'] = lp
    lp.goto()                      # 先落到应用源（about:blank 上无 localStorage）
    driver.delete_all_cookies()
    lp.clear_login_state()
    lp.goto()                      # 清空登录态后重新 boot（未登录态）
    return lp


# ── 失败取证钩子：截图 + console + page source ───────────────
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != 'call' or not rep.failed:
        return
    drv = _DRIVER_REF.get('driver')
    if drv is None:
        return
    out_dir = BasePage.node_artifact_dir(item.nodeid)
    saved = []
    try:
        pg = _DRIVER_REF.get('page')
        if pg is not None:
            saved = pg.capture_artifacts(out_dir)
        else:
            from tests.ui.pages.base_page import BasePage as _BP
            saved = _BP(drv, FRONTEND_BASE).capture_artifacts(out_dir)
    except Exception as exc:  # 取证自身失败不得吞掉原始测试失败
        print(f'[UI-ARTIFACT] 取证失败: {exc}')
    if saved:
        rel = os.path.relpath(out_dir, PROJECT_ROOT)
        rep.sections.append(('UI 失败取证（tests/ui/artifacts）',
                             '\n'.join(f'- {os.path.relpath(p, PROJECT_ROOT)}' for p in saved)))


def pytest_configure(config):
    # artifacts 目录留 .gitkeep 占位，失败取证运行期落盘
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    keep = os.path.join(ARTIFACTS_DIR, '.gitkeep')
    if not os.path.exists(keep):
        with open(keep, 'w', encoding='utf-8') as fh:
            fh.write('')
