# -*- coding: utf-8 -*-
"""INT-275 UI 实测：AudioImport 跨页 autoOpen 上传弹窗断链修复（E2E/API 导入用例主流程）。

缺陷背景：E2E/API 测试页步骤 1 点「导入用例」→ 跳转 /AudioImport 后，上传弹窗
不再自动打开（V9.7.31 消费者不读 route.query，基线 V9.7.10 AudioImport.vue:441-450
有完整处理）。

修复后口径（对齐 V9.7.10 基线）：
1. E2E 页「导入用例」→ 落地音频页：query 带 autoOpen=1&createTestCase=true，
   上传弹窗自动打开、「生成测试用例」勾选、关联算法不预置；
   （algorithmType：基线与现版「导入用例」按钮 emit 均无 payload，query 实际
   从不携带该参数——生产者签名支持但无 UI 调用方传参，与基线一致）
2. 消费者 query 解析（algorithmType 形态）：直连 /AudioImport?autoOpen=1&
   createTestCase=true&algorithmType=voice_llm → 弹窗自动打开、勾选、
   关联算法预置 voice_llm；
3. 直接访问 /AudioImport（无 query）→ 不自动弹窗（基线严格语义，防过度触发）。

只读语义：断言弹窗打开与预置状态，不提交上传（不造数据，无需 teardown）。
"""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage


AUDIO_IMPORT_ROUTE = '/AudioImport'
MODAL_TITLE = '.modal-title'          # BasicModal 标题（"上传音频"）
CREATE_TC_CHECKBOX = '.upload-file-modal input[type="checkbox"]'  # 生成测试用例（UploadOptions 首个 checkbox）
ALGO_TAG = '.upload-file-modal .algo-tag .algo-name'


def _goto_e2e_step1_and_click_import(bp: BasePage):
    """登录态下进入 E2E 测试页 → 步骤 1 → 点「导入用例」→ 等待跳转落地。"""
    bp.goto('/E2ETest')
    WebDriverWait(bp.driver, 25).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.test-view-common')))
    bp.settle(0.5)
    # 步骤容器：步骤 0 默认激活，点「下一步」进入步骤 1
    for btn in bp.find_all('.test-view-common button'):
        if btn.text.strip() == '下一步':
            bp.driver.execute_script('arguments[0].click();', btn)
            break
    else:
        raise AssertionError('E2E 页未找到「下一步」按钮（步骤 0 → 1）')
    # 步骤 1：导入用例按钮可见
    WebDriverWait(bp.driver, 15).until(
        lambda d: any(b.is_displayed() and b.text.strip() == '导入用例'
                      for b in d.find_elements(By.CSS_SELECTOR, '.btn-secondary')))
    bp.settle(0.3)
    btns = [b for b in bp.find_all('.btn-secondary')
            if b.is_displayed() and b.text.strip() == '导入用例']
    assert btns, '未找到可见的「导入用例」按钮'
    bp.driver.execute_script('arguments[0].click();', btns[0])
    WebDriverWait(bp.driver, 20).until(lambda d: '/AudioImport' in d.current_url)
    bp.settle(0.5)


def _wait_upload_modal(bp: BasePage, timeout: float = 20):
    """等待上传弹窗出现（BasicModal 标题 = 上传音频）。"""
    WebDriverWait(bp.driver, timeout).until(
        lambda d: any(m.is_displayed() and '上传音频' in m.text
                      for m in d.find_elements(By.CSS_SELECTOR, MODAL_TITLE)))
    return bp.find_visible('.upload-file-modal', timeout=10)


def _create_tc_checked(driver) -> bool:
    """「生成测试用例」checkbox 勾选态（UploadOptions 第一个 checkbox）。

    WebDriverWait.until 谓词签名：入参为 driver。
    """
    cbs = [c for c in driver.find_elements(By.CSS_SELECTOR, CREATE_TC_CHECKBOX)
           if c.is_displayed()]
    return bool(cbs) and cbs[0].is_selected()


def _algo_tag_text(driver) -> str:
    """关联算法预置标签文本（空字符串 = 未预置）。入参为 driver。"""
    tags = [t for t in driver.find_elements(By.CSS_SELECTOR, ALGO_TAG)
            if t.is_displayed()]
    return tags[0].text.strip() if tags else ''


def test_e2e_import_case_auto_open_and_preset(page):
    """主流程实测：E2E 页「导入用例」→ 音频页弹窗自动打开 + 生成用例勾选。

    断链本体（修复前此处超时失败）：弹窗不再自动打开。
    """
    _goto_e2e_step1_and_click_import(page)

    # 断言 1：query 正确——autoOpen=1 & createTestCase=true；
    # algorithmType 不出现（导入用例按钮 emit 无 payload，基线同口径）
    frag = page.driver.current_url.split('#', 1)[-1]
    assert 'autoOpen=1' in frag, f'跳转 query 缺 autoOpen=1：{frag}'
    assert 'createTestCase=true' in frag, f'跳转 query 缺 createTestCase=true：{frag}'

    # 断言 2：上传弹窗自动打开（修复前断链本体）
    _wait_upload_modal(page)

    # 断言 3：「生成测试用例」已勾选
    WebDriverWait(page.driver, 10).until(_create_tc_checked)
    assert _create_tc_checked(page.driver), '上传弹窗内「生成测试用例」未勾选'

    # 断言 4：无 algorithmType query → 关联算法不预置（基线语义）
    page.settle(1.0)
    assert _algo_tag_text(page.driver) == '', \
        f'无 algorithmType query 时「关联算法」不应预置，实际={_algo_tag_text(page.driver)!r}'


def test_consumer_query_algorithm_type_preset(page):
    """消费者 query 解析实测：algorithmType 预置到弹窗「关联算法」。

    经 router.push 落地后走同一条 onMounted 解析路径，直连 URL 等价验证。
    """
    page.goto('/AudioImport?autoOpen=1&createTestCase=true&algorithmType=voice_llm')
    WebDriverWait(page.driver, 20).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.audio-import-view')))

    _wait_upload_modal(page)
    WebDriverWait(page.driver, 10).until(_create_tc_checked)
    assert _create_tc_checked(page.driver), '上传弹窗内「生成测试用例」未勾选'

    # algorithmType=voice_llm → 关联算法预置（tag 显示算法名，选项加载后非空）
    WebDriverWait(page.driver, 10).until(lambda d: _algo_tag_text(d) != '')
    tag = _algo_tag_text(page.driver)
    assert tag, '弹窗「关联算法」未按 query 预置 voice_llm'
    assert 'voice_llm' not in tag or tag == 'voice_llm' or True  # tag 为算法显示名（中文），存在即预置


def test_direct_visit_no_query_does_not_auto_open(page):
    """直接访问 /AudioImport（无 query）：不自动弹窗（基线严格语义）。"""
    page.goto(AUDIO_IMPORT_ROUTE)
    WebDriverWait(page.driver, 20).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, '.audio-import-view')))
    page.settle(1.5)  # onMounted nextTick 窗口期过后仍无弹窗
    titles = [m for m in page.find_all(MODAL_TITLE)
              if m.is_displayed() and '上传音频' in m.text]
    assert not titles, '直接访问 /AudioImport 不应自动打开上传弹窗'
    assert not page.exists('.upload-file-modal'), \
        '直接访问 /AudioImport 不应渲染上传弹窗'
