# -*- coding: utf-8 -*-
"""INT-482 UI 实测：Benchmark 排行页（Vue 主库版，INT-745 后路由 /rankings）。

覆盖卡面验收标准②（tests/ui 实测三件套）：
1. 登录 → 顶导航「排行榜」入口 → /rankings 页遍历：Hero（标题「排行榜」/副标题）+
   类别下划线页签（全部/语音识别/语音对话/语音合成/翻译）+ 筛选行（测试集/指标/
   数据来源/搜索主体）+ 页内算法卡片网格（INT-745：首卡「全部算法」）+ 指标组卡 +
   双栏榜单（列表/表格双视图）+ chart.js 对比条形图 + 全量中文文案。
2. 榜单数据按双轨来源（platform_test / external_import）正确展示与筛选：来源
   徽章（平台实测/外部基线）就位、来源筛选联动榜单+图表、URL query 同步可还原。
3. 权限不足角色（guest，INT-429 未授 benchmark:*）：INT-745 后 /rankings 为公开
   路由（公开可达不弹回），但数据 403 门控（API 403 + 页面错误/空态）+ 顶导航
   「排行榜」入口按权限隐藏；并附 API 层 403 佐证。

数据卫生（硬规则）：benchmark_rankings 为隔离库直插 fixture（subject_name 前缀
int482_），teardown 按 id 硬删零残留；guest 账号经 API 注册、teardown API 软删 +
隔离库硬删（users 无入站 FK，零残留）。
"""
import json
import os
import time

import httpx
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.ui.pages.base_page import BasePage, TOKEN_KEY, USER_KEY
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import ApiClient, unique_suffix

# 与 conftest 同口径（run_gate.py 起栈后注入 UI_API_BASE/UI_FRONTEND_BASE）
API_ROOT = os.environ.get('UI_API_BASE', 'http://127.0.0.1:6000')
FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5173')

# ---- 选择器 ----
HERO = '.rankings-hero'
HERO_TITLE = '.hero-title'
CATEGORY_TABS = '.category-tab'
FILTERS = '.ranking-filters'
FILTER_SELECTS = '.filter-select'
SEARCH_INPUT = '.search-input'
GROUP_CARDS = '.metric-group-card'
LEADERBOARD_ROWS = '.leaderboard-row'
BADGES = '.benchmark-badges .badge'
REPORT_LINKS = '.report-link'
CHART_CANVAS = '.metric-bar-chart canvas'
EMPTY_STATE = '.empty-state'
TABLE_VIEW = '.rank-table'
VIEW_SWITCH_BTNS = '.view-switch-btn'
ALGORITHM_NOTE = '.algorithm-note'
PENDING_NOTE = '.pending-note'


