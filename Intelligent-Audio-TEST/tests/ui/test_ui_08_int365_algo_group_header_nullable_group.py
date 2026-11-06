# -*- coding: utf-8 -*-
"""INT-365 验收：算法参数映射补差（V9.7.10 792b3de7 两处差异）。

差异 1 —— 分组头 colspan 压缩修复（MappingEditor.vue）：
评估维度视图（componentType=evaluation，默认 dimension 视图）的分组头行
``<tr class="dimension-group-header-row"><td :colspan="7">`` 是该行唯一
单元格（即 :last-child），被全局 ``.data-table td:last-child``
（table.css:151 ``display:flex; min-width:150px``）压出表格布局——flex
单元脱离表格列网格，colspan 塌缩、分组头被压成一条窄列。修复：分组头
样式补 ``display: table-cell !important; min-width: 0 !important``
（与既有组尾 ``.add-row td`` 同一修复口径）。

差异 2 —— 保存校验 group_id 可空（AlgorithmConfigModal.vue + useAlgorithmCrudOps.ts）：
新建/编辑算法不选分组（group_id=null）保存此前被前端拦截
（``!formState.groupId`` → warning「请填写必填字段」）；后端全链路本就可空
（PO 列 nullable、Create schema Optional、网关 exclude_none 透传 None）。
修复：去掉必填* 与空 groupId 拦截。

验收断言（对应 issue 验收标准 1/2；标准 3 全量回归由 vitest/vue-tsc/
build 另行收集，本文件不含）：

1. **静态**：MappingEditor.vue 分组头规则含 table-cell 覆盖与 min-width:0；
   AlgorithmConfigModal「所属分组」label 无必填 *；useAlgorithmCrudOps
   handleOk 无 ``!formState.groupId`` 拦截。
2. **运行时（核心）**：headless Chrome 打开算法配置 → 编辑 voice_llm
   （隔离库既有算法，21 条评估映射）→ 参数映射 tab → 展开评估参数映射
   → 断言每组分组头 td 计算样式 display=table-cell、渲染宽度 = 表格
   内容区宽（colspan 完整跨列不塌缩）；正向补断言普通映射行 td 仍为
   flex（修复只影响分组头行，全局操作列布局未被反向破坏）。
3. **group_id 可空落库（主验收项）**：新建算法不选分组直接确定 →
   保存成功（无 warning 通知、无「请填写必填字段」），API 查回
   group_id=null；列表「分组」列显示「-」。teardown 删除该算法
   （软删 + 不留残留）。
4. **反向回归**：新建算法选既有分组保存 → group_id 落库为所选分组
   （可空修复未误伤非空路径）；teardown 删除算法与分组。

环境口径：tests/ui 门禁三件套沿用（RUN_LIVE_STACK=1 显式纳入、隔离库
守卫、引导自举），并行隔离栈跑（run_gate.py，:6000/:6273）。

测试数据卫生（硬规则）：本文件新建的算法/分组全部 teardown 删除
（fixture finally），隔离库不留本卡残留。
"""
import os
import re
from uuid import uuid4

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage

ALGO_ROUTE = '/AlgorithmConfig'
MODAL = '.modal'                        # BasicModal 容器
MODAL_TITLE = '.modal-title'
# 算法配置页「新建算法」按钮（页头 header-actions 内，区别于模态窗同名按钮）
PAGE_CREATE_BTN = '.algorithm-config-page .page-header button.btn-primary'
# 基本信息表单字段（按 form-group 内 label 文本定位，见 _field_input）
GROUP_SELECT = '.mode-form select.form-input'
# 模态窗页签
TAB_MAPPINGS = '.mode-form .tabs-nav .tab-btn'
# 评估参数映射折叠区
EVAL_SECTION_HEADER = '.mapping-section .mapping-header'
EVAL_EDITOR = '.mapping-body .mapping-editor, .mapping-body [class*="mapping"]'
GROUP_HEADER_ROW = '.dimension-group-header-row td'
VIEW_TABS = '.view-mode-tab'


def _field_input(bp: BasePage, label_text: str):
    """按 label 文本定位同 form-group 内的 input/select（modal 基本信息字段）。"""
    groups = bp.find_all('.mode-form .form-group')
    for g in groups:
        labels = g.find_elements(By.TAG_NAME, 'label')
        if labels and label_text in labels[0].text:
            for tag in ('input', 'select', 'textarea'):
                els = g.find_elements(By.TAG_NAME, tag)
                if els:
                    return els[0]
    raise AssertionError(f'未找到字段「{label_text}」对应的输入控件')


