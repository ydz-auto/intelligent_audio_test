# ASR Server

独立部署的 ASR（自动语音识别）HTTP 服务，基于 ModelScope Paraformer-large-vad-punc 模型。

## 目录

| 文件 | 说明 |
|------|------|
| [asr_server.py](asr_server.py) | 本地 ASR HTTP 服务（ModelScope Paraformer，主服务） |
| [asr_transcribe.py](asr_transcribe.py) | 阿里云百炼录音文件转写示例（云端方案，可选） |

## 设计目标

- **独立部署**：运行在专用 ASR 主机上（纯 CPU 推理），避免 ASR 推理占用自动化测试主机的 CPU，从而保证时延测量的准确性
- **HTTP 调用**：测试主机通过 HTTP 上传 wav 文件获取识别结果，解耦推理与测试
- **结构化输出**：返回 `{text, chunks:[{text, timestamp:[start_s, end_s]}]}`，与 [asr_adapator.py](../eval_server/app/utils/asr_adapator.py) 的 `parse_result` 完全兼容

## 架构

```
┌──────────────────────┐        HTTP (wav 上传)        ┌──────────────────────┐
│  自动化测试主机       │  POST /asr  (multipart)      │  ASR 主机             │
│  (eval_server)       │ ──────────────────────────▶  │  asr_server.py       │
│                      │                              │  ModelScope Paraformer│
│  asr_adapator.py     │ ◀──────────────────────────  │  (CPU 推理)           │
│  call_modelscope_asr │  JSON {text, chunks}         │                      │
└──────────────────────┘                              └──────────────────────┘
```

## 部署

### 环境要求

- Python 3.8+
- 纯 CPU 即可运行（无需 GPU）
- 首次启动需联网下载模型（约 3GB），之后可直接读本地缓存

### 安装

```bash
pip install funasr torch fastapi uvicorn python-multipart
```

### 配置

复制 `.env.example` 为 `.env` 并按需修改：

```bash
cp .env.example .env
```

所有配置项均通过 `.env` 文件管理，参考 [.env.example](.env.example)。

### 启动

```bash
python asr_server.py
```

启动时会预加载模型（首次从 ModelScope 下载，约 3GB，需要几分钟），随后监听 `0.0.0.0:10095`。

> **代理注意**：ModelScope 为国内站点，代码已自动清除 `HTTP_PROXY` / `HTTPS_PROXY` 等代理环境变量，避免 SSL 握手失败。如仍遇到下载问题，请检查系统代理设置。

## 配置项

### ASR Server (asr_server.py)

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ASR_HOST` | `0.0.0.0` | 监听地址 |
| `ASR_PORT` | `10095` | 监听端口 |
| `ASR_CACHE_DIR` | `../static/asr_models` | 模型缓存目录（ModelScope 下载的模型存放在此） |
| `ASR_MODELSCOPE_MODEL` | `iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | 主 ASR 模型 |
| `ASR_VAD_MODEL` | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | VAD（语音活动检测）模型 |
| `ASR_PUNC_MODEL` | `iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch` | 标点恢复模型 |

### 阿里云百炼云端转写 (asr_transcribe.py)

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DASHSCOPE_API_KEY` | （无） | 阿里云百炼 API Key（必填） |
| `DASHSCOPE_MODEL` | `fun-asr` | 转写模型 |
| `DASHSCOPE_LANGUAGES` | `zh,en` | 语言提示（逗号分隔） |
| `DASHSCOPE_BASE_URL` | （空） | 自定义 API 地址（可选，用于华北2等地域） |

## API 接口

### `GET /`

服务信息，列出所有可用端点。

**响应示例：**

```json
{
  "service": "ModelScope ASR Service",
  "model": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
  "endpoints": {
    "health": "GET /health",
    "asr": "POST /asr (上传 wav 文件)",
    "asr_file": "POST /asr_file?wav_path=<本地路径>"
  }
}
```

---

### `GET /health`

健康检查。

**响应：**

```json
{
  "status": "ok",
  "model_loaded": true
}
```

`model_loaded` 为 `false` 表示模型尚未加载完成。

---

### `POST /asr`

上传 wav 文件，执行 ASR 推理并返回结构化结果。**远程调用的主接口。**

**请求：**

- Content-Type: `multipart/form-data`
- 表单字段 `file`：wav 文件

**响应示例：**

```json
{
  "text": "你好世界",
  "chunks": [
    {"text": "你", "timestamp": [0.10, 0.25]},
    {"text": "好", "timestamp": [0.25, 0.40]},
    {"text": "世", "timestamp": [0.40, 0.55]},
    {"text": "界", "timestamp": [0.55, 0.70]}
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 识别全文 |
| `chunks` | array | 逐字分片，含时间戳（单位：秒） |
| `chunks[].text` | string | 单字 |
| `chunks[].timestamp` | `[float, float]` | `[开始秒, 结束秒]` |

**错误码：**

| HTTP | 说明 |
|------|------|
| 400 | 非 wav 文件 |
| 500 | ASR 推理失败 |

---

### `POST /asr_file`

本机调用：传 wav 文件绝对路径返回 ASR 结果。仅限 ASR 主机本地测试使用。

**请求：**

```
POST /asr_file?wav_path=C:/xxx/audio.wav
```

**响应**：同 `POST /asr`。

## 调用方集成

测试主机（eval_server）通过 [asr_adapator.py](../eval_server/app/utils/asr_adapator.py) 调用本服务：

```python
from app.utils.asr_adapator import call_modelscope_asr, parse_result

raw = call_modelscope_asr("/path/to/audio.wav")
result = parse_result(raw)
# result = {"text": "...", "chunks": [{"text": "字", "timestamp": [start_s, end_s]}, ...]}
```

### 测试主机配置

在 `eval_server/.env` 中配置 ASR 服务地址：

```env
ASR_SERVER_URL=http://<ASR主机IP>:10095
ASR_TIMEOUT=120
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ASR_SERVER_URL` | `http://127.0.0.1:10095` | ASR 服务地址（改为实际 ASR 主机 IP） |
| `ASR_TIMEOUT` | `120` | 请求超时秒数 |

## 备选方案：阿里云百炼云端转写

[asr_transcribe.py](asr_transcribe.py) 提供基于阿里云百炼（DashScope）的录音文件转写方案，适用于不需要本地部署、希望使用云端算力的场景。

### 使用前提

- 在 `.env` 中配置 `DASHSCOPE_API_KEY`
- 音频文件需上传至可公网访问的 URL（如 OSS）

### 调用示例

```python
from asr_transcribe import transcribe

# 模型和语言从 .env 读取（DASHSCOPE_MODEL / DASHSCOPE_LANGUAGES），也可显式传入
transcribe(
    file_urls=['https://example.com/audio.wav'],
)
```

> 云端方案为异步转写，适合批量离线处理；本地 `asr_server.py` 为同步推理，适合实时性要求高的自动化测试场景。
