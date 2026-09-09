# case_config → played_audios 音频传递方案

## 1. 文档目的

本文记录微服务版中“被播放音频/背景噪声/干扰人”三类轮次结构化音频从用例配置传递到评估服务的实现方案、验证方法和当前结论（自 V9.7.10 单体版同步，见文末差异说明）。

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

- 代码库：`V9.7.31/Intelligent-Audio-TEST`
- 运行形态：微服务架构（评估链路位于 `evaluation_service`，存储与模型抽象位于 `shared`）
- 共享数据库：PostgreSQL `intelligent_audio_test`
- 开发环境对象存储：本地 MinIO，使用 S3 协议
- 验证基线：V9.7.10 单体版实测（TASK 310，维度 3、4、6，mock 端到端 42/42 ALL PASS + 离线验证 19/19 PASS）

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

### 3.2 评估参数映射

评估维度参数映射共三组（由种子脚本 `seed_stimulus_audios.py` 注册）：

| source | source_param | target_param | 评估参数含义 |
| --- | --- | --- | --- |
| case_config | audios | played_audios | 被播放音频 |
| case_config | background_noise | background_noise | 背景噪声（含历史 stimulus_audios 归一化） |
| case_config | interferers | interferers | 干扰人音频列表 |

微服务版中，`round_data_builder._build_rounds_list` 在发现评估映射使用 `source='case_config'` 后，调用 `_load_case_config` 加载整份 `test_case.config`（**含 rounds 外层的用例级 `background_noise`**），并在 `_build_single_round` 的 `case_config` 分支按轮取值。音频 ID 通过查库（`audios.file_path`）补全为 `oss://` URI。

### 3.3 轮次数归一化（评估上下文）

评估按轮取值走 `cfg_round.get(source_param)`，但播放侧三类音频的字段位置不一致（干扰人嵌套在 `algorithm_params`、背景噪声存在用例级全局）。为此 `round_data_builder._normalize_round_eval_fields` 在深拷贝的轮配置上做归一化（原地修改、幂等、不污染原 `case.config`）：

1. 背景噪声：轮次无 `background_noise` 且用例级存在全局背景噪声时，注入用例级副本（深拷贝）；轮次级配置优先。
2. 干扰人：从 `rounds[].algorithm_params`（dict 或 `[{field_code, field_value}]` 两种形态）提取 `interferers`，提升为轮级字段（复用 `algorithm_service` 的 `ParamNormalizerService.normalize_algorithm_params`）。
3. `audio_path` 补全：`_fill_round_audio_paths` 遍历 `audios`（list）、`background_noise`（dict）、`interferers`（list）中的 `audio_id`，查库补全 `audio_path`（已填则跳过）。

调用点为单一入口：`round_data_builder._build_single_round` 的 `case_config` 分支（评估参数按映射提取时），与 V9.7.10 的双调用点（`_build_evaluation_params` + `_build_case_config`）等价——微服务版将上下文组装合并进了 `_build_rounds_list → _build_single_round` 链路。

### 3.4 为什么不能只取每轮第一个音频

`rounds[].audios` 可能包含多个音频。首个音频读取逻辑只能用于历史摘要字段或兼容旧算法参数，不能作为评估请求的完整来源。评估请求必须保留完整列表，并对列表内每个音频递归提取文件。

## 4. OSS/MinIO 存储方案

微服务版将对象存储能力统一收敛到共享层：

```text
shared/infrastructure/storage.py
```

对比 V9.7.10 单体版的独立 `oss_client.py`，微服务版由 `storage` 抽象统一处理：

- `oss://` URI 与 `local://` URI 的识别与分发
- `build_path(category, key)`：相对 key 构建完整对象 key
- `load_file(path)` / `exists(path)`：下载与存在性判断

对象 key 约定保持一致：

```text
URI：oss://{category}/{key}
实际对象 key：{OSS_KEY_PREFIX}/{category}/{key}
```

