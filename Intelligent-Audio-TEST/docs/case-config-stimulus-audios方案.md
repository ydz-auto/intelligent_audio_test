# case_config → played_audios 音频传递方案

## 1. 文档目的

本文记录 V9.7.10 单体版中“被播放音频/背景噪声/干扰人”从用例配置传递到评估服务的实现方案、验证方法和当前结论。

目标是保证以下数据能够端到端保持一致：

```text
test_case.config.rounds[].audios / background_noise / interferers
        ↓
评估参数映射：case_config → audios / background_noise / interferers
        ↓
轮次数归一化 _normalize_round_eval_fields（噪声注入 / 干扰人提升 / audio_path 补全）
        ↓
case_config.rounds[].{audios|background_noise|interferers}[].audio_path
        ↓
multipart 文件上传 + JSON 占位符
        ↓
评估服务端占位符还原为本地音频文件
```

本文中的“音频正确传递”包含三个条件：

1. 评估请求的 `rounds` 中保留 `played_audios` 结构。
2. 结构中的 `audio_path` 不以 OSS URI 直接暴露给评估服务，而是转成 multipart 文件。
3. 评估服务还原后的文件与 MinIO/OSS 源文件字节数一致。

`played_audios` 是被播放音频的评估参数名。背景噪声 `background_noise` 和干扰人 `interferers` 属于同一类轮次结构化音频，复用相同的递归上传和服务端还原机制，不再为每类音频设计独立的 multipart 协议。

## 2. 适用范围

- 代码库：`V9.7.10/Intelligent-Audio-TEST`
- 运行形态：Flask 单体版
- 主服务端口：`5010`
- 共享数据库：PostgreSQL `intelligent_audio_test`
- 开发环境对象存储：本地 MinIO，使用 S3 协议
- 本次实测任务：`TASK 310`
- 本次实测维度：3、4、6

本方案验证的是请求构造和文件传输链路。真实外部评估端点恢复后，还需要进行一次在线回归，以确认网络、鉴权和评估服务自身处理均正常。

## 3. 数据与映射约定

### 3.1 用例配置

用例配置的轮次结构示例（三类结构化音频字段）：

```json
{
  "background_noise": {"audio_id": 901, "spl": 65},
  "rounds": [
    {
      "audios": [
        {"audio_id": 123, "audio_path": "oss://audios/example.wav"}
      ],
      "background_noise": {"audio_id": 902, "spl": 70},
      "algorithm_params": [
        {"field_code": "interferers", "field_value": [{"audio_id": 801, "spl": 60}]}
      ]
    }
  ]
}
```

字段位置约定与播放链一致：

- 被播放音频：`rounds[].audios`（列表）
- 背景噪声：用例级 `config.background_noise`（全局，跨轮持续播放）或轮次级 `rounds[].background_noise`
- 干扰人：`rounds[].algorithm_params.interferers`（列表，评估前提升为轮级字段）

兼容历史字段时，音频名称和路径可以分别从 `audio_name`/`name`、`audio_path`/`path` 读取。`e2e_executor.py` 中保留了首个音频的摘要读取逻辑，用于兼容既有执行流程；完整的多音频列表由 `rounds[].audios` 传递。

### 3.2 评估参数映射

评估维度参数映射共三组（由种子脚本 `seed_stimulus_audios.py` 注册）：

| source | source_param | target_param | 评估参数含义 |
| --- | --- | --- | --- |
| case_config | audios | played_audios | 被播放音频 |
| case_config | background_noise | background_noise | 背景噪声（含历史 stimulus_audios 归一化） |
| case_config | interferers | interferers | 干扰人音频列表 |

`evaluation_service.py` 在发现评估映射使用 `case_config` 后，调用 `_build_case_config` 组装评估上下文，并从对应轮次读取上述字段。音频 ID 通过 `case_parameter_extractor.py` 查询音频记录，补全为 `file_path`（当前为 `oss://` URI）。

### 3.3 轮次数归一化（评估上下文）

评估按轮取值走 `cfg_round.get(source_param)`，但播放侧三类音频的字段位置不一致（干扰人嵌套在 `algorithm_params`、背景噪声存在用例级全局）。为此 `case_parameter_extractor._normalize_round_eval_fields` 在深拷贝的轮配置上做归一化（原地修改、幂等、不污染原 `case.config`）：

1. 背景噪声：轮次无 `background_noise` 且用例级存在全局背景噪声时，注入用例级副本（深拷贝）；轮次级配置优先。
2. 干扰人：从 `rounds[].algorithm_params`（dict 或 `[{field_code, field_value}]` 两种形态）提取 `interferers`，提升为轮级字段。
3. `audio_path` 补全：遍历 `audios`（list）、`background_noise`（dict）、`interferers`（list）中的 `audio_id`，查库补全 `audio_path`（已填则跳过）。

调用点有两处，共用同一归一化：

- `case_parameter_extractor._build_evaluation_params` 的 `case_config` 分支（评估参数按映射提取时）
- `evaluation_service._build_case_config` 的 rounds 循环（组装评估上下文时）