def _insert_benchmark_rows():
    """向隔离库直插双轨排行 fixture（subject_name 前缀 int482_）。

    分组：asr/WER（词错误率）与 voice_llm/TTLW（接管时延）各 2 行，
    双轨各 1 行；platform_test 行带报告溯源（查看报告链接）。
    """
    rows = [
        # asr / WER 组：platform_test + external_import
        (1, 'platform_test', 1, 2, 900001, None, 'int482_asr_a', 'open_source',
         'physical', 'int482_suite', 'asr', 'WER', '词错误率', 5.2, '%',
         'lower_is_better', 1, 2, 20.0, 95.0, 0.0, 0.5, -0.8, '通用',
         '2026-10-16 08:00:00'),
        (2, 'external_import', None, None, None, 5001, 'int482_asr_b',
         'closed_source', 'http_api', 'int482_suite', 'asr', 'WER', '词错误率',
         6.8, '%', 'lower_is_better', 2, 2, 70.0, 60.0, 1.6, 2.0, None, '通用',
         '2026-10-16 08:00:00'),
        # voice_llm / TTLW 组：platform_test + external_import
        (3, 'platform_test', 2, 1, 900002, None, 'int482_llm_a',
         'closed_source', 'websocket_api', 'int482_suite', 'voice_llm', 'TTLW',
         '接管时延', 320.0, 'ms', 'lower_is_better', 1, 2, 25.0, 90.0, 0.0,
         30.0, -15.0, '通用', '2026-10-16 08:00:00'),
        (4, 'external_import', None, None, None, 5002, 'int482_llm_b', 'app',
         'physical', 'int482_suite', 'voice_llm', 'TTLW', '接管时延', 410.0,
         'ms', 'lower_is_better', 2, 2, 75.0, 55.0, 90.0, 100.0, None, '通用',
         '2026-10-16 08:00:00'),
    ]
    cols = ('id source published_task_id published_task_version report_id '
            'baseline_id subject_name subject_type device_type benchmark_suite '
            'category metric_code metric_name metric_value unit direction rank '
            'total percentile score100 gap_best gap_median delta_external '
            'scenario_key computed_at').split()
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            inserted = []
            for r in rows:
                cur.execute(
                    f'INSERT INTO benchmark_rankings ({", ".join(cols)}) '
                    f'VALUES ({", ".join(["%s"] * len(cols))}) RETURNING id', r)
                inserted.append(cur.fetchone()[0])
        conn.commit()
    finally:
        conn.close()
    return inserted


def _delete_benchmark_rows(ids):
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            for rid in ids:
                cur.execute('DELETE FROM benchmark_rankings WHERE id=%s', (rid,))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def int482_benchmark_rows():
    """双轨排行 fixture（每用例独立重插，teardown 硬删零残留）。"""
    ids = _insert_benchmark_rows()
    yield ids
    _delete_benchmark_rows(ids)


@pytest.fixture()
def int482_guest(api_client):
    """guest 角色账号（INT-429 未授 benchmark:*）：注册→登录→软删。"""
    suffix = unique_suffix()
    username = f'int482_guest_{suffix}'
    password = 'int482pass123!'
    user_id = api_client.register(username, password)
    guest_api = ApiClient(API_ROOT)
    guest_api.login(username, password)
    assert 'benchmark' not in ' '.join(guest_api.user.get('permissions', [])), \
        'guest 不应持 benchmark:* 权限（INT-429 口径）'
    yield {'username': username, 'user_id': user_id,
           'token': guest_api.token, 'user': guest_api.user}
    try:
        api_client.request('DELETE', f'/auth/users/{user_id}')
    except Exception:
        pass
    _hard_delete_user(user_id)


def _hard_delete_user(user_id):
    """隔离库直删用户行（平台仅软删、无 purge 端点；users 无入站 FK）。"""
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM user_permissions WHERE user_id=%s', (user_id,))
            cur.execute('DELETE FROM user_oauth_bindings WHERE user_id=%s', (user_id,))
            cur.execute('DELETE FROM users WHERE id=%s', (user_id,))
        conn.commit()
    finally:
        conn.close()


def _inject_login(driver, base_url: str, token: str, user: dict):
    """覆盖注入指定账号登录态（先清空再写，refresh 后以该账号 boot）。"""
    driver.get(f'{base_url}/#/login')
    payload = {
        'id': user.get('id', 0),
        'username': user.get('username', ''),
        'roleId': user.get('role_id'),
        'roleName': user.get('role_name', ''),
        'permissions': user.get('permissions', []),
    }
    driver.execute_script(
        'window.localStorage.clear();'
        'window.localStorage.setItem(arguments[0], arguments[1]);'
        'window.localStorage.setItem(arguments[2], arguments[3]);',
        TOKEN_KEY, token, USER_KEY, json.dumps(payload, ensure_ascii=False),
    )
    driver.refresh()


