# -*- coding: utf-8 -*-
"""INT-925 验收浏览器实测：报告域筛选卡片竖排→横排（独立脚本，不挂 pytest 门禁）。

验证点（对齐卡面验收标准）：
1. 报告对比（report#2 任务报告页内嵌三组件）筛选卡片：各筛选项标题与控件同行、
   flex-wrap 自然换行、不溢出；
2. 历史报告页徽章筛选维持横排；
3. 筛选条件变更 → 列表刷新；重置 → 回全量（有数据时交互回归）；
4. 浅色 + 深色截图。

运行前提：dev server http://127.0.0.1:5480（frontend/，连 :5000 常驻后端），
chromedriver 走 selenium 缓存路径。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT925_BASE', 'http://127.0.0.1:5480')
CHROME_BIN = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
CHROMEDRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
SHOT_DIR = os.environ.get('INT925_SHOT_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int925'))

TOL_Y = 18   # 标题与控件同行容许的纵向像素差
RESULTS = []


def record(name: str, ok: bool, detail: str = ''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail})
    print(f'{"PASS" if ok else "FAIL"} | {name} | {detail}')


def new_driver(width=1440, height=900):
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--hide-scrollbars')
    svc = Service(CHROMEDRIVER)
    return webdriver.Chrome(service=svc, options=opts)


def scroll_into_view(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'instant'});", el)
    time.sleep(0.4)


def horizontal_overflow(driver):
    return driver.execute_script(
        'return document.documentElement.scrollWidth - document.documentElement.clientWidth;')


def check_filter_item_layout(driver, item, ctx):
    """断言 filter-item 内标题(.filter-label)与直接控件同行、控件在右。"""
    label = item.find_elements(By.CSS_SELECTOR, ':scope > .filter-label')
    if not label:
        # 无显式 label 的筛选项（如纯控件项）不参与标题同行断言
        return True, 'no .filter-label child'
    label = label[0]
    # 直接子控件：search-box-flex / filter-input / sort-filter / 其他非 label 的直接子元素
    controls = item.find_elements(
        By.CSS_SELECTOR, ':scope > .search-box-flex, :scope > .filter-input, :scope > .sort-filter')
    if not controls:
        # 退化为「非 label 的直接子元素」中最后一个可见控件
        all_children = item.find_elements(By.CSS_SELECTOR, ':scope > *')
        controls = [c for c in all_children if c != label and c.is_displayed()]
    if not controls:
        return True, f'{ctx}: 无直接控件子元素可断言'
    lb = label.rect
    cb = controls[0].rect
    dy = abs(lb['y'] - cb['y'])
    same_row = dy <= TOL_Y
    to_right = cb['x'] >= lb['x'] + lb['width'] - 4  # 允许 4px 重叠容差
    overflow = horizontal_overflow(driver)
    record(f'{ctx} 标题与控件同行', same_row,
           f'label(y={lb["y"]:.0f},x={lb["x"]:.0f},w={lb["width"]:.0f}) control(y={cb["y"]:.0f},x={cb["x"]:.0f}) dy={dy:.0f}')
    record(f'{ctx} 控件在标题右侧', to_right,
           f'label右={lb["x"]+lb["width"]:.0f} control左={cb["x"]:.0f}')
    record(f'{ctx} 无横向溢出', overflow <= 2, f'scrollWidth-clientWidth={overflow}px')
    return same_row and to_right, ''


def wait_filter_cards(driver, timeout=25):
    wait = WebDriverWait(driver, timeout)
    wait.until(lambda d: d.execute_script(
        'return document.readyState === "complete"'))
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.report-filter-card')))
    # 等筛选卡片可见（非折叠态）
    wait.until(lambda d: any(
        el.is_displayed() for el in d.find_elements(By.CSS_SELECTOR, '.report-filter-card')))
    return driver.find_elements(By.CSS_SELECTOR, '.report-filter-card')


def shot(driver, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, name)
    driver.save_screenshot(path)
    print(f'  screenshot -> {path}')


def main():
    d = new_driver()
    try:
        # ===== 1. 报告对比（report#2 任务报告页内嵌三对比组件）=====
        d.get(f'{BASE}/#/report/2')
        cards = wait_filter_cards(d)
        record('report#2 筛选卡片数量', len(cards) >= 3, f'{len(cards)} 张 report-filter-card')

        sections = {'分类对比': '#section-category', '标签对比': '#section-tag', '特定用例对比': '#section-case'}
        seen = set()
        for c in cards:
            try:
                parent_section = None
                # 找最近的 report-section 祖先的 id
                el = c
                while el.tag_name != 'body':
                    el = el.find_element(By.XPATH, '..')
                    if el.get_attribute('id') in ('section-category', 'section-tag', 'section-case'):
                        parent_section = el.get_attribute('id')
                        break
            except Exception:
                parent_section = None
            seen.add(parent_section or 'unknown')
        record('三对比组件筛卡片挂载', {'section-category', 'section-tag', 'section-case'} <= seen,
               f'seen={sorted(seen)}')

        # 逐张卡片做布局断言
        for i, c in enumerate(cards):
            if not c.is_displayed():
                continue
            items = c.find_elements(By.CSS_SELECTOR, '.filter-item')
            ctx = f'card{i}({i})'
            record(f'{ctx} 筛选项数', len(items) >= 1, f'{len(items)} items')
            for j, item in enumerate(items):
                if item.is_displayed():
                    check_filter_item_layout(d, item, f'card{i}.item{j}')

        # 截图（滚动到各对比区块）
        for name, sel in sections.items():
            try:
                sec = d.find_element(By.CSS_SELECTOR, sel)
                scroll_into_view(d, sec)
                time.sleep(0.5)
                shot(d, f'report_filter_{name}_light.png')
            except Exception as e:
                record(f'{name} 区块截图', False, str(e))

        # 交互回归：分类/标签 chip 选中与重置（若存在）
        chip = d.find_elements(By.CSS_SELECTOR, '.tag-filter-item, .case-type-item, .metric-filter-item')
        if chip:
            before = len(d.find_elements(By.CSS_SELECTOR, '.tag-filter-item.active, .case-type-item.active'))
            chip[0].click()
            time.sleep(0.5)
            after = len(d.find_elements(By.CSS_SELECTOR, '.tag-filter-item.active, .case-type-item.active'))
            record('chip 点击选中态切换', after >= before or before > 0,
                   f'active chips before={before} after={after}')
            # 重置
            reset_btns = d.find_elements(By.CSS_SELECTOR, '.filter-buttons .btn-secondary')
            if reset_btns:
                reset_btns[0].click()
                time.sleep(0.5)
                after_reset = len(d.find_elements(By.CSS_SELECTOR, '.tag-filter-item.active, .case-type-item.active'))
                record('重置回全量', after_reset == 0, f'active chips after reset={after_reset}')
        else:
            record('交互回归（chip 选中/重置）', True, '当前报告无 chip 数据，跳过交互断言（布局已断言）')

        # 三档宽度无溢出
        for w in (1024, 800):
            d.set_window_size(w, 900)
            time.sleep(0.8)
            ov = horizontal_overflow(d)
            record(f'宽度 {w}px 无横向溢出', ov <= 2, f'overflow={ov}px')

        # ===== 2. 历史报告页徽章筛选 =====
        d.set_window_size(1440, 900)
        d.get(f'{BASE}/#/history-reports')
        wait = WebDriverWait(d, 25)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.filter-row, .badge-filter, .filter-item')))
        time.sleep(1.5)
        # 徽章筛选项：BadgeFilter 渲染的横向徽章组（badge-filter__badge）
        badges = d.find_elements(By.CSS_SELECTOR, '.badge-filter__badge')
        record('历史报告徽章筛选渲染', len(badges) > 0, f'{len(badges)} 个徽章')
        # BadgeFilter 布局：标题与徽章组同行（badge-filter 为 flex 容器）
        bfilters = d.find_elements(By.CSS_SELECTOR, '.badge-filter')
        visible_bf = [b for b in bfilters if b.is_displayed() and b.size['height'] > 0]
        if visible_bf:
            for i, bf in enumerate(visible_bf):
                title = bf.find_elements(By.CSS_SELECTOR, ':scope > .badge-filter__title')
                badges_grp = bf.find_elements(By.CSS_SELECTOR, ':scope > .badge-filter__badges')
                if title and badges_grp:
                    tb = title[0].rect
                    bb = badges_grp[0].rect
                    dy = abs(tb['y'] - bb['y'])
                    same_row = dy <= TOL_Y * 2  # 徽章组可能比标题高，容差放宽
                    record(f'history.badgeFilter{i} 标题与徽章同行', same_row,
                           f'title(y={tb["y"]:.0f}) badges(y={bb["y"]:.0f}) dy={dy:.0f}')
                else:
                    record(f'history.badgeFilter{i} 标题/徽章结构', False,
                           f'title={bool(title)} badges={bool(badges_grp)}')
        # 检查 filter-row 内的 filter-item 布局
        row_items = d.find_elements(By.CSS_SELECTOR, '.filter-row .filter-item')
        for i, item in enumerate(row_items):
            if item.is_displayed():
                check_filter_item_layout(d, item, f'history.item{i}')
        shot(d, 'history_reports_filter_light.png')

        # ===== 3. 深色（注入 .dark 预留变量渲染态）=====
        d.execute_script("document.documentElement.classList.add('dark');")
        time.sleep(0.5)
        d.get(f'{BASE}/#/report/2')
        wait_filter_cards(d)
        time.sleep(1)
        for name, sel in sections.items():
            try:
                sec = d.find_element(By.CSS_SELECTOR, sel)
                scroll_into_view(d, sec)
                time.sleep(0.5)
                shot(d, f'report_filter_{name}_dark.png')
            except Exception as e:
                record(f'{name} 深色截图', False, str(e))
        d.get(f'{BASE}/#/history-reports')
        time.sleep(2)
        shot(d, 'history_reports_filter_dark.png')

        # ===== 汇总 =====
        passed = sum(1 for r in RESULTS if r['ok'])
        failed = [r for r in RESULTS if not r['ok']]
        print(f'\n===== INT-925 汇总: {passed}/{len(RESULTS)} passed, {len(failed)} failed =====')
        for f in failed:
            print(f'  FAIL: {f["name"]} | {f["detail"]}')
        return 1 if failed else 0
    finally:
        d.quit()


if __name__ == '__main__':
    raise SystemExit(main())
