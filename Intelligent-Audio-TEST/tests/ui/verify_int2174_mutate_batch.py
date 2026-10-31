# -*- coding: utf-8 -*-
"""INT-2174 走查（React 用例域增量）—— 新建/编辑抽屉 + 批量设置 UI 实测。

覆盖卡面第 9（抽屉基础字段/标签/音频绑定/轮次/评估维度创建与编辑回读）、
10（批量设置设备/维度/噪声/声压=轮次范围批量写）项；两处写操作后均 GET 回读。

环境：前端 http://localhost:15173（容器 iat-react-frontend）、后端 http://localhost:15000。
夹具前缀「接线测试_走查R2_<run>_」，按落盘 id 与唯一前缀清理。

用法：python verify_int2174_mutate_batch.py --run mb-a
输出：tests/ui/artifacts/int2174_ui/report_mutate.json + *.png
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

RESULTS = []
CLEANUP = {'cases': [], 'groups': [], 'tags': []}
RUN = 'mb-a'
PREFIX = f'{L.PREFIX}{RUN}_'


def record(item, name, ok, detail, evidence=None):
    RESULTS.append({'item': item, 'check': name, 'pass': bool(ok), 'detail': detail, 'evidence': evidence})
    print(('[PASS] ' if ok else '[FAIL] ') + f'{item} {name} :: {detail}')
    return ok


def health(tag, token):
    st, r = L.req('GET', 'http://localhost:15000/health')
    db = (r or {}).get('database') if isinstance(r, dict) else None
    st2, d = L.req('GET', '/testcases?page=1&per_page=1', token=token)
    total = (L.data(d) or {}).get('total')
    print(f'[health:{tag}] status={st} database={db} total={total}')
    return {'tag': tag, 'status': st, 'database': db, 'total': total}


def cleanup(token):
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    for i in d.get('items') or []:
        if (i.get('name') or '').startswith(PREFIX) and i['id'] not in CLEANUP['cases']:
            CLEANUP['cases'].append(i['id'])
    for cid in CLEANUP['cases']:
        try:
            L.delete_case_hard(token, cid)
        except Exception as e:
            print('case cleanup warn', cid, e)
    for gid in CLEANUP['groups']:
        try:
            L.delete_group(token, gid)
        except Exception as e:
            print('group cleanup warn', gid, e)
    for tid in CLEANUP['tags']:
        try:
            L.delete_tag(token, tid)
        except Exception as e:
            print('tag cleanup warn', tid, e)
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    left = [i['name'] for i in d.get('items') or [] if (i.get('name') or '').startswith(PREFIX)]
    groups_left = [g['name'] for g in L.list_groups(token) if (g.get('name') or '').startswith(PREFIX)]
    return {'cases': left, 'groups': groups_left}


def open_cases(drv):
    U.goto(drv, '/testcases/by-group')
    U.wait_text(drv, '用例管理', 60)
    WebDriverWait(drv, 60).until(lambda d: '个分组' in U.body(d))


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


def select_group(drv, name, trigger_placeholder='请选择分组'):
    trig = U.find_xpath(drv, "//button[contains(., '%s')]" % trigger_placeholder, timeout=10)
    U.js_click(drv, trig)
    opt = U.find_xpath(drv, f"//*[@role='option'][contains(., '{name}')]", timeout=10)
    U.js_click(drv, opt)
    time.sleep(0.5)


def row_visible(drv, keyword):
    return bool(drv.find_elements(By.XPATH, f"//*[@role='checkbox'][contains(@aria-label,'{keyword}')]"))


def ensure_row_visible(drv, keyword, group_name):
    U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), keyword)
    try:
        U.wait_text(drv, '命中', timeout=30)
    except Exception:
        print('ensure_row_visible: 未出现命中汇总，body 片段=', U.body(drv)[:300].replace('\n', ' '))
    time.sleep(1.8)
    hdr = U.find_xpath(drv, f"//span[normalize-space(.)='{group_name}']/ancestor::div[contains(@class,'cursor-pointer')][1]")
    if not row_visible(drv, keyword):
        U.js_click(drv, hdr)
        for _ in range(10):
            time.sleep(0.6)
            if row_visible(drv, keyword):
                break
    if not row_visible(drv, keyword):
        print('ensure_row_visible: 行仍不可见', keyword, U.body(drv)[:300].replace('\n', ' '))


def clear_search(drv):
    U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
    time.sleep(1.5)


def select_cases(drv, names):
    """确保勾选目标用例（已勾选的不再点，避免反选）。"""
    for nm in names:
        cb = U.find_xpath(drv, f"//*[@role='checkbox'][@aria-label='选择 {nm}']", timeout=15)
        if cb.get_attribute('aria-checked') != 'true':
            U.js_click(drv, cb)
        time.sleep(0.3)
    U.wait_text(drv, f'已选择 {len(names)}', timeout=15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='mb-a')
    args = ap.parse_args()
    global RUN, PREFIX
    RUN = args.run
    PREFIX = f'{L.PREFIX}{RUN}_'
    os.makedirs(U.ARTIFACTS, exist_ok=True)

    tok, err = L.login()
    assert tok, err
    health_checks = [health('start', tok)]

    # ---------------- 夹具 ----------------
    gname = PREFIX + '抽屉组'
    gid = L.create_group(tok, gname)
    CLEANUP['groups'].append(gid)
    tagname = PREFIX + '标签'
    tid = L.create_tag(tok, tagname, '#10b981')
    CLEANUP['tags'].append(tid)
    audios = L.find_audio(tok)
    audio = next((a for a in audios if 'INT2052' in (a.get('name') or '')), audios[0])
    st, r = L.req('GET', '/evaluation/dimensions?page=1&per_page=1', token=tok)
    dim_item = ((L.data(r) or {}).get('items') or [{}])[0]
    dim_id, dim_name = dim_item.get('id'), dim_item.get('name')
    st, r = L.req('GET', '/playback-devices/speaker-groups', token=tok)
    speaker_groups = L.data(r) or []
    base_sg = speaker_groups[0] if speaker_groups else None
    target_sg = speaker_groups[1] if len(speaker_groups) > 1 else None
    sg_id = target_sg['id'] if target_sg else (base_sg['id'] if base_sg else None)
    sg_name = target_sg['name'] if target_sg else (base_sg['name'] if base_sg else None)

    def mkcase(suffix):
        cfg = L.case_config(audio['id'], audio['name'], dim_id, dim_name, rounds=1,
                            speaker_group_id=base_sg['id'] if base_sg else None)
        cfg['rounds'][0]['audios'][0]['spl'] = 65
        cid = L.create_case(tok, PREFIX + suffix, group_id=gid, config=cfg)
        CLEANUP['cases'].append(cid)
        return cid

    cA = mkcase('批量A')
    cB = mkcase('批量B')
    time.sleep(0.8)
    print('fixture', {'group': gname, 'audio': audio['id'], 'dim': [dim_id, dim_name],
                      'speaker': [sg_id, sg_name]})

    drv = U.make_driver()
    try:
        U.login(drv)
        open_cases(drv)
        load_more_until(drv, gname)

        # ---------------- 9 新建抽屉 ----------------
        U.click_xpath(drv, "(//button[normalize-space(.)='新增用例'])[1]")
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '新增测试用例')]"))
        new_name = PREFIX + '抽屉A'
        U.set_input(drv, U.find_xpath(drv, "//input[@id='case-name']"), new_name)
        select_group(drv, gname)
        tag_input = U.find_xpath(drv, "//input[@aria-label='标签']")
        tag_input.send_keys(tagname)
        tag_input.send_keys(Keys.ENTER)
        time.sleep(0.8)
        U.set_input(drv, U.find_xpath(drv, "//textarea[@id='case-desc']"), 'INT-2174 抽屉新建描述')
        # 音频：第 1 轮
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '新增测试用例')]//button[@role='tab' and contains(., '音频列表')]")
        time.sleep(0.5)
        U.click_xpath(drv, "//button[contains(., '从音频库选择')]")
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '选择音频文件')]"))
        U.set_input(drv, U.find_xpath(drv, "//*[@role='dialog'][contains(., '选择音频文件')]//input[@aria-label='搜索音频文件名或描述']"),
                    audio['name'])
        time.sleep(2.0)
        U.click_xpath(drv, f"//*[@role='dialog'][contains(., '选择音频文件')]//*[@aria-label='选择音频 {audio['name']}']", timeout=20)
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '选择音频文件')]//button[contains(., '确认选择')]")
        U.wait_text(drv, '已添加', timeout=20)
        time.sleep(0.5)
        # 轮次 +1（第 1 轮音频已落，新增第 2 轮）
        U.click_xpath(drv, "//button[normalize-space(.)='添加轮次']")
        time.sleep(0.6)
        # 评估维度：整体评估维度节（默认启用）
        try:
            sw = U.find_xpath(drv, "//*[@aria-label='启用整体评估']", timeout=5)
            if sw.get_attribute('aria-checked') in ('false', None):
                U.js_click(drv, sw)
                time.sleep(0.5)
        except Exception:
            pass
        U.click_xpath(drv, f"//button[@aria-pressed and contains(., '{dim_name}')]", timeout=20)
        time.sleep(0.5)
        U.shot(drv, '20-drawer-create-filled-light.png')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '新增测试用例')]//button[normalize-space(.)='保存']")
        U.wait_text(drv, '添加测试用例成功', timeout=30)
        WebDriverWait(drv, 20).until(lambda d: not d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '新增测试用例')]"))
        time.sleep(1.0)
        row = L.find_case_by_name(tok, new_name)
        if row:
            CLEANUP['cases'].append(row['id'])
        st, det = L.get_case(tok, row['id']) if row else (None, {})
        rounds = (det.get('config') or {}).get('rounds') or []
        audios_all = [a for rd in rounds for a in (rd.get('audios') or [])]
        dims = (det.get('config') or {}).get('dimensions') or det.get('dimensions') or []
        tags = [t.get('name') if isinstance(t, dict) else t for t in (det.get('tags') or [])]
        ok9 = (bool(row) and det.get('group_name') == gname
               and det.get('description') == 'INT-2174 抽屉新建描述'
               and tagname in tags and len(rounds) == 2
               and audios_all and audios_all[0].get('audio_id') == audio['id']
               and any(int(d.get('id', -1)) == int(dim_id) for d in dims))
        record(9, '新建抽屉：名称/分组/标签/描述/音频/轮次/维度保存并回读',
               ok9,
               f'GET /testcases/{row["id"] if row else "?"} group={det.get("group_name")} desc={det.get("description")} '
               f'tags={tags} rounds={len(rounds)} audios={json.dumps(audios_all, ensure_ascii=False)[:180]} '
               f'dimensions={json.dumps(dims, ensure_ascii=False)[:150]}',
               U.shot(drv, '21-drawer-created-list-light.png'))

        # 编辑：重开抽屉，校验回填 → 改名+描述 → 保存 → 回读
        edit_clicked = False
        for attempt in range(2):
            ensure_row_visible(drv, new_name, gname)
            btns = drv.find_elements(By.XPATH, "//button[@aria-label='编辑用例']")
            print('edit buttons:', len(btns), 'attempt', attempt + 1)
            if not btns:
                print('body snippet:', U.body(drv)[:500].replace('\n', ' '))
            if btns:
                U.js_click(drv, btns[0])
                edit_clicked = True
                break
            open_cases(drv)
            load_more_until(drv, gname)
        assert edit_clicked, '未找到编辑用例按钮'
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '编辑测试用例')]"))
        pref_name = U.find_xpath(drv, "//input[@id='case-name']").get_attribute('value')
        pref_desc = U.find_xpath(drv, "//textarea[@id='case-desc']").get_attribute('value')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '编辑测试用例')]//button[@role='tab' and contains(., '音频列表')]")
        time.sleep(1.0)
        body = U.find_xpath(drv, "//*[@role='dialog'][contains(., '编辑测试用例')]").text
        pref_ok = pref_name == new_name and pref_desc == 'INT-2174 抽屉新建描述' and tagname in body and audio['name'] in body
        record(9, '编辑抽屉：名称/描述/标签/音频回填一致',
               pref_ok,
               f'回填 name={pref_name!r} desc={pref_desc!r} 含标签={tagname in body} 含音频名={audio["name"] in body}',
               U.shot(drv, '22-drawer-edit-prefill-light.png'))
        new_name2 = new_name + '_改'
        U.set_input(drv, U.find_xpath(drv, "//input[@id='case-name']"), new_name2)
        U.set_input(drv, U.find_xpath(drv, "//textarea[@id='case-desc']"), 'INT-2174 抽屉编辑后描述')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '编辑测试用例')]//button[normalize-space(.)='保存']")
        U.wait_text(drv, '更新测试用例成功', timeout=30)
        time.sleep(1.5)
        st, det2 = L.get_case(tok, row['id'])
        record(9, '编辑抽屉：改名/描述保存后 GET 回读一致',
               det2.get('name') == new_name2 and det2.get('description') == 'INT-2174 抽屉编辑后描述',
               f'GET /testcases/{row["id"]} name={det2.get("name")} desc={det2.get("description")}',
               U.shot(drv, '23-drawer-edited-light.png'))

        # ---------------- 10 批量设置 ----------------
        ensure_row_visible(drv, PREFIX + '批量', gname)
        select_cases(drv, (PREFIX + '批量A', PREFIX + '批量B'))

        # (a) 设备（逻辑音箱）
        device_ok = False
        if sg_id is not None:
            U.click_xpath(drv, "//button[contains(., '批量设置播放设备')]")
            WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量设置逻辑音箱')]"))
            U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置逻辑音箱')]//button[contains(., '请选择逻辑音箱')]")
            U.click_xpath(drv, f"//*[@role='option'][contains(., '逻辑音箱') and contains(., '{sg_name}')]")
            time.sleep(0.5)
            U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置逻辑音箱')]//button[normalize-space(.)='确定']")
            U.wait_text(drv, '批量操作执行成功', timeout=30)
            time.sleep(1.5)
            dA = L.get_case(tok, cA)[1]
            rounds = (dA.get('config') or {}).get('rounds') or []
            sg = ((rounds[0].get('audios') if rounds else None) or [{}])[0].get('playback_speaker_group_id')
            device_ok = str(sg) == str(sg_id)
            record(10, '批量设置播放设备（逻辑音箱）→ 回读 round.audios[].playback_speaker_group_id',
                   device_ok,
                   f'POST /testcases/batch action=update_playback_devices；GET 回读 speaker_group_id={sg} 期望={sg_id}',
                   U.shot(drv, '24-batch-device-light.png'))
        else:
            record(10, '批量设置播放设备（逻辑音箱）', False, '环境无逻辑音箱可测', None)

        # (b) 评估维度
        ensure_row_visible(drv, PREFIX + '批量', gname)
        select_cases(drv, (PREFIX + '批量A', PREFIX + '批量B'))
        U.click_xpath(drv, "//button[contains(., '批量设置评估维度')]")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量设置评估维度')]"))
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置评估维度')]//button[@aria-pressed and contains(., '%s')]" % dim_name)
        time.sleep(0.5)
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置评估维度')]//button[normalize-space(.)='确定']")
        U.wait_text(drv, '批量操作执行成功', timeout=30)
        time.sleep(1.5)
        dB = L.get_case(tok, cA)[1]
        roundsB = (dB.get('config') or {}).get('rounds') or []
        dimsB = [d for rd in roundsB for d in ((rd.get('evaluation') or {}).get('dimensions') or [])]
        record(10, '批量设置评估维度 → 回读 rounds[].evaluation.dimensions',
               any(int(d.get('id', -1)) == int(dim_id) for d in dimsB),
               f'POST /testcases/batch action=update_dimensions；GET 回读 dimensions={json.dumps(dimsB, ensure_ascii=False)[:200]}',
               U.shot(drv, '25-batch-dimensions-light.png'))

        # (c) 声压（轮次范围=所有轮次，批量写）
        ensure_row_visible(drv, PREFIX + '批量', gname)
        select_cases(drv, (PREFIX + '批量A', PREFIX + '批量B'))
        U.click_xpath(drv, "//button[contains(., '批量设置声压')]")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量设置声压级')]"))
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='声压级 dB']"), '77')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置声压级')]//button[normalize-space(.)='确定']")
        U.wait_text(drv, '批量操作执行成功', timeout=30)
        time.sleep(1.5)
        dC = L.get_case(tok, cA)[1]
        rounds = (dC.get('config') or {}).get('rounds') or []
        spls = [a.get('spl') for rd in rounds for a in (rd.get('audios') or [])]
        record(10, '批量设置声压（所有轮次）→ 回读 round.audios[].spl=77',
               bool(spls) and all(float(x or 0) == 77 for x in spls),
               f'POST /testcases/batch action=update_spl round_mode=all；GET 回读 spls={spls}',
               U.shot(drv, '26-batch-spl-light.png'))

        # (d) 噪声：环境 0 条噪声音频（GET /audios?audio_type=noise total=0），验证弹窗空态
        ensure_row_visible(drv, PREFIX + '批量', gname)
        U.click_xpath(drv, "//button[contains(., '批量设置噪声')]")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量设置噪声')]"))
        noise_dlg = U.find_xpath(drv, "//*[@role='dialog'][contains(., '批量设置噪声')]")
        noise_text = noise_dlg.text
        st_noise, r_noise = L.req('GET', '/audios?page=1&per_page=1&audio_type=noise', token=tok)
        noise_total = (L.data(r_noise) or {}).get('total')
        U.shot(drv, '27-batch-noise-empty-light.png')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '批量设置噪声')]//button[normalize-space(.)='取消']")
        record(10, '批量设置噪声：弹窗可开（环境噪声音频 0 条，仅验证空态，未提交）',
               noise_total == 0 and '噪声' in noise_text,
               f'GET /audios?audio_type=noise total={noise_total}；弹窗片段={noise_text.replace(chr(10), " | ")[:160]}',
               None)

        # ---------------- 深色截图（抽屉/批量弹窗同源） ----------------
        U.set_theme(drv, True)
        open_cases(drv)
        load_more_until(drv, gname)
        ensure_row_visible(drv, PREFIX + '批量', gname)
        U.click_xpath(drv, "(//button[@aria-label='编辑用例'])[1]")
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '编辑测试用例')]"))
        U.shot(drv, '28-drawer-edit-dark.png')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '编辑测试用例')]//button[normalize-space(.)='取消']")
        time.sleep(0.8)
        ensure_row_visible(drv, PREFIX + '批量', gname)
        select_cases(drv, (PREFIX + '批量A', PREFIX + '批量B'))
        U.click_xpath(drv, "//button[contains(., '批量设置播放设备')]")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量设置逻辑音箱')]"))
        U.shot(drv, '29-batch-device-dark.png')
        U.set_theme(drv, False)
        health_checks.append(health('before-delivery', tok))
    except Exception as e:
        import traceback
        traceback.print_exc()
        record('run', 'UI 实测异常中断', False, repr(e))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    leftover = cleanup(tok)
    record('cleanup', '本 run 夹具清理干净',
           not leftover['cases'] and not leftover['groups'], json.dumps(leftover, ensure_ascii=False))
    health_checks.append(health('after-cleanup', tok))

    passed = sum(1 for r in RESULTS if r['pass'])
    report = {'run': RUN, 'passed': passed, 'total': len(RESULTS), 'health': health_checks,
              'results': RESULTS, 'leftover': leftover}
    with open(os.path.join(U.ARTIFACTS, 'report_mutate.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n==== {passed}/{len(RESULTS)} passed ====')
    print(json.dumps(health_checks, ensure_ascii=False))


if __name__ == '__main__':
    main()