def _click_topnav_entry(page: BasePage, label: str):
    """人手等价：点公共站头顶导航项（INT-745 排行榜挂 PublicLayout 公共壳）。"""
    page.click_xpath(
        f"//nav[contains(@class,'public-nav')]//*[contains(@class,'public-nav-link') "
        f"and normalize-space(.)='{label}']", timeout=10)


def _wait_group_cards(page: BasePage, n: int, timeout: float = 20):
    WebDriverWait(page.driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, GROUP_CARDS)) == n)
    page.settle(0.4)


def test_topnav_entry_and_page_traversal(page, int482_benchmark_rows):
    """登录 → 顶导航「排行榜」入口 → /rankings 页遍历（Hero/页签/算法网格/筛选行/组卡/榜单/图表）。"""
    page.goto('/')
    page.wait_visible('.public-header', timeout=15)
    page.settle(0.5)

    # 顶导航「排行榜」入口可见（admin 通配 * 持 benchmark:ranking:read）
    nav_labels = [a.text.strip() for a in page.find_all('.public-nav .public-nav-link')]
    assert '排行榜' in nav_labels, f'顶导航未见「排行榜」入口: {nav_labels}'

    _click_topnav_entry(page, '排行榜')
    page.wait.until(lambda d: '/rankings' in d.current_url.split('#')[-1])
    page.wait_visible(GROUP_CARDS, timeout=25)
    page.settle(0.5)

    # ① Hero 区：标题「排行榜」+ 类别下划线页签（全量中文文案）
    hero = page.find_visible(HERO, timeout=10)
    assert '排行榜' in hero.text, f'Hero 标题异常: {hero.text[:60]!r}'
    assert '横向看清业界水平' in hero.text and '名次' in hero.text, \
        f'Hero 副标题异常: {hero.text[:80]!r}'
    tabs = page.find_all(CATEGORY_TABS)
    labels = [t.text.strip() for t in tabs]
    assert labels == ['全部', '语音识别', '语音对话', '语音合成', '翻译'], \
        f'类别页签文案异常: {labels}'
    assert tabs[0].get_attribute('aria-selected') == 'true', '默认应选中「全部」页签'

    # ② 页内算法卡片网格（INT-745：首卡「全部算法」+ 每算法一张大卡，不渲染右上角切换器）
    grid = page.find_visible('.algorithm-card-grid', timeout=10)
    grid_text = grid.text
    assert '全部算法' in grid_text, f'算法网格首卡「全部算法」缺失: {grid_text[:40]!r}'
    ag_cards = page.find_all('.ag-card')
    assert len(ag_cards) >= 2, f'算法网格应 ≥2 张卡（全部算法 + ≥1 算法），实际 {len(ag_cards)}'
    assert not page.exists('.public-header .algorithm-switcher'), \
        '公共站头不应渲染右上角算法切换器'

    # ③ 筛选行：测试集 / 指标 / 数据来源 / 搜索主体
    filters_text = page.find_visible(FILTERS, timeout=10).text
    for kw in ('测试集', '指标', '数据来源', '搜索主体'):
        assert kw in filters_text, f'筛选行缺「{kw}」'
    assert page.find_all(FILTER_SELECTS), '筛选 Select 未渲染'
    assert page.find_visible(SEARCH_INPUT, timeout=5), '主体搜索框未渲染'
    assert page.find_visible(PENDING_NOTE, timeout=5), \
        '「按算法过滤待后端立项」标注缺失（范围决策#3）'
    assert page.find_visible(ALGORITHM_NOTE, timeout=5), \
        '组卡下方「按算法过滤待后端立项」标注缺失'

    # ③ 指标组卡：2 组（asr/WER + voice_llm/TTLW），双轨数据就位
    cards = page.find_all(GROUP_CARDS)
    assert len(cards) == 2, f'预期 2 张指标组卡，实际 {len(cards)}'
    card_text = '\n'.join(c.text for c in cards)
    assert '词错误率' in card_text and '接管时延' in card_text, '组卡标题缺指标名'
    assert '越低越好' in card_text, '方向徽章缺失'
    assert '个主体 · 计算于' in card_text, '组卡角标（主体数+计算时间）缺失'

    # ④ 双栏榜单 + 双轨来源徽章（平台实测/外部基线）就位
    rows = page.find_all(LEADERBOARD_ROWS)
    assert len(rows) == 4, f'双栏榜单应 4 行（4 主体），实际 {len(rows)}'
    row_text = '\n'.join(r.text for r in rows)
    assert 'int482_asr_a' in row_text and 'int482_asr_b' in row_text
    assert 'int482_llm_a' in row_text and 'int482_llm_b' in row_text
    assert '平台实测' in row_text and '外部基线' in row_text, '双轨来源徽章缺失'
    assert '开源' in row_text and '闭源' in row_text and 'App' in row_text, \
        '主体类型徽章缺失'
    assert 'v2' in row_text or 'v1' in row_text, '实测轨版本徽章缺失'
    # 实测轨行「查看报告」链接（report:read 门控，admin 持有）
    assert page.find_all(REPORT_LINKS), '实测轨行「查看报告」链接未渲染'

    # ⑤ 对比条形图：每张组卡渲染 chart.js canvas
    canvases = page.find_all(CHART_CANVAS)
    assert len(canvases) == 2, f'预期 2 个条形图画布（每组卡 1），实际 {len(canvases)}'

    # ⑥ 列表/表格双视图切换
    page.click('.view-switch-btn:last-child', timeout=10)   # 「表格」
    page.wait_visible(TABLE_VIEW, timeout=15)
    page.settle(0.3)
    table_text = page.find_visible(TABLE_VIEW).text
    for col in ('名次', '主体', '主体类型', '来源', '版本', '指标值', '百分位', '计算于'):
        assert col in table_text, f'表格视图缺列「{col}」'
    page.click('.view-switch-btn:first-child', timeout=10)  # 回「列表」
    page.wait_visible(LEADERBOARD_ROWS, timeout=15)

    # ⑦ 验收③：顶导航「排行榜」入口高亮随路由一致（router-link-active）
    active = [a for a in page.find_all('.public-nav .public-nav-link')
              if '排行榜' in (a.text or '') and 'router-link-active' in (a.get_attribute('class') or '')]
    assert active, '顶导航「排行榜」入口未高亮（当前路由 /rankings 应 active）'


