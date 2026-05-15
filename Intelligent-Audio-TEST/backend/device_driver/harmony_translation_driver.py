import time
import subprocess
import os
from .base_driver import BaseDeviceDriver
from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from hypium.model import UiParam


class HarmonyXiaoyiTranslationDriver(HarmonyDriver):
    """鸿蒙 Next 专用驱动示例"""

    def initialize(self, device_id, **kwargs) -> bool:
        initialize_success = super().initialize(device_id, **kwargs)
        if not initialize_success:
            return False
        # 2. 尝试通过桌面图标启动 (使用用户提供的 Key)
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_id} for...")
        driver = self._get_driver(device_id)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_id}")
            return False
        # 3. 点击右上角“用户中心/头像”
        user_center = driver.find_component(By.description("用户中心")) or \
                      driver.find_component(By.type("Image"))
        if user_center:
            self._log(level='DEBUG', content="Clicking User Center...")
            user_center.click()
            time.sleep(2)

        # 4. 点击“设置”
        settings_btn = driver.find_component(By.text("设置"))
        if settings_btn:
            self._log(level='DEBUG', content="Clicking Settings...")
            settings_btn.click()
            time.sleep(2)

        # 5. 点击“小艺翻译”
        trans_setting = driver.find_component(By.text("小艺翻译"))
        if trans_setting:
            self._log(level='DEBUG', content="Clicking Celia Translation...")
            trans_setting.click()
            time.sleep(2)

        # 6. 检查并点击“启用”
        enable_btn = driver.find_component(By.text("启用小艺翻译"))
        if enable_btn:
            self._log(level='DEBUG', content="Enabling service...")
            enable_btn.click()
            time.sleep(1.5)

        # 7. 点击“小艺翻译助手”
        assistant_btn = driver.find_component(By.text("小艺翻译助手"))
        if assistant_btn:
            self._log(level='DEBUG', content="Entering Assistant...")
            assistant_btn.click()
            time.sleep(2)
            return True

        return False


class XiaoyiFace2FaceDriver(HarmonyXiaoyiTranslationDriver):
    def initialize(self, device_id, **kwargs) -> bool:
        initialize_success = super().initialize(device_id, **kwargs)
        if not initialize_success:
            return False
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_id} for...")
        driver = self._get_driver(device_id)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_id}")
            return False
        try:
            mode_text = '面对面翻译'
            mode_btn = driver.find_component(By.text(mode_text))
            if mode_btn:
                self._log(level='DEBUG', content=f"Clicking Mode...{mode_text}")
                mode_btn.click()
                time.sleep(1)
            self._log(level='INFO', content=f"Mode: {mode_text}")
            if driver.find_component(By.text('点击下方按钮说话')):
                self._log(level='INFO', content=f"成功打开面对面翻译")
                return True
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to get mode for device {device_id}: {e}")
            return False

    def pre_process(self, device_id, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_id)
        translation_direction = kwargs.get('translation_direction', 'zh2en')
        if 'en2zh' in translation_direction:
            driver.touch((939, 2624))
        elif 'zh2en' in translation_direction:
            driver.touch((336, 2624))
        self._log(level='INFO', content=f"成功进行面对面翻译pre_process步骤")

    def post_process(self, device_id, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_id)
        translation_direction = kwargs.get('translation_direction', 'zh2en')
        if 'en2zh' in translation_direction:
            driver.touch((939, 2624))
        elif 'zh2en' in translation_direction:
            driver.touch((336, 2624))
        self._log(level='INFO', content=f"成功进行面对面翻译post_process步骤")

    def get_results(self, device_id, **kwargs) -> dict:
        driver = self._get_driver(device_id)
        ori_text_list = driver.find_all_component(By.id("conv_item_input_text"))
        ori_text = '无内容'
        trans_text = '无内容'
        if len(ori_text_list) > 0:
            ori_text = ori_text_list[-1].getText()
        trans_text_list = driver.find_all_component(By.id("conv_item_translated_text"))
        if len(trans_text_list) > 0:
            trans_text = trans_text_list[-1].getText()
        self._log('成功抓取结果：ori_text={ori_text}, trans_text={trans_text}')
        return {'success': True, 'message': 'Success', 'asr': ori_text, 'translation': trans_text}


