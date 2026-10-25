# -*- coding: utf-8 -*-
"""INT-1486 回归 M3-dark：任务命名弹窗深色截图（先置主题再整页导航，主题才生效）。"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402


def main():
    token = open(F.TOKEN_FILE).read().strip()
    d = F.make_driver(token)
    try:
        F.wait_step1(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(F.BASE + '/start-test')  # 重新导航让主题 provider 初始化时读到 dark
        F.wait_text(d, '按分组', 90)
        for _ in range(40):
            if d.find_elements(F.By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
                break
            time.sleep(2)
        time.sleep(2)
        print('DARK class =', d.execute_script(
            "return document.documentElement.classList.contains('dark')"))
        F.select_manual_cases(d, 1)
        F.next_step(d)
        F.pick_device(d)
        F.close_dialog(d)
        F.click_start(d)
        inp = F.taskname_input(d)
        print('dialog input =', inp.get_attribute('value') if inp else None)
        time.sleep(1)
        F.shot(d, 'M3_task_name_dark.png')
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
    finally:
        d.quit()


if __name__ == '__main__':
    main()
