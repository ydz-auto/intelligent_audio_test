# -*- coding: utf-8 -*-
"""INT-1840 取证：购物车 / 复核「用例层组织」接 INT-1693 真名（tags/group_id/group_name）后的组头。

数据源：真实库（docker 15000，库 intelligent_audio_test）任务 418「豆包拒识…」/ 419「小艺拒识…」，
各 138 条候选，库内 group_name=拒识、tags 非空 —— 修复前购物车恒落「未分组 / 未设置标签」单桶。

页面：本 run worktree 构建的 dist 起旁路 nginx 容器（15294，--network intelligent-audio-test_default，
/api → api_gateway:5000），不重建共享 15173。

用法：python capture_int1840.py light | dark
输出：tests/ui/artifacts/int1840/<mode>_*.png（用例视图 / 设备视图 / 任务视图用例子模式 / 结果类型视图）
     tests/ui/artifacts/int1840/<mode>_network.png（cart_get 真实响应字段证据）
"""
import json
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1694 as base  # noqa: E402

base.BASE = os.environ.get('INT1840_BASE', 'http://127.0.0.1:15294')
base.ART = os.path.join(
    HERE, 'artifacts', os.environ.get('INT1840_ART', 'int1840')
)
os.makedirs(base.ART, exist_ok=True)

TASK_NAME_A = '豆包拒识'
TASK_NAME_B = '小艺拒识'
FAILS = []
CART_FETCH_JS = r"""
return (async () => {
  const token = localStorage.getItem('iatp:auth:token:v1');
  const r = await fetch('/api/v1/tasks/cherry-picks/cart', {headers: {Authorization: 'Bearer ' + token}});
  const j = await r.json();
  return {status: r.status, body: j};
})()
"""


def shot(drv, name):
    """截图前把内层滚动容器归零（展开会把树容器滚走）。"""
    drv.execute_script(
        "window.scrollTo(0,0);"
        "document.querySelectorAll('*').forEach(function(e){"
        "  if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight + 20) e.scrollTop = 0;"
        "});"
    )
    time.sleep(0.5)
    base.shot(drv, name)


def dialog_text(drv):
    ds = drv.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    if not ds:
        return ''
    return base.text_of(drv, ds[-1])


def last_dialog(drv):
    """最后一个 dialog（Base UI 关闭后的弹窗仍留在 DOM，取最后一个可见的）。"""
    ds = drv.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    for d in reversed(ds):
        try:
            if d.is_displayed():
                return d
        except Exception:
            pass
    return ds[-1] if ds else drv


def expand_nodes(drv, level, limit=2, scope=None):
    """按层级展开前 limit 个节点（row 级定位）。

    默认只在最后一个 dialog 内点——Base UI 关闭后的弹窗仍留在 DOM，
    全局按 aria-label 取「展开」会先点到隐藏弹窗里的同名按钮（点了没反应）。
    """
    scope = scope or last_dialog(drv)
    rows = scope.find_elements(By.CSS_SELECTOR, '[data-testid*="-%s:"]' % level)
    n = 0
    for row in rows:
        if n >= limit:
            break
        try:
            if not row.is_displayed():
                continue
            btns = row.find_elements(By.CSS_SELECTOR, "button[aria-label='展开']")
            if btns:
                base.js_click(drv, btns[0])
                n += 1
                time.sleep(0.5)
        except Exception:
            pass
    print('EXPAND_NODES', level, n, 'rows', len(rows))
    time.sleep(1)
    return n


def click_exact(drv, label, required=True, scope=None):
    """按钮文案精确匹配，只点作用域内（页面背后筛选栏有同名「设备 / 结果类型」按钮）。

    required=False：找不到返回 None（如 result_type 单一种类时「结果类型视图」入口按口径隐藏）。
    """
    scope = scope or last_dialog(drv)
    for el in scope.find_elements(By.CSS_SELECTOR, 'button'):
        try:
            if not el.is_displayed():
                continue
            if base.text_of(drv, el).strip() == label:
                base.js_click(drv, el)
                return el
        except Exception:
            pass
    if not required:
        return None
    raise RuntimeError('找不到精确文案按钮: %s' % label)


