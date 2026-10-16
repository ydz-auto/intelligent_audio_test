# -*- coding: utf-8 -*-
"""鸿蒙基础驱动结果采集混入 —— 录屏链 + 小艺 UI 文本抓取

参考 harmony_xiaoyichat（小艺通话聊天驱动）的成熟链路，为平台基础驱动
（HarmonyDriver，is_base_driver=True）提供真实结果采集能力：

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
    SHORT_WAIT, NORMAL_WAIT, HDC_TIMEOUT, EXTRA_LONG_HDC_TIMEOUT, DEVICE_TMP_DIR,
    BASE_RECORDER_START_TIMEOUT, BASE_RECORDER_START_RECOVERY_TIMEOUT,
    BASE_REPLY_END_TIMEOUT, BASE_REPLY_SETTLE_INTERVAL, BASE_REPLY_STABLE_ROUNDS,
    BASE_RECORDER_STOP_VERIFY_TIMEOUT, BASE_RECORDER_STOP_VERIFY_INTERVAL,
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

        快照启动前已存在的 mp4 集合（self._preexisting_mp4_set）：部分机型
        忽略 --ps CustomizedFileName（产物为 VID_* 名称），mediatool 按名兜底
        查询永不命中，拉取失败时用该集合 diff 找本轮实际产物。
        """
        self._preexisting_mp4_set = self._list_device_mp4_set(device_sn)
        existing_paths = self._preexisting_mp4_set

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
        if device_path is None:
            # toggle 语义兜底：上一轮停止失败时服务仍处于录制态，第一次 aa start
            # 停掉了残留录制而非开启新录制（INT-158 验收问题 3）。再 toggle 一次
            # 并短轮询兜底。
            self._hdc_shell(device_sn, *args)
            recovery_deadline = time.time() + BASE_RECORDER_START_RECOVERY_TIMEOUT
            while time.time() < recovery_deadline:
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
        """停止录屏服务并校验收尾，返回 bool

        toggle 成功不等于录制已停止（screenrecorder 进程常驻，ps 可见不可作为
        停止依据；进程存活时下一轮 aa start 打在存活服务上不触发新录制）。
        以本轮录屏文件 size 连续两次读数稳定为停止判据；仍增长则再 toggle 一次。
        """
        result = self._hdc_shell(device_sn, 'aa', 'start',
                                 '-b', self.RECORDER_BUNDLE,
                                 '-a', self.RECORDER_ABILITY)
        if result.returncode != 0:
            return False
        if not self._wait_recorder_stopped(device_sn):
            # size 仍增长 → 第一次 toggle 可能有效但收尾慢，或未生效；再 toggle 一次并复验
            self._hdc_shell(device_sn, 'aa', 'start',
                            '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY)
            if not self._wait_recorder_stopped(device_sn):
                return False
        return True

    def _wait_recorder_stopped(self, device_sn):
        """轮询本轮录屏文件 size 稳定（连续两次读数相同）作为录制停止判据"""
        device_path = getattr(self, '_record_device_path', None)
        if not device_path:
            # 未发现本轮文件（start 轮询超时）时无法观测 size，退固定收尾等待
            time.sleep(NORMAL_WAIT * 3)
            return True
        last_size = -1
        deadline = time.time() + BASE_RECORDER_STOP_VERIFY_TIMEOUT
        while time.time() < deadline:
            size = self._get_device_file_size(device_sn, device_path)
            if size > 0 and size == last_size:
                return True
            last_size = size
            time.sleep(BASE_RECORDER_STOP_VERIFY_INTERVAL)
        return False

    def _mp4_to_wav(self, mp4_path, task_id=None, test_case_id=None):
        """mp4 无损转 wav（pcm_s16le 44.1kHz 双声道），失败返回 None

        ffmpeg 不可用（FFMPEG_PATH 配置无效或不在 PATH）时跳过转换并显式
        告警，降级口径由调用方在结果 message 中标注。
        """
        if not mp4_path or not os.path.exists(mp4_path):
            return None
        ffmpeg_path = Config.FFMPEG_PATH
        if not shutil.which(ffmpeg_path):
            self._log(level='WARNING',
                      content=(f"ffmpeg 不可用（FFMPEG_PATH={ffmpeg_path!r} 无效或不在 PATH），"
                               f"mp4→wav 转换跳过，wav_path 将回退使用 mp4"),
                      task_id=task_id, test_case_id=test_case_id)
            return None
        wav_path = os.path.splitext(mp4_path)[0] + '.wav'
        cmd = [ffmpeg_path, '-y', '-i', mp4_path,
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
        """上传本地文件到存储，返回真实落点路径（oss:// 或本地降级 local://）

        路径取 storage.save_file 的实际返回值，不做构造性拼接——OSS 不可用
        降级本地时返回 local:// 路径，上传彻底失败返回 None。
        """
        if not local_path or not os.path.exists(local_path):
            return None
        try:
            key = f'{oss_key_prefix}/{os.path.basename(local_path)}'
            url = storage.save_file(local_path, category, key)
            self._log(level='DEBUG', content=f"存储上传完成: {url}",
                      task_id=task_id, test_case_id=test_case_id)
            return url
        except Exception as e:
            self._log(level='WARNING', content=f"存储上传失败: {local_path}: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _validate_mp4(self, local_path, task_id=None, test_case_id=None):
        """ffprobe 校验本地 mp4 可解析（moov 完整、非半截文件）

        录屏未收尾即拉取会产出 moov atom 缺失的不可播放文件——这类文件不得
        上传或回退为 wav_path（INT-158 验收问题 1）。以 ffprobe 退出码为准
        （损坏文件非零退出）；ffprobe 不可用时跳过校验（仅告警）。
        返回 True=可解析或未校验，False=确认损坏。
        """
        ffprobe = getattr(Config, 'FFPROBE_PATH', 'ffprobe')
        try:
            r = subprocess.run([ffprobe, '-v', 'error', '-show_entries',
                                'format=format_name', '-of', 'csv=p=0', local_path],
                               check=False, capture_output=True, text=True,
                               timeout=HDC_TIMEOUT)
        except FileNotFoundError:
            self._log(level='WARNING', content=f"ffprobe 不可用({ffprobe})，跳过 mp4 校验",
                      task_id=task_id, test_case_id=test_case_id)
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"mp4 校验异常({e})，按损坏处理",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        if r.returncode != 0:
            self._log(level='ERROR',
                      content=f"mp4 校验失败(不可播放): {r.stderr[-300:] if r.stderr else 'no stderr'}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        return True

    def _discover_round_record_file(self, device_sn, task_id=None, test_case_id=None):
        """确定本轮录屏文件设备路径，返回 (device_path, actual_name)

        优先用 _start_recorder 发现的真实路径；缺失时按"本轮新增 mp4"diff
        （当前集合 - 启动前快照）取 size 最大者——兼容忽略 --ps CustomizedFileName
        的机型（产物为 VID_* 名称，mediatool 按名查询永不命中，INT-158 验收问题 3）。
        """
        device_path = getattr(self, '_record_device_path', None) or ''
        if device_path:
            return device_path, os.path.basename(device_path)

        # 兜底 1：本轮新增 mp4 diff（晚于启动轮询才发现的文件会落在这里）
        preexisting = getattr(self, '_preexisting_mp4_set', None)
        if preexisting is not None:
            new_paths = self._list_device_mp4_set(device_sn) - preexisting
            sized = [(p, self._get_device_file_size(device_sn, p)) for p in new_paths]
            sized = [(p, s) for p, s in sized if s > 0]
            if sized:
                device_path = max(sized, key=lambda x: x[1])[0]
                self._log(level='INFO',
                          content=f"通过新增文件 diff 发现本轮录屏: {device_path}",
                          task_id=task_id, test_case_id=test_case_id)
                return device_path, os.path.basename(device_path)

        # 兜底 2：mediatool 按名查询（对尊重 CustomizedFileName 的机型有效）
        record_file_name = getattr(self, '_record_file_name', None)
        if record_file_name:
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
            if device_path:
                return device_path, record_file_name
        return '', ''

    def _pull_record_to_oss(self, device_sn, task_id=None, test_case_id=None):
        """拉取本轮录屏 mp4 → 校验可解析 → 转 wav → mp4+wav 上传存储

        返回 (record_path, wav_path, error, wav_note)：record_path/wav_path 为
        存储真实落点（oss:// 或本地降级 local://）。error 非 None 表示拉取失败
        或 mp4 不可解析（record_path/wav_path 为 None，不回退坏文件）。
        wav_note 非 None 表示 wav 产物缺失的降级原因（转换失败/上传失败），
        供 get_results 在 message 中标注回退口径。本地临时目录即传即清。
        """
        record_file_name = getattr(self, '_record_file_name', None)
        if not record_file_name:
            return None, None, '本轮未启动录屏（pre_process 未记录文件名）', None

        task_id_path = str(task_id) if task_id else 'default_task_id'
        test_case_id_path = str(test_case_id) if test_case_id else 'default_id'
        oss_key_prefix = f'{task_id_path}/{test_case_id_path}/{device_sn}'

        device_path, actual_name = self._discover_round_record_file(
            device_sn, task_id=task_id, test_case_id=test_case_id)
        if not device_path:
            return None, None, (f'录屏文件设备路径为空: '
                                f'expected={getattr(self, "_record_file_name", None)}'), None
        if actual_name != getattr(self, '_record_file_name', None):
            self._log(level='INFO',
                      content=f"录屏产物实际文件名(设备忽略 CustomizedFileName): {actual_name}",
                      task_id=task_id, test_case_id=test_case_id)

        local_dir = tempfile.mkdtemp(prefix=f'case_record_{task_id_path}_{test_case_id_path}_')
        try:
            local_path = os.path.join(local_dir, actual_name)
            recv_result = subprocess.run(
                ['hdc', '-t', device_sn, 'file', 'recv', device_path, local_path],
                check=False, capture_output=True, text=True,
                timeout=EXTRA_LONG_HDC_TIMEOUT)
            if not os.path.exists(local_path):
                return None, None, (f'录屏文件拉取失败: device_path={device_path} '
                                    f'stderr={recv_result.stderr}'), None
            # 收尾校验：moov 缺失等不可播放文件直接按失败处理，不上传不回退
            if not self._validate_mp4(local_path, task_id=task_id, test_case_id=test_case_id):
                return None, None, (f'录屏 mp4 不可播放(moov 缺失/未收尾): '
                                    f'{actual_name} @ {device_path}'), None
            wav_note = None
            wav_path = self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
            if wav_path is None:
                wav_note = 'wav 转换失败（ffmpeg 不可用或转换出错），wav_path 回退使用 mp4'
            record_oss = self._upload_file_to_oss(local_path, oss_key_prefix,
                                                  task_id=task_id, test_case_id=test_case_id)
            wav_oss = self._upload_file_to_oss(wav_path, oss_key_prefix,
                                               task_id=task_id, test_case_id=test_case_id)
            if wav_path and not wav_oss:
                wav_note = 'wav 上传存储失败，wav_path 回退使用 mp4'
            if not record_oss and not wav_oss:
                return None, None, f'录屏文件上传存储失败: {local_path}', None
            return record_oss, wav_oss, None, wav_note
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
