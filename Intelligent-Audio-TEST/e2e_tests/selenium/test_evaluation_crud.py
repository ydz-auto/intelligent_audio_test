# -*- coding: utf-8 -*-
"""
评估维度管理页 前端交互 → 后端 CRUD 接口 的 Selenium 端到端自动化测试

覆盖链路（全部通过浏览器 UI 操作，最终落到真实后端接口）：
- Create: 点击「新增维度」→ 填写表单 → 提交  → POST   /api/v1/evaluation/dimensions
- Read:   搜索框输入名称 → 列表渲染          → GET    /api/v1/evaluation/dimensions
- Update: 点击「编辑」→ 修改名称 → 保存       → PUT    /api/v1/evaluation/dimensions/{id}
- Delete: 点击「删除」→ 确认 → 删除           → DELETE /api/v1/evaluation/dimensions/{id}

运行环境：
- 前端: http://localhost:5173   (run_all.py 启动)
- 网关: http://localhost:5000   (AUTH_MODE=off 后端放行)
- 依赖: pip install selenium    (Chrome, Selenium Manager 自动匹配 driver)

运行: python test_evaluation_crud.py
"""
import json
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# 显式指定浏览器与驱动二进制，避免 Selenium Manager 联网下载导致卡死
CHROME_BINARY = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DRIVER_BINARY = r"D:\00_code\V9.7.31\Intelligent-Audio-TEST\e2e_tests\selenium\drivers\chromedriver-win32\chromedriver.exe"

FRONTEND_BASE = "http://localhost:5173"
BACKEND_BASE = "http://localhost:5000"
EVAL_PAGE = f"{FRONTEND_BASE}/#/Evaluation"
API_DIMENSIONS = f"{BACKEND_BASE}/api/v1/evaluation/dimensions"

RESULTS = []


def report(name: str, ok: bool, extra: str = "") -> bool:
    RESULTS.append((name, ok))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{('  |  ' + extra) if extra else ''}")
    return ok