def wait_task_rows(drv, timeout=300):
    """阶段 1 任务行（pickable-tasks 真实库较慢）；优先勾任务 418 / 419 两个拒识任务。

    回退：第一个「豆包拒识」+ 第一个「小艺拒识」；再回退：前两个拒识任务。
    返回 (aria-label 列表, 名称列表)。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = [
            c
            for c in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if (c.get_attribute('aria-label') or '').startswith('选择任务')
        ]
        if len(rows) >= 2:
            labels = [(c, c.get_attribute('aria-label') or '') for c in rows]
            matched = []
            for name in (TASK_NAME_A, TASK_NAME_B):
                hit = next((lab for _, lab in labels if name in lab), None)
                if hit and hit not in matched:
                    matched.append(hit)
            print('TASK_ROWS', len(rows), 'matched', matched)
            if len(matched) >= 2:
                return matched[:2]
            for _, lab in labels:
                if lab not in matched:
                    matched.append(lab)
                if len(matched) >= 2:
                    return matched[:2]
        time.sleep(3)
    raise RuntimeError('阶段 1 任务行未加载（pickable-tasks 超时）')


def select_tasks(drv, labels):
    rows = drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
    chosen = []
    for lab in labels:
        for cb in rows:
            if (cb.get_attribute('aria-label') or '') == lab:
                base.js_click(drv, cb)
                time.sleep(0.4)
                chosen.append(lab)
                break
    print('STAGE1_SELECTED', chosen)
    if len(chosen) < 2:
        raise RuntimeError('阶段 1 未勾到两个任务')


def wait_tree(drv, timeout=300, selector=None):
    """等购物车内容渲染：抽屉内出现任一「展开」钮（分支行 / 用例卡共用该 aria-label）。

    用例视图顶层是 PickCaseOrgList 的用例卡（无 cart-branch testid），按 cart-branch 等会空等超时。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        dialogs = drv.find_elements(By.CSS_SELECTOR, "[role='dialog']")
        scope = dialogs[-1] if dialogs else drv
        if scope.find_elements(By.CSS_SELECTOR, "button[aria-label='展开']") or (
            selector and scope.find_elements(By.CSS_SELECTOR, selector)
        ):
            time.sleep(1.5)
            return
        time.sleep(2)
    raise RuntimeError('购物车内容未渲染')


def org_labels(drv, scope=None):
    """caseOrg 组头（设备/结果类型视图/任务视图子模式）——testid 取组 key，文本取组名首行。"""
    scope = scope or last_dialog(drv)
    out = []
    for el in scope.find_elements(By.CSS_SELECTOR, '[data-testid*="-org:"]'):
        try:
            if not el.is_displayed():
                continue
        except Exception:
            pass
        tid = el.get_attribute('data-testid') or ''
        first = (base.text_of(drv, el) or '').split('\n')[0].strip()
        out.append((tid.split('-org:')[-1], first[:40]))
    return out


LEAF_TEXTS_JS = r"""
var scope = arguments[0] || document.body;
var out = [];
scope.querySelectorAll('*').forEach(function (e) {
  if (e.children.length === 0) {
    var t = (e.textContent || '').trim();
    if (t && t.length <= 24) out.push(t);
  }
});
return out;
"""


def leaf_texts(drv, scope=None):
    """作用域内叶子节点文本（组头名是独立 span；组织控件提示语是长句，不会误命中）。"""
    sc = scope if scope is not None else last_dialog(drv)
    arg = None if sc is drv else sc  # 无 dialog → 不传参，JS 侧回落 document.body
    return drv.execute_script(LEAF_TEXTS_JS, arg) or []


def assert_real_headers(drv, tag, expect_name='拒识', forbid='未分组', scope=None):
    """组头断言：真名模式要求出「拒识」且不出现兜底桶；fallback 模式（A/B 旧包）要求相反。

    设备 / 结果类型视图的 caseOrg 组头带 testid（文本即组名，判据最强）；
    用例视图顶层与任务视图用例子模式由 PickCaseOrgList 渲染（CaseSubGroupHeader 无 testid），
    用作用域内叶子文本判（组织控件的提示长句含「未分组」，用叶子精确匹配排除）。
    断言失败只记录，不中断截图（一次跑完全部视图再汇总）。
    """
    expect = os.environ.get('INT1840_EXPECT', 'real')
    labels = org_labels(drv, scope)
    leaves = leaf_texts(drv, scope)
    print('ORG_LAYER', tag, 'count=%d' % len(labels), labels[:4])
    if labels:
        names = ' '.join(t for _, t in labels)
    else:
        names = ' | '.join(leaves)
        print('LEAF_TEXTS', tag, leaves[:12])
    hit = expect_name in names
    bad = forbid in names
    if expect == 'real':
        if not hit or bad:
            FAILS.append('组头未出真名（%s）：hit=%s 兜底桶=%s %s' % (tag, hit, bad, labels[:4] or leaves[:12]))
    else:
        if not bad:
            FAILS.append('A/B 旧包应落兜底桶「%s」却未见（%s）' % (forbid, tag))


