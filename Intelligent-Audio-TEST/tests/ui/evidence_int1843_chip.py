# -*- coding: utf-8 -*-
"""INT-1843 取证补图：放大截取带音乐图标的主维度 chip + 导出该 chip 的 outerHTML。

复用 walk_int1843_dimicon 的打开路径（列表→分组展开→编辑用例→评估维度步）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import walk_int1843_dimicon as W  # noqa: E402  (同一目录)
from selenium.webdriver.common.by import By

OUT = os.path.join(W.ART, 'int1843_evidence')
os.makedirs(OUT, exist_ok=True)


def main():
    d = W.L.driver()
    try:
        d.get(W.BASE + '/')
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")
        W.open_audio_step(d)
        time.sleep(2.5)
        icons = [e for e in d.find_elements(By.XPATH, "//*[@title='%s']" % W.ICON_TITLE) if e.is_displayed()]
        print('visible icons:', len(icons))
        shot_html = []
        picked = 0
        for ic in icons:
            if picked >= 2:
                break
            try:
                btn = ic.find_element(By.XPATH, './ancestor::button[1]')
                d.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
                time.sleep(0.4)
                p = os.path.join(OUT, 'chip-%d.png' % picked)
                btn.screenshot(p)
                shot_html.append({'png': os.path.basename(p), 'chip': btn.text.strip(), 'html': ic.get_attribute('outerHTML')})
                picked += 1
            except Exception as e:
                print('crop fail', e)
        # 整段分组云（含多枚图标）整屏
        d.save_screenshot(os.path.join(OUT, 'cloud-full.png'))
        with open(os.path.join(OUT, 'chips.json'), 'w', encoding='utf-8') as f:
            json.dump(shot_html, f, ensure_ascii=False, indent=2)
        print(json.dumps({'shots': [s['png'] for s in shot_html], 'chips': [s['chip'] for s in shot_html]}, ensure_ascii=False))
        print('evidence ->', OUT)
    finally:
        try:
            d.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
