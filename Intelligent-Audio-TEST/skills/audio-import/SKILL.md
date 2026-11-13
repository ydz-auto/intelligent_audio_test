---
name: audio-import
description: >-
  音频资源只读排查与导入前准备：查列表、看详情、按 MD5 查重、看目录树、标签、
  特征 / 质量、已配算法、播放历史。触发词：音频列表、查音频、音频详情、这个音频
  有没有导入过、MD5 查重、重复音频、音频目录树、文件夹结构、音频标签、音频格式、
  采样率、音频质量、信噪比、特征、已配算法、播放历史、导入前检查。
  不适用：真正执行导入 / 上传 / 批量标注 / 改元数据（M1 写工具未启用，请在音频
  页面操作或等 M2）；也不负责用例生成、任务执行、报告导出——那些各有专门 Skill。
version: 1.0.0
owner: audio-service
allowed-tools:
  - audio_query
  - platform_contract
  - tool_search
permissions:
  - audio:read
budgets:
  maxToolCalls: 30
  maxTokens: 40000
---

# audio-import

音频域只读 Skill：回答「有哪些音频、某个音频长什么样、这个文件是不是已经导入过、
目录怎么分层、质量如何」，并为导入操作做**读侧准备**（查重、看清目录与标签口径）。

数据一律来自 `audio_query`（网关 `/api/v1/audios` 的真实返回）。**只读不编造**：
接口没返回的字段就说没有，不要用 0、估算值或示例值补齐。

## 何时用

- 用户问音频列表、按关键词 / 格式 / 类型 / 目录 / 标签筛音频；
- 查看某个音频的完整元数据、标签、标注、已配算法；
- 导入前查重：同一 MD5 是否已在库里（命中即秒传复用，不会新建记录）；
- 了解目录树结构，判断目录层级会不会变成标签；
- 看音频特征（基频、主频、THD、能量）或质量（SNR、动态范围、评分）；
- 查某个音频被哪些用例 / 设备播放过（播放历史）。

## 何时不用

- 要「导入 / 上传 / 批量标注 / 改元数据」：M1 只读，`audio_import` /
  `audio_annotate` 仍返回 `TOOL_NOT_ENABLED`；明确告诉用户去音频页面操作，不要假装已导入；
- 要「用标注生成用例 / 跑任务 / 出报告」：转 `testcase-authoring` / `task-operations` /
  `report-studio` 等对应 Skill；
- 问平台通用字段 / 枚举 / 权限码：先用 `platform_contract`；
- 要长尾能力（如分片上传进度 `audio_upload_progress`）：先 `tool_search` 找工具，
  返回了才可调用，没返回就是平台没有该能力。

## 工具与动作

`audio_query` 只有一个必填参数 `action`，动作 → 目标 REST：

| action | 目标端点 | 用途 | 必填参数 |
|---|---|---|---|
| `list` | `GET /api/v1/audios` | 分页列表 + 统计 | — |
| `detail` | `GET /api/v1/audios/{audio_id}` | 单条完整元数据（严格可见性） | `audio_id` |
| `by_ids` | `POST /api/v1/audios/by-ids` | 批量回填元数据（宿主语境） | `ids` |
| `by_md5` | `POST /api/v1/audios/by-md5` | 按 MD5 查重 | `md5_list` |
| `tags` | `GET /api/v1/audios/tags` | 全部标签名 | — |
| `folder_tree` | `POST /api/v1/audios/folder-tree` | 目录树（可按需展开） | — |
| `features` | `GET /api/v1/audios/{id}/features` | 特征分析 | `audio_id` |
| `quality` | `GET /api/v1/audios/{id}/quality` | 质量评估 | `audio_id` |
| `algorithms` | `GET /api/v1/audios/{id}/algorithms` | 已配算法关系 | `audio_id` |
| `playback_history` | `GET /api/v1/audios/{id}/playback-history` | 播放历史分页 | `audio_id` |

列表 / 目录树可用过滤：`keyword`、`format`、`audio_type`、`folder`（仅 list）、
`sample_rate`、`duration`、`tags`、`direction`、`algorithm_type`、`visibility`
（`shared` / `private`，仅 list）；目录树另加 `parent_path`、`depth`（默认 1）。

## 字段口径（与 REST 一致）

**列表**：`{items, total, page, per_page, pages, stats}`；`stats` 是
`total_files`、`total_size`（**带单位的字符串**，如 `12.34 MB`）、
`total_duration`（带单位字符串）、`today_uploads`。总数看 `total`，不要自己数 `items`。

**单条音频**：`id`、`name`（= 文件名）、`original_filename`、`file_path`、
`duration`（秒，float）、`size`（字节）、`sample_rate`、`channels`、`bitrate`、
`format`、`audio_type`（`dry` / `noise` 等）、`asr_text`、`description`、
`source_language`、`md5`、`visibility`（`shared` / `private`）、
`created_by_user_id`、`tags`（字符串数组）、`annotations`（对象数组，含
`format` / `code` / `data` / `source_language` / `target_language`）、
`created_at` / `updated_at`（ISO 8601 字符串）。

**by_md5**：返回 `{md5: {id, name}}` 映射——**只有 id 和 name**，没有完整元数据；
要细节就再用 `detail` 拿。

**tags**：`{items: [标签名...], total}`（单页全量，无分页语义）。

**features**：`audio_id`、`duration`，加三组：
`spectral`（`fundamental_range_low/high`、`dominant_frequency`、`harmonic_distortion`）、
`energy`（`average_energy_db`、`peak_energy_db`、`energy_concentration`）、
`time_domain`（`zero_crossing_rate`、`active_duration_ratio`、`onset_time`）。
数值是**现算的 DSP 结果**（读取音频字节解码），同一文件也可能因解码参数有微小差异；
引用时原样转述，不要四舍五入成整数或补「评级」等接口没有的字段。