def cart_shots(drv, mode):
    # 任务视图 · 用例子模式：任务 → 用例层组织组头（展开前 2 个任务节点）
    expand_nodes(drv, 'task', 2)
    assert_real_headers(drv, 'cart_task_case')
    shot(drv, '%s_cart_task_case' % mode)

    # 用例视图：顶层组织组头（按真分组聚合）
    click_exact(drv, '用例视图')
    time.sleep(2)
    wait_tree(drv)
    assert_real_headers(drv, 'cart_case')
    shot(drv, '%s_cart_case' % mode)

    # 设备视图：设备 → result_type → caseOrg 组头
    click_exact(drv, '设备视图')
    time.sleep(2)
    wait_tree(drv)
    expand_nodes(drv, 'device', 2)
    expand_nodes(drv, 'resultType', 2)
    assert_real_headers(drv, 'cart_device')
    shot(drv, '%s_cart_device' % mode)

    # 结果类型视图：result_type → 设备 → caseOrg 组头
    # （真实库 result_type 全为 default 时该入口按 INT-1694 口径隐藏 → 跳过，不算失败）
    rt_btn = click_exact(drv, '结果类型视图', required=False)
    if rt_btn is None:
        print('SKIP 结果类型视图：result_type 单一种类，入口隐藏（hasResultTypeVariety=false）')
    else:
        time.sleep(2)
        wait_tree(drv)
        expand_nodes(drv, 'resultType', 2)
        expand_nodes(drv, 'device', 2)
        assert_real_headers(drv, 'cart_resulttype')
        shot(drv, '%s_cart_resulttype' % mode)

    # 标签视图（用例视图顶层按真标签名分组）
    # 注意：必须按作用域点——Base UI 关闭后的残留弹窗里也有同名「标签视图」tab，
    # 全局按文案点会点到看不见的那个，截图仍是「分组视图」（INT-1840 首轮踩过）。
    click_exact(drv, '用例视图')
    time.sleep(2)
    wait_tree(drv)
    click_text_scoped(drv, '标签视图')
    time.sleep(2)
    tab = selected_tab(drv)
    leaves = leaf_texts(drv)
    expect = os.environ.get('INT1840_EXPECT', 'real')
    untagged = '未设置标签' in leaves
    print('TAG_VIEW', tab, leaves[:10], '未设置标签=', untagged)
    if tab != '标签视图':
        FAILS.append('标签视图未切换成功（aria-selected=%r）' % tab)
    if expect == 'real' and untagged:
        FAILS.append('标签视图仍落「未设置标签」兜底桶')
    if expect != 'real' and not untagged:
        FAILS.append('A/B 旧包标签视图应落「未设置标签」却未见')
    shot(drv, '%s_cart_case_tag' % mode)
    click_text_scoped(drv, '分组视图', required=False)
    time.sleep(1)


def font(size=17, bold=False):
    for fp in (
        r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
    ):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_evidence(name, title, lines):
    f = font(17)
    wrapped = []
    for line in lines:
        while len(line) > 78:
            wrapped.append(line[:78])
            line = line[78:]
        wrapped.append(line)
    W = 1120
    H = max(150, 30 * len(wrapped) + 90)
    img = Image.new('RGB', (W, H), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 46], fill=(32, 38, 52))
    draw.text((16, 12), title, fill=(255, 255, 255), font=font(20, True))
    y = 58
    for ln in wrapped:
        draw.text((16, y), ln, fill=(25, 25, 25) if not ln.startswith('FAIL') else (180, 0, 0), font=f)
        y += 28
    path = os.path.join(base.ART, name + '.png')
    img.save(path)
    print('EVIDENCE', path)
    return path


def network_evidence(drv, mode):
    res = drv.execute_script(CART_FETCH_JS)
    body = (res or {}).get('body') or {}
    data = body.get('data') or body
    groups = data.get('groups') or []
    items = [it for g in groups for it in (g.get('items') or [])]
    with_group = [it for it in items if it.get('group_id')]
    with_tags = [it for it in items if it.get('tags')]
    print('CART_ITEMS', len(items), 'groups', len(groups), 'with_group', len(with_group), 'with_tags', len(with_tags))
    for it in items[:4]:
        print(
            'ITEM %s task=%s case=%s group_id=%s group_name=%s tags=%s'
            % (
                it.get('item_id'),
                it.get('source_task_id'),
                it.get('source_case_name'),
                it.get('group_id'),
                it.get('group_name'),
                json.dumps(it.get('tags'), ensure_ascii=False),
            )
        )
    if not with_group:
        FAILS.append('cart_get 本轮条目未带真实分组（无法验证真名）')
    fields = ', '.join(items[0].keys()) if items else '无条目'
    lines = [
        'GET %s/api/v1/tasks/cherry-picks/cart' % base.BASE,
        '状态码 %s   条目 %d 条 / 分组 %d 个' % (res.get('status'), len(items), len(groups)),
        '返回字段：%s' % fields,
        '',
        '逐行真名（前 4 条）：',
    ]
    for it in items[:4]:
        lines.append(
            '  item %s · 用例 %s · group_id=%s · group_name=%s · tags=%s'
            % (
                it.get('item_id'),
                it.get('source_case_name'),
                it.get('group_id'),
                it.get('group_name'),
                json.dumps(it.get('tags'), ensure_ascii=False),
            )
        )
    lines += [
        '',
        '带 group_id 的条目 %d / %d；带 tags 的条目 %d / %d'
        % (len(with_group), len(items), len(with_tags), len(items)),
    ]
    if not with_group:
        lines.append('FAIL 本轮夹具未带真实分组，组织层无法出真名')
    render_evidence('%s_network' % mode, 'INT-1840 购物车 cart_get 真实响应（%s）' % mode, lines)