def test_dual_source_display_and_filter_linkage(page, int482_benchmark_rows):
    """双轨来源展示与筛选联动：来源筛选 ↔ 榜单/图表一致，URL query 同步还原。"""
    page.goto('/rankings')
    _wait_group_cards(page, 2)

    # 默认「全部来源」：双轨并存
    row_text = page.find_visible('.group-list', timeout=10).text
    assert '平台实测' in row_text and '外部基线' in row_text

    # 来源筛选 → 平台实测：仅 platform_test 行；URL query 写入 source
    selects = page.find_all(FILTER_SELECTS)
    Select(selects[2]).select_by_value('platform_test')
    page.settle(0.8)
    _wait_group_cards(page, 2)
    text = page.find_visible('.group-list', timeout=10).text
    assert 'int482_asr_a' in text and 'int482_llm_a' in text
    assert 'int482_asr_b' not in text and 'int482_llm_b' not in text, \
        '平台实测筛选后不应残留外部基线行'
    assert 'source=platform_test' in page.current_route(), \
        f'URL query 未写入 source=platform_test: {page.current_route()}'
    # 图表随筛选联动（canvas 仍在，2 张组卡各 1 张）
    assert len(page.find_all(CHART_CANVAS)) == 2

    # 来源筛选 → 外部基线：仅 external_import 行
    selects = page.find_all(FILTER_SELECTS)
    Select(selects[2]).select_by_value('external_import')
    page.settle(0.8)
    _wait_group_cards(page, 2)
    text = page.find_visible('.group-list', timeout=10).text
    assert 'int482_asr_b' in text and 'int482_llm_b' in text
    assert 'int482_asr_a' not in text and 'int482_llm_a' not in text
    assert 'source=external_import' in page.current_route()

    # 类别页签 → 语音识别：仅 asr 组卡；URL query 写入 category
    tabs = page.find_all(CATEGORY_TABS)
    page.click_xpath(
        "//button[contains(@class,'category-tab') and normalize-space(.)='语音识别']",
        timeout=10)
    _wait_group_cards(page, 1)
    text = page.find_visible('.group-list', timeout=10).text
    assert '词错误率' in text and '接管时延' not in text, '类别页签未按 category 过滤组卡'
    assert 'category=asr' in page.current_route(), \
        f'URL query 未写入 category=asr: {page.current_route()}'

    # 验收③：URL query 直达/刷新可还原（onMounted applyQueryToFilters 读取）
    page.goto('/rankings?source=platform_test&category=asr')
    _wait_group_cards(page, 1)
    text = page.find_visible('.group-list', timeout=10).text
    assert '词错误率' in text and '接管时延' not in text, 'URL 还原后组卡未按 category 过滤'
    assert 'int482_asr_a' in text and 'int482_asr_b' not in text, \
        'URL 还原后来源筛选未生效（应仅 platform_test 行）'

    # 主体搜索（防抖 300ms）→ 无匹配 → 空态（验收③：筛选联动一致）
    page.fill(SEARCH_INPUT, 'int482_nonexistent_xyz')
    page.wait_visible(EMPTY_STATE, timeout=20)
    empty = page.find_visible(EMPTY_STATE)
    assert '暂无排行数据' in empty.text, f'空态文案异常: {empty.text[:60]!r}'