def _field_group(bp: BasePage, label_text: str):
    for g in bp.find_all('.mode-form .form-group'):
        labels = g.find_elements(By.TAG_NAME, 'label')
        if labels and label_text in labels[0].text:
            return g
    raise AssertionError(f'未找到字段「{label_text}」所在 form-group')


def _hard_cleanup(suffix: str):
    """把本卡测试行从隔离库物理清除（软删不释放 UNIQUE(type)）。

    仅匹配 INT-365 前缀 + run 后缀的行，不触碰其它数据。
    """
    import sqlalchemy as sa
    url = os.environ.get('TEST_DB_URL')
    if not url:
        # 与并行隔离栈同参（shared/constants/database.py 隔离库名）
        from shared.constants.database import ISOLATED_TEST_DB_NAME
        url = ('postgresql://intelligent_audio_test:intelligent_audio_test666'
               f'@localhost:5432/{ISOLATED_TEST_DB_NAME}')
    eng = sa.create_engine(url)
    pat = f'int365%_{suffix}'
    gpat = 'INT365%'
    with eng.connect() as c:
        for table in ('param_mappings', 'algorithm_dimension_relations',
                      'algorithm_device_params', 'algorithm_api_params',
                      'case_algorithm_params', 'algorithm_reference_params'):
            c.execute(sa.text(f'DELETE FROM {table} WHERE algorithm_type LIKE :p'),
                      {'p': pat})
        c.execute(sa.text('DELETE FROM algorithm_definitions WHERE type LIKE :p'),
                  {'p': pat})
        c.execute(sa.text('DELETE FROM algorithm_groups WHERE name LIKE :g'),
                  {'g': gpat})
        c.commit()


def _open_create_modal(bp: BasePage):
    """登录态下进入算法配置页 → 点「新建算法」→ 等模态窗出现（create 模式）。"""
    bp.goto(ALGO_ROUTE)
    WebDriverWait(bp.driver, 25).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.algorithm-config-page')))
    bp.settle(0.5)
    bp.click(PAGE_CREATE_BTN)
    bp.wait_visible(MODAL, timeout=15)
    bp.wait_visible('.mode-form', timeout=10)
    bp.settle(0.3)


def _fill_required_and_save(bp: BasePage, algo_type: str, name: str):
    """基本信息页签填算法代码/显示名称（分组保持「请选择分组」）→ 确定。"""
    type_input = _field_input(bp, '算法代码')
    type_input.clear()
    type_input.send_keys(algo_type)
    bp.settle(0.2)
    name_input = _field_input(bp, '显示名称')
    name_input.clear()
    name_input.send_keys(name)
    bp.settle(0.2)
    bp.click(f'{MODAL} .modal-footer .btn-primary')
    bp.settle(1.0)


def _notification_text(bp: BasePage) -> str:
    els = bp.find_all('.notification-container .notification-message')
    return ' | '.join(e.text.strip() for e in els if e.text.strip())


# ── 静态断言（不依赖实机栈）──────────────────────────────────
def _read(*rel: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, *rel), encoding='utf-8') as fh:
        return fh.read()


class TestInt365Static:
    """静态：修复代码在位（防止后续被无声回退）。"""

    def test_mapping_editor_group_header_rule_restores_table_cell(self):
        """差异 1：分组头规则补 display:table-cell + min-width:0 覆盖。"""
        css = _read('frontend', 'src', 'components', 'algorithm', 'MappingEditor.vue')
        m = re.search(r'\.dimension-group-header-row td\s*\{([^}]*)\}', css)
        assert m, 'MappingEditor.vue 缺少 .dimension-group-header-row td 规则'
        body = m.group(1)
        assert 'table-cell' in body, (
            '分组头规则缺 display:table-cell 覆盖——全局 .data-table td:last-child '
            '的 display:flex 会压塌 colspan（INT-365 缺陷回归）')
        assert 'min-width: 0' in body, '分组头规则缺 min-width:0 覆盖'

    def test_modal_group_label_not_required(self):
        """差异 2a：「所属分组」label 无必填 *。"""
        vue = _read('frontend', 'src', 'components', 'algorithm', 'AlgorithmConfigModal.vue')
        m = re.search(r'<label>所属分组(.*?)</label>', vue, re.S)
        assert m, 'AlgorithmConfigModal.vue 未找到「所属分组」label'
        assert 'required' not in m.group(1), (
            '「所属分组」label 仍带必填 * 标记（INT-365 差异回归）')

    def test_crud_ops_no_empty_groupid_interception(self):
        """差异 2b：handleOk 不再拦截空 groupId。"""
        ts = _read('frontend', 'src', 'components', 'algorithm', 'useAlgorithmCrudOps.ts')
        assert '!formState.groupId' not in ts, (
            'useAlgorithmCrudOps 仍拦截空 groupId——不选分组保存会被前端'
            '「请填写必填字段」挡下（INT-365 差异回归）')


