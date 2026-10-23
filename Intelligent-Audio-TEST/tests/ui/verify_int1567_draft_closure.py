# -*- coding: utf-8 -*-
"""INT-1567 复走补测：算法编辑窗「存草稿 → 改名发布 → 关闭重开」界面闭环（INT-1514 修复上线后）。

覆盖卡内 7 项：
  1. 新建「接线测试_」算法 → 保存草稿（名称 A）→ 同弹窗改名 B 发布
  2. 关闭重开编辑：无「存在未发布的草稿」横幅，回显已发布值 B；GET 草稿为空
  3. 草稿残留反例：只存草稿不发布，重开仍恢复草稿 A
  4. 发布失败路径：名称留空 → 更新失败、草稿仍在、重开可继续编辑
  5. 删除 / 批量删除后草稿行清零（GET 草稿为空）
  6. 浅色 + 深色截图 + Network（发布 PUT / 后续 GET 草稿）
  7. 数据卫生：走应用删除路径清理 itest1483_v_*
"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

HERE = os.path.dirname(os.path.abspath(__file__))
H.ART = os.path.join(HERE, 'artifacts', 'int1567')
os.makedirs(H.ART, exist_ok=True)

TAG = 'V' + H.RUN_TAG
TYPE = f'itest1483_v_{TAG.lower()}'
NAME = f'接线测试_INT1567_{TAG}'
TYPE_B1 = TYPE + '_b1'
TYPE_B2 = TYPE + '_b2'
NAME_B1 = NAME + '_批1'
NAME_B2 = NAME + '_批2'
OUT = {'type': TYPE, 'name': NAME, 'run_tag': TAG}

d = None


def find(xp, t=25):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def body():
    return H.body_text(d)


def wtext(text, t=40):
    WebDriverWait(d, t).until(lambda x: text in body())


def ev():
    H.save_evidence('int1567_evidence', OUT)


def def_body(t, n, status='offline'):
    return {'type': t, 'name': n, 'group_id': None, 'display_order': 1, 'status': status,
            'description': 'INT-1567 草稿闭环复走', 'device_params': [], 'api_params': [],
            'case_params': [], 'reference_params': [],
            'mappings': {'device': [], 'api': [], 'evaluation': []},
            'associated_dimensions': []}


def create_algo(t, n):
    st, pay, raw = H.api_json(d, '/algorithm/definitions', 'POST', def_body(t, n))
    return {'status': st, 'type': (pay or {}).get('data', {}).get('type'), 'raw': raw[:200]}


def draft_get(t):
    st, pay, raw = H.api_json(d, f'/algorithm/definitions/draft/{t}')
    data = (pay or {}).get('data') if isinstance(pay, dict) else None
    if isinstance(data, dict) and 'definition' in data:
        data = data.get('definition')
    return {'status': st, 'empty': not bool(data),
            'name': (data or {}).get('name') if isinstance(data, dict) else None,
            'keys': sorted((data or {}).keys())[:8] if isinstance(data, dict) else None}


def set_name(value):
    el = WebDriverWait(d, 30).until(EC.presence_of_element_located((By.ID, 'algo-name')))
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    el.send_keys(u'', 'a')          # Ctrl+A（clear() 不触发 React onChange）
    el.send_keys(u'')               # Delete
    time.sleep(0.3)
    if value:
        el.send_keys(value)
    time.sleep(0.6)
    return el.get_attribute('value')


def click_btn(text, t=30):
    H.js_click(d, find(f"//button[contains(normalize-space(.), '{text}')]", t))


def open_edit(row_name):
    H.open_row_menu(d, row_name)
    H.click_menuitem(d, '编辑')
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1.2)


def close_edit():
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(1.0)
    if '有未保存的更改' in body():
        try:
            H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]", 10))
        except Exception:
            pass
        time.sleep(0.8)


def dialog_open():
    return '管理算法定义、参数与映射关系' in body()


def netlog(needle='/algorithm/definitions'):
    out = []
    for e in H.fetch_log(d, needle):
        item = {'method': e.get('method'), 'url': e.get('url'), 'status': e.get('status')}
        if e.get('reqBody'):
            try:
                rb = json.loads(e['reqBody'])
                item['req_body_name'] = rb.get('name') or (rb.get('definition') or {}).get('name')
                item['req_body_keys'] = sorted(rb.keys())[:10]
            except Exception:
                item['req_body_head'] = str(e['reqBody'])[:120]
        if e.get('resBody'):
            item['res_head'] = str(e['resBody'])[:200]
        out.append(item)
    return out


d = H.driver()
try:
    OUT['login_url'] = H.login(d)
    H.goto_page(d)

    # ---------------- Phase 1：新建 + 存草稿(A) + 改名发布(B) ----------------
    OUT['create'] = create_algo(TYPE, NAME)
    H.goto_page(d)
    open_edit(NAME)
    OUT['p1_edit_initial_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['p1_name_a'] = set_name(NAME + '_草稿态')
    click_btn('保存草稿')
    time.sleep(4)
    OUT['p1_draft_after_save'] = draft_get(TYPE)
    OUT['p1_toasts_after_save'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]

    OUT['p1_name_b'] = set_name(NAME + '_发布态')
    H.clear_fetch_log(d)
    click_btn('发布')
    WebDriverWait(d, 120).until(lambda x: not dialog_open())
    time.sleep(3)
    OUT['p1_publish_fetches'] = netlog()
    OUT['p1_draft_after_publish'] = draft_get(TYPE)
    OUT['p1_definition_after_publish'] = H.api_detail_summary(d, TYPE)
    ev()

    # ---------------- Phase 2：关闭重开编辑（无横幅、回显 B） ----------------
    d.refresh(); H.goto_page(d)
    H.clear_fetch_log(d)
    open_edit(NAME + '_发布态')
    OUT['p2_reopen_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['p2_banner_present'] = '存在未发布的草稿' in body()
    OUT['p2_dialog_text_head'] = body()[:400]
    OUT['p2_get_draft_fetches'] = netlog()
    H.shot(d, 'P2_reopen_after_publish_light')
    H.apply_theme(d, 'dark')
    OUT['p2_dark_html_class'] = d.execute_script('return document.documentElement.className')
    H.shot(d, 'P2_reopen_after_publish_dark')
    H.apply_theme(d, 'light')
    ev()

    # ---------------- Phase 3：草稿残留反例（只存草稿不发布） ----------------
    OUT['p3_name_a2'] = set_name(NAME + '_草稿态2')
    click_btn('保存草稿')
    time.sleep(4)
    OUT['p3_draft_after_save'] = draft_get(TYPE)
    close_edit()
    OUT['p3_dialog_closed'] = not dialog_open()
    d.refresh(); H.goto_page(d)
    open_edit(NAME + '_发布态')
    OUT['p3_reopen_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['p3_reopen_banner'] = '存在未发布的草稿' in body()
    H.shot(d, 'P3_draft_residue_reopen_light')
    ev()

    # ---------------- Phase 4：发布失败路径（名称留空） ----------------
    OUT['p4_set_empty'] = set_name('')
    H.clear_fetch_log(d)
    click_btn('发布')
    time.sleep(8)
    OUT['p4_dialog_still_open'] = dialog_open()
    OUT['p4_fetches'] = netlog()
    OUT['p4_toasts'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    OUT['p4_body_has_error'] = any(k in body() for k in ('不能为空', '请填写', '必填'))
    OUT['p4_draft_still_there'] = draft_get(TYPE)
    OUT['p4_name_after_fail'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    H.shot(d, 'P4_publish_fail_empty_name_light')
    # 重开可继续编辑
    if dialog_open():
        close_edit()
    d.refresh(); H.goto_page(d)
    open_edit(NAME + '_发布态')
    OUT['p4_reopen_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['p4_reopen_editable'] = d.find_element(By.ID, 'algo-name').is_enabled()
    close_edit()
    ev()

    # ---------------- Phase 5a：单条删除后草稿清零 ----------------
    H.goto_page(d)
    OUT['p5a_draft_before_delete'] = draft_get(TYPE)
    H.open_row_menu(d, NAME + '_发布态')
    H.clear_fetch_log(d)
    H.click_menuitem(d, '删除')
    try:
        WebDriverWait(d, 12).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")) > 0)
        time.sleep(1.2)   # ConfirmDialog 动画期点击会被吞
        H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]", 10))
    except Exception as e:
        OUT['p5a_confirm_err'] = str(e)[:200]
    H.wait_toast(d, 60)
    time.sleep(4)
    OUT['p5a_delete_fetches'] = netlog()
    OUT['p5a_draft_after_delete'] = draft_get(TYPE)
    OUT['p5a_definition_after_delete'] = H.api_detail_summary(d, TYPE)['status']
    H.goto_page(d)
    OUT['p5a_gone_from_list'] = NAME + '_发布态' not in body()
    H.shot(d, 'P5a_after_single_delete_light')
    ev()

    # ---------------- Phase 5b：批量删除后草稿清零 ----------------
    OUT['p5b_create'] = [create_algo(TYPE_B1, NAME_B1), create_algo(TYPE_B2, NAME_B2)]
    for t, n in ((TYPE_B1, NAME_B1), (TYPE_B2, NAME_B2)):
        st, _, _ = H.api_json(d, '/algorithm/definitions/draft', 'PUT',
                              {'algorithm_type': t, 'definition': def_body(t, n + '_草稿态')})
        OUT.setdefault('p5b_draft_put', []).append({'type': t, 'status': st})
    OUT['p5b_drafts_before'] = [draft_get(TYPE_B1), draft_get(TYPE_B2)]
    H.goto_page(d)
    for n in (NAME_B1, NAME_B2):
        row = d.find_element(By.XPATH, f"//tr[.//*[contains(normalize-space(.), '{n}')]]")
        cb = row.find_element(By.CSS_SELECTOR, "[role='checkbox'], input[type='checkbox']")
        H.js_click(d, cb)
        time.sleep(0.5)
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '批量删除')]"))
    time.sleep(1.2)
    OUT['p5b_confirm_text_ok'] = f'将删除已选择的 2 个算法' in body()
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]", 12))
    H.wait_toast(d, 60)
    time.sleep(5)
    OUT['p5b_bulk_fetches'] = netlog()
    OUT['p5b_drafts_after'] = [draft_get(TYPE_B1), draft_get(TYPE_B2)]
    try:
        OUT['p5b_definition_status_after'] = [H.api_detail_summary(d, TYPE_B1)['status'],
                                              H.api_detail_summary(d, TYPE_B2)['status']]
    except Exception as e:          # 浏览器会话抖动不应吞掉本条之外的证据
        OUT['p5b_definition_status_err'] = str(e)[:200]
    H.goto_page(d)
    OUT['p5b_gone_from_list'] = all(n not in body() for n in (NAME_B1, NAME_B2))
    H.shot(d, 'P5b_after_bulk_delete_light')
    ev()

finally:
    # ---------------- 数据卫生：应用删除路径清理本 run 记录 ----------------
    # 注：草稿没有独立 DELETE 路由（/definitions/draft/{type} 只 GET），删定义即连带清草稿（本卡 p5a/p5b 已验证）。
    try:
        for t in (TYPE, TYPE_B1, TYPE_B2):
            st2, _, _ = H.api_json(d, f'/algorithm/definitions/{t}', 'DELETE')
            OUT.setdefault('cleanup', []).append({'type': t, 'def_del': st2})
        OUT['cleanup_readback'] = {t: H.api_detail_summary(d, t)['status']
                                   for t in (TYPE, TYPE_B1, TYPE_B2)}
        OUT['cleanup_drafts'] = {t: draft_get(t)['empty'] for t in (TYPE, TYPE_B1, TYPE_B2)}
    except Exception as e:
        OUT['cleanup_error'] = str(e)[:300]
    ev()
    try:
        d.quit()
    except Exception:
        pass

print(json.dumps(OUT, ensure_ascii=False, indent=2))
