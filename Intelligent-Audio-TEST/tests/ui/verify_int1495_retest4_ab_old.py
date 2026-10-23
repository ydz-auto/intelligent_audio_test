# -*- coding: utf-8 -*-
"""INT-1495 复测第 4 轮 A/B 对照——同一脚本逻辑跑「打回前的旧交付构建」，证明用例有区分力。

旧构建 = 7a9ca92e（打回前，agent/react-b/int-1495-29f26913183c），旁路容器 15499。
预期旧构建上：P2-A 非 2xx 删除仍弹「实验室已删除」；P3-b 播放测试失败后「测试中」徽章残留。
本脚本只观测并打印，不判 PASS/FAIL；数据同样只写「接线测试_INT1495V4AB_」前缀并清理。
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('v4', os.path.join(HERE, 'verify_int1495_retest4.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

m.BASE = os.environ.get('AB_BASE', 'http://127.0.0.1:15499')
m.ARTIFACTS = os.path.join(HERE, 'artifacts', 'int1495_v4_ab_old')
LAB_NAME = '接线测试_INT1495V4AB_假成功'
LAB_CODE = 'JX1495V4AB'


def main():
    os.makedirs(m.ARTIFACTS, exist_ok=True)
    drv = m._driver()
    try:
        m._goto(drv, '/devices/test')
        m._wait_text(drv, '设备管理', 40)
        print('served:', drv.execute_script('return document.title'))
        m._purge(drv, LAB_CODE)
        st, d = m._create_lab(drv, LAB_NAME, LAB_CODE, '701')
        print('create lab', st, str(d)[:120])
        _, labs = m._labs(drv)
        lab = next((x for x in labs if x.get('code') == LAB_CODE), None)
        if not lab:
            print('NO LAB — abort')
            return 1
        m._goto(drv, '/devices/test')
        m._wait_text(drv, '设备管理', 40)
        m._open_lab_dialog(drv)
        m._wait_text(drv, LAB_NAME, 40)
        st, _ = m._api(drv, f"/api/v1/laboratories/{lab['id']}", 'DELETE')
        print('behind-UI delete status', st)
        m._wait_no_toast(drv)
        m._clear_reqlog(drv)
        m._js_click(drv, drv.find_element('xpath', f"//button[@aria-label='删除实验室 {LAB_NAME}']"))
        m._wait_text(drv, '删除实验室', 15)
        time.sleep(1.2)
        m._alert_click(drv, '删除')
        toasts = m._toasts(drv)
        net = [r for r in m._reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
        print('OLD P2-A toasts:', toasts)
        print('OLD P2-A DELETE:', net)
        print('OLD P2-A alert still open:', m._alert_open(drv))
        m._shot(drv, 'old_p2a_false_success')

        # P3-b：旧构建播放测试失败后占用徽章应残留
        m._synth(drv, forceOnline=True)
        m._goto(drv, '/devices/playback')
        m._wait_text(drv, '设备管理', 40)
        buttons = m._row_buttons(drv)
        print('playback rows', len(buttons))
        if buttons:
            m._js_click(drv, buttons[0])
            item = m._menu_item(drv, '播放测试')
            m._wait_no_toast(drv)
            m._clear_reqlog(drv)
            m._js_click(drv, item)
            time.sleep(1.5)
            toasts = m._toasts(drv, timeout=20)
            net = [r for r in m._reqlog(drv) if r['method'] == 'POST' and '/playback-devices/' in r['url']]
            print('OLD P3-b toasts:', toasts)
            print('OLD P3-b POST:', net)
            time.sleep(3.0)
            left = m._testing_badges(drv)
            print('OLD P3-b 测试中徽章数（失败后立刻）:', len(left))
            left2 = m._badges_after_refetch(drv)
            print('OLD P3-b 测试中徽章数（过 staleTime 重取列表后）:', len(left2))
            m._shot(drv, 'old_p3b_occupied_stuck')
        m._purge(drv, LAB_CODE)
        _, labs = m._labs(drv)
        print('left V4AB labs:', [x.get('code') for x in labs if 'V4AB' in str(x.get('code'))])
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
