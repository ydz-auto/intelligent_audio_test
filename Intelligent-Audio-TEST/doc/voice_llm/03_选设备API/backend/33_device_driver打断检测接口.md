# 33_device_driver 打断检测接口

> 文件：`backend/device_driver/base_driver.py`

## 现状分析

现有 BaseDeviceDriver 没有打断检测相关接口。全双工打断检测是 voice_llm E2E 测试的特有能力：被测设备在播放语音时应能检测并响应外部语音输入（打断当前播放）。

## 改造方案

### 1. base_driver 新增接口

```python
class BaseDeviceDriver:
    # ...现有方法...

    def detect_interruption(self, sensitivity: float = 0.5) -> Optional[dict]:
        """检测全双工打断事件
        
        在被测设备播放音频期间，监听外部语音输入是否触发了打断。
        
        Args:
            sensitivity: 打断灵敏度（0.0-1.0），越高越敏感
            
        Returns:
            None: 不支持打断检测或未检测到打断
            dict: 打断事件数据
                - timestamp: float — 打断发生时间（相对于播放开始的秒数）
                - duration: float — 打断持续时间（秒）
                - intensity: float — 打断强度（0.0-1.0）
        """
        return None  # 默认实现：不支持打断检测
```

### 2. 打断事件数据结构

```python
@dataclass
class InterruptionEvent:
    """打断事件"""
    timestamp: float       # 发生时间（秒，相对于播放开始）
    duration: float        # 持续时间（秒）
    intensity: float       # 强度（0.0-1.0）

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'duration': self.duration,
            'intensity': self.intensity
        }
```

### 3. 支持打断检测的驱动实现

```python
class FullDuplexCapableDriver(BaseDeviceDriver):
    """支持全双工打断检测的设备驱动"""
    
    def detect_interruption(self, sensitivity: float = 0.5) -> Optional[dict]:
        """通过设备日志/信号检测打断事件"""
        try:
            # 方式1：通过设备系统日志检测
            # 某些设备在被打断时会输出特定日志
            log_output = self._read_device_log(
                keywords=['interrupt', '打断', 'barge-in'],
                since=self._play_start_time
            )
            if log_output:
                return self._parse_interruption_from_log(log_output)
            
            # 方式2：通过音频信号分析
            # 检测播放过程中是否有外部语音输入信号
            audio_signal = self._capture_audio_snippet(duration=0.5)
            if self._has_voice_input(audio_signal, sensitivity):
                return {
                    'timestamp': time.time() - self._play_start_time,
                    'duration': 0.0,  # 待填充
                    'intensity': self._calculate_intensity(audio_signal)
                }
            
            return None
        except Exception as e:
            self._log(level='WARN', content=f"打断检测失败: {e}")
            return None
```

### 4. 与 E2E 执行器的集成

```python
# e2e_executor.py 多轮循环内（从 round.algorithmParams 读取）
def _execute_rounds(self, task_id, rounds, device_info_list):
    for i, round_config in enumerate(rounds):
        algo_params = CaseParameterExtractor.convert_params_to_dict(
            round_config.get('algorithmParams', [])
        )

        # 播放音频
        self._play_audio(driver, round_config)

        # 打断检测（从 algorithmParams 读取，field_code=interruptionEnabled）
        interruption_enabled = algo_params.get('interruptionEnabled', 'false')
        sensitivity = algo_params.get('interruptionSensitivity', '0.5')

        interruption_events = []
        if str(interruption_enabled).lower() == 'true':
            # 在等待响应期间持续监听打断
            while self._is_waiting_for_response():
                event = driver.detect_interruption(float(sensitivity))
                if event:
                    interruption_events.append(event)
                    self._log(content=f"检测到打断: t={event['timestamp']:.2f}s")
                time.sleep(0.1)  # 100ms 检测间隔

        # 将打断事件附加到本轮结果
        round_result['interruption_events'] = interruption_events
```

### 5. 参数来源

打断检测参数从 `round.algorithmParams` 读取，不再从 round 顶层读取：

```python
# 读取方式
algo_params = CaseParameterExtractor.convert_params_to_dict(round_config.get('algorithmParams', []))
interruption_enabled = algo_params.get('interruptionEnabled', 'false')
sensitivity = algo_params.get('interruptionSensitivity', '0.5')
```

```json
// round.algorithmParams 中的打断检测参数
[
    { "field_code": "interruptionEnabled", "field_value": "true" },
    { "field_code": "interruptionSensitivity", "field_value": "0.5" }
]
```

```python
# voice_llm 的 CaseAlgorithmParam 种子数据
[
    {
        'param_code': 'interruptionEnabled',
        'param_name': '允许打断',
        'param_type': 'boolean',
        'scope': 'e2e',
        'default_value': 'false',
        'component': 'switch'
    },
    {
        'param_code': 'interruptionSensitivity',
        'param_name': '打断灵敏度',
        'param_type': 'float',
        'scope': 'e2e',
        'default_value': '0.5',
        'component': 'slider'
    }
]
```

## 不变部分

- 所有现有方法（scan/initialize/unlock/get_results 等）不变
- 不支持打断的驱动返回 None，E2E 执行器正常继续

## 引用关系

- ← `01_选算法/backend/07_voice_llm算法参数种子数据` — interruptionEnabled/interruptionSensitivity 参数
- → `04_执行测试/backend/21_全双工打断检测` — E2E 执行器中的打断检测调用
- → `04_执行测试/backend/22_E2E每轮结果收集` — 打断事件附加到轮次结果
