# -*- coding: utf-8 -*-
"""鸿蒙基础驱动结果采集混入 —— 录屏链 + 小艺 UI 文本抓取

参考 harmony_xiaoyichat（小艺通话聊天驱动）的成熟链路，为平台基础驱动
（HarmonyDriver，AppType.HARMONY_BASE）提供真实结果采集能力：

- 录屏（round 模式，每轮一段 mp4）：pre_process 启动 / post_process 停止
- 回复等待：回答气泡文本连续多次采样稳定即视为回复完成（不依赖特定 UI 文案）
- 文本抓取：小艺聊天页问题/回答气泡文本（xpath 走 device_config 配置）
- 文件拉取：hdc file recv → ffmpeg mp4→wav → OSS 上传（本地临时目录即传即清）

不包含 xiaoyichat 的 PCM/DSP 抓取链（user_wav/ai_wav 由专用驱动负责）。
专用驱动（xiaoyichat/livechat/translation/huiji 等）各自覆写了同名方法，
本混入不影响其行为。
"""
import os
import shutil
import subprocess
import tempfile
import time

from .driver_constants import (
    SHORT_WAIT, HDC_TIMEOUT, EXTRA_LONG_HDC_TIMEOUT, DEVICE_TMP_DIR,
    BASE_RECORDER_START_TIMEOUT, BASE_REPLY_END_TIMEOUT,
    BASE_REPLY_SETTLE_INTERVAL, BASE_REPLY_STABLE_ROUNDS,
)
from .device_config import get_device_config
from .utils import By
from device_service.config.config import Config
from shared.infrastructure.storage import storage