def click_text_scoped(drv, needle, required=True, scope=None):
    """作用域内按文案包含匹配点按钮（Base UI 关闭后的残留弹窗里也有同名 tab，
    全局点会点到看不见的那个，点了没反应）。"""
    scope = scope or last_dialog(drv)
    for el in scope.find_elements(By.CSS_SELECTOR, 'button'):
        try:
            if not el.is_displayed():
                continue
            if needle in base.text_of(drv, el):
                base.js_click(drv, el)
                return el
        except Exception:
            pass
    if not required:
        return None
    raise RuntimeError('作用域内找不到文案: %s' % needle)


def selected_tab(drv, scope=None):
    """当前选中的 tab 文案（用例视图 / 标签视图 / 分组视图 …）。"""
    scope = scope or last_dialog(drv)
    for el in scope.find_elements(By.CSS_SELECTOR, "[role='tab'][aria-selected='true']"):
        try:
            if el.is_displayed():
                return base.text_of(drv, el).strip()
        except Exception:
            pass
    return ''


def close_drawer(drv):
    """关掉购物车抽屉（Base UI 关闭后仍留 DOM，后面按作用域取元素要避开它）。"""
    dlg = last_dialog(drv)
    if dlg is drv:
        return False
    for label in ('Close', '关闭'):
        btns = dlg.find_elements(By.CSS_SELECTOR, "button[aria-label='%s']" % label)
        if btns:
            base.js_click(drv, btns[0])
            time.sleep(1.5)
            print('DRAWER_CLOSED', label)
            return True
    drv.find_element(By.TAG_NAME, 'body').send_keys('')  # ESC
    time.sleep(1.5)
    print('DRAWER_ESC')
    return False


def review_scope(drv):
    """复核步骤的作用域：优先含「复核」文案的可见 dialog，否则整页 body。"""
    for d in reversed(drv.find_elements(By.CSS_SELECTOR, "[role='dialog']")):
        try:
            if d.is_displayed() and '复核' in (base.text_of(drv, d) or ''):
                return d
        except Exception:
            pass
    return drv


def wait_ready(drv, scope, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if scope.find_elements(By.CSS_SELECTOR, "button[aria-label='展开']"):
                time.sleep(1.5)
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def review_shots(drv, mode):
    """复核步骤：review-step.tsx 复用同一 CartPanel（同一 store / 同一树）→ 组头应同为真名。"""
    try:
        base.click_text(drv, '去复核', limit=True)
        time.sleep(4)
        close_drawer(drv)
        time.sleep(1)
        scope = review_scope(drv)
        print('REVIEW_SCOPE', 'dialog' if scope is not drv else 'body')
        wait_ready(drv, scope)
        expand_nodes(drv, 'task', 2, scope)
        assert_real_headers(drv, 'review_task_case', scope=scope)
        shot(drv, '%s_review_task_case' % mode)
        click_exact(drv, '用例视图', required=False, scope=scope)
        time.sleep(2)
        assert_real_headers(drv, 'review_case', scope=scope)
        shot(drv, '%s_review_case' % mode)
    except Exception as exc:
        FAILS.append('复核步骤取证失败：%s' % exc)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'light'
    d = base.make_driver()
    try:
        base.login(d)
        base.clear_cart()  # 先用空购物车起跑（可能有其他 run 残留）
        d.get(base.BASE + '/tasks/cherry-pick')
        time.sleep(2)
        base.set_theme(d, 'dark' if mode == 'dark' else 'light')
        base.open_pick(d)
        labels = wait_task_rows(d)
        select_tasks(d, labels)
        base.click_text(d, '下一步', limit=True)
        WebDriverWait(d, 240).until(
            lambda x: len(x.find_elements(By.CSS_SELECTOR, '.animate-pulse')) == 0
        )
        time.sleep(3)
        base.add_to_cart(d)
        base.open_cart(d)
        wait_tree(d)
        network_evidence(d, mode)
        cart_shots(d, mode)
        if os.environ.get('INT1840_REVIEW', '1') == '1':
            review_shots(d, mode)
        if FAILS:
            raise RuntimeError('；'.join(FAILS))
        print('OK', mode)
    finally:
        d.quit()
        base.clear_cart()


if __name__ == '__main__':
    main()