class XiaoyiSimultaneousInterpretationDriver(HarmonyXiaoyiTranslationDriver):
    def initialize(self, device_id, **kwargs) -> bool:
        initialize_success = super().initialize(device_id, **kwargs)
        if not initialize_success:
            return False
        self._log(level='INFO', content=f"Initializing HarmonyOS device {device_id} for...")
        driver = self._get_driver(device_id)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_id}")
            return False
        try:
            mode_text = '同声传译'
            mode_btn = driver.find_component(By.text(mode_text))
            if mode_btn:
                self._log(level='DEBUG', content=f"Clicking Mode...{mode_text}")
                mode_btn.click()
                time.sleep(1)
            self._log(level='INFO', content=f"Mode: {mode_text}")
            if driver.find_component(By.text('开启同传')):
                self._log(level='INFO', content=f"成功打开同传")
                return True
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to get mode for device {device_id}: {e}")
            return False

    def pre_process(self, device_id, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_id)
        translation_direction = kwargs.get('translation_direction', 'zh2en')

        def translation_direct(driver, translation_direction):
            if translation_direction == 'zh2en':
                # 点击中文按钮
                if driver.find_component(By.xpath('//RelativeContainer/Column/Text')).getText() != '中文 (简体)':
                    driver.touch(By.id('language_selector.build.image'))
                time.sleep(1)
                if driver.find_component(By.xpath('//RelativeContainer/Column/Text[2]')).getText() != '英语':
                    driver.touch(By.xpath('//RelativeContainer/Column/Text[2]'))
                    driver.touch(By.xpath('//Row/Flex/Text[@text="英语"]'))
            elif translation_direction == 'en2zh':
                # 点击中文按钮
                if driver.find_component(By.xpath('//RelativeContainer/Column/Text')).getText() != '英语':
                    driver.touch(By.id('language_selector.build.image'))
                time.sleep(1)
                if driver.find_component(By.xpath('//RelativeContainer/Column/Text[2]')).getText() != '中文 (简体)':
                    driver.touch(By.xpath('//RelativeContainer/Column/Text[2]'))
                    driver.touch(By.xpath('//Row/Flex/Text[@text="中文"]'))

        translation_direct(driver, translation_direction)
        start_btn = driver.find_component(By.text('开启同传'))
        if start_btn:
            self._log(level='DEBUG', content=f"Clicking Start Button...")
            start_btn.click()
            time.sleep(0.2)
        #
        if driver.find_component(By.text('暂停')) or driver.find_component(By.text('完成')):
            self._log(level='INFO', content=f"成功打开同传")
            return True
        self._log(level='INFO', content=f"打开同传失败")
        return False

    def post_process(self, device_id, **kwargs) -> bool:
        """开启面对面翻译"""
        driver = self._get_driver(device_id)
        end_btn = driver.find_component(By.text('完成'))
        if end_btn:
            self._log(level='DEBUG', content=f"Clicking 完成 Button...")
            end_btn.click()
            time.sleep(2)
        end_btn = driver.find_component(By.text('结束'))
        if end_btn:
            self._log(level='DEBUG', content=f"Clicking 结束 Button...")
            end_btn.click()
            time.sleep(2)
            return True
        return False

    def get_results(self, device_id, **kwargs) -> dict:
        driver = self._get_driver(device_id)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_id}")
            return {'success': False, 'message': 'False', 'asr': 'asr中文', 'translation': 'translation中文'}
        try:
            driver.touch((974, 271))
            driver.touch(By.text('同传'))
            driver.touch(By.xpath('//RelativeContainer/List[2]/ListItem[1]'))

            targert_lsits = driver.find_all_component(By.xpath('//RelativeContainer/List'))
            list1 = targert_lsits[0]
            self._log(level='DEBUG', content=f"List1: {list1}")
            asr_result = []
            translation_result = []
            extracted_pairs = set()
            max_retry = 1
            retry_count = 0
            self._log(level='DEBUG', content=f"开始向下滚动边提取对应项内容")
            while retry_count < max_retry:
                items1 = driver.find_component(By.xpath('//Row/Column/RelativeContainer/List/ListItem/Text'))
                items2 = driver.find_component(By.xpath('//Row/Column/RelativeContainer/List/ListItem/Column/Text'))

                new_pair_found = False
                current_max_idx = min(len(items1), len(items2))

                for idx in range(current_max_idx + 1):
                    text1 = items1[idx].get_text().strip()
                    text2 = items2[idx].get_text().strip()
                    pair_key = (text1, text2)
                    if pair_key in extracted_pairs:
                        asr_result.append(text1)
                        translation_result.append(text2)
                        extracted_pairs.remove(pair_key)
                        new_pair_found = True
                        self._log(level='DEBUG',
                                  content=f"已记录第{idx + 1}对，List1={text1[:20]}...List2={text2[-20:]}")

                if new_pair_found:
                    retry_count = 0
                    driver.swipe(UiParam.UP, 15, speed=2000, start_point=list1.getBoundsCenter())
                    time.sleep(0.1)
                else:
                    retry_count += 1
            asr_final_result_list = list(dict.fromkeys(asr_result).keys())
            transl_final_result_list = list(dict.fromkeys(translation_result).keys())
            asr_final_result = ' '.join(asr_final_result_list)
            transl_final_result = ' '.join(transl_final_result_list)

            self._log(level='DEBUG', content=f"提取完成，共{len(asr_final_result_list)}对有效项")

            self._log(level='INFO',
                      content=f'成功提取：ori_text:{asr_final_result},translate_text:{transl_final_result}')
            return {'success': True, 'message': 'Success', 'asr': asr_final_result, 'translation': transl_final_result}
        except Exception as e:
            self._log(level='ERROR', content=f"Failed to get results for 小艺同传 {device_id}，{e}")