存储连接配置位于 `shared/infrastructure/config.py`（OSS_ENDPOINT / OSS_ACCESS_KEY / OSS_SECRET_KEY / OSS_BUCKET_NAME / OSS_KEY_PREFIX）。生产环境应通过环境变量注入真实 S3/OSS 地址、凭证、桶名和前缀，不应把凭证写入业务代码。

## 5. 请求转换流程

实现位置：

```text
evaluation_service/infrastructure/evaluation_api/api_request_handler.py
```

### 5.1 普通文件字段

当 payload 中出现可识别的本地路径、`oss://` URI 或已存在的文件值时：

1. 判断文件是否存在。
2. 对 `oss://` URI 调用 `storage.load_file()` 下载临时文件。
3. 读取二进制内容。
4. 放入 multipart 的 `files` 参数。
5. 从 JSON/form 字段中移除原始路径，避免同一文件被重复传输。

### 5.2 结构化轮次字段

`rounds` 不是单一文件字段，而是嵌套的 list/dict。请求层对每一轮的所有结构化字段递归处理（`_extract_nested_files`），不依赖固定的 `audio_field_names` 白名单。当前覆盖：

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

微服务版中，该还原逻辑位于算法侧 `eval_server`（独立部署，不在本仓库内），行为与 V9.7.10 仓库内版本一致。

## 7. 验证方案

### 7.1 静态验证

对改动文件执行 `py_compile` 编译检查：

```bash
python -m py_compile evaluation_service/domain/services/evaluation_service/round_data_builder.py scripts/migrations/202609/seed_stimulus_audios.py
```

### 7.2 移植基线（V9.7.10 实测结论）

本轮代码为 V9.7.10 已验证方案的同步移植，V9.7.10 侧验证结论作为移植正确性的基线：

- Mock 端到端验证（mock eval server）：TASK 310 入队 129 用例，stimulus 音频上传 42 条，占位符还原与文件大小三重校验 42/42 ALL PASS。
- 三类音频离线验证：归一化行为（用例级噪声注入/轮级优先/dict 与 list 双形态干扰人提升/幂等/三类字段 audio_path 真库补全）+ 递归提取（噪声/干扰人占位符与上传字段、标量保留）共 19 项断言全部通过。

### 7.3 微服务版回归项

V9.7.31 侧待执行/待覆盖：

1. ~~离线归一化验证~~ **已执行（22/22 ALL PASS）**：对齐 V9.7.10 的 19 项断言并在微服务代码上扩展为 22 项（新增 `_resolve_config_round` 1-indexed 对齐/下标兜底/越界 3 项与 `_extract_files_from_payload` 整链 payload 断言 1 项），mock `get_db_session` 重放归一化 7 项 + 轮次解析 3 项 + case_config 映射取值 4 项（含深拷贝隔离）+ 递归提取/占位符 8 项。
2. mock eval server 端到端回归（经 api_gateway 触发 reevaluate，验证 multipart 协议与文件一致性）。
3. 种子脚本 `scripts/migrations/202609/seed_stimulus_audios.py` 对共享数据库执行（交互式确认，幂等可重复）。

## 8. 当前验证状态

| 验证项 | V9.7.10（移植源） | V9.7.31（本分支） |
| --- | --- | --- |
| py_compile | 通过 | 通过（round_data_builder / seed_stimulus_audios，另确认 api_request_handler / param_normalizer） |
| 归一化 + 递归提取离线验证 | 19/19 PASS | 22/22 ALL PASS（§7.3 第 1 条） |
| mock 端到端 | 42/42 ALL PASS | 待执行（§7.3 第 2 条） |
| 种子脚本执行 | 未执行 | 未执行 |

## 9. 失败模式与排查顺序

### 9.1 请求中没有 `played_audios`

检查顺序：

1. 维度映射的 `source` 是否为 `case_config`。
2. `source_param` 是否为 `audios`，`target_param` 是否为 `played_audios`。
3. 用例 `config.rounds` 是否存在 `audios`。
4. `_load_case_config` 是否加载成功（失败时仅 WARNING 降级，映射不注入）。

如果缺少的是 `background_noise` 或 `interferers`，除以上检查外，还要确认该字段没有在用例拆分或评估参数组装阶段被剥离，并且 `body_template.rounds[]` 中存在同名字段。