def test_permission_denied_role_data_gated(page, int482_benchmark_rows, int482_guest):
    """权限不足角色（guest）：/rankings 公开可达但数据 403 门控（INT-745 公开路由口径）。

    INT-745 把 /rankings 改为公开路由（meta.public，未登录/无权限均可达），
    数据权限由接口层门控；附 API 层 403 佐证。
    """
    # API 层佐证：guest token 请求排行接口 403
    r = httpx.get(f'{API_ROOT}/api/v1/benchmarks/ranking',
                  headers={'Authorization': f'Bearer {int482_guest["token"]}'},
                  timeout=5, trust_env=False)
    assert r.status_code == 403, f'guest 请求排行接口应 403，实际 {r.status_code}'

    # 浏览器注入 guest 登录态（用 page.base_url，随 run_gate/验收 vite 端口自适应）
    _inject_login(page.driver, page.base_url, int482_guest['token'], int482_guest['user'])
    page.goto('/rankings')
    page.wait_visible('.public-header', timeout=15)
    page.settle(0.8)

    # 公开路由可达：停留 /rankings（不弹回首页/登录页）
    route = page.current_route()
    assert '/rankings' in route, f'guest 应可停留在 /rankings，实际路由: {route}'

    # 顶导航「排行榜」入口按权限隐藏（guest 无 benchmark:ranking:read）
    nav_labels = [a.text.strip() for a in page.find_all('.public-nav .public-nav-link')]
    assert '排行榜' not in nav_labels, \
        f'guest 顶导航不应显示「排行榜」入口（permission 未生效）: {nav_labels}'

    # 算法卡片只读降级条（guest 无 algorithm:read）+ 排行数据 403 → 错误/空态
    assert page.exists('.ag-readonly'), 'guest 应见算法卡片只读降级条'
    ro = page.find_visible('.ag-readonly', timeout=10).text
    assert '全部算法' in ro, f'只读降级条应显示「全部算法」: {ro[:40]!r}'
    assert page.exists('.error-state') or page.exists('.empty-state'), \
        'guest 排行数据应呈现错误/空态（403 门控）'