**quality**：`snr_db`、`dynamic_range_db`、`frequency_response_score`（0~100）、
`quality_score`（0~100 整数）、`audio_id`、`duration`。没有「优 / 良 / 差」标签，
需要定性结论时按分数说明是你的判断，不是接口字段。

**algorithms**：`[{algorithm_type, is_primary, weight, params}]`，`params` 可能为 null。

**playback_history**：`{items, total, page, per_page, pages}`，条目含
`id`、`audio_id`、`testcase_id`、`testcase_name`、`device_id`、`device_name`、
`result`、`duration`、`source`（如 `preview`）、`played_at`。

## 导入前校验（只读准备）

1. **先查重**：拿到文件 MD5 后 `action=by_md5, md5_list=[...]`。
   命中说明库里有同内容音频——导入会走**秒传**：复用已有记录，不新建、不改名、
   不覆盖标签（请求里的 tags 也不会写回已有记录）。把命中的 `id` / `name` 告诉用户，
   让他决定要不要继续。
2. **确认是否已有记录**：要判断某音频能否查特征 / 质量 / 算法 / 历史，先 `detail`
   看 `file_path` 是否为空；路径缺失时这些接口会报「音频文件路径缺失」。
3. **看目录与标签预期**：`folder_tree` 先看清层级。导入时 `tag_source` 决定目录段
   是否变成标签（`json` 只用手填 / JSON tags，`path` 手填 + 目录段，`both` 全部，
   缺省 `both`）；目录每级目录名各成一个标签，文件名本身不算标签。
4. **看现有标签拼写**：`action=tags` 拿全部标签名，按已有拼写对齐，避免「noise」
   与「噪音」并存。
5. **看质量基线**：`quality` 的 `snr_db` / `quality_score` 可作为同批素材的对比参照；
   不要用它判定「能不能导入」——平台没有这条规则。

## Gotchas

- **M1 写工具未启用**：`audio_import`、`audio_annotate` 返回 `TOOL_NOT_ENABLED`。
  不要因为用户说「帮我导入」就声称已导入；说清楚当前只能查、导入要在音频页面做。
- **by_md5 只回 id/name**：想确认格式、时长、标签，必须再 `detail`，别拿 name 推断格式。
- **detail 对私有音频严格**：`visibility=private` 且非创建人时返回「资源不存在或无权访问」
  （404 与 403 同一文案，防探测）。**不要**据此断言音频一定不存在，只能说「无权访问或不存在」。
- **by_ids 是宿主语境批量通道**：不做 owner 过滤（用例回填场景），能见宿主即可见其引用
  音频；不要把 `by_ids` 的可见范围当成用户对音频的完整权限。
- **目录树权限单独**：`folder_tree` 需要 `audio:folder` 权限；只有 `audio:read` 的用户
  调它会得到普通拒绝文本。其余只读动作只需要 `audio:read`。
- **空结果不是错误**：`by_md5` 无命中返回 `{}`；`by_ids` 空数组返回 `[]`；列表
  `items=[]` 且 `total=0` 是正常空态。不要把它说成「查询失败」。
- **遗留音频的 `md5` 可能为空**：早期入库的音频 `md5` 字段可能是 null。`by_md5`
  无命中只说明库里没有该 MD5 的记录，不能反推文件本身有问题，也不能因此断言「没导入过」。
- **不存在资源的错误码不统一**：详情 / 特征 / 算法对不存在的 ID 可能返回
  HTTP 400 + 业务文案「音频文件不存在」（不是 404）。工具侧表现为普通失败文本，
  如实转述「该音频不存在或无权访问」，不要说成系统故障，也不要猜 ID 重试。
- **0 字节 / 无法解码 / 时长 ≤ 0 的文件不入库**：导入元数据探测失败会整条失败，
  所以列表里查不到这类文件；用户说「明明上传了却查不到」时先问文件是否有效，
  不要编造记录。
- **格式按内容判定，不按扩展名**：导入会用解码器探测真实音频内容，改名的文本文件
  或损坏文件会因无法解码被拒（MIME 与扩展名都不作准）。平台没有统一的单文件大小
  上限（前端直传按 5MB/片分片），不要向用户承诺具体上限。
- **标签过滤语义**：`tags` 传字符串按 AND（全部命中）；要 OR 语义传
  `{name, mode: "or"}` 对象。拼错标签名只会过滤掉数据，不会报错。
- **`sample_rate` / `duration` 是字符串口径**：目录树按 ±100Hz 容差匹配采样率，
  列表与目录树的时长都是区间过滤，不是精确值。
- **不要用 stats 外推**：`total_size` / `total_duration` 是可见行汇总的展示字符串，
  不要拿去算单条平均值。
- **改动未提交前不要承诺数量**：列表会随库变化，报数量时说明是「当前查询时点」。

## 验收

- 任一动作返回的字段名与 REST `/api/v1/audios` 实际返回逐字一致，没有补造字段；
- 列表返回 `total` / `stats` 时与接口一致，不出现自算的近似值；
- 查询前先想清楚必填参数：`detail` / `features` / `quality` / `algorithms` /
  `playback_history` 必须有 `audio_id`，`by_ids` 要有 `ids`，`by_md5` 要有 `md5_list`，
  缺参数会得到「缺少必填参数」，不要绕过；
- 越权 / 不存在资源时如实转述普通拒绝文本，不泄漏资源是否存在；
- 只读工具列表内调用；写动作一律说明未启用并给出替代路径。