### 9.2 JSON 中有 URI，但 multipart 没有文件

检查顺序：

1. `shared/infrastructure/config.py` 的 OSS bucket、凭证和 endpoint 是否正确。
2. MinIO 中的对象 key 是否符合 `{prefix}/{category}/{key}`。
3. `storage.exists()` 是否返回 true。
4. `_extract_nested_files()` 是否覆盖对应的 list/dict 路径。

### 9.3 multipart 有文件，但算法拿到占位符

检查算法侧 eval_server 的递归还原逻辑，重点确认 list 内部的 dict 是否被遍历，以及占位符字段名是否与 multipart 字段名完全一致。

### 9.4 只传了每轮第一个音频

检查是否错误地使用了首轮摘要逻辑作为评估请求来源。完整评估请求应使用 `rounds[].played_audios` 列表。

## 10. 当前遗留项

1. 外部评估端点恢复后，需要进行一次真实在线验证；V9.7.10 的 42/42 结果是 mock eval server 下的协议和文件一致性验证。
2. 种子脚本 `scripts/migrations/202609/seed_stimulus_audios.py` 已同步为三组参数/映射，尚未对共享数据库执行（交互式确认，幂等可重复）。
3. V9.7.31 侧离线归一化验证已执行（22/22 ALL PASS，§7.3），mock 端到端回归待执行。
4. 若噪声/干扰人纳入具体评估维度，需确认该维度 `body_template.rounds[]` 声明了同名字段并补充端到端回归用例。

## 11. 与 V9.7.10 的实现差异

| 项 | V9.7.10（单体） | V9.7.31（微服务） |
| --- | --- | --- |
| 归一化实现位置 | `backend/utils/algorithm/case_parameter_extractor.py` | `evaluation_service/domain/services/evaluation_service/round_data_builder.py` |
| 归一化调用点 | `_build_evaluation_params` + `_build_case_config` 双调用点 | `_build_single_round` case_config 分支单调用点 |
| 用例配置加载 | `_build_case_config` 整体 deepcopy 剥离 dimensions/evaluation | `_load_case_config` 返回整份 config（含用例级 background_noise），轮配置在分支内 deepcopy |
| 干扰人归一化 | 本地 `_normalize_algorithm_params` | 复用 `algorithm_service` 的 `ParamNormalizerService.normalize_algorithm_params` |
| audio_path 补全 | `_fill_round_audio_paths`（ORM 查询 Audio） | 同名函数（`get_db_session` + 裸 SQL 查 `audios.file_path`） |
| OSS 客户端 | `backend/utils/clients/oss_client.py` | `shared/infrastructure/storage.py` |
| multipart 提取 | `backend/services/evaluation/api_request_handler.py` | `evaluation_service/infrastructure/evaluation_api/api_request_handler.py`（行为一致） |
| 服务端还原 | 仓库内 `eval_server/app/controllers/api.py` | 算法侧 eval_server（仓库外） |
| 前端预设/开关 | `AlgorithmConfigModal.vue` 内联（snake_case + `'e2e'`） | `frontend/src/components/algorithm/algorithmConstants.ts`（camelCase + `TestType.E2E` 枚举） |

## 12. 相关代码

- [轮次归一化与 case_config 映射](../../../evaluation_service/domain/services/evaluation_service/round_data_builder.py)
- [请求与 multipart 处理](../../../evaluation_service/infrastructure/evaluation_api/api_request_handler.py)
- [存储抽象（oss:// 识别与下载）](../../../shared/infrastructure/storage.py)
- [算法参数归一化服务](../../../algorithm_service/domain/services/param_normalizer.py)
- [轮次结构化音频维度参数种子脚本](../../../scripts/migrations/202609/seed_stimulus_audios.py)
- [算法配置预设与功能开关（case_config bundle）](../../../frontend/src/components/algorithm/algorithmConstants.ts)
- [播放链路时间戳记录](../../voice_llm/04_执行测试/backend/33_播放链路时间戳记录.md)