class EvaluationCRUDTest:
    """评估维度 CRUD 端到端用例（独特名称避免污染既有数据）"""

    def __init__(self, unique: str):
        self.unique = unique
        self.unique_updated = f"{unique}_updated"
        options = Options()
        options.binary_location = CHROME_BINARY
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1600,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        service = Service(executable_path=DRIVER_BINARY)
        self.driver = webdriver.Chrome(options=options, service=service)
        self.wait = WebDriverWait(self.driver, 20)

    # ---------------- 公共工具 ----------------

    def _row_locator(self, name: str):
        return (
            By.XPATH,
            f"//tbody[@id='dimensionsTable']/tr"
            f"[.//span[contains(@class,'dimension-name-text') and normalize-space(.)='{name}']]",
        )

    def _get_row(self, name: str, timeout: int = 20):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located(self._row_locator(name))
        )

    def _row_exists(self, name: str) -> int:
        return len(self.driver.find_elements(*self._row_locator(name)))

    def _click_row_button(self, row, label: str, btn_class: str):
        btn = row.find_element(
            By.XPATH,
            f".//button[contains(@class,'{btn_class}') and contains(normalize-space(.),'{label}')]",
        )
        btn.click()

    def _fill_input(self, css: str, value: str):
        el = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css))
        )
        el.clear()
        el.click()
        el.send_keys(str(value))
        time.sleep(0.2)
        # headless 下偶发按键丢失 → 读回校验，不符则 JS 直写 + 派发 input 事件（Vue v-model 监听）
        if (el.get_attribute("value") or "") != str(value):
            self.driver.execute_script(
                "arguments[0].value = arguments[1]", el, str(value)
            )
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}))", el
            )
            time.sleep(0.2)

    def _wait_message(self, text: str, timeout: int = 20):
        el = WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-confirmMessage"))
        )
        return el.text, text in el.text

    def _confirm_and_close(self):
        """点击弹窗确认按钮（确定/删除），并等待所有弹窗消失"""
        btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".modal-confirmActions button.btn:last-child")
            )
        )
        btn.click()
        WebDriverWait(self.driver, 10).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".modal-overlay"))
        )

    def _backend_search(self, keyword: str) -> dict:
        url = f"{API_DIMENSIONS}?page=1&perPage=50&search={urllib.parse.quote(keyword)}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _backend_items(self, keyword: str) -> list:
        """后端响应结构: {success, data: {items: [...]}}，取值兜底列表"""
        data = self._backend_search(keyword)
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner.get("items") or []
        if isinstance(inner, list):
            return inner
        return []

    # ---------------- 用例 ----------------

    def test_page_load(self):
        self.driver.get(EVAL_PAGE)
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-input"))
        )
        time.sleep(1.5)  # 等待列表数据请求返回
        page_title = self.driver.find_element(By.CSS_SELECTOR, ".page-title").text
        report("前置: 评估维度管理页面加载", "评估维度" in page_title, page_title)

    def test_create(self):
        self.driver.find_element(
            By.XPATH,
            "//button[contains(@class,'btn-link') and contains(normalize-space(.),'新增维度')]",
        ).click()
        WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#field-name"))
        )
        self._fill_input("#field-name", self.unique)
        Select(self.driver.find_element(By.CSS_SELECTOR, "#field-type")).select_by_value("auto")
        Select(self.driver.find_element(By.CSS_SELECTOR, "#field-resultType")).select_by_value("1")
        for css, val in (
            ("#field-resultMin", "0"),
            ("#field-resultMax", "100"),
            ("#field-decimalPlaces", "2"),
            ("#field-weight", "6"),
            ("#field-estimatedExecTime", "5"),
        ):
            self._fill_input(css, val)

        self.driver.find_element(
            By.CSS_SELECTOR, ".crud-form-modal button[type='submit']"
        ).click()
        msg, ok = self._wait_message("评估维度添加成功")
        report("Create: 新增提交 → 成功弹窗", ok, msg)
        self._confirm_and_close()

    def test_read(self):
        self._fill_input(".search-input", self.unique)
        self._get_row(self.unique)
        items = self._backend_items(self.unique)
        ok = any((item.get("name") == self.unique) for item in items)
        report("Read: 列表/搜索渲染出新维度", ok, f"后端命中 {len(items)} 条")

    def test_update(self):
        row = self._get_row(self.unique)
        self._click_row_button(row, "编辑", "btn-primary")
        name_input = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#field-name"))
        )
        old_value = name_input.get_attribute("value") or ""
        self._fill_input("#field-name", self.unique_updated)
        self.driver.find_element(
            By.CSS_SELECTOR, ".crud-form-modal button[type='submit']"
        ).click()
        msg, ok = self._wait_message("评估维度更新成功")
        report("Update: 编辑保存 → 成功弹窗", ok, msg)
        report("Update: 编辑表单回填原名称", old_value == self.unique, old_value)
        self._confirm_and_close()

        self._fill_input(".search-input", self.unique_updated)
        self._get_row(self.unique_updated)
        report("Update: 列表显示更新后的名称", True, self.unique_updated)

    def test_delete(self, keep=False):
        row = self._get_row(self.unique_updated)
        self._click_row_button(row, "删除", "btn-danger")
        msg, ok = self._wait_message("确定要删除维度")
        report("Delete: 删除确认弹窗弹出", ok, msg)
        self._confirm_and_close()

        msg, ok = self._wait_message("维度已删除")
        report("Delete: 删除成功弹窗", ok, msg)
        self._confirm_and_close()

        # 删除成功 → 前端自动 fetchData 刷新列表，显式等待该行消失
        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(*self._row_locator(self.unique_updated))) == 0
            )
            remain = 0
        except TimeoutException:
            remain = self._row_exists(self.unique_updated)
        report("Delete: 列表不再显示该维度", remain == 0, f"剩余行 {remain}")

        items = self._backend_items(self.unique_updated)
        ok_backend = all(item.get("name") != self.unique_updated for item in items)
        report("Delete: 后端接口已不再返回该维度", ok_backend, f"后端命中 {len(items)} 条")

    def run(self):
        self.test_page_load()
        print("[TRACE] step: test_create")
        self.test_create()
        print("[TRACE] step: test_read")
        self.test_read()
        print("[TRACE] step: test_update")
        self.test_update()
        print("[TRACE] step: test_delete")
        self.test_delete()

    def cleanup(self):
        try:
            self.driver.quit()
        except Exception:
            pass


def main():
    unique = f"selenium_dim_{int(time.time())}"
    runner = EvaluationCRUDTest(unique)
    try:
        runner.run()
    except Exception as exc:  # noqa: BLE001 - 测试脚本需要兜底报告
        report("流程异常中止", False, f"{type(exc).__name__}: {exc}")
    finally:
        runner.cleanup()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in RESULTS if ok)
    failed = len(RESULTS) - passed
    print(f"用例结果: {passed} PASS / {failed} FAIL / 共 {len(RESULTS)} 项")
    for name, ok in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())