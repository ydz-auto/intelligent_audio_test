import time
import subprocess
import os
import re
import wave
import struct
import base64

try:
    from hypium.model import UiParam
except Exception:
    UiParam = None

from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit, with_rpc_retry
from config.config import Config
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT

class Xiaoyilivechat(HarmonyDriver):
    RECORDER_BUNDLE = 'com.huawei.hmos.screenrecorder'
    RECORDER_ABILITY = 'com.huawei.hmos.screenrecorder.ServiceExtAbility'
    # 华为音乐 bundle:测试中小艺有时会把播放的音频误识别为"播放音乐"指令而拉起音乐,
    # 污染录屏/pcm。pre_process 开局与 teardown 兜底各 force-stop 一次兜住。
    MUSIC_BUNDLE = 'com.huawei.hmsapp.music'
    # 时钟 app:测试中设的闹钟可能响铃打断测试,开局与收尾各清一次保证无残留
    CLOCK_BUNDLE = 'com.huawei.hmos.clock'
    CLOCK_DB_PATH = '/data/app/el1/100/database/com.huawei.hmos.clock/entry/rdb/Clock.db'

    def __init__(self):
        super().__init__()
        # 仅覆盖与父类不同的属性
        self.app_icon_key = 'AppIcon_Image_com.huawei.hmos.vassistant.launcherVoiceAbilityentry0_undefined_0'
        # ai PCM 首帧时间戳(替代录屏 first_frame 作为模型回复起始基准) + 本轮基线快照
        self._ai_first_frame_ms = None
        self._ai_pcm_size_base = None
    # 是否启用录屏(小艺=True 保留录屏 wav 作为评估音频源)。
    # Doubao/ChatGPT 在各自子类置 False:无录屏,get_results 跳过录屏拉取,
    # 改把 ai_wav 塞进 wav_path 复用 wav_path→record_file 映射喂评估。
    _record_enabled = True
    # 各 app 的 pcm 缓存目录、用户输入后缀、AI 回复后缀
    # 当前驱动仅抓取小艺(xiaoyi)数据；通过 app 参数可切换到 doubao/chatgpt
    PCM_APP_CONFIG = {
        'xiaoyi': {
            # AI 回复 PCM 只取 aibase/cache 的 cap_client_ec_out.pcm。
            # ⚠️ 不从 vassistant/cache 取 client_in..pcm: 实测其时间轴不对齐
            #   (PCM 内容与 AI 实际说话时刻错位), 用于 RMS 回复完成检测会误判, 已弃用。
            'cache_dirs': ['/data/app/el2/100/base/com.huawei.hmos.aibase/cache'],
            # 实测设备文件名: 用户 cap_client_out.pcm / AI cap_client_ec_out.pcm
            'user_suffix': 'cap_client_out.pcm',
            'ai_suffix': 'cap_client_ec_out.pcm',
        },
        'doubao': {
            'cache_dirs': ['/data/app/el2/100/base/com.larus.nova.hm/cache'],
            'user_suffix': 'cap_client_out.pcm',
            'ai_suffix': 'client_in..pcm',
        },
        'chatgpt': {
            'cache_dirs': ['/data/local/tmp'],
            'user_suffix': 'cap_client_out.pcm',
            # 实测设备上 AI 回复文件名为 *_client_in..pcm(双点,无 cap_ 前缀)；
            # 另有 *_dump_process_client_play_audio_*.pcm 为 TTS dump,不取
            'ai_suffix': 'client_in..pcm',
        },
    }
    # 清理时一并清的公共目录
    PCM_COMMON_CLEAR_DIRS = ['/data/data/.pulse_dir', '/data/local/tmp']

    # ===== DSP 层 audio_hook PCM(仅小艺用,替换 fwk 层) =====
    # 来源:华为全双工调试脚本 AudioLogTools/1.start-dump-smartpa.bat 的 DSP 子集产物。
    # audio_hook 目录下两类时间轴对齐的裸 PCM(s16le,固定格式,非文件名解析):
    #   in_after_imedia_asr_module*  16000Hz/4ch/16bit → 取第 1 声道(ch0)为用户输入(mono)
    #   in_raw1*                    16000Hz/2ch/16bit → 模型回复(2ch)
    DSP_AUDIO_HOOK_DIR = '/data/vendor/log/audio_logs/audio_hook'
    DSP_USER_PREFIX = 'in_after_imedia_asr_module'   # 用户麦克风采集流前缀
    DSP_AI_PREFIX = 'in_raw1'                        # 模型回复流前缀
    DSP_USER_FMT = (16000, 4, 2)                     # (sample_rate, channels, sample_width)
    DSP_AI_FMT = (16000, 2, 2)
    DSP_USER_EXTRACT_CHANNEL = 0                     # 4ch 取第 1 声道(ch0)→ mono
    # audiodebug 二进制版本(对应 libaudio_proxy_<V>.z.so),本地随驱动打包
    DSP_BIN_DIR = os.path.join(os.path.dirname(__file__), 'bin', 'dsp')
    DSP_AUDIODEBUG_VERSIONS = ['4.0', '5.0']          # 本地有这两个版本(缺 6.0)
    DSP_HOOKCHANNEL = 196609                          # bat1 实测的 hook 通道


    # AI 回复完成检测(RMS 能量法)参数 — 不依赖控件文本,按 AI PCM 尾部能量判定。
    # 小艺/豆包/ChatGPT 共用;采样率从 PCM 文件名解析(小艺16k/豆包48k),1s 尾部字节随之自适应。
    RMS_THRESHOLD = 300          # RMS 阈值,低于此值视为静音
    RMS_SILENCE_SECONDS = 8      # 连续静默秒数(实测回复中停顿≤6s,8s 不误触发)
    RMS_START_TIMEOUT = 25       # 等 AI 开始说话的超时(超时走兜底扫最后 15s 历史)
    RMS_END_TIMEOUT = 60         # 等 AI 说完的超时(单轮回复+8s静默够,超时视为已回复可能截断)
    RMS_SCAN_SECONDS = 15        # 阶段A超时后扫最后 N 秒历史

    def _mp4_to_wav(self, mp4_path, task_id=None, test_case_id=None):
        """将 mp4 无损转换为 wav（pcm_s16le，44.1kHz，双声道）。
        成功返回 wav 绝对路径，失败返回 None。"""
        if not os.path.exists(mp4_path):
            return None
        wav_path = os.path.splitext(mp4_path)[0] + '.wav'
        cmd = [Config.FFMPEG_PATH, '-y', '-i', mp4_path,
               '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav_path]
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(wav_path):
                self._log(level='ERROR',
                          content=f"mp4转wav失败: {r.stderr[-500:] if r.stderr else ''}",
                          task_id=task_id, test_case_id=test_case_id)
                return None
            self._log(level='INFO', content=f"mp4转wav成功: {wav_path}",
                      task_id=task_id, test_case_id=test_case_id)
            return wav_path
        except Exception as e:
            self._log(level='ERROR', content=f"mp4转wav异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _pcm_to_wav(self, pcm_path, task_id=None, test_case_id=None):
        """将裸 pcm 转 wav（pcm_s16le）。

        pcm 文件名数字前缀格式: <流ID>_<采样率>_<声道数>_<位深>_...
        例如 100188_48000_2_1_cap_client_out.pcm 表示:
          - 100188: 流ID
          - 48000:  采样率
          - 2:      声道数
          - 1:      位深标志(1=16位, 2=32位)
        目前仅支持 16 位。成功返回 wav 绝对路径, 失败返回 None。

        本地拉取的文件名可能带轮次前缀 r{round}_ (由 _pull_pcm 添加),
        如 r1_100188_48000_2_1_cap_client_out.pcm。解析前先剥离该前缀。
        """
        if not os.path.exists(pcm_path):
            return None
        # 从文件名解析采样参数
        base = os.path.basename(pcm_path)
        # 剥离轮次前缀 r{round}_ (如 r1_),避免干扰采样参数解析
        parse_base = re.sub(r'^r\d+_', '', base)
        parts = parse_base.split('_')
        try:
            sample_rate = int(parts[1])
            channels = int(parts[2])
            bit_depth_flag = int(parts[3])
        except (IndexError, ValueError):
            self._log(level='ERROR', content=f"pcm文件名无法解析采样参数: {base}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

        # 位深标志 -> 每采样字节数
        if bit_depth_flag == 1:
            sample_width = 2  # 16-bit
        elif bit_depth_flag == 2:
            self._log(level='ERROR', content=f"暂不支持32位pcm转换: {base}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        else:
            self._log(level='ERROR', content=f"未知位深标志 bit_depth={bit_depth_flag}: {base}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

        wav_path = os.path.splitext(pcm_path)[0] + '.wav'
        try:
            with open(pcm_path, 'rb') as f:
                pcm_data = f.read()
            # 校验数据长度对齐到帧大小, 避免尾部不完整帧导致 wave 写入异常
            frame_size = sample_width * channels
            if frame_size > 0 and len(pcm_data) % frame_size != 0:
                pcm_data = pcm_data[:len(pcm_data) - (len(pcm_data) % frame_size)]
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_data)
            self._log(level='INFO',
                      content=f"pcm转wav成功: {wav_path} (sr={sample_rate} ch={channels} bw={sample_width})",
                      task_id=task_id, test_case_id=test_case_id)
            return wav_path
        except Exception as e:
            self._log(level='ERROR', content=f"pcm转wav异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _pcm_to_wav_fixed(self, pcm_path, sample_rate, channels, sample_width=2,
                          extract_channel=None, task_id=None, test_case_id=None):
        """将裸 pcm 转 wav,采样参数由调用方显式给出(不从文件名解析)。

        用于 DSP 层 audio_hook PCM——其文件名(in_after_imedia_asr_module* / in_raw1*)
        不符合 <id>_<sr>_<ch>_<bdf>_... 契约,无法用 _pcm_to_wav 解析。

        extract_channel: 若不为 None,只取该声道(0-based)写 mono wav。
          例如 4ch PCM 取第 1 声道: extract_channel=0 → samples[0::4] → nchannels=1。
          None 则原样写多声道。成功返回 wav 绝对路径,失败返回 None。
        """
        if not os.path.exists(pcm_path):
            return None
        wav_path = os.path.splitext(pcm_path)[0] + '.wav'
        try:
            with open(pcm_path, 'rb') as f:
                pcm_data = f.read()
            frame_size = sample_width * channels
            if frame_size > 0 and len(pcm_data) % frame_size != 0:
                pcm_data = pcm_data[:len(pcm_data) - (len(pcm_data) % frame_size)]
            if extract_channel is not None:
                # 抽单声道: 全部 16-bit 样本解包后按下标跨步取目标声道
                total = len(pcm_data) // 2  # s16le 每样本 2 字节
                samples = struct.unpack('<' + 'h' * total, pcm_data)
                mono = samples[extract_channel::channels]
                with wave.open(wav_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(sample_width)
                    wf.setframerate(sample_rate)
                    wf.writeframes(struct.pack('<' + 'h' * len(mono), *mono))
                self._log(level='INFO',
                          content=(f"pcm转wav成功(抽声道{extract_channel}/{channels}): {wav_path} "
                                   f"(sr={sample_rate} mono bw={sample_width})"),
                          task_id=task_id, test_case_id=test_case_id)
            else:
                with wave.open(wav_path, 'wb') as wf:
                    wf.setnchannels(channels)
                    wf.setsampwidth(sample_width)
                    wf.setframerate(sample_rate)
                    wf.writeframes(pcm_data)
                self._log(level='INFO',
                          content=(f"pcm转wav成功(定参): {wav_path} "
                                   f"(sr={sample_rate} ch={channels} bw={sample_width})"),
                          task_id=task_id, test_case_id=test_case_id)
            return wav_path
        except Exception as e:
            self._log(level='ERROR', content=f"pcm转wav异常(定参): {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def _hdc_shell(self, device_sn, *args):
        return subprocess.run(
            ['hdc', '-t', device_sn, 'shell'] + list(args),
            check=False, capture_output=True, text=True, timeout=10
        )

    def _list_device_mp4_set(self, device_sn):
        """获取设备录屏目录下最近 20 分钟内新增的 mp4 文件路径集合。

        设备 Photo 目录有 16 个子目录、近千个历史 mp4, find 全量返回会被
        hdc shell 输出截断, 导致 _start_recorder 的 before/after diff 漏掉
        新文件。改用 -mmin -20 只返回最近 20 分钟内修改过的文件, 量级可控
        且覆盖 case 模式多轮对话的时长(单用例最长约 10 分钟)。
        """
        r = self._hdc_shell(
            device_sn, 'find', '/storage/media/100/local/files/Photo',
            '-name', '*.mp4', '-type', 'f', '-mmin', '-20'
        )
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

    def _is_recorder_running(self, device_sn):
        """检查 screenrecorder 服务是否正在运行"""
        result = self._hdc_shell(device_sn, 'aa', 'dump', '-l')
        if result.returncode != 0:
            return False
        # 服务运行时 dump 输出会包含 bundle 名称
        return self.RECORDER_BUNDLE in (result.stdout or '')

    def _start_recorder(self, device_sn, file_name=None):
        """启动录屏服务

        说明: aa dump -l 的输出与录屏服务是否真正在前台运行并非严格对应,
        用它做二次校验会把已成功启动的录屏误判为"未运行", 从而导致整个用例失败。
        这里改为以 aa start 命令本身的返回码为准: 命令执行成功即视为启动成功,
        录屏是否真正生效交给后续 post_process 的等待逻辑兜底。

        时延测量:
        - first_frame_ms: 首帧真正写入时刻（轮询文件 size 从 0 变非0）
          录屏录制的即模型回复内容, first_frame_ms 即模型回复起始时刻
        """
        # 记录 aa start 前已存在的 mp4 集合
        existing_paths = self._list_device_mp4_set(device_sn)

        args = ['aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY]
        if file_name:
            args += ['--ps', 'CustomizedFileName', file_name]
        result = self._hdc_shell(device_sn, *args)
        if result.returncode != 0:
            self._recorder_first_frame_ms = None
            return False

        # 轮询：发现新文件 + 等待首帧写入（size 从 0 变非0）
        first_frame_ms = None
        self._record_device_path = None  # _start_recorder 发现的真实录屏文件设备路径(VID_*.mp4),供 get_results/_pull_record_file 直接 recv
        deadline = int(time.time() * 1000) + 30000  # 30 秒超时
        while int(time.time() * 1000) < deadline:
            current_paths = self._list_device_mp4_set(device_sn)
            new_paths = current_paths - existing_paths
            if new_paths:
                new_path = next(iter(new_paths))
                size = self._get_device_file_size(device_sn, new_path)
                if size > 0:
                    first_frame_ms = int(time.time() * 1000)
                    self._record_device_path = new_path  # 记下真实路径,绕开 mediatool 按 CustomizedFileName 查询
                    break
            time.sleep(0.1)

        self._recorder_first_frame_ms = first_frame_ms
        return True

    def _stop_recorder(self, device_sn, task_id=None, test_case_id=None):
        """停止录屏服务

        说明: 与 _start_recorder 同理, aa dump -l 的二次校验不可靠,
        这里直接以 toggle 命令执行成功为准; 真正的兜底放在 teardown 中按
        _recording 标志位判断, 避免对已停止的录屏再次 toggle 反而打开。
        """
        self._hdc_shell(device_sn, 'aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY)
        return True

    def _stop_music_app(self, device_sn, task_id=None, test_case_id=None):
        """停止华为音乐 app。

        测试中小艺有时会把播放的音频误识别为"播放音乐"指令而拉起音乐,
        其播放声会污染本轮录屏/pcm。开局与收尾各清一次保证音乐不残留。
        用 hypium 的 driver.stop_app(bundle) 停 app——实测裸 hdc aa force-stop
        未能停止音乐 app,改走 hypium 接口(与 teardown 停小艺 app 同一套)。
        包 try/except: 失败时退化成 WARNING 日志,绝不阻断 pre_process/teardown
        主流程——音乐防护是锦上添花,不能反过来把整个用例拖垮。
        """
        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='WARNING',
                      content=f"stop_music: 无 UiDriver,跳过 {self.MUSIC_BUNDLE}",
                      task_id=task_id, test_case_id=test_case_id)
            return
        try:
            driver.stop_app(self.MUSIC_BUNDLE)
            self._log(level='DEBUG', content=f"stop_app {self.MUSIC_BUNDLE} 完成",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING',
                      content=f"stop_app {self.MUSIC_BUNDLE} 失败(忽略,不阻断用例): {e}",
                      task_id=task_id, test_case_id=test_case_id)

    def _clear_alarms(self, device_sn, task_id=None, test_case_id=None):
        """清空设备时钟 app 的闹钟记录(ALARM_CLOCK 表)。

        测试中设的闹钟可能响铃打断测试,开局与收尾各清一次保证无残留。
        先 force-stop 时钟 app 释放数据库锁,再用 sqlite3 DELETE 清空表。
        失败时退化成 WARNING 日志,绝不阻断 pre_process/teardown 主流程。
        """
        try:
            self._hdc_shell(
                device_sn,
                f"aa force-stop {self.CLOCK_BUNDLE} && "
                f"sqlite3 {self.CLOCK_DB_PATH} 'DELETE FROM ALARM_CLOCK;' && "
                f"echo 'alarm_cleared'"
            )
            self._log(level='DEBUG', content=f"clear_alarms 完成: {self.CLOCK_DB_PATH}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING',
                      content=f"clear_alarms 失败(忽略,不阻断用例): {e}",
                      task_id=task_id, test_case_id=test_case_id)

    def _pull_record_file(self, device_sn, task_id=None, test_case_id=None):
        """从设备拉取录屏文件到本地并转 wav，返回 local_path（失败返回 None）。teardown 兜底用。"""
        record_file_name = getattr(self, '_record_file_name', None)
        if not record_file_name:
            return None
        local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result',
                                 str(task_id) if task_id else 'default_task_id',
                                 str(test_case_id) if test_case_id else 'default_id', device_sn)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, record_file_name)
        # 优先用 _start_recorder 发现的真实 VID 路径直接 recv(稳定,绕开 mediatool 按 CustomizedFileName 查询)
        device_path = getattr(self, '_record_device_path', None) or ''
        if not device_path:
            try:
                query = self._hdc_shell(device_sn, 'mediatool', 'query', record_file_name, '-u')
                lines = query.stdout.strip().split('\n')
                device_path = lines[1].strip() if len(lines) > 1 else ''
                if 'uri' in query.stdout and len(lines) > 2:
                    subprocess.run(
                        ['hdc', '-t', device_sn, 'shell', 'mediatool', 'recv', lines[2].strip(), '/data/local/tmp'],
                        check=False, capture_output=True, text=True, timeout=120
                    )
                    device_path = f'/data/local/tmp/{record_file_name}'
            except Exception as e:
                self._log(level='WARNING', content=f"teardown兜底 mediatool 查询异常: {e}",
                          task_id=task_id, test_case_id=test_case_id)
                device_path = ''
        try:
            recv_result = subprocess.run(['hdc', '-t', device_sn, 'file', 'recv', device_path, local_path],
                                         check=False, capture_output=True, text=True, timeout=120)
            if not os.path.exists(local_path):
                self._log(level='WARNING', content=f"teardown兜底拉取录屏失败: device_path={device_path!r} err={recv_result.stderr}",
                          task_id=task_id, test_case_id=test_case_id)
                return None
            self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
            return local_path
        except Exception as e:
            self._log(level='WARNING', content=f"teardown兜底拉取录屏异常: {e}", task_id=task_id, test_case_id=test_case_id)
            return None

    def _clear_pcm(self, device_sn, app='xiaoyi', task_id=None, test_case_id=None):
        """清理设备上指定 app 的 pcm 缓存文件（连同公共目录一并清理）。

        app: xiaoyi(默认) / doubao / chatgpt
        """
        cfg = self.PCM_APP_CONFIG.get(app)
        if not cfg:
            self._log(level='WARNING', content=f"未知 pcm app: {app}, 跳过清理",
                      task_id=task_id, test_case_id=test_case_id)
            return
        # 去重保序: app 专属目录 + 公共目录
        dirs = list(cfg['cache_dirs']) + self.PCM_COMMON_CLEAR_DIRS
        seen = set()
        dirs = [d for d in dirs if not (d in seen or seen.add(d))]
        rm_args = []
        for d in dirs:
            rm_args.extend(['rm', '-f', f'{d}/*.pcm', '&&'])
        if rm_args and rm_args[-1] == '&&':
            rm_args.pop()
        if not rm_args:
            return
        result = self._hdc_shell(device_sn, *rm_args)
        self._log(level='DEBUG',
                  content=f"清理 {app} pcm 完成: rc={result.returncode}",
                  task_id=task_id, test_case_id=test_case_id)

        # 清除后检测：若仍有残留 .pcm 文件，仅日志告警（不改行为，便于排查）
        # 可能原因：文件被采集进程占用/权限不足/路径不存在
        remaining = []
        for d in dirs:
            remaining.extend(self._list_dir_pcm(device_sn, d))
        if remaining:
            self._log(level='WARNING',
                      content=f"pcm清除失败: 残留 {len(remaining)} 个文件: {remaining}",
                      task_id=task_id, test_case_id=test_case_id)

    def _list_dir_pcm(self, device_sn, remote_dir):
        """列出设备指定目录下所有 pcm 文件路径（用于按后缀匹配区分用户输入/AI回复）"""
        r = self._hdc_shell(device_sn, 'find', remote_dir, '-name', '*.pcm', '-type', 'f')
        if r.returncode != 0:
            return []
        return [line.strip() for line in (r.stdout or '').splitlines() if line.strip()]

    def _snapshot_ai_pcm_sizes(self, device_sn, app='xiaoyi'):
        """快照当前 ai 后缀 PCM 文件及其 size（{remote_path: size}），作为本轮首帧检测基线。

        在 pre_process 轮首调用（用户语音播放/AI 回复前建立基线），post_process
        的 _detect_ai_pcm_first_frame 据此判断 size 增长=模型开始写回复。
        """
        cfg = self.PCM_APP_CONFIG.get(app)
        if not cfg:
            return {}
        ai_suffix = cfg['ai_suffix']
        # endswith 仅接受 str 或 tuple(不接受 list),这里统一转 tuple
        ai_suffix = tuple(ai_suffix) if isinstance(ai_suffix, list) else ai_suffix
        files = []
        for d in cfg['cache_dirs']:
            files.extend(self._list_dir_pcm(device_sn, d))
        return {f: self._get_device_file_size(device_sn, f)
                for f in files if f.endswith(ai_suffix)}

    def _detect_ai_pcm_first_frame(self, device_sn, app='xiaoyi',
                                   task_id=None, test_case_id=None, timeout_ms=15000):
        """轮询 ai PCM 首帧写入（相对基线 size 增长/新文件出现），返回墙钟毫秒或 None。

        替代录屏 first_frame 作为模型回复起始基准（first_frame_ms）。基线
        _ai_pcm_size_base 由 pre_process 轮首快照。任一 ai 后缀文件 size>0 且
        >基线即视为首帧，记 int(time.time()*1000)。打断轮不调用（留 None 走 fallback）。
        """
        base = getattr(self, '_ai_pcm_size_base', None) or {}
        cfg = self.PCM_APP_CONFIG.get(app)
        if not cfg:
            return None
        ai_suffix = cfg['ai_suffix']
        # endswith 仅接受 str 或 tuple(不接受 list),这里统一转 tuple
        ai_suffix = tuple(ai_suffix) if isinstance(ai_suffix, list) else ai_suffix
        deadline = int(time.time() * 1000) + timeout_ms
        while int(time.time() * 1000) < deadline:
            if self._check_stop('ai_pcm首帧检测'):
                return None
            files = []
            for d in cfg['cache_dirs']:
                files.extend(self._list_dir_pcm(device_sn, d))
            for f in files:
                if not f.endswith(ai_suffix):
                    continue
                sz = self._get_device_file_size(device_sn, f)
                if sz > 0 and sz > base.get(f, 0):
                    ts = int(time.time() * 1000)
                    self._log(level='INFO',
                              content=f"ai PCM 首帧: {f} size={sz} base={base.get(f, 0)} ts={ts}",
                              task_id=task_id, test_case_id=test_case_id)
                    return ts
            time.sleep(0.1)
        self._log(level='WARNING',
                  content=f"ai PCM 首帧检测超时({timeout_ms}ms), first_frame 将走录屏 fallback",
                  task_id=task_id, test_case_id=test_case_id)
        return None

    # ------------------------------------------------------------------
    # AI 回复完成检测（基于 AI PCM 尾部 RMS 能量，双阶段+历史兜底）
    # 不依赖控件文本(说话可打断/正在听…),后者在语音态透传性不稳定。
    # 豆包/ChatGPT 在各自子类有同名覆盖(签名略异),此处为小艺基线实现。
    # ------------------------------------------------------------------
    def _parse_pcm_fmt(self, remote):
        """从 PCM 文件名解析 (sample_rate, channels, sample_width)。

        文件名前缀 <流ID>_<采样率>_<声道>_<位深标志>_;位深标志 1=16bit(width=2)。
        与 _pcm_to_wav 同源解析逻辑;不可解析返回 None。
        """
        base = os.path.basename(remote)
        parts = re.sub(r'^r\d+_', '', base).split('_')
        try:
            sr, ch, bdf = int(parts[1]), int(parts[2]), int(parts[3])
        except (IndexError, ValueError):
            return None
        if bdf != 1:  # 仅支持 16-bit
            return None
        return sr, ch, 2

    def _find_ai_pcm_remote(self, device_sn, task_id=None, test_case_id=None):
        """在当前 app(PCM_APP_CONFIG[self._pcm_app]) 缓存目录找 AI 回复 PCM(ai_suffix)。

        多个匹配取 size 最大者(同 _pick_pcm 策略,避免选中静音探针流)。无匹配返回 None。
        小艺 ai_suffix=cap_client_ec_out.pcm(aibase); vassistant 的 client_in..pcm 时间轴
        不对齐,已从 ai_suffix 移除(详见 PCM_APP_CONFIG 注释)。
        """
        app = getattr(self, '_pcm_app', 'xiaoyi')
        cfg = self.PCM_APP_CONFIG.get(app) or {}
        ai_suffix = cfg.get('ai_suffix')
        if not ai_suffix:
            return None
        files = []
        for d in cfg.get('cache_dirs', []):
            files.extend(self._list_dir_pcm(device_sn, d))
        if not files:
            return None
        return self._pick_pcm(device_sn, files, ai_suffix,
                             task_id=task_id, test_case_id=test_case_id)

    def _read_tail_rms(self, device_sn, remote, tail_seconds=1.0,
                       task_id=None, test_case_id=None):
        """读 AI PCM 最后 tail_seconds 秒字节(经 base64 文本传输,二进制安全)算左声道 RMS。

        采样率/声道从文件名解析(小艺16k/豆包48k 均可),1s 尾部字节随之自适应。
        返回 (rms, size);文件不存在/不足尾部/读取失败返回 (None, size 或 None)。
        """
        fmt = self._parse_pcm_fmt(remote)
        if not fmt:
            self._log(level='DEBUG', content=f"_read_tail_rms 无法解析采样格式: {remote}",
                      task_id=task_id, test_case_id=test_case_id)
            return None, None
        sr, ch, sw = fmt
        tail_bytes = int(tail_seconds * sr * ch * sw)
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < tail_bytes:
            return None, (size if size >= 0 else None)
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=20,
            )
            raw = base64.b64decode(r.stdout)
            if len(raw) < 4:
                return None, size
            samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::ch]  # 取第一声道(ch=1 取全部, ch=2 取左声道)
            rms = (sum(s * s for s in mono) / len(mono)) ** 0.5 if mono else 0
            return rms, size
        except Exception as e:
            self._log(level='DEBUG', content=f"_read_tail_rms 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None, size

    def _scan_remote_for_speech(self, device_sn, remote, seconds=None,
                                energy_thr=None, task_id=None, test_case_id=None):
        """读最后 N 秒按 0.5s 窗算 RMS,任一窗>阈值视为近期有语音。

        用于"回复已结束但 post_process 起得晚"的兜底判定。返回 True/False。
        """
        if seconds is None:
            seconds = self.RMS_SCAN_SECONDS
        if energy_thr is None:
            energy_thr = self.RMS_THRESHOLD
        fmt = self._parse_pcm_fmt(remote)
        if not fmt:
            return False
        sr, ch, sw = fmt
        tail_bytes = int(seconds * sr * ch * sw)
        size = self._get_device_file_size(device_sn, remote)
        if size < 0 or size < sr * ch * sw:  # 至少 1s 数据
            return False
        try:
            r = subprocess.run(
                ['hdc', '-t', device_sn, 'shell',
                 f"tail -c {tail_bytes} '{remote}' | base64"],
                capture_output=True, timeout=40,
            )
            raw = base64.b64decode(r.stdout)
            samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)
            mono = samples[0::ch]  # 取第一声道(ch=1 取全部, ch=2 取左声道)
            win = int(0.5 * sr)
            for i in range(0, len(mono), win):
                c = mono[i:i + win]
                if not c:
                    break
                rms = (sum(s * s for s in c) / len(c)) ** 0.5
                if rms > energy_thr:
                    return True
        except Exception as e:
            self._log(level='DEBUG', content=f"_scan_remote_for_speech 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
        return False

    def _wait_ai_reply_start_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                    start_timeout=None, energy_thr=None, interval=1.0):
        """等 AI 开始回复(阶段A)：基于 AI PCM 尾部 1s RMS>阈值 判定 AI 开始说话。

        用于 barge-in 门：打断轮 post_process 检测到 AI 开始回复后即放下一轮打断音频，
        让打断发生在 AI 回复期间(而非 AI 说完之后)。仅复用 _wait_ai_reply_end_via_pcm
        的阶段 A 逻辑，不等说完(阶段 B)，避免改动正常轮。

        返回 (status, remote):
          'fresh'  = 刚检测到 AI 开始说话(barge-in 窗口打开)；记 self._ai_first_frame_ms
          'ended'  = start_timeout 内未检测到新语音，但近 scan_seconds 曾有语音(起得晚,回复已结束)
          'none'   = 未回复(无任何语音)
        """
        if start_timeout is None:
            start_timeout = self.RMS_START_TIMEOUT
        if energy_thr is None:
            energy_thr = self.RMS_THRESHOLD
        remote = None
        deadline_start = time.time() + start_timeout
        saw_speech = False
        while time.time() < deadline_start:
            if self._check_stop("post_process_等AI回复开始"):
                return 'none', remote
            remote = self._find_ai_pcm_remote(device_sn, task_id=task_id, test_case_id=test_case_id)
            if remote:
                rms, size = self._read_tail_rms(device_sn, remote, tail_seconds=1.0,
                                                task_id=task_id, test_case_id=test_case_id)
                if rms is not None and rms > energy_thr:
                    saw_speech = True
                    self._ai_first_frame_ms = int(time.time() * 1000)  # 回复起点(替代 size 增长)
                    self._log(level='INFO',
                              content=f"AI回复开始: {remote} size={size} tail_rms={rms:.0f}",
                              task_id=task_id, test_case_id=test_case_id)
                    break
            time.sleep(interval)
        if saw_speech:
            return 'fresh', remote
        # 兜底: post_process 起得晚、回复可能已结束——扫最后 scan_seconds 是否曾有语音
        if remote and self._scan_remote_for_speech(device_sn, remote, seconds=self.RMS_SCAN_SECONDS,
                                                   energy_thr=energy_thr,
                                                   task_id=task_id, test_case_id=test_case_id):
            self._log(level='INFO',
                      content="AI回复已结束(post_process起得晚,尾部虽静默但近15s曾有语音)",
                      task_id=task_id, test_case_id=test_case_id)
            return 'ended', remote
        self._log(level='INFO',
                  content=f"小艺未回复({start_timeout}s 内 AI PCM 尾部无语音能量)",
                  task_id=task_id, test_case_id=test_case_id)
        return 'none', remote

    def _wait_ai_reply_end_via_pcm(self, device_sn, task_id=None, test_case_id=None,
                                   interval=1.0):
        """等 AI 回复完成: 基于 AI PCM 尾部 RMS 能量判定(双阶段+历史兜底)。

        阶段A: 等尾部 1s RMS>阈值(AI 开始说话), start_timeout 内。
               ——必须先看到说话,避免在用户提问期(AI 通道静默)误判"说完"。
               超时则扫最后 scan_seconds 历史:曾有语音→回复已结束(起得晚)→True;
               否则未回复→False。
        阶段B: AI 开说过后,等连续 silence_seconds 秒 RMS<阈值(说完回静默)。
        实测: 回复中停顿≤6s, 回复后静默很长, silence_seconds=8 不误触发。

        返回: True=回复结束(或超时但已说过,视为已回复); False=未回复。
        """
        remote = None
        # 阶段A: 等 AI 开始说话
        deadline_start = time.time() + self.RMS_START_TIMEOUT
        saw_speech = False
        while time.time() < deadline_start:
            if self._check_stop("post_process_等AI回复开始"):
                return False
            remote = self._find_ai_pcm_remote(device_sn, task_id=task_id, test_case_id=test_case_id)
            if remote:
                rms, size = self._read_tail_rms(device_sn, remote,
                                                task_id=task_id, test_case_id=test_case_id)
                if rms is not None and rms > self.RMS_THRESHOLD:
                    saw_speech = True
                    self._log(level='INFO',
                              content=f"AI回复开始: {remote} size={size} tail_rms={rms:.0f}",
                              task_id=task_id, test_case_id=test_case_id)
                    break
            time.sleep(interval)
        if not saw_speech:
            # 兜底: post_process 起得晚、回复可能已结束——扫最后 15s 是否曾有语音
            if remote and self._scan_remote_for_speech(device_sn, remote,
                                                       task_id=task_id, test_case_id=test_case_id):
                self._log(level='INFO',
                          content="AI回复已结束(post_process起得晚,尾部虽静默但近15s曾有语音)",
                          task_id=task_id, test_case_id=test_case_id)
                return True
            self._log(level='INFO',
                      content=f"小艺未回复({self.RMS_START_TIMEOUT}s 内 AI PCM 尾部无语音能量)",
                      task_id=task_id, test_case_id=test_case_id)
            return False

        # 阶段B: 等 AI 说完(连续 silence_seconds 秒 RMS<阈值)
        silence_since = None
        deadline_end = time.time() + self.RMS_END_TIMEOUT
        while time.time() < deadline_end:
            if self._check_stop("post_process_等AI回复结束"):
                return False
            rms, size = self._read_tail_rms(device_sn, remote,
                                            task_id=task_id, test_case_id=test_case_id)
            now = time.time()
            if rms is None:
                time.sleep(interval)
                continue
            if rms >= self.RMS_THRESHOLD:
                silence_since = None  # 还在说,重置
            else:
                if silence_since is None:
                    silence_since = now
                elif (now - silence_since) >= self.RMS_SILENCE_SECONDS:
                    self._log(level='INFO',
                              content=(f"AI回复结束(尾部静默 {self.RMS_SILENCE_SECONDS}s, "
                                       f"size={size} rms={rms:.0f})"),
                              task_id=task_id, test_case_id=test_case_id)
                    return True
            time.sleep(interval)
        # 超时: 已开说过但未等到静默(回复过长被截断),视为已回复
        self._log(level='WARNING',
                  content=(f"等待AI回复结束超时 {self.RMS_END_TIMEOUT}s"
                           f"(已说过但未静默,视为已回复可能截断)"),
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def _pick_pcm(self, device_sn, files, suffix, exclude=None,
                  task_id=None, test_case_id=None):
        """从文件列表中按后缀匹配一个 pcm 路径，多个匹配时【取文件最大者】。

        suffix 支持单个字符串或列表(任一后缀匹配即可)，用于小艺 AI 回复
        同时存在 cap_client_ec_out.pcm 和 client_in..pcm 两种命名的情况。

        cap_client 在一次会话里可能写多个同名后缀流：真麦克风采集流(有声、
        时长最长、size 最大) + 若干探针/回声流(静音、size 小)。若按文件名排序
        取最后一个，可能恰好选中静音探针流(如 *_1_1_cap_client_out.pcm)，
        导致转出的 user_wav 无声。故改为按设备上实际文件 size 取最大。

        size 全部取不到(stat 失败/全 0)时退回按文件名排序取最后一个,保持旧行为。
        """
        suffixes = [suffix] if isinstance(suffix, str) else suffix
        matches = [f for f in files
                   if any(f.endswith(s) for s in suffixes) and f != exclude]
        if not matches:
            return None
        sized = []
        for f in matches:
            sz = self._get_device_file_size(device_sn, f)
            sized.append((sz, f))
        # 仅当至少一个 size>0 时按 size 降序取最大;否则退回按名取最后(旧行为)
        if any(sz > 0 for sz, _ in sized):
            sized.sort(key=lambda t: t[0], reverse=True)
            picked = sized[0][1]
            self._log(level='DEBUG',
                      content=f"pick_pcm 按size取最大: suffix={suffix} picked={picked} "
                              f"candidates={[(s, os.path.basename(f)) for s, f in sized]}",
                      task_id=task_id, test_case_id=test_case_id)
            return picked
        matches.sort()
        return matches[-1]

    def _recv_pcm(self, device_sn, remote_path, local_path, task_id=None, test_case_id=None, app='', role=''):
        """从设备拉取单个 pcm 文件到本地，成功返回 local_path，失败返回 None"""
        if not remote_path:
            return None
        try:
            subprocess.run(['hdc', '-t', device_sn, 'file', 'recv', remote_path, local_path],
                           check=False, capture_output=True, text=True, timeout=120)
        except Exception as e:
            self._log(level='WARNING', content=f"{app} {role} pcm 拉取异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        if not os.path.exists(local_path):
            self._log(level='WARNING', content=f"{app} {role} pcm 拉取失败: remote={remote_path}",
                      task_id=task_id, test_case_id=test_case_id)
            return None
        self._log(level='INFO', content=f"{app} {role} pcm 拉取成功: {local_path}",
                  task_id=task_id, test_case_id=test_case_id)
        return local_path

    def _pull_pcm(self, device_sn, app='xiaoyi', task_id=None, test_case_id=None, round_number=None):
        # 获取小艺对话pcm。AI 回复 cap_client_ec_out.pcm、用户输入 cap_client_out.pcm,
        # 均在 aibase/cache。⚠️ vassistant/cache 的 client_in..pcm 时间轴不对齐, 不取(已弃用)。
        # 获取豆包对话PCM，文件位置:/data/app/el2/100/base/com.larus.nova.hm/cache/, 用户输入名称格式100186_48000_2_1_cap_client_out.pcm。AI助手回复名称格式100184_48000_2_1_client_in..pcm
        # 获取chagpt对话PCM，文件位置：/data/local/tmp/。用户输入名称格式100174_48000_2_1_cap_client_out.pcm。AI助手回复名称格式100175_48000_2_1_cap_client_in.pcm
        #
        # 按 app 参数选择对应 app 的缓存目录与文件后缀:
        # - 小艺(xiaoyi):   aibase/cache            用户 cap_client_out.pcm  / AI cap_client_ec_out.pcm(vassistant 的 client_in..pcm 时间轴不对齐, 不取)
        # - 豆包(doubao):   .../com.larus.nova.hm/cache      用户 cap_client_out.pcm        / AI client_in..pcm
        # - chatgpt:        /data/local/tmp                  用户 cap_client_out.pcm        / AI cap_client_in.pcm
        # 返回: {'user': local_path_or_None, 'ai': local_path_or_None, 'user_remote':..., 'ai_remote':...}
        # 本地文件名加轮次前缀 r{round_number}_, 如 r1_100184_48000_2_1_cap_client_out.pcm,
        # 便于多轮场景区分各轮 pcm 文件; _pcm_to_wav 解析时会剥离该前缀。
        result = {'user': None, 'ai': None, 'user_remote': None, 'ai_remote': None}
        cfg = self.PCM_APP_CONFIG.get(app)
        if not cfg:
            self._log(level='WARNING', content=f"未知 pcm app: {app}, 跳过拉取",
                      task_id=task_id, test_case_id=test_case_id)
            return result
        user_suffix = cfg['user_suffix']
        ai_suffix = cfg['ai_suffix']

        local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_pcm',
                                 str(task_id) if task_id else 'default_task_id',
                                 str(test_case_id) if test_case_id else 'default_id',
                                 device_sn)
        os.makedirs(local_dir, exist_ok=True)

        # 聚合该 app 所有缓存目录下的 pcm 文件
        files = []
        for remote_dir in cfg['cache_dirs']:
            files.extend(self._list_dir_pcm(device_sn, remote_dir))
        if not files:
            self._log(level='DEBUG', content=f"{app} 目录无 pcm 文件: {cfg['cache_dirs']}",
                      task_id=task_id, test_case_id=test_case_id)
            return result
        # 诊断: 打印设备上找到的所有 pcm 文件完整路径,便于排查"未匹配到"问题
        self._log(level='DEBUG',
                  content=f"{app} 设备 pcm 文件({len(files)}个): {files}",
                  task_id=task_id, test_case_id=test_case_id)

        # 用户输入与 AI 回复按后缀区分；ai 排除已选中的用户文件避免后缀包含导致误匹配
        user_remote = self._pick_pcm(device_sn, files, user_suffix,
                                     task_id=task_id, test_case_id=test_case_id)
        ai_remote = self._pick_pcm(device_sn, files, ai_suffix, exclude=user_remote,
                                   task_id=task_id, test_case_id=test_case_id)

        for role, remote in (('user', user_remote), ('ai', ai_remote)):
            if not remote:
                self._log(level='DEBUG',
                          content=f"{app} 未匹配到 {role} pcm (后缀 user={user_suffix} ai={ai_suffix})",
                          task_id=task_id, test_case_id=test_case_id)
                continue
            remote_base = os.path.basename(remote)
            # 加轮次前缀 r{round_number}_, 便于多轮区分; round_number 为 None 时不加前缀(保持兼容)
            if round_number is not None:
                local_name = f"r{round_number}_{remote_base}"
            else:
                local_name = remote_base
            local_path = os.path.join(local_dir, local_name)
            pulled = self._recv_pcm(device_sn, remote, local_path,
                                    task_id=task_id, test_case_id=test_case_id, app=app, role=role)
            if pulled:
                result[role] = pulled
                result[f'{role}_remote'] = remote
        return result

    def _pull_pcm_wav(self, device_sn, app='xiaoyi', task_id=None, test_case_id=None, round_number=None):
        """拉取指定 app 的用户输入/AI 回复 pcm 并转为 wav。

        round_number: 轮次号,传给 _pull_pcm 用于本地文件名加 r{round}_ 前缀。
        返回 (user_wav_path_or_None, ai_wav_path_or_None)。

        小艺走 DSP 层 audio_hook(in_after_imedia_asr_module* / in_raw1*),
        替换 fwk 层 cap_client_*;豆包/ChatGPT 走原 fwk 逻辑。
        """
        if app == 'xiaoyi':
            return self._pull_dsp_pcm_wav(device_sn, task_id=task_id,
                                          test_case_id=test_case_id, round_number=round_number)
        pulled = self._pull_pcm(device_sn, app=app, task_id=task_id,
                                test_case_id=test_case_id, round_number=round_number)
        user_pcm = pulled.get('user')
        ai_pcm = pulled.get('ai')
        user_wav = self._pcm_to_wav(user_pcm, task_id=task_id, test_case_id=test_case_id) if user_pcm else None
        ai_wav = self._pcm_to_wav(ai_pcm, task_id=task_id, test_case_id=test_case_id) if ai_pcm else None
        return user_wav, ai_wav

    # ------------------------------------------------------------------
    # DSP 层 audio_hook PCM(仅小艺用)
    # ------------------------------------------------------------------
    def _enable_dsp_audio_dump(self, device_sn, task_id=None, test_case_id=None):
        """开启 DSP 层 audio 抓取(照 AudioLogTools/1.start-dump-smartpa.bat 的 DSP 子集,幂等)。

        产物落 /data/vendor/log/audio_logs/audio_hook/:in_after_imedia_asr_module*(用户4ch)
        与 in_raw1*(模型2ch),时间轴对齐。仅小艺用(替换 fwk write*.enable)。
        豆包/ChatGPT 不调用。每步 try/except 不中断后续。
        """
        lg = lambda msg, lv='INFO': self._log(level=lv, content=msg,
                                              task_id=task_id, test_case_id=test_case_id)

        def sh(*args):
            return self._hdc_shell(device_sn, *args)

        try:
            sh('mount', '-o', 'rw,remount', '/')
            self._hdc_shell(device_sn, 'target', 'mount')
            sh('setenforce', '0')
        except Exception as e:
            lg(f"[DSP] 挂载/setenforce 失败(继续): {e}", 'WARNING')

        try:
            sh('pkill', 'dhifimesg')
        except Exception:
            pass

        # 版本对齐推送 audiodebug: 探测 libaudio_proxy_<V>.z.so, 命中则推对应二进制;
        # 不命中(如 6.0,本地无对应二进制)则探测设备是否已有可用 audiodebug,有就用,不报错。
        pushed_audiodebug = False
        for v in self.DSP_AUDIODEBUG_VERSIONS:
            local_bin = os.path.join(self.DSP_BIN_DIR, f'audiodebug_{v}')
            if not os.path.exists(local_bin):
                continue
            probe = sh('find', '/system', '-name', f'libaudio_proxy_{v}.z.so')
            if probe.stdout and f'libaudio_proxy_{v}' in probe.stdout:
                subprocess.run(['hdc', '-t', device_sn, 'file', 'send', local_bin, '/system/bin/audiodebug'],
                               check=False, capture_output=True, text=True, timeout=30)
                sh('chmod', '777', '/system/bin/audiodebug')
                lg(f"[DSP] 推送 audiodebug_{v} → /system/bin/audiodebug (匹配 libaudio_proxy_{v}.z.so)")
                pushed_audiodebug = True
                break
        if not pushed_audiodebug:
            # 探测设备自带的 audiodebug(如 6.0 系统/之前装过)
            ab = sh('ls', '/system/bin/audiodebug')
            if ab.returncode == 0 and ab.stdout.strip():
                lg("[DSP] 未推送 audiodebug(本地无匹配版本),使用设备自带 /system/bin/audiodebug")
            else:
                lg("[DSP] 未匹配 audiodebug 版本且设备无自带 audiodebug,audio_hook 可能无 PCM 产出",
                   'ERROR')

        def inject2(cmd):
            try:
                subprocess.run(['hdc', '-t', device_sn, 'shell',
                                f'echo {cmd} > /proc/hifidebug/dspfaultinject'],
                               check=False, capture_output=True, text=True, timeout=10)
            except Exception as e:
                lg(f"[DSP] dspfaultinject '{cmd}' 异常: {e}", 'WARNING')

        inject2('hook_data_to_ap stop')
        inject2('hifi_test_set_poweroff_enable_flag false')
        inject2('audio_cmd histen,cmd,8')
        inject2('audio_cmd histen_lite,cmd,8')

        for p in ('primary dump_file off', 'primary dump_file all', 'primary dump_file on'):
            sh('audiodebug', 'setparameter', *p.split())

        # hifi 日志 daemon(PCM hook 依赖其运行)
        dhifimesg_bin = os.path.join(self.DSP_BIN_DIR, 'dhifimesg')
        if os.path.exists(dhifimesg_bin):
            subprocess.run(['hdc', '-t', device_sn, 'file', 'send', dhifimesg_bin, '/system/bin/dhifimesg'],
                           check=False, capture_output=True, text=True, timeout=30)
            sh('chmod', '777', '/system/bin/dhifimesg')
            sh('dhifimesg', '-D')

        # 目录(audio_hook 可能已存在, -p 兼容)
        sh('mkdir', '-p', '/data/hisi_logs/om_data')
        sh('mkdir', '-p', '/data/data/.pulse_dir')
        sh('mkdir', '-p', '/data/vendor/log/audio_logs')
        sh('mkdir', '-p', self.DSP_AUDIO_HOOK_DIR)

        inject2('hook_data_to_ap start')
        sh('audiodebug', 'setparameter', 'primary', 'hookChannel', str(self.DSP_HOOKCHANNEL))
        sh('param', 'set', 'vendor.cust.audio.dump', 'true')
        for d in ('/data/data/.pulse_dir', '/data/local/tmp', '/data/hisi_logs/om_data', self.DSP_AUDIO_HOOK_DIR):
            sh('chmod', '777', d)
        inject2('hook_data_to_ap start')  # 二次确保
        lg("[DSP] DSP audio dump 已开启(audio_hook): "
           f"user={self.DSP_USER_PREFIX}* ai={self.DSP_AI_PREFIX}*")

    def _clear_dsp_audio_hook(self, device_sn, task_id=None, test_case_id=None):
        """清理 audio_hook 目录(子目录 + stub + 旧 pcm),供 pre_process/teardown 调用。

        rm -rf <dir>/* 清整个 audio_hook 内容(hook tap stub 与 CustStreamConfig 会被系统重建)。
        """
        try:
            self._hdc_shell(device_sn, 'shell',
                            f'rm -rf {self.DSP_AUDIO_HOOK_DIR}/*')
            self._log(level='DEBUG', content=f"[DSP] 已清 {self.DSP_AUDIO_HOOK_DIR}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"[DSP] 清 audio_hook 异常: {e}",
                      task_id=task_id, test_case_id=test_case_id)

    def _pull_dsp_pcm_wav(self, device_sn, task_id=None, test_case_id=None, round_number=None):
        """从 audio_hook 拉取 DSP 层 用户/模型 PCM 并转 wav。

        前缀匹配(非后缀):in_after_imedia_asr_module*(用户4ch→抽ch0 mono)、
        in_raw1*(模型2ch)。多个匹配取 size 最大者(避开 0 字节 stub)。
        返回 (user_wav_path_or_None, ai_wav_path_or_None)。
        """
        # 列 audio_hook 下所有 .pcm(递归,文件可能在 pcm_in_22_*/pcm_out_21_* 子目录)
        r = self._hdc_shell(device_sn, 'find', self.DSP_AUDIO_HOOK_DIR,
                            '-name', '*.pcm', '-type', 'f')
        files = [line.strip() for line in (r.stdout or '').splitlines() if line.strip()]
        self._log(level='DEBUG',
                  content=f"[DSP] audio_hook pcm({len(files)}个): {files}",
                  task_id=task_id, test_case_id=test_case_id)

        local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_pcm',
                                 str(task_id) if task_id else 'default_task_id',
                                 str(test_case_id) if test_case_id else 'default_id',
                                 device_sn)
        os.makedirs(local_dir, exist_ok=True)

        def pick_by_prefix(prefix):
            matched = [f for f in files if os.path.basename(f).startswith(prefix)]
            if not matched:
                return None
            # 取 size 最大者(避开 0 字节 stub)
            best, best_sz = None, -1
            for f in matched:
                sz = self._get_device_file_size(device_sn, f)
                if sz > best_sz:
                    best, best_sz = f, sz
            return best

        user_remote = pick_by_prefix(self.DSP_USER_PREFIX)
        ai_remote = pick_by_prefix(self.DSP_AI_PREFIX)

        user_wav = ai_wav = None
        sr_u, ch_u, sw_u = self.DSP_USER_FMT
        sr_a, ch_a, sw_a = self.DSP_AI_FMT
        for role, remote, fmt, extract in (
            ('user', user_remote, self.DSP_USER_FMT, self.DSP_USER_EXTRACT_CHANNEL),
            ('ai', ai_remote, self.DSP_AI_FMT, None),
        ):
            if not remote:
                self._log(level='DEBUG',
                          content=f"[DSP] 未匹配到 {role} pcm (prefix "
                                  f"{self.DSP_USER_PREFIX if role=='user' else self.DSP_AI_PREFIX})",
                          task_id=task_id, test_case_id=test_case_id)
                continue
            remote_base = os.path.basename(remote)
            local_name = f"r{round_number}_{remote_base}" if round_number is not None else remote_base
            local_path = os.path.join(local_dir, local_name)
            pulled = self._recv_pcm(device_sn, remote, local_path,
                                    task_id=task_id, test_case_id=test_case_id,
                                    app='xiaoyi', role=role)
            if pulled:
                wav = self._pcm_to_wav_fixed(pulled, fmt[0], fmt[1], fmt[2],
                                             extract_channel=extract,
                                             task_id=task_id, test_case_id=test_case_id)
                if role == 'user':
                    user_wav = wav
                else:
                    ai_wav = wav
        return user_wav, ai_wav

    @with_rpc_retry()
    def initialize(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        if not super().initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs):
            return False
        driver = self._get_driver(device_sn)
        if not driver:
            return False
        # 重置跨用例残留的录屏状态（驱动为单例，跨用例复用，避免上个用例的标志位污染本次）
        self._recording = False
        self._record_mode = kwargs.get('record_mode', 'round')
        self._total_rounds = 1
        self._round_number = 0
        self._record_file_name = None
        self._record_pulled = False
        self._record_device_path = None  # 重置: 避免上个用例的 VID 路径残留
        # pcm 抓取目标 app（当前驱动默认只抓小艺；可通过 kwargs.pcm_app 切换 doubao/chatgpt）
        self._pcm_app = kwargs.get('pcm_app', 'xiaoyi')
        # 开启抓取pcm权限: 小艺用 DSP 层 audio_hook(替换 fwk write*.enable);
        # 豆包/ChatGPT 各自重写 initialize 跑自己的 write*.enable,基类这条 fwk 兜底分支
        # 实际只服务 小艺 之外的兜底场景,保留不动。
        if self._pcm_app == 'xiaoyi':
            self._enable_dsp_audio_dump(device_sn, task_id=task_id, test_case_id=test_case_id)
        else:
            driver.shell("mount -o rw,remount /")
            driver.shell("param set sys.audio.dump.writeserver.enable w")
            driver.shell("param set sys.audio.dump.writehdi.enable w")
            driver.shell("param set sys.audio.dump.writeclient.enable a")
            driver.shell("chmod 777 /data/local/tmp")
        # 清空闹钟(ALARM_CLOCK 表),避免测试中途闹钟响铃打断用例
        self._clear_alarms(device_sn, task_id=task_id, test_case_id=test_case_id)
        # 清理设备上残留的 pcm 缓存(防止上个用例 teardown 失败残留干扰本轮)
        self._clear_pcm(device_sn, app=self._pcm_app,
                        task_id=task_id, test_case_id=test_case_id)
        if self._pcm_app == 'xiaoyi':
            # DSP 层 audio_hook 也要清(防止上轮残留干扰本轮基线)
            self._clear_dsp_audio_hook(device_sn, task_id=task_id, test_case_id=test_case_id)
        # 点开小艺聊天窗口
        # 注:08-17 fdb087a43 曾注掉此段(假设窗口已开只点通话按钮),
        # 但实测窗口常不在前台→pre_process 通话 SymbolGlyph 找不到→小艺没打开,故解回。
        user_center = driver.find_component(By.text("小艺"))
        if user_center:
            user_center.click()
            time.sleep(2)
            self._log(level='DEBUG', content="initialize: 已点开小艺聊天窗口",
                      task_id=task_id, test_case_id=test_case_id)
        else:
            self._log(level='WARNING', content="initialize: 未找到'小艺'入口,聊天窗口可能未打开(后续 pre_process 点通话按钮可能失败)",
                      task_id=task_id, test_case_id=test_case_id)
        # 清除上下文
        # 进入设置界面

        # 根据条件点击控件
        driver.touch((1154, 234))
        driver.wait(2)
        clear_text = driver.find_component(By.text('清除上下文'))
        if clear_text:
            clear_text.click()
            time.sleep(2)
        # 进入设置界面删除对话记录
        driver.touch((1154, 234))
        driver.wait(2)
        clear_chat = driver.find_component(By.text("删除对话记录"))
        if clear_chat:
            clear_chat.click()
            time.sleep(1)
            # 确认删除
            delete_button = driver.find_component(By.text("删除"))
            if delete_button:
                delete_button.click()
                time.sleep(1)


        return True

    @with_rpc_retry()
    def pre_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        # 打印 kwargs 参数用于调试
        self._log(level='DEBUG',
                  content=f"pre_process kwargs: {kwargs}",
                  task_id=task_id, test_case_id=test_case_id)
        # 录屏模式: round=每轮一段（默认）; case=整用例一段
        record_mode = kwargs.get('record_mode', 'round')
        total_rounds = kwargs.get('total_rounds', 1)
        round_number = kwargs.get('round_number', 0)
        self._record_mode = record_mode
        self._total_rounds = total_rounds
        self._round_number = round_number
        is_first = not getattr(self, '_recording', False)
        # 先停华为音乐 + 清闹钟: 音乐 app 若被上轮误识别"播放音乐"拉起,其音频正被 dump 写到
        # 打开文件,必须先 force-stop 关掉(释放 dump 句柄)再清 PCM,否则 rm 删到仍打开的文件→
        # "写入中清空"。放在 case 分支之前,每轮都清。
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)
        # 每轮清空闹钟(ALARM_CLOCK 表),防止上轮测试设的闹钟响铃打断本轮
        self._clear_alarms(device_sn, task_id=task_id, test_case_id=test_case_id)
        # 清理 pcm 缓存: round 每轮清(上轮拉取后残留)、case 仅首轮清(中间轮不能清,
        # 会破坏连续通话已积累的音频)。打断轮不清(pcm 可能仍在写入/尚未拉取)。
        # 时序安全: 正常轮 post_process 用 UI 文案(说话可打断/正在听…)等 AI 说完才返回,
        # 到 get_results 时 AI 的 dump 文件已关闭;此处又先停了音乐,故清的是已关闭文件,不会
        # "写入中清空"。
        # 残留风险: 若系统音频 dump(sys.audio.dump.write*)跨轮保持文件句柄常开,仍可能清坏——
        # 真机验证若再拉不到,改为清前 param set ...enable n 关 dump→rm→enable w 重开。
        is_interruption = kwargs.get('is_interruption') in (True, 'true', '1', 1)
        if (record_mode != 'case' or is_first) and not is_interruption:
            self._clear_pcm(device_sn, app=getattr(self, '_pcm_app', 'xiaoyi'),
                            task_id=task_id, test_case_id=test_case_id)
            # 小艺 DSP 层 audio_hook 也要清(轮首清上轮残留)
            if getattr(self, '_pcm_app', 'xiaoyi') == 'xiaoyi':
                self._clear_dsp_audio_hook(device_sn, task_id=task_id, test_case_id=test_case_id)
        # ai PCM 首帧基准：必须在 _clear_pcm 之后快照,保证基线干净(清完残留再建基线)
        self._ai_first_frame_ms = None
        self._ai_pcm_size_base = self._snapshot_ai_pcm_sizes(
            device_sn, app=getattr(self, '_pcm_app', 'xiaoyi'))

        # case 模式非首轮：通话与录屏已在进行，无需重复启动
        if record_mode == 'case' and not is_first:
            self._log(level='DEBUG',
                      content=f"case模式非首轮,跳过启动录屏(录屏进行中): r{round_number}/{total_rounds}",
                      task_id=task_id, test_case_id=test_case_id)
            return True

        # 开启通话聊天（首轮）
        # 根据条件点击控件
        driver.touch(By.isAfter(By.key('ChatTitleMenu')).isBefore(By.key('title_bar.broadcastType.icon')).type('SymbolGlyph'))
        driver.wait(2)
        try:
            if driver.find_component(By.text("小艺")):
                self._log(level='DEBUG', content="成功进行通话", task_id=task_id, test_case_id=test_case_id)
        except Exception:
            self._log(level='ERROR', content="通话失败", task_id=task_id, test_case_id=test_case_id)
            return False
        # 开启录屏
        if record_mode == 'case':
            # 整用例一个文件，不带轮次后缀
            self._record_file_name = f"{test_case_id}.mp4"
        else:
            # 每轮一个文件，文件名含轮次号避免多轮冲突
            self._record_file_name = f"{test_case_id}_r{round_number}.mp4"
        if not self._start_recorder(device_sn, file_name=self._record_file_name):
            self._log(level='ERROR', content=f"启动录屏失败,服务未运行: {self._record_file_name}",
                      task_id=task_id, test_case_id=test_case_id)
            return False
        self._recording = True
        self._log(level='INFO', content=f"启动录屏成功: {self._record_file_name}", task_id=task_id,
                  test_case_id=test_case_id)
        time.sleep(2)
        return True

    @with_rpc_retry()
    def post_process(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        driver = self._get_driver(device_sn)
        # 打印接收到的播放时间戳（验证链路）
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[post_process] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']} "
                          f"detail_count={len(ts['detail']) if ts['detail'] else 0})",
                  task_id=task_id, test_case_id=test_case_id)

        # 打断轮(is_interruption=True):不等 AI 回复完成,直接收尾进入下一轮 pre_process
        if kwargs.get('is_interruption') in (True, 'true', '1', 1):
            self._log(level='INFO', content='is_interruption=True,跳过等待 AI 回复完成,直接收尾',
                      task_id=task_id, test_case_id=test_case_id)
            replied = True
        else:
            # 检测 ai PCM 首帧(模型回复起始时刻,替代录屏 first_frame)
            self._ai_first_frame_ms = self._detect_ai_pcm_first_frame(
                device_sn, app=getattr(self, '_pcm_app', 'xiaoyi'),
                task_id=task_id, test_case_id=test_case_id)
            # ===== 开始回复检测（UI 法）：等"说话可打断"控件消失=AI 开始说话 =====
            replied = self._wait_for_condition(
                lambda: driver.find_component(By.text("说话可打断")) is None,
                timeout=300, interval=1,
                operation_name='等待回复开始',
            )
            if not replied:
                self._log(level='INFO', content='小艺未回复', task_id=task_id, test_case_id=test_case_id)
                self.question_text = '小艺识别为空'
                self.answer_text = '小艺回复为空'
            else:
                self._log(level='INFO', content='模型成功回复', task_id=task_id, test_case_id=test_case_id)
                # ===== 结束回复检测（UI 法）：等"说话可打断"重现 + "正在听…"出现 =====
                self._wait_for_condition(
                    lambda: driver.find_component(By.text('说话可打断')),
                    timeout=10, interval=1, operation_name="post_process_说话可打断"
                )
                self._wait_for_condition(
                    lambda: driver.find_component(By.text('正在听…')),
                    timeout=300, interval=1, operation_name="post_process_正在听"
                )
        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        # case 模式打断轮非末轮：延迟 5s 再进下一轮播放（可被停止/暂停打断）
        if (kwargs.get('is_interruption') in (True, 'true', '1', 1)
                and record_mode == 'case' and not is_last):
            self._log(level='INFO',
                      content=f"打断轮结束,等待5s后进入下一轮播放: r{round_number}/{total_rounds}",
                      task_id=task_id, test_case_id=test_case_id)
            for _ in range(10):  # 10 * 0.5s = 5s
                if self._check_stop('轮间延迟5s'):
                    return True
                time.sleep(0.5)

        if record_mode == 'case':
            # case 模式：中间轮不停录屏、不挂断（保持通话与录屏连续）；
            # 仅末轮停止录屏，以便 get_results 拉取完整文件；全程不在此挂断，交给 teardown 兜底
            if is_last:
                if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(5)
        else:
            # round 模式：每轮停止录屏 + 挂断（原逻辑）
            if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                self._log(level='WARNING', content="停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
            else:
                self._log(level='INFO', content="停止录屏成功", task_id=task_id, test_case_id=test_case_id)
            self._recording = False
            time.sleep(5)
            # 通话挂断
            try:
                # 根据条件点击控件
                hangup_btn = driver.find_component(
                    By.isAfter(By.key('live.tool_bar.hangup_button')).isBefore(By.key('GuideText')).type('SymbolGlyph'))
                if hangup_btn:
                    hangup_btn.click()
            except Exception as e:
                self._log(level='WARNING', content=f"挂断通话失败: {e}", task_id=task_id, test_case_id=test_case_id)
            driver.wait(5)
        if not replied:
            driver.wait(5)
            return True
        # 提取聊天文本，取最后一条（本轮），未识别到则返回 None
        question_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Row/Text'))
        self._log(level='DEBUG', content=f"question_components count={len(question_components) if question_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if question_components:
            for i, comp in enumerate(question_components):
                self._log(level='DEBUG', content=f"question_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.question_text = question_components[-1].getText() if question_components else None
        answer_components = driver.find_all_components(By.xpath(
            '//ListItem//GridRow/GridCol/Row/__Common__/__Common__/Column//Stack/Text'))
        self._log(level='DEBUG', content=f"answer_components count={len(answer_components) if answer_components else 0}",
                  task_id=task_id, test_case_id=test_case_id)
        if answer_components:
            for i, comp in enumerate(answer_components):
                self._log(level='DEBUG', content=f"answer_comp[{i}] text={comp.getText()}",
                          task_id=task_id, test_case_id=test_case_id)
        self.answer_text = answer_components[-1].getText() if answer_components else None

        return True

    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> list:
        # 打印接收到的播放时间戳（验证链路）
        ts = self._extract_playback_timestamps(kwargs)
        self._log(level='INFO',
                  content=f"[get_results] 播放时间戳 "
                          f"start={ms_to_utc8_str(ts['start_ms'], MS_FMT)} "
                          f"end={ms_to_utc8_str(ts['end_ms'], MS_FMT)} "
                          f"(start_ms={ts['start_ms']} end_ms={ts['end_ms']} "
                          f"detail_count={len(ts['detail']) if ts['detail'] else 0})",
                  task_id=task_id, test_case_id=test_case_id)
        # 无录屏驱动(Doubao/ChatGPT):跳过录屏拉取,只拉 pcm/wav,
        # 把 ai_wav 塞进 wav_path 复用 wav_path→record_file 映射喂评估。
        if not getattr(self, '_record_enabled', True):
            user_wav, ai_wav = self._pull_pcm_wav(
                device_sn, app=getattr(self, '_pcm_app', 'xiaoyi'),
                task_id=task_id, test_case_id=test_case_id,
                round_number=getattr(self, '_round_number', None))
            question_text = getattr(self, 'question_text', None)
            answer_text = getattr(self, 'answer_text', None)
            self._log(level='INFO',
                      content=f"[get_results] 无录屏模式: user_wav={user_wav} ai_wav={ai_wav} "
                              f"question={question_text!r} answer={answer_text!r}",
                      task_id=task_id, test_case_id=test_case_id)
            return [{
                'success': True,
                'message': 'Success (no recording, ai_wav as record_file)',
                'record_path': '',
                'record_device_path': '',
                'wav_path': ai_wav or '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': getattr(self, '_ai_first_frame_ms', None),
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
            }]
        record_file_name = getattr(self, '_record_file_name', 'record.mp4')
        question_text = getattr(self, 'question_text', None)
        answer_text = getattr(self, 'answer_text', None)
        # first_frame_ms 优先用 ai PCM 首帧(模型回复起始时刻)，缺失则回退录屏 first_frame
        first_frame_ms = getattr(self, '_ai_first_frame_ms', None) or getattr(self, '_recorder_first_frame_ms', None)
        wav_path = None
        query = None
        device_path = ''
        local_path = ''
        recv_result = None
        user_wav = None
        ai_wav = None
        # case 模式且录屏仍在进行（非末轮）：录屏 mp4 是整段文件，中途拉是半截，留到末轮；
        # 但对话 pcm（user_wav/ai_wav）每轮都要拉并传给评估系统（打断/话轮等指标需要逐轮音频），
        # 不能因录屏未结束就给空串，否则 interruption_metrics 报 missing user_wav。
        if getattr(self, '_record_mode', 'round') == 'case' and getattr(self, '_recording', False):
            pcm_app = getattr(self, '_pcm_app', 'xiaoyi')
            user_wav, ai_wav = self._pull_pcm_wav(
                device_sn, app=pcm_app, task_id=task_id, test_case_id=test_case_id,
                round_number=getattr(self, '_round_number', None))
            self._log(level='DEBUG',
                      content=f"case模式录屏进行中,跳过录屏mp4,仍拉对话pcm: user_wav={user_wav} ai_wav={ai_wav}",
                      task_id=task_id, test_case_id=test_case_id)
            return [{
                'success': True,
                'message': 'recording in progress (pcm pulled, mp4 deferred to final round)',
                'record_path': '',
                'record_device_path': getattr(self, '_record_device_path', '') or '',
                'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
            }]
        # 拉取对话 pcm 并转 wav（用户输入 + AI 回复），抓取目标 app 由 _pcm_app 指定
        pcm_app = getattr(self, '_pcm_app', 'xiaoyi')
        user_wav, ai_wav = self._pull_pcm_wav(device_sn, app=pcm_app,
                                              task_id=task_id, test_case_id=test_case_id,
                                              round_number=getattr(self, '_round_number', None))
        try:
            # 优先用 _start_recorder 发现的真实 VID 路径直接 recv(绕开 mediatool 按 CustomizedFileName
            # 查询——后者对部分文件名报 "displayName format is not correct" 而查不到,case 模式尤其常见)
            device_path = getattr(self, '_record_device_path', None) or ''
            query = None
            if not device_path:
                self._log(level='WARNING',
                          content=f"_record_device_path 为空（录屏启动时未发现新 mp4），回退 mediatool query: {record_file_name}",
                          task_id=task_id, test_case_id=test_case_id)
                query = self._hdc_shell(device_sn, 'mediatool', 'query', record_file_name, '-u')
                lines = query.stdout.strip().split('\n')
                device_path = lines[1].strip() if len(lines) > 1 else ''
                if 'uri' in query.stdout and len(lines) > 2:
                    subprocess.run(
                        ['hdc', '-t', device_sn, 'shell', 'mediatool', 'recv', lines[2].strip(), '/data/local/tmp'],
                        check=False, capture_output=True, text=True, timeout=120
                    )
                    device_path = f'/data/local/tmp/{record_file_name}'
            if not device_path:
                self._log(level='ERROR',
                          content=f"录屏文件设备路径为空，无法拉取: record_file_name={record_file_name}, mediatool stdout={query.stdout if query else 'N/A'}",
                          task_id=task_id, test_case_id=test_case_id)
            local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result',
                                     str(task_id) if task_id else 'default_task_id',
                                     str(test_case_id) if test_case_id else 'default_id', device_sn)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, record_file_name)
            recv_result = subprocess.run(['hdc', '-t', device_sn, 'file', 'recv', device_path, local_path],
                                         check=False, capture_output=True, text=True, timeout=120)
            if not os.path.exists(local_path):
                self._log(level='ERROR', content=f"录屏文件拉取失败: {recv_result.stderr}",
                          task_id=task_id, test_case_id=test_case_id)
                result = {
                    'success': False,
                    'message': f'录屏文件拉取失败: {recv_result.stderr}',
                    'record_path': '',
                    'record_device_path': device_path or '',
                    'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
                }
                return [result]
            # mp4 无损转 wav
            wav_path = self._mp4_to_wav(local_path, task_id=task_id, test_case_id=test_case_id)
            print(f"[录屏] mp4 路径: {local_path}")
            print(f"[录屏] wav 路径: {wav_path}")
            self._record_pulled = True
            result = {
                'success': True,
                'message': 'Success',
                'record_path': local_path,
                'record_device_path': device_path or '',
                'wav_path': wav_path or '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text,
                'answer': answer_text,
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
            }
            return [result]
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            # 收集异常发生时已拿到的关键上下文，便于定位失败点
            query_out = query.stdout if query else '<query未执行>'
            query_err = query.stderr if query else ''
            recv_err = recv_result.stderr if recv_result else '<recv未执行>'
            self._log(level='ERROR',
                      content=(f"获取录屏文件失败: {e}\n"
                               f"  record_file_name={record_file_name}\n"
                               f"  device_path={device_path!r}\n"
                               f"  local_path={local_path!r}\n"
                               f"  query.stdout={query_out!r}\n"
                               f"  query.stderr={query_err!r}\n"
                               f"  recv.stderr={recv_err!r}\n"
                               f"  traceback:\n{tb}"),
                      task_id=task_id, test_case_id=test_case_id)
            result = {
                'success': False,
                'message': (f"获取录屏文件失败: {e} | "
                            f"device_path={device_path!r} | "
                            f"query_stdout={query_out!r} | "
                            f"recv_stderr={recv_err!r}"),
                'record_path': local_path,
                'record_device_path': device_path or '',
                'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
            }
            return [result]

    def teardown(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> bool:
        """用例结束后清理设备状态（与 initialize 对称）

        做以下清理：
        1. 确保录屏已停止（兜底，防止 post_process 异常残留）
        2. 确保通话已挂断（兜底）
        3. 退出小艺聊天界面，回桌面
        4. 清掉华为音乐 5. 清空闹钟 6. 停止小艺 APP
        """
        # 1. 兜底停止录屏（仅在仍在录屏时执行，避免 toggle 把已停止的录屏又打开）
        if getattr(self, '_recording', False):
            try:
                if not self._stop_recorder(device_sn, task_id=task_id, test_case_id=test_case_id):
                    self._log(level='WARNING', content="teardown: 兜底停止录屏失败,服务仍在运行",
                              task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='DEBUG', content="teardown: 兜底停止录屏成功",
                              task_id=task_id, test_case_id=test_case_id)
                self._recording = False
            except Exception as e:
                self._log(level='WARNING', content=f"teardown: 停止录屏失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # case 模式兜底：末轮 post_process 异常未拉取时，此处补拉一次单视频，避免整段录屏丢失
        if getattr(self, '_record_mode', 'round') == 'case' and not getattr(self, '_record_pulled', False):
            pulled = self._pull_record_file(device_sn, task_id=task_id, test_case_id=test_case_id)
            if pulled:
                self._log(level='INFO', content=f"teardown: 兜底拉取录屏成功: {pulled}",
                          task_id=task_id, test_case_id=test_case_id)
                self._record_pulled = True

        driver = self._get_driver(device_sn)
        if not driver:
            return True

        # 2. 兜底挂断通话
        try:
            hangup_btn = driver.find_component(
                By.isAfter(By.key('live.tool_bar.hangup_button')).isBefore(By.key('GuideText')).type('SymbolGlyph'))
            if hangup_btn:
                hangup_btn.click()
                self._log(level='DEBUG', content="teardown: 挂断残留通话", task_id=task_id, test_case_id=test_case_id)
                time.sleep(2)
        except Exception as e:
            self._log(level='DEBUG', content=f"teardown: 无残留通话或挂断失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # 3. 回桌面（退出小艺聊天界面）
        try:
            driver.press_home()
            time.sleep(1)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 回桌面失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # 4. 兜底清掉华为音乐(本轮中途小艺可能误识别"播放音乐"拉起的,防跨用例残留)
        self._stop_music_app(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 5. 清空闹钟(ALARM_CLOCK 表),防止响铃跨用例残留
        self._clear_alarms(device_sn, task_id=task_id, test_case_id=test_case_id)

        # 6. 停止小艺 APP（彻底释放）
        try:
            driver.stop_app(self.app_name)
            self._log(level='DEBUG', content="teardown: 已停止小艺 APP", task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止小艺 APP 失败: {e}", task_id=task_id, test_case_id=test_case_id)

        # 7. 清理 pcm 缓存(get_results 已拉取完毕,此处清设备残留,防止下个用例干扰)
        self._clear_pcm(device_sn, app=getattr(self, '_pcm_app', 'xiaoyi'),
                        task_id=task_id, test_case_id=test_case_id)
        if getattr(self, '_pcm_app', 'xiaoyi') == 'xiaoyi':
            self._clear_dsp_audio_hook(device_sn, task_id=task_id, test_case_id=test_case_id)

        return True
