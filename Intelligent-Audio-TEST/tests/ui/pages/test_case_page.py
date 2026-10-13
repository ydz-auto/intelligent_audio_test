# -*- coding: utf-8 -*-
"""用例管理页 Page Object：视图切换（分组/标签）、列表数据读取。"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base_page import BasePage


class TestCasePage(BasePage):
    # Page Object，非测试类：阻止 pytest 误收集（类名 Test* 前缀）
    __test__ = False

    ROUTE = '/TestCaseManager'

    PAGE_HEADER = '.test-case-manager .page-title'
    LIST_CONTAINER = '.test-case-list-container'
    VIEW_SWITCHER = '.test-case-list-container .view-switcher'
    GROUP_VIEW_BTN = ".view-switcher button[title='分组视图']"
    TAG_VIEW_BTN = ".view-switcher button[title='标签视图']"
    CATEGORY_CARDS = '.single-column-layout .category-card'
    CATEGORY_TITLE = '.category-card .category-title'
    CATEGORY_HEADER = '.category-card .category-header'
    CATEGORY_CONTENT = '.category-card .category-content'
    EXPAND_ICON = '.category-card .category-toggle'
    CASE_CARDS = '.category-card .case-card'
    CASE_NAME = '.case-card .case-name'
    EMPTY_STATE = '.single-column-layout .empty-state'

    def wait_loaded(self, timeout: float = 20):
        WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, self.LIST_CONTAINER)))
        return self

    def view_mode(self) -> str:
        """当前激活视图：'group' | 'tag'（按切换钮 active 态判定）。"""
        if 'active' in (self.find(self.TAG_VIEW_BTN).get_attribute('class') or ''):
            return 'tag'
        return 'group'

    def switch_view(self, mode: str):
        btn = self.TAG_VIEW_BTN if mode == 'tag' else self.GROUP_VIEW_BTN
        self.click(btn)
        WebDriverWait(self.driver, 15).until(
            lambda d: self.view_mode() == mode)
        self.settle(0.5)  # 列表数据渲染余量
        return self

    def _exhaust_load_more(self, max_clicks: int = 40):
        """点尽「加载更多」：分组/标签视图均分页懒加载（itemsPerPage=5，按计数
        排序），新自建分组（1 条用例）常在第 1 页之外——与用户行为一致地
        连点到加载完为止，保证读取覆盖全量类别。"""
        for _ in range(max_clicks):
            btns = self.find_all('.single-column-layout .load-more-trigger button')
            if not btns:
                return
            try:
                self.driver.execute_script('arguments[0].click();', btns[0])
            except Exception:
                return
            self.settle(0.6)

    def _read_categories(self) -> dict:
        """读取当前视图全部类别（分组名/标签名 → 卡片内用例名集合）。

        先点尽「加载更多」（分页懒加载），类别体按需展开（懒加载），逐个
        点击展开后读用例名；保持只读语义，不点任何会改数据的操作。
        """
        self._exhaust_load_more()
        result = {}
        cards = self.find_all(self.CATEGORY_CARDS)
        for card in cards:
            try:
                title = card.find_element(By.CSS_SELECTOR, '.category-title').text.strip()
            except Exception:
                continue
            expanded = card.find_elements(By.CSS_SELECTOR, '.category-content.expanded')
            if not expanded:
                try:
                    header = card.find_element(By.CSS_SELECTOR, '.category-header')
                    self.driver.execute_script('arguments[0].click();', header)
                except Exception:
                    result[title] = set()
                    continue
                try:
                    WebDriverWait(self.driver, 8).until(
                        lambda d, c=card: c.find_elements(By.CSS_SELECTOR, '.category-content.expanded'))
                except Exception:
                    pass
                self.settle(0.3)
            names = set()
            for name_el in card.find_elements(By.CSS_SELECTOR, self.CASE_NAME):
                # .case-name 内嵌 tooltip/类型徽章子元素，仅取首个文本节点
                try:
                    text = self.driver.execute_script(
                        'return arguments[0].childNodes.length '
                        '? arguments[0].childNodes[0].textContent : "";',
                        name_el,
                    ).strip()
                except Exception:
                    text = name_el.text.strip().split('\n')[0].strip()
                if text:
                    names.add(text)
            result[title] = names
        return result

    def categories(self) -> dict:
        return self._read_categories()

    def all_case_names(self) -> set:
        names = set()
        for cases in self._read_categories().values():
            names |= cases
        return names

    def has_empty_state(self) -> bool:
        return self.exists(self.EMPTY_STATE)