### 3.4 为什么不能只取每轮第一个音频

`rounds[].audios` 可能包含多个音频。首个音频读取逻辑只能用于历史摘要字段或兼容旧算法参数，不能作为评估请求的完整来源。评估请求必须保留完整列表，并对列表内每个音频递归提取文件。

## 4. OSS/MinIO 存储方案

V9.7.10 原有代码没有识别 `oss://` URI 的客户端能力，而共享 `audios.file_path` 已使用该格式。因此新增：

```text
backend/utils/clients/oss_client.py
```

客户端采用延迟初始化单例，当前支持：

- `exists(path)`：判断对象是否存在
- `load_file(path, local_path=None)`：下载到本地临时文件
- `download_bytes(path)`：直接下载二进制内容

当前采用单桶模式：

```text
URI：oss://{category}/{key}
实际对象 key：{OSS_KEY_PREFIX}/{category}/{key}
```

开发环境配置位于 `backend/.env`，配置项包括：

```dotenv
OSS_ENDPOINT=http://localhost:9000
OSS_REGION=us-east-1
OSS_ACCESS_KEY=minio
OSS_SECRET_KEY=minio123
OSS_BUCKET_NAME=intelligent-audio-test
OSS_KEY_PREFIX=intelligent_audio_test
```

生产环境应通过环境变量注入真实 S3/OSS 地址、凭证、桶名和前缀，不应把凭证写入业务代码。

## 5. 请求转换流程

实现位置：

```text
backend/services/evaluation/api_request_handler.py
```

### 5.1 普通文件字段

当 payload 中出现可识别的本地路径、`oss://` URI 或已存在的文件值时：

1. 判断文件是否存在。
2. 对 `oss://` URI 调用 `oss.load_file()` 下载临时文件。
3. 读取二进制内容。
4. 放入 `requests` multipart 的 `files` 参数。
5. 从 JSON/form 字段中移除原始路径，避免同一文件被重复传输。

### 5.2 结构化轮次字段

`rounds` 不是单一文件字段，而是嵌套的 list/dict。请求层对每一轮的所有结构化字段递归处理，不依赖固定的 `audio_field_names` 白名单。当前覆盖：

- `played_audios`：被播放音频列表
- `background_noise`：背景噪声配置
- `interferers`：干扰人音频列表
- 其他未来新增的 dict/list 音频字段

只要字段已进入评估上下文，且维度的 `body_template.rounds[]` 声明了该字段，递归处理就会自动发现其中的 `audio_path`、`audio` 等可识别文件值：

```text
rounds[0].played_audios[0].audio_path
        ↓
files["rounds_0_played_audios_0_audio_path"]
        ↓
"__MULTIPART__:rounds_0_played_audios_0_audio_path"
```

递归规则：

- `dict`：递归处理每个 value，保留 key。
- `list`：递归处理每个 item，保留数组顺序。
- 文件值：加入 multipart，并替换成 `__MULTIPART__:{upload_key}`。
- 其他标量：原样保留。

这样既能传输文件，又不会破坏 `rounds` 的业务结构和音频顺序。

## 6. 评估服务端还原

评估服务收到 multipart 后，需要对 JSON 中的占位符递归还原：

```text
__MULTIPART__:rounds_0_played_audios_0_audio_path
        ↓
评估服务上传目录下的本地 .wav 文件路径
```

还原必须覆盖 dict 和 list，不能只处理顶层字段，否则 `played_audios`、`background_noise` 或 `interferers` 内部音频会保持为字符串占位符，最终算法拿不到文件。

## 7. 验证方案

### 7.1 离线验证

使用 V9.7.10 虚拟环境验证：

- OSS 客户端可以从 MinIO 下载源文件。
- `oss://` URI 能被识别为文件值。
- `rounds[].played_audios[].audio_path` 会被替换为 multipart 占位符。
- 上传文件字节数与源对象一致。

### 7.2 Mock 端到端验证

为隔离外部评估端点，临时启动 mock eval server，执行以下流程：

1. 将维度 3、4、6 的 `api_url` 临时切换到 mock 地址。
2. 启动 V9.7.10 Flask 服务（端口 `5010`）。
3. 调用：

```http
POST http://127.0.0.1:5010/api/v1/evaluation/task/reevalidate
Content-Type: application/json

{
  "task_id": 310,
  "reevaluate_type": "all",
  "reextract_device_output": false
}
```

4. 确认返回入队 `129` 个用例。
5. 检查 mock report 中的 `rounds_raw`、`files_received`、`restored`。
6. 对每条 stimulus 音频执行三重校验：
   - 原始 JSON 值是 `__MULTIPART__` 占位符。
   - 还原值是本地 `.wav` 文件。
   - 本地文件大小与 MinIO 源对象大小一致。

## 8. V9.7.10 实测结果

```text
评估入队：129 个用例
stimulus 音频上传记录：42 条
校验总数：42
通过：42
失败：0
无记录：0
RESULT: ALL PASS
```

