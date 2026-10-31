# -*- coding: utf-8 -*-
"""INT-2174 走查补充：批量改标签后列表/标签计数联动刷新（卡面覆盖项 11 的标签计数分支）。

流程：API 建分组+2 用例+标签 → UI 勾选 2 条 → 批量管理标签加标签 →
列表行标签角标出现（列表刷新）+ 切「按标签」视图该标签卡计数=2（标签计数刷新）→
API GET /testcases 回读两条用例 tags 含该标签。夹具按唯一前缀清理。

用法：python verify_int2174_sync_tags.py --run st-a
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

import _int2174_lib as L
import _int2174_ui as U
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

RESULTS = []
RUN = 'st-a'
PREFIX = f'{L.PREFIX}{RUN}_'
CLEAN = {'cases': [], 'groups': [], 'tags': []}


def record(item, name, ok, detail, evidence=None):
    RESULTS.append({'item': item, 'check': name, 'pass': bool(ok), 'detail': detail, 'evidence': evidence})
    print(('[PASS] ' if ok else '[FAIL] ') + f'{item} {name} :: {detail}')
    return ok


def load_more_until(drv, needle, max_clicks=8):
    for _ in range(max_clicks):
        if needle in U.body(drv):
            return True
        btns = drv.find_elements(By.XPATH, "//button[contains(., '加载更多')]")
        if not btns:
            break
        U.js_click(drv, btns[0])
        time.sleep(1.4)
    return needle in U.body(drv)


def cleanup(tok):
    st, d = L.list_cases(tok, keyword=PREFIX, include_deleted='true')
    for i in d.get('items') or []:
        if (i.get('name') or '').startswith(PREFIX):
            L.delete_case_hard(tok, i['id'])
    for g in L.list_groups(tok):
        if (g.get('name') or '').startswith(PREFIX):
            L.delete_group(tok, g['id'])
    for t in L.list_tags(tok):
        if (t.get('name') or '').startswith(PREFIX):
            L.delete_tag(tok, t['id'])
    st, d = L.list_cases(tok, keyword=PREFIX, include_deleted='true')
    return [i['name'] for i in d.get('items') or [] if (i.get('name') or '').startswith(PREFIX)]


def main():
    global RUN, PREFIX
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='st-a')
    args = ap.parse_args()
    RUN = args.run
    PREFIX = f'{L.PREFIX}{RUN}_'
    os.makedirs(U.ARTIFACTS, exist_ok=True)
    tok, err = L.login()
    assert tok, err
    st, r = L.req('GET', 'http://localhost:15000/health')
    print('[health:start]', st, (r or {}).get('database'))

    gname = PREFIX + '分组'
    tag = PREFIX + '标签'
    gid = L.create_group(tok, gname)
    L.create_tag(tok, tag, '#8b5cf6')
    a = L.find_audio(tok)[0]
    for suffix in ('同步A', '同步B'):
        CLEAN['cases'].append(L.create_case(tok, PREFIX + suffix, group_id=gid,
                                            config=L.case_config(a['id'], a['name'])))
    time.sleep(1.0)

    drv = U.make_driver()
    try:
        U.login(drv)
        U.goto(drv, '/testcases/by-group')
        U.wait_text(drv, '用例管理', 60)
        WebDriverWait(drv, 60).until(lambda d: '个分组' in U.body(d))
        load_more_until(drv, gname)
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), PREFIX + '同步')
        U.wait_text(drv, '命中', 30)
        time.sleep(1.6)
        hdr = U.find_xpath(drv, f"//span[normalize-space(.)='{gname}']/ancestor::div[contains(@class,'cursor-pointer')][1]")
        if not drv.find_elements(By.XPATH, f"//*[@role='checkbox'][@aria-label='选择 {PREFIX}同步A']"):
            U.js_click(drv, hdr)
            time.sleep(1.2)
        for nm in (PREFIX + '同步A', PREFIX + '同步B'):
            cb = U.find_xpath(drv, f"//*[@role='checkbox'][@aria-label='选择 {nm}']", timeout=15)
            if cb.get_attribute('aria-checked') != 'true':
                U.js_click(drv, cb)
            time.sleep(0.3)
        U.wait_text(drv, '已选择 2', 15)
        U.click_xpath(drv, "//button[contains(., '批量管理标签')]")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量管理标签')]"))
        U.click_xpath(drv, f"//*[@role='dialog'][contains(., '批量管理标签')]//button[normalize-space(.)='{tag}']")
        time.sleep(0.5)
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量管理标签')]//button[normalize-space(.)='确定']")
        U.wait_text(drv, '批量操作执行成功', 30)
        time.sleep(2.0)
        # 列表行标签角标（列表刷新）
        body = U.body(drv)
        badge_ok = body.count(tag) >= 2
        U.shot(drv, '30-batch-tags-list-light.png')
        # 按标签视图：该标签卡计数=2
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
        time.sleep(1.0)
        U.click_xpath(drv, "//button[@role='tab' and contains(., '按标签')]")
        U.wait_text(drv, '个标签', 30)
        load_more_until(drv, tag)
        U.js_click(drv, U.find_xpath(drv, f"//span[normalize-space(.)='{tag}']/ancestor::div[contains(@class,'cursor-pointer')][1]", timeout=10))
        time.sleep(1.2)
        tag_card_text = U.find_xpath(drv, f"//span[normalize-space(.)='{tag}']/ancestor::div[contains(@class,'cursor-pointer')][1]").text
        tagcount_ok = '2 条' in tag_card_text
        U.shot(drv, '31-tag-view-count-light.png')
        # API 回读
        st, dl = L.list_cases(tok, keyword=PREFIX + '同步')
        tags_ok = all(any((t.get('name') if isinstance(t, dict) else t) == tag for t in (i.get('tags') or []))
                      for i in dl.get('items') or [])
        record(11, '批量改标签后列表角标 + 标签视图计数 + API 回读一致',
               badge_ok and tagcount_ok and tags_ok and (dl.get('total') == 2),
               f'列表行角标出现={badge_ok} 标签卡「{tag_card_text!r}」计数2条={tagcount_ok} '
               f'GET /testcases 回读 tags 全含={tags_ok} total={dl.get("total")}')
        # 深色补一张标签视图
        U.set_theme(drv, True)
        U.goto(drv, '/testcases/by-group')
        U.wait_text(drv, '用例管理', 60)
        U.click_xpath(drv, "//button[@role='tab' and contains(., '按标签')]")
        U.wait_text(drv, '个标签', 30)
        load_more_until(drv, tag)
        U.shot(drv, '32-tag-view-count-dark.png')
        U.set_theme(drv, False)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        left = cleanup(tok)
        record('cleanup', '夹具清理干净', not left, json.dumps(left, ensure_ascii=False))
        st, r = L.req('GET', 'http://localhost:15000/health')
        print('[health:end]', st, (r or {}).get('database'))

    passed = sum(1 for r in RESULTS if r['pass'])
    with open(os.path.join(U.ARTIFACTS, 'report_sync_tags.json'), 'w', encoding='utf-8') as f:
        json.dump({'run': RUN, 'passed': passed, 'total': len(RESULTS), 'results': RESULTS}, f,
                  ensure_ascii=False, indent=2)
    print(f'==== {passed}/{len(RESULTS)} passed ====')


if __name__ == '__main__':
    main()