class HarmonyCollectionMixin:
    """录屏 + UI 文本采集混入（鸿蒙平台基础驱动用）"""

    RECORDER_BUNDLE = 'com.huawei.hmos.screenrecorder'
    RECORDER_ABILITY = 'com.huawei.hmos.screenrecorder.ServiceExtAbility'
    # 设备录屏产物目录（仅扫描近 20 分钟新增 mp4，避免全量 find 被 hdc 截断）
    RECORD_DIR = '/storage/media/100/local/files/Photo'

    def _hdc_shell(self, device_sn, *args):
        return subprocess.run(
            ['hdc', '-t', device_sn, 'shell'] + list(args),
            check=False, capture_output=True, text=True, timeout=HDC_TIMEOUT
        )

    def _chat_xpaths(self, config_key):
        """从 harmonyos 设备配置读取聊天页文本抓取 xpath 列表"""
        return get_device_config('harmonyos').get(config_key, [])

    def _last_component_text(self, driver, xpaths):
        """按 xpath 列表依次抓取组件文本，返回最后一个非空文本；抓不到返回 None"""
        for xpath in xpaths:
            try:
                components = driver.find_all_components(By.xpath(xpath))
            except Exception:
                continue
            for comp in reversed(components or []):
                try:
                    text = comp.getText()
                except Exception:
                    continue
                if text and str(text).strip():
                    return str(text).strip()
        return None

    # ------------------------------------------------------------------
    # 录屏链（round 模式：每轮一段）
    # ------------------------------------------------------------------
    def _list_device_mp4_set(self, device_sn):
        """获取设备录屏目录下最近 20 分钟内新增的 mp4 文件路径集合"""
        r = self._hdc_shell(device_sn, 'find', self.RECORD_DIR,
                            '-name', '*.mp4', '-type', 'f', '-mmin', '-20')
        if r.returncode != 0:
            return set()
        return {line.strip() for line in (r.stdout or '').splitlines() if line.strip()}

    def _get_device_file_size(self, device_sn, device_path):
        """获取设备上指定文件大小（字节），不存在返回 -1"""
        r = self._hdc_shell(device_sn, 'stat', '-c', '%s', device_path)
        if r.returncode != 0:
            return -1
        try:
            return int(r.stdout.strip())
        except Exception:
            return -1

    def _start_recorder(self, device_sn, file_name=None):
        """启动录屏服务，返回 (started, device_path, first_frame_ms)

        以 aa start 命令返回码为准（aa dump -l 与真实运行状态不严格对应，
        会把已成功启动的录屏误判为未运行）；录屏是否生效由轮询发现新 mp4
        文件（size 从 0 变非 0）验证，该时刻即录屏首帧 first_frame_ms。
        """
        existing_paths = self._list_device_mp4_set(device_sn)

        args = ['aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY]
        if file_name:
            args += ['--ps', 'CustomizedFileName', file_name]
        result = self._hdc_shell(device_sn, *args)
        if result.returncode != 0:
            return False, None, None

        device_path = None
        first_frame_ms = None
        deadline = time.time() + BASE_RECORDER_START_TIMEOUT
        while time.time() < deadline:
            new_paths = self._list_device_mp4_set(device_sn) - existing_paths
            for new_path in new_paths:
                if self._get_device_file_size(device_sn, new_path) > 0:
                    first_frame_ms = int(time.time() * 1000)
                    device_path = new_path
                    break
            if device_path:
                break
            time.sleep(SHORT_WAIT)
        return True, device_path, first_frame_ms

    def _stop_recorder(self, device_sn):
        """停止录屏服务（toggle 语义，执行成功即视为已停止）"""
        result = self._hdc_shell(device_sn, 'aa', 'start',
                                 '-b', self.RECORDER_BUNDLE,
                                 '-a', self.RECORDER_ABILITY)
        return result.returncode == 0

    def _mp4_to_wav(self, mp4_path, task_id=None, test_case_id=None):
        """mp4 无损转 wav（pcm_s16le 44.1kHz 双声道），失败返回 None"""
        if not mp4_path or not os.path.exists(mp4_path):
            return None
        wav_path = os.path.splitext(mp4_path)[0] + '.wav'
        cmd = [Config.FFMPEG_PATH, '-y', '-i', mp4_path,
               '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav_path]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True,
                               timeout=EXTRA_LONG_HDC_TIMEOUT)
            if r.returncode != 0 or not os.path.exists(wav_path):
                self._log(level='ERROR',
                          content=f"mp4转wav失败: {r.stderr[-500:] if r.stderr else ''}",
                          task_id=task_id, test_case_id=test_case_id)
                return None
            return wav_path
        except Exception as e:
            self._log(level='ERROR', content=f"mp4转wav异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _upload_file_to_oss(self, local_path, oss_key_prefix,
                            task_id=None, test_case_id=None, category='case_result'):
        """上传本地文件到 OSS 并返回访问路径；本地路径无效或上传失败返回 None"""
        if not local_path or not os.path.exists(local_path):
            return None
        try:
            key = f'{oss_key_prefix}/{os.path.basename(local_path)}'
            storage.save_file(local_path, category, key)
            url = storage.build_path(category, key)
            self._log(level='DEBUG', content=f"OSS上传成功: {url}",
                      task_id=task_id, test_case_id=test_case_id)
            return url
        except Exception as e:
            self._log(level='WARNING', content=f"OSS上传失败: {local_path}: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _pull_record_to_oss(self, device_sn, task_id=None, test_case_id=None):
        """拉取本轮录屏 mp4 → 转 wav → mp4+wav 上传 OSS，返回 (record_oss, wav_oss, error)

        error 非 None 表示拉取失败（record_oss/wav_oss 为 None）。
        本地临时目录即传即清。
        """
        record_file_name = getattr(self, '_record_file_name', None)
        if not record_file_name:
            return None, None, '本轮未启动录屏（pre_process 未记录文件名）'

        task_id_path = str(task_id) if task_id else 'default_task_id'
        test_case_id_path = str(test_case_id) if test_case_id else 'default_id'
        oss_key_prefix = f'{task_id_path}/{test_case_id_path}/{device_sn}'

        # 优先用 _start_recorder 发现的真实路径直接 recv（稳定，绕开 mediatool 按
        # CustomizedFileName 查询——后者对部分文件名报 displayName format 错误）
        device_path = getattr(self, '_record_device_path', None) or ''
        if not device_path:
            try:
                query = self._hdc_shell(device_sn, 'mediatool', 'query',
                                        record_file_name, '-u')
                lines = query.stdout.strip().split('\n')
                device_path = lines[1].strip() if len(lines) > 1 else ''
                if 'uri' in query.stdout and len(lines) > 2:
                    # 设备端把媒体库文件拷到 shell 可读目录，再从该路径 file recv 回本地
                    self._hdc_shell(device_sn, 'mediatool', 'recv',
                                    lines[2].strip(), DEVICE_TMP_DIR)
                    device_path = f'{DEVICE_TMP_DIR}/{record_file_name}'
            except Exception as e:
                self._log(level='WARNING', content=f"mediatool 查询录屏路径异常: {e}",
                          task_id=task_id, test_case_id=test_case_id)
                device_path = ''
        if not device_path:
            return None, None, f'录屏文件设备路径为空: {record_file_name}'

        local_dir = tempfile.mkdtemp(prefix=f'case_record_{task_id_path}_{test_case_id_path}_')
        try:
            local_path = os.path.join(local_dir, record_file_name)
            recv_result = subprocess.run(
                ['hdc', '-t', device_sn, 'file', 'recv', device_path, local_path],
                check=False, capture_output=True, text=True,
                timeout=EXTRA_LONG_HDC_TIMEOUT)
            if not os.path.exists(local_path):
                return None, None, (f'录屏文件拉取失败: device_path={device_path} '
                                    f'stderr={recv_result.stderr}')
            wav_path = self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
            record_oss = self._upload_file_to_oss(local_path, oss_key_prefix,
                                                  task_id=task_id, test_case_id=test_case_id)
            wav_oss = self._upload_file_to_oss(wav_path, oss_key_prefix,
                                               task_id=task_id, test_case_id=test_case_id)
            if not record_oss and not wav_oss:
                return None, None, f'录屏文件 OSS 上传失败: {local_path}'
            return record_oss, wav_oss, None
        finally:
            shutil.rmtree(local_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 回复等待 + UI 文本抓取
    # ------------------------------------------------------------------
    def _wait_reply_settled(self, driver, device_sn, task_id=None, test_case_id=None, **kwargs):
        """等待本轮小艺回复完成，返回 (replied, question_text, answer_text)

        回答气泡文本连续 BASE_REPLY_STABLE_ROUNDS 次采样不变即视为回复完成，
        不依赖特定 UI 文案（聊天页/通话页控件文案有差异，xpath 走配置）。
        打断轮（is_interruption）不等回复，采样一次立即返回。
        """
        if driver is None:
            return False, None, None

        is_interruption = kwargs.get('is_interruption') in (True, 'true', '1', 1)
        if is_interruption:
            self._log(level='INFO', content='is_interruption=True, 跳过等待 AI 回复完成',
                      task_id=task_id, test_case_id=test_case_id)
            question_text = self._last_component_text(
                driver, self._chat_xpaths('chat_question_xpaths'))
            answer_text = self._last_component_text(
                driver, self._chat_xpaths('chat_answer_xpaths'))
            return bool(question_text or answer_text), question_text, answer_text

        last_question = last_answer = prev_answer = None
        stable_count = 0
        deadline = time.time() + BASE_REPLY_END_TIMEOUT
        while time.time() < deadline:
            if self._check_stop('等待回复'):
                break
            last_question = self._last_component_text(
                driver, self._chat_xpaths('chat_question_xpaths'))
            last_answer = self._last_component_text(
                driver, self._chat_xpaths('chat_answer_xpaths'))
            if last_answer and last_answer == prev_answer:
                stable_count += 1
                if stable_count >= BASE_REPLY_STABLE_ROUNDS:
                    self._log(level='INFO', content='小艺回复完成（回答文本已稳定）',
                              task_id=task_id, test_case_id=test_case_id)
                    return True, last_question, last_answer
            else:
                stable_count = 0
            prev_answer = last_answer
            time.sleep(BASE_REPLY_SETTLE_INTERVAL)

        self._log(level='INFO',
                  content=f'小艺回复等待超时({BASE_REPLY_END_TIMEOUT}s)，按当前采样收口',
                  task_id=task_id, test_case_id=test_case_id)
        return bool(last_answer), last_question, last_answer