该结果证明 V9.7.10 的以下链路已打通：

```text
case_config.rounds[].audios
→ played_audios 映射
→ audio_path 补全为 oss:// URI
→ OSS 下载
→ multipart 上传
→ __MULTIPART__ 占位符
→ 服务端本地文件还原
→ 文件大小与源对象一致
```

本次 TASK 310 的 42 条记录重点覆盖 `played_audios`。噪声和干扰人字段已经由同一递归机制支持，但未作为本次 42 条统计的独立覆盖项；纳入具体评估维度时，应在该维度的模板和映射中显式声明并补充对应回归用例。

### 8.1 噪声/干扰人链路离线验证

在扩展三类音频参数/映射后，对归一化与递归提取做了离线单元级验证（不依赖外部评估端点），共 19 项断言全部通过：

- 归一化行为（`_normalize_round_eval_fields`）：
  - 用例级 `background_noise` 注入轮次（深拷贝副本，不污染原 config）。
  - 轮次级 `background_noise` 优先，不被用例级覆盖。
  - `algorithm_params` dict 与 `[{field_code, field_value}]` 列表两种形态均能提升 `interferers`。
  - 重复调用幂等，结果不变。
  - `audio_path` 补全三类字段（audios/background_noise/interferers）均查库生效（真库 audio_id 实测）。
- 递归提取（`_extract_files_from_payload`）：
  - `rounds[0].background_noise.audio_path` → `__MULTIPART__:rounds_0_background_noise_audio_path`，上传字段存在。
  - `rounds[0].interferers[0/1].audio_path` → 占位符 + 两条上传字段，key 可在 files 中还原。
  - 非文件标量（如 `spl`）原样保留，业务结构不破坏。

验证完成后，维度 3、4、6 的 `api_url` 已恢复为：

```text
http://100.70.20.135:5000
```

V9.7.10 Flask 和 mock eval server 均已停止，临时验证脚本和报告已清理。

## 9. 失败模式与排查顺序

### 9.1 请求中没有 `played_audios`

检查顺序：

1. 维度映射的 `source` 是否为 `case_config`。
2. `source_param` 是否为 `audios`，`target_param` 是否为 `played_audios`。
3. 用例 `config.rounds` 是否存在 `audios`。
4. `_build_case_config` 是否被调用。

如果缺少的是 `background_noise` 或 `interferers`，除以上检查外，还要确认该字段没有在用例拆分或评估参数组装阶段被剥离，并且 `body_template.rounds[]` 中存在同名字段。

### 9.2 JSON 中有 URI，但 multipart 没有文件

检查顺序：

1. `OSS_BUCKET_NAME`、凭证和 endpoint 是否正确。
2. MinIO 中的对象 key 是否符合 `{prefix}/{category}/{key}`。
3. `OSSClient.exists()` 是否返回 true。
4. `_extract_nested_files()` 是否覆盖对应的 list/dict 路径。

### 9.3 multipart 有文件，但算法拿到占位符

检查评估服务端的递归还原逻辑，重点确认 list 内部的 dict 是否被遍历，以及占位符字段名是否与 multipart 字段名完全一致。

### 9.4 只传了每轮第一个音频

检查是否错误地使用了 `e2e_executor.py` 中的 `first_audio` 摘要逻辑作为评估请求来源。完整评估请求应使用 `rounds[].played_audios` 列表。

## 10. 当前遗留项

1. 外部评估端点 `100.70.20.135:5000` 恢复后，需要进行一次真实在线验证；本次 42/42 结果是 mock eval server 下的协议和文件一致性验证。
2. 维度 44、48、49、50 存在 `bodyTemplate` 与执行器读取 `body_template` 的键名差异。若这些维度纳入评估，应先统一键名并复测。
3. 种子脚本 `backend/scripts/migrations/202606/seed_stimulus_audios.py` 已扩展为三组参数/映射，尚未对共享数据库执行（交互式确认，幂等可重复）。
4. V9.7.31 微服务版 `evaluation_service` 尚未接入同等的运行时归一化（`_normalize_round_eval_fields`），当前仅同步了注释；待其独立回归时补齐。
5. 若噪声/干扰人纳入具体评估维度，需确认该维度 `body_template.rounds[]` 声明了同名字段并补充端到端回归用例。

## 11. 相关代码

- [OSS 客户端](../backend/utils/clients/oss_client.py)
- [请求与 multipart 处理](../backend/services/evaluation/api_request_handler.py)
- [评估参数组装](../backend/services/evaluation/evaluation_service.py)
- [音频路径补全与参数提取](../backend/utils/algorithm/case_parameter_extractor.py)
- [轮次结构化音频维度参数种子脚本](../backend/scripts/migrations/202606/seed_stimulus_audios.py)
- [算法配置弹窗（case_config 功能开关声明）](../frontend/src/components/algorithm/AlgorithmConfigModal.vue)
- [首个音频兼容摘要逻辑](../backend/services/execution/e2e_executor.py)
- [OSS 配置](../backend/config/config.py)
- [开发环境变量](../backend/.env)
