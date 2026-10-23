# -*- coding: utf-8 -*-
"""INT-1596 A/B 对照：docker 15173（wiring/react 旧镜像，未含本卡修复）应复现两条缺陷。

用于证明本轮浏览器脚本的区分力：同一套操作在 15173 上应看到
- 模型行输入 `gd-4o` 只剩首字符 `g`、焦点丢失；
- 填好名称后「请输入供应商名称」红字仍挂着。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1596_provider_manager as v  # noqa: E402

v.BASE = 'http://127.0.0.1:15173'
v.RESULT = {}
v.FAILS = []


def main():
    d = v.make_driver()
    try:
        v.set_theme(d, 'light')
        v.clear_providers(d)
        v.open_manager_from_empty(d)
        v.open_add_form(d)

        v.save_form(d)
        v.wait_error(d, '请输入供应商名称')
        print('15173 blank_errors=%r' % v.error_texts(d))

        name = v.by_id(d, 'provider-name')
        v.type_into(d, name, '接线测试_AB供应商')
        time.sleep(0.8)
        after_name = v.error_texts(d)
        print('15173 after_name_errors=%r' % after_name)
        print('AB_15173_name_error_persists=%s' % ('请输入供应商名称' in after_name))

        inputs = v.add_model_rows(d, 1)
        v.type_into(d, inputs[0], 'gd-4o')
        time.sleep(0.6)
        # 旧实现每敲一个字符重建整行 input，原元素句柄会变 stale；重新取 DOM 看实际值
        fresh = v.model_inputs(d)
        val = fresh[0].get_attribute('value') if fresh else '<row missing>'
        print('AB_15173_model_value=%r' % val)
        focused = (
            d.execute_script('return document.activeElement === arguments[0];', fresh[0])
            if fresh else None
        )
        print('AB_15173_model_focused=%s' % focused)
        print('AB_15173_input_stale_after_typing=%s' % (val != 'gd-4o'))
        v.shot(d, '09_ab_15173_models_typed')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
