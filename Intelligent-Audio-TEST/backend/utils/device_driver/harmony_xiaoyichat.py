import time
import subprocess
import os
import re
import wave

try:
    from hypium.model import UiParam
except Exception:
    UiParam = None

from .harmony_driver import HarmonyDriver
from .utils import check_stop, UiDriver, By, MatchPattern, log_and_emit
from config.config import Config
from backend.utils.common.time_utils import ms_to_utc8_str, MS_FMT

class Xiaoyilivechat(HarmonyDriver):
    RECORDER_BUNDLE = 'com.huawei.hmos.screenrecorder'
    RECORDER_ABILITY = 'com.huawei.hmos.screenrecorder.ServiceExtAbility'


    # 是否启用录屏(小艺=True 保留录屏 wav 作为评估音频源)。
    # Doubao/ChatGPT 在各自子类置 False:无录屏,get_results 跳过录屏拉取,
    # 改把 ai_wav 塞进 wav_path 复用 wav_path→record_file 映射喂评估。
    _record_enabled = True
    # 各 app 的 pcm 缓存目录、用户输入后缀、AI 回复后缀
    # 当前驱动仅抓取小艺(xiaoyi)数据；通过 app 参数可切换到 doubao/chatgpt
    PCM_APP_CONFIG = {
        'xiaoyi': {
            'cache_dirs': ['/data/app/el2/100/base/com.huawei.hmos.aibase/cache',
                           '/data/app/el2/100/base/com.huawei.hmos.vassistant/cache'],
            'user_suffix': 'cap_client_process_out.pcm',
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
        """
        if not os.path.exists(pcm_path):
            return None
        # 从文件名解析采样参数
        base = os.path.basename(pcm_path)
        parts = base.split('_')
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

    def _hdc_shell(self, device_sn, *args):
        return subprocess.run(
            ['hdc', '-t', device_sn, 'shell'] + list(args),
            check=False, capture_output=True, text=True, timeout=10
        )

    def _list_device_mp4_set(self, device_sn):
        """获取设备录屏目录下所有 mp4 文件路径集合（用于区分新增文件）"""
        r = self._hdc_shell(
            device_sn, 'find', '/storage/media/100/local/files/Photo',
            '-name', '*.mp4', '-type', 'f'
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

    def _stop_recorder(self, device_sn):
        """停止录屏服务

        说明: 与 _start_recorder 同理, aa dump -l 的二次校验不可靠,
        这里直接以 toggle 命令执行成功为准; 真正的兜底放在 teardown 中按
        _recording 标志位判断, 避免对已停止的录屏再次 toggle 反而打开。
        """
        self._hdc_shell(device_sn, 'aa', 'start', '-b', self.RECORDER_BUNDLE, '-a', self.RECORDER_ABILITY)
        return True

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

    def _list_dir_pcm(self, device_sn, remote_dir):
        """列出设备指定目录下所有 pcm 文件路径（用于按后缀匹配区分用户输入/AI回复）"""
        r = self._hdc_shell(device_sn, 'find', remote_dir, '-name', '*.pcm', '-type', 'f')
        if r.returncode != 0:
            return []
        return [line.strip() for line in (r.stdout or '').splitlines() if line.strip()]

    def _pick_pcm(self, device_sn, files, suffix, exclude=None,
                  task_id=None, test_case_id=None):
        """从文件列表中按后缀匹配一个 pcm 路径，多个匹配时【取文件最大者】。

        cap_client 在一次会话里可能写多个同名后缀流：真麦克风采集流(有声、
        时长最长、size 最大) + 若干探针/回声流(静音、size 小)。若按文件名排序
        取最后一个，可能恰好选中静音探针流(如 *_1_1_cap_client_out.pcm)，
        导致转出的 user_wav 无声。故改为按设备上实际文件 size 取最大。

        size 全部取不到(stat 失败/全 0)时退回按文件名排序取最后一个,保持旧行为。
        """
        matches = [f for f in files if f.endswith(suffix) and f != exclude]
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

    def _pull_pcm(self, device_sn, app='xiaoyi', task_id=None, test_case_id=None):
        # 获取小艺对话pcm,文件位置:/data/app/el2/100/base/com.huawei.hmos.aibase/cache/。用户输入名称格式100184_16000_1_1_cap_client_process_out.pcm。 AI助手回复名称格式100184_16000_2_1_cap_client_ec_out.pcm
        # 获取豆包对话PCM，文件位置:/data/app/el2/100/base/com.larus.nova.hm/cache/, 用户输入名称格式100186_48000_2_1_cap_client_out.pcm。AI助手回复名称格式100184_48000_2_1_client_in..pcm
        # 获取chagpt对话PCM，文件位置：/data/local/tmp/。用户输入名称格式100174_48000_2_1_cap_client_out.pcm。AI助手回复名称格式100175_48000_2_1_cap_client_in.pcm
        #
        # 按 app 参数选择对应 app 的缓存目录与文件后缀:
        # - 小艺(xiaoyi):   .../com.huawei.hmos.aibase/cache  用户 cap_client_process_out.pcm / AI cap_client_ec_out.pcm
        # - 豆包(doubao):   .../com.larus.nova.hm/cache      用户 cap_client_out.pcm        / AI client_in..pcm
        # - chatgpt:        /data/local/tmp                  用户 cap_client_out.pcm        / AI cap_client_in.pcm
        # 返回: {'user': local_path_or_None, 'ai': local_path_or_None, 'user_remote':..., 'ai_remote':...}
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
            local_path = os.path.join(local_dir, os.path.basename(remote))
            pulled = self._recv_pcm(device_sn, remote, local_path,
                                    task_id=task_id, test_case_id=test_case_id, app=app, role=role)
            if pulled:
                result[role] = pulled
                result[f'{role}_remote'] = remote
        return result

    def _pull_pcm_wav(self, device_sn, app='xiaoyi', task_id=None, test_case_id=None):
        """拉取指定 app 的用户输入/AI 回复 pcm 并转为 wav。

        返回 (user_wav_path_or_None, ai_wav_path_or_None)。
        """
        pulled = self._pull_pcm(device_sn, app=app, task_id=task_id, test_case_id=test_case_id)
        user_pcm = pulled.get('user')
        ai_pcm = pulled.get('ai')
        user_wav = self._pcm_to_wav(user_pcm, task_id=task_id, test_case_id=test_case_id) if user_pcm else None
        ai_wav = self._pcm_to_wav(ai_pcm, task_id=task_id, test_case_id=test_case_id) if ai_pcm else None
        return user_wav, ai_wav




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
        # pcm 抓取目标 app（当前驱动默认只抓小艺；可通过 kwargs.pcm_app 切换 doubao/chatgpt）
        self._pcm_app = kwargs.get('pcm_app', 'xiaoyi')
        # 用例开始前清理设备上目标 app 的 pcm 缓存，避免上个用例残留文件干扰本轮匹配
        self._clear_pcm(device_sn, app=self._pcm_app, task_id=task_id, test_case_id=test_case_id)
        # 点开小艺聊天窗口
        # user_center = driver.find_component(By.text("小艺"))
        # if user_center:
        #     user_center.click()
        #     time.sleep(2)
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
            replied=self._wait_for_condition(
                lambda:driver.find_component(By.text("说话可打断"))  is None,
                timeout=60,interval=1,
                operation_name='等待回复开始',
            )

            if not replied:
                self._log(level='INFO',content='小艺未回复', task_id=task_id, test_case_id=test_case_id)
                self.question_text='小艺识别为空'
                self.answer_text='小艺回复为空'
            else:
                self._log(level='INFO',content='模型成功回复', task_id=task_id, test_case_id=test_case_id)
                # 等待小艺回复结束（带超时和停止检查）
                self._wait_for_condition(
                    lambda: driver.find_component(By.text('说话可打断')),
                    timeout=60, interval=1, operation_name="post_process_说话可打断"
                )
                self._wait_for_condition(
                    lambda: driver.find_component(By.text('正在听…')),
                    timeout=60, interval=1, operation_name="post_process_正在听"
                )
        record_mode = getattr(self, '_record_mode', 'round')
        round_number = getattr(self, '_round_number', 0)
        total_rounds = getattr(self, '_total_rounds', 1)
        is_last = (total_rounds and round_number == total_rounds - 1)

        if record_mode == 'case':
            # case 模式：中间轮不停录屏、不挂断（保持通话与录屏连续）；
            # 仅末轮停止录屏，以便 get_results 拉取完整文件；全程不在此挂断，交给 teardown 兜底
            if is_last:
                if not self._stop_recorder(device_sn):
                    self._log(level='WARNING', content="末轮停止录屏失败,服务仍在运行", task_id=task_id, test_case_id=test_case_id)
                else:
                    self._log(level='INFO', content="末轮停止录屏成功", task_id=task_id, test_case_id=test_case_id)
                self._recording = False
                time.sleep(5)
        else:
            # round 模式：每轮停止录屏 + 挂断（原逻辑）
            if not self._stop_recorder(device_sn):
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
                task_id=task_id, test_case_id=test_case_id)
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
                'wav_path': ai_wav or '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': None,
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': user_wav or '',
                'ai_wav': ai_wav or ''
            }]
        record_file_name = getattr(self, '_record_file_name', 'record.mp4')
        question_text = getattr(self, 'question_text', None)
        answer_text = getattr(self, 'answer_text', None)
        first_frame_ms = getattr(self, '_recorder_first_frame_ms', None)
        wav_path = None
        query = None
        device_path = ''
        local_path = ''
        recv_result = None
        user_wav = None
        ai_wav = None
        # case 模式且录屏仍在进行（非末轮）：不拉取半截文件，只返回本轮问答文本
        if getattr(self, '_record_mode', 'round') == 'case' and getattr(self, '_recording', False):
            self._log(level='DEBUG', content="case模式录屏进行中,跳过拉取半截文件",
                      task_id=task_id, test_case_id=test_case_id)
            return [{
                'success': True,
                'message': 'recording in progress',
                'record_path': '',
                'wav_path': '',
                'start_ms': ts['start_ms'],
                'end_ms': ts['end_ms'],
                'first_frame_ms': first_frame_ms,
                'question': question_text or '',
                'answer': answer_text or '',
                'user_wav': '',
                'ai_wav': ''
            }]
        # 拉取对话 pcm 并转 wav（用户输入 + AI 回复），抓取目标 app 由 _pcm_app 指定
        pcm_app = getattr(self, '_pcm_app', 'xiaoyi')
        user_wav, ai_wav = self._pull_pcm_wav(device_sn, app=pcm_app,
                                              task_id=task_id, test_case_id=test_case_id)
        try:
            # 优先用 _start_recorder 发现的真实 VID 路径直接 recv(绕开 mediatool 按 CustomizedFileName
            # 查询——后者对部分文件名报 "displayName format is not correct" 而查不到,case 模式尤其常见)
            device_path = getattr(self, '_record_device_path', None) or ''
            query = None
            if not device_path:
                query = self._hdc_shell(device_sn, 'mediatool', 'query', record_file_name, '-u')
                lines = query.stdout.strip().split('\n')
                device_path = lines[1].strip() if len(lines) > 1 else ''
                if 'uri' in query.stdout and len(lines) > 2:
                    subprocess.run(
                        ['hdc', '-t', device_sn, 'shell', 'mediatool', 'recv', lines[2].strip(), '/data/local/tmp'],
                        check=False, capture_output=True, text=True, timeout=120
                    )
                    device_path = f'/data/local/tmp/{record_file_name}'
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
        """
        # 1. 兜底停止录屏（仅在仍在录屏时执行，避免 toggle 把已停止的录屏又打开）
        if getattr(self, '_recording', False):
            try:
                if not self._stop_recorder(device_sn):
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

        # 4. 停止小艺 APP（彻底释放）
        try:
            driver.stop_app(self.app_name)
            self._log(level='DEBUG', content="teardown: 已停止小艺 APP", task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            self._log(level='WARNING', content=f"teardown: 停止小艺 APP 失败: {e}", task_id=task_id, test_case_id=test_case_id)

        return True