class TestInt365GroupHeaderColspan:
    """运行时核心：评估维度视图分组头完整跨列不塌缩（验收标准 1）。"""

    def test_group_header_spans_full_table_width(self, page: BasePage):
        """分组头 td 计算样式 table-cell 且渲染宽度≈表格内容区宽。"""
        page.goto(ALGO_ROUTE)
        WebDriverWait(page.driver, 25).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '.algorithm-config-page')))
        page.settle(0.8)
        # 精确点编辑 voice_llm（display_order=100 排后，前序用例造的数据已清，
        # 但仍按类型定位防列表顺序漂移）
        _open_edit_modal(page, 'voice_llm')
        # 参数映射 tab：按 label 文本定位（tab 顺序可能变化）
        for btn in page.find_all(TAB_MAPPINGS):
            if '参数映射' in btn.text:
                page.driver.execute_script('arguments[0].click();', btn)
                break
        else:
            raise AssertionError('模态窗未找到「参数映射」页签')
        page.settle(0.5)
        # 评估参数映射折叠区：mappingExpanded 默认三区全展开
        # （useAlgorithmMappingOps），若已展开则不点（再点是收起）；
        # 以 mapping-body 的 display 状态为准。
        header = None
        for h in page.find_all(EVAL_SECTION_HEADER):
            if '评估参数映射' in h.text:
                header = h
                break
        assert header is not None, '未找到「评估参数映射」折叠区头'
        body = header.find_element(By.XPATH, 'following-sibling::div[contains(@class,"mapping-body")]')
        if not body.is_displayed():
            page.driver.execute_script('arguments[0].click();', header)
            WebDriverWait(page.driver, 10).until(
                lambda d: body.is_displayed())
        page.wait_visible(GROUP_HEADER_ROW, timeout=15)
        page.settle(0.8)  # 表格布局稳定余量

        probe = page.driver.execute_script("""
            const headers = [...document.querySelectorAll('.dimension-group-header-row td')];
            const table = document.querySelector('.mapping-body table.data-table');
            if (!headers.length || !table) return null;
            const cs = getComputedStyle(headers[0]);
            const tcs = getComputedStyle(table);
            const padL = parseFloat(tcs.paddingLeft) || 0;
            const padR = parseFloat(tcs.paddingRight) || 0;
            // 表格内容区宽（colspan=7 应铺满的宽度）
            const contentW = table.getBoundingClientRect().width - padL - padR - 2;
            // 普通映射行首个 td（修复不应影响全局操作列 flex 布局）
            const normalTd = document.querySelector(
              '.mapping-body tbody tr:not(.dimension-group-header-row):not(.add-row) td');
            return {
                headerCount: headers.length,
                display: cs.display,
                minWidth: cs.minWidth,
                colspan: headers[0].getAttribute('colspan'),
                headerW: Math.round(headers[0].getBoundingClientRect().width),
                tableContentW: Math.round(contentW),
                rowW: Math.round(headers[0].closest('tr').getBoundingClientRect().width),
                normalDisplay: normalTd ? getComputedStyle(normalTd).display : null,
            };
        """)
        assert probe, '参数映射区未渲染出分组头或表格'
        assert probe['headerCount'] >= 1, f'分组头行数量异常: {probe}'
        assert probe['display'] == 'table-cell', (
            f"分组头 td 计算样式 display={probe['display']}（期望 table-cell，"
            '全局 .data-table td:last-child flex 压塌 colspan——INT-365 缺陷回归）')
        assert probe['colspan'] == '7', f"分组头 colspan={probe['colspan']}（评估视图应为 7）"
        # 渲染宽度覆盖表格内容区（容差 4px 边框/舍入）
        assert probe['headerW'] >= probe['tableContentW'] - 4, (
            f"分组头渲染宽 {probe['headerW']}px < 表格内容区 {probe['tableContentW']}px "
            '——colspan 塌缩（INT-365 缺陷回归）')
        # 正向：普通映射行 td 仍是 flex（全局口径未被反向破坏）
        assert probe['normalDisplay'] == 'flex', (
            f"普通映射行 td display={probe['normalDisplay']}（期望 flex，"
            '修复不应影响全局操作列布局）')


class TestInt365GroupIdNullable:
    """group_id 可空落库（验收标准 2）+ 非空反向回归 + 数据卫生兜底。

    口径注记：算法 type 列为全表 UNIQUE（非 partial），软删除不释放 type，
    用例间同 type 重建会 UniqueViolation——每条用例用唯一 type（uuid 后缀）
    保证可重跑；teardown 软删后由 _hard_cleanup 把本卡测试行从隔离库
    物理清除（测试数据卫生硬规则：验收后库内零残留）。
    """

    # 类级容器：本类所有用例创建的算法类型/分组 id 统一登记，
    # autouse fixture teardown 逐个清理（函数级容器拿不到别处的数据）
    _created_algos: list = []
    _created_group_ids: list = []
    _suffix = uuid4().hex[:6]

    @pytest.fixture(autouse=True)
    def _register(self, api_client):
        yield
        # 每条用例结束即清本用例登记的数据（幂等；失败也不留残留）
        for algo_type in list(self._created_algos):
            try:
                api_client.request('DELETE', f'/algorithm/definitions/{algo_type}')
            except Exception:
                pass
            self._created_algos.remove(algo_type)
        for gid in list(self._created_group_ids):
            try:
                api_client.request('DELETE', f'/algorithm/groups/{gid}')
            except Exception:
                pass
            self._created_group_ids.remove(gid)
        # 软删不释放 UNIQUE(type)，硬清残留保证重跑（隔离测试库内操作）
        _hard_cleanup(suffix=self._suffix)

    @staticmethod
    def _t(base: str) -> str:
        """带 run 级唯一后缀的算法 type（规避 UNIQUE(type) 软删不释放）。"""
        return f'{base}_{TestInt365GroupIdNullable._suffix}'

    def test_create_without_group_saves_nullable(self, page: BasePage, api_client):
        """主验收项：新建算法不选分组直接确定 → 落库 group_id=null。"""
        algo_type = self._t('int365_nogroup')
        name = 'INT365无分组算法'
        self._created_algos.append(algo_type)
        _open_create_modal(page)
        _fill_required_and_save(page, algo_type, name)

        # 无 warning 通知（修复前：'请填写必填字段' 拦截）
        note = _notification_text(page)
        assert '请填写必填字段' not in note, (
            f'空 group_id 保存仍被前端拦截（INT-365 差异回归）：通知={note!r}')

        # 模态窗关闭（保存成功路径）
        def modal_gone(d):
            try:
                els = d.find_elements(By.CSS_SELECTOR, '.mode-form')
                return not els or not els[0].is_displayed()
            except Exception:
                return False
        WebDriverWait(page.driver, 15).until(modal_gone)

        # API 查回：group_id=null 落库
        detail = api_client.request('GET', f'/algorithm/definitions/{algo_type}')
        data = detail.get('data') or {}
        assert data.get('type') == algo_type, f'算法未查回（保存失败？）: {str(detail)[:200]}'
        assert data.get('group_id') is None, (
            f"group_id 应为 null，实际 {data.get('group_id')!r}（INT-365 差异回归）")

    def test_list_shows_dash_for_null_group(self, page: BasePage, api_client):
        """列表「分组」列：group_id=null 显示「-」。"""
        algo_type = self._t('int365_nogroup')
        name = 'INT365无分组算法'
        self._created_algos.append(algo_type)
        _open_create_modal(page)
        _fill_required_and_save(page, algo_type, name)
        page.settle(1.5)  # 保存后 loadAlgorithms 刷新列表余量
        page.wait_gone('.mode-form', timeout=10)

        row = None
        for tr in page.find_all('.algorithm-config-page tbody tr'):
            if algo_type in tr.text:
                row = tr
                break
        assert row is not None, f'列表未见新建算法 {algo_type}'
        tds = row.find_elements(By.TAG_NAME, 'td')
        assert len(tds) >= 3, f'列表行单元格数异常: {len(tds)}'
        group_cell = tds[2].text.strip()
        assert group_cell == '-', (
            f"分组列应显示「-」（group_id=null），实际 {group_cell!r}")

    def test_create_with_existing_group_still_saves(self, page: BasePage, api_client):
        """反向回归：选既有分组保存 → group_id 落库为所选分组（非空路径未误伤）。"""
        group_name = 'INT365验收组'
        g = api_client.request('POST', '/algorithm/groups', {'name': group_name})
        group_id = (g.get('data') or {}).get('id')
        assert group_id, f'分组创建失败: {str(g)[:200]}'
        self._created_group_ids.append(group_id)
        algo_type = self._t('int365_withgroup')
        name = 'INT365有分组算法'
        self._created_algos.append(algo_type)
        _open_create_modal(page)
        # 填必填字段
        type_input = _field_input(page, '算法代码')
        type_input.clear()
        type_input.send_keys(algo_type)
        page.settle(0.2)
        name_input = _field_input(page, '显示名称')
        name_input.clear()
        name_input.send_keys(name)
        page.settle(0.2)
        # 选分组（select value 为 group id；Vue v-model 需派发 change）
        sel = _field_input(page, '所属分组')
        page.driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            sel, str(group_id))
        page.settle(0.3)
        assert sel.get_attribute('value') == str(group_id), (
            f"分组下拉未选中 id={group_id}，value={sel.get_attribute('value')!r}")
        # 确定
        page.click(f'{MODAL} .modal-footer .btn-primary')
        page.settle(1.2)
        note = _notification_text(page)
        assert '失败' not in note, f'带分组保存报错: {note!r}'
        detail = api_client.request('GET', f'/algorithm/definitions/{algo_type}')
        data = detail.get('data') or {}
        assert data.get('group_id') == group_id, (
            f"group_id 应为 {group_id}，实际 {data.get('group_id')!r}")

    def test_edit_existing_group_to_null_keeps_value_patch_semantics(self, page: BasePage, api_client):
        """口径核对（非本卡缺陷）：编辑时把有分组改为「请选择分组」——
        网关 exclude_none + 后端 PATCH 语义（None 不覆盖）下分组保持现值，
        与 V9.7.10 源行为一致；用 API 断言固化当前口径防无声漂移。"""
        algo_type = self._t('int365_patchsem')
        name = 'INT365口径核对'
        self._created_algos.append(algo_type)
        g = api_client.request('POST', '/algorithm/groups', {'name': 'INT365口径组'})
        group_id = (g.get('data') or {}).get('id')
        self._created_group_ids.append(group_id)
        api_client.request('POST', '/algorithm/definitions', {
            'type': algo_type, 'name': name, 'group_id': group_id, 'status': 'online'})
        # 编辑：UI 打开 → 不动分组 → 确定（PATCH 不带 group_id 变化）
        _open_edit_modal(page, algo_type)
        page.click(f'{MODAL} .modal-footer .btn-primary')
        page.settle(1.2)
        detail = api_client.request('GET', f'/algorithm/definitions/{algo_type}')
        data = detail.get('data') or {}
        assert data.get('group_id') == group_id, (
            f"编辑重存后 group_id 应保持 {group_id}，实际 {data.get('group_id')!r}")

def _open_edit_modal(bp: BasePage, algo_type: str):
    """算法列表页找到指定类型行 → 编辑 → 等模态窗出现（详情加载完成后打开）。"""
    bp.goto(ALGO_ROUTE)
    WebDriverWait(bp.driver, 25).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.algorithm-config-page')))
    bp.settle(0.8)
    for tr in bp.find_all('.algorithm-config-page tbody tr'):
        tds = tr.find_elements(By.TAG_NAME, 'td')
        if tds and algo_type in tds[0].text:
            btns = tr.find_elements(By.CSS_SELECTOR, '.table-actions button')
            bp.driver.execute_script('arguments[0].click();', btns[0])  # 编辑
            bp.wait_visible('.mode-form', timeout=15)
            bp.settle(0.8)  # loadAlgorithmDetail 异步加载余量
            return
    raise AssertionError(f'列表未见算法 {algo_type}')
