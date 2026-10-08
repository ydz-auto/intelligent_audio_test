# 用例结果评估工作记录（2026-07 ~ 2026-08）

> 统计范围：2026-07-01 ~ 2026-08-31，用例结果评估共涉及 **116 次提交**（全部模块中工作量最大，主改动 94 次）。
> 包含：评估引擎（eval_server）、ASR 服务（asr_server）、评估接口/维度种子（backend）。
> 人员分布：lijiahao(41), wjh(28), Zhangbecool(26), ydz-auto(13), tang(6), huqu-pattern(2)

## 一、总览

| 子模块 | 涉及提交 | 时间跨度（活跃天数） | 主力人员 |
|---|---|---|---|
| 评估引擎（eval_server） | 82 | 07-06 ~ 08-29（27 天） | wjh(26), Zhangbecool(20), lijiahao(19), ydz-auto(9), tang(6), huqu-pattern(2) |
| 评估接口/维度种子（backend） | 62 | 07-06 ~ 08-29（24 天） | lijiahao(32), Zhangbecool(18), ydz-auto(8), wjh(4) |
| ASR 服务（asr_server） | 9 | 07-22 ~ 08-28（6 天） | wjh(6), tang(1), lijiahao(1), Zhangbecool(1) |

**评估维度体系演进**：LLM 裁判（7 月上旬）→ 小艺指标/接管准确率（7 月中下旬）→ ASR 子服务独立（7-22）→ 打断指标 interruption_metrics（8 月上旬）→ 话轮接管 takeover（8 月中旬）→ 环境音 env_judge → 拆分 rejection_judge/interruption_judge + 高频轮换（8 月下旬）。

---

## 二、评估引擎（eval_server）明细

### 阶段 1：多轮评估闭环与 LLM Judge（07-06 ~ 07-16）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-06 | lijiahao | 维度输出字段配置 + 用例标签视图性能优化（评估侧） |
| 07-10 | lijiahao | **补全多轮评估三层闭环** |
| 07-10 | lijiahao | 拆分大函数/大文件、处理重复代码（评估引擎代码质量专项） |
| 07-10 | lijiahao | 修复单轮评估 rounds 索引越界 + 端点 Worker local_db_session 未定义 |
| 07-13 | lijiahao | **LLM Judge 支持多模态音频评估** + 重构日志系统 |
| 07-13 | lijiahao | 批量上传维度支持单轮/多轮使用范围选择，API 与 E2E 维度处理分开 |
| 07-14 | lijiahao | 统一单轮/多轮评估路径，字段名与 param_mappings 对齐 |
| 07-14 | huqu-pattern | **LLM Judge 计算器支持自定义 prompt、query 参数、score/reason 解析及 httpx 绕过代理** |
| 07-16 | huqu-pattern | 修改 LLM prompt |
| 07-16 | lijiahao | 重构多轮评估流程 + 新增 Modbus 设备支持（评估侧） |

### 阶段 2：接管准确率与 ASR 子服务（07-20 ~ 07-31）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-20 | wjh | **接管准确率计算：user_ask 与 model_response 内容切分；以词级时间戳返回 json 文件** |
| 07-22 | wjh | 新增 **ASR 子服务**（独立服务） |
| 07-22 | wjh | 接管/误接管判定 |
| 07-22 | lijiahao | **eval_server/asr_server 配置外部化与目录重构** |
| 07-22 | wjh | 远程调用 ASR 模型获取 json |
| 07-23 | lijiahao | multipart 参数只能通过 form 传递（修复） |
| 07-23 | wjh | xiaoyi_metrics: record_path 改名 record_file + 调用日志 |
| 07-27 | tang | **回复延时运算逻辑修改：模型首字 - 输入首字** |
| 07-27 | ydz-auto | 优化设备驱动、执行器和前端视图的实现（评估侧适配） |
| 07-28 | wjh | 小艺指标迭代（0728） |
| 07-29 | tang | 用户 query 的 ASR 结果识别 |
| 07-30 | wjh | takeover_latency 与 input_asr 修改 |
| 07-30 | tang | 减去 first_frame 时延 |

### 阶段 3：打断指标体系（08-07 ~ 08-13）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-07 | Zhangbecool | 新增打断维度种子 seed_interruption_dimensions |
| 08-07 | Zhangbecool | **新增 interruption_metrics 打断指标任务类型** |
| 08-11 | Zhangbecool | 打断维度种子补 LLM 评估入参与 llm_* 输出参数 |
| 08-11 | Zhangbecool | 打断轮跳过等 AI 回复 + 回到原话题配置传评估系统 |
| 08-11 | Zhangbecool | **打断指标加入可选 LLM 评估** |
| 08-11 | Zhangbecool | ASR 换用 **Silero VAD + SenseVoiceSmall** 出真实段级时间戳 |
| 08-12 | Zhangbecool | xiaoyi_metrics 并入打断指标，打印接收到的双路 wav |
| 08-13 | wjh | LLM 429 重试 + record_file 可空 + false_takeover 空值防护 |

### 阶段 4：话轮接管 takeover 维度（08-14 ~ 08-17）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-16 | wjh | **新增话轮接管维度（takeover）：tor + false_takeover + takeover_latency** |
| 08-16 | wjh | takeover 维度注册到 API 支持列表 + 种子数据 |
| 08-16 | wjh | takeover 健壮性修复：body_template/round0/pause/offset_ms/日志 |
| 08-16 | wjh | 撤回 test_class=接管准确率 分支，恢复全量执行 |
| 08-17 | lijiahao | **turn_taking 主子维度架构：主维度挂 input/mappings，子维度继承 input_params** |
| 08-17 | lijiahao | xiaoyi_metrics 拆分模块到子包 + 新增对应任务类型 |
| 08-17 | lijiahao | **环境音理解指标重构为 env_judge 模块** + 新增 latency/interruption seed |
| 08-17 | lijiahao | 修复重采样启动瞬态吃首字 + takeover 维度参数清理 |
| 08-17 | Zhangbecool | **打断 LLM 评测对齐 Full-Duplex-Bench：量表 0~5 + 行为 v1.5 C 轴四分类** |
| 08-17 | wjh | xiaoyi_metrics 拆分为 turn_taking/llm_judge 子包 + summarize_tasks 脚本 |
| 08-17 | lijiahao | pass_rate 聚合策略（评估侧） |

### 阶段 5：高频轮换与输入路径重构（08-19 ~ 08-21）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-19 | tang | **新增高频轮换场景测试能力（时延计算 + LLM 裁判）** |
| 08-19 | wjh | high_freq_turn_taking/high_freq_llm_judge 集成到 calculate_xiaoyi_metrics 统一入口 |
| 08-19 | Zhangbecool | 打断维度补 LLM 评估文本映射 query/answer/is_return_to_topic |
| 08-19 | Zhangbecool | 打断指标改走 wav 路径，eval_server 内部调 ASR |
| 08-19 | lijiahao | xiaoyi seed 补充 + eval_server 配置/路由更新 |
| 08-20 | wjh | high_freq_llm_judge 超时/编码修复 + latency 指标回退逻辑 |
| 08-20 | Zhangbecool | 录屏不可用时 LLM 裁判维度改用模型回复音频 ai_wav 作主输入 |
| 08-20 | Zhangbecool | LLM 语义裁判录屏→ai_wav 路径收尾 + 音频格式修复 |
| 08-20 | wjh | 录屏失败时字段映射器不再覆盖有效音频路径 |
| 08-20 | lijiahao | noise_latency/non_interactive_latency 入参由 ASR 结果改为 wav 路径 |
| 08-21 | ydz-auto | **计算器基类抽取单轮/多轮公共方法 + llm_judge 策略内联实现** |
| 08-21 | ydz-auto | **重构小艺指标计算器架构 + 完善 ASR/并发/执行引擎** |
| 08-21 | Zhangbecool | env_judge 控制器校验放开 ai_wav + seed 维度从录屏迁到 ai_wav |

### 阶段 6：裁判拆分与 LLM 深化（08-23 ~ 08-29）

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-23 | tang | **env_judge 拆分为 rejection_judge + interruption_judge 两个独立子维度** |
| 08-23 | wjh | env_judge 行为类别从五类改为四类（回应/恢复/不确定询问/未知） |
| 08-23 | wjh | **误接管率 LLM 语义判断 + ASR JSON 按 pcm_case 层级保存** |
| 08-23 | wjh | 简化拒识/打断裁判输入与 prompt，LLM 配置移至 .env |
| 08-23 | Zhangbecool | 打断评估加 5 类行为判断与 LLM 子维度 + ChatGPT barge-in 简化 |
| 08-23 | Zhangbecool | 鸿蒙驱动 PCM dump / ChatGPT barge-in 阶段拆分 / 打断评估 LLM 默认开+success 兜底 |
| 08-23 | ydz-auto | 误接管 LLM 判定字段拆分为 3 个独立字段 + 修正 ASR 模块导入路径 |
| 08-23 | ydz-auto | 小艺驱动闹钟清理逻辑 + 裁判维度拆分与参数重构 |
| 08-24 | wjh | **打断评估改用词级 ASR + 逐轮 LLM，替换段级 ASR + 多模态方案** |
| 08-24 | wjh | VAD 参数调优（threshold=0.6, min_speech=500ms）+ turn_taking 支持 sub_tasks 子维度筛选 |
| 08-24 | wjh | 打断参数 SEG_MERGE_GAP_S 恢复 3.0 + turn_taking 输出格式与误接管联动修复 |
| 08-24 | Zhangbecool | **打断三项主指标改 LLM 计算（gemini 听音频）+ gap3.0 + ASR 非致命** |
| 08-24 | Zhangbecool | 连贯性/相关性/适应性改用例级单值（非轮均值） |
| 08-24 | Zhangbecool | 修复打断 field_path 前缀不匹配——返回嵌套 {interruption: flat} |
| 08-24 | Zhangbecool | 打断 LLM prompt 补量表/行为定义/每指标 reason + 删死方法 |
| 08-24 | Zhangbecool | 打断评估 LLM 失败回退本地时序兜底 |
| 08-24 | Zhangbecool | 打断返回值一致性——LLM 成功时 aux 字段也从 LLM 派生 |
| 08-24 | lijiahao | env_judge 多轮取参改为取最后一轮单次评估 |
| 08-24 | lijiahao | env_judge 行为类别拆分为 0/1 子维度，支持 pass_rate 占比统计 |
| 08-24 | lijiahao | 补全评估维度辅助字段配置并修正 field_path |
| 08-25 | lijiahao | enable_llm_eval 默认值未生效——multipart 布尔序列化修复 |
| 08-25 | lijiahao | 子维度 calculator 独立调用时包装响应结构 |
| 08-25 | lijiahao | **tor 计算修复：MIN_HIT_WORD_TEXT_LEN 改为 1，n_words 改为词数** |
| 08-25 | lijiahao | **子维度 task_type_code 独立 + 主维度共享 ASR + 平台动态 sub_tasks** |
| 08-25 | lijiahao | rejection_judge LLM timeout + param passthrough + 并发配置 |
| 08-26 | wjh | 修复 Paraformer 词级时间戳标点对齐 bug |
| 08-27 | ydz-auto | 重估功能优化 + 打断指标计算完善 |
| 08-27 | ydz-auto | 更新 xiaoyi_metrics README + 新增 API 入参出参文档 |
| 08-28 | Zhangbecool | 打断时延时长指标改为毫秒（ms） |
| 08-28 | Zhangbecool | **打断评估数值指标全回本地，LLM 改吃词级 ASR 做复核+打分** |
| 08-28 | Zhangbecool | 打断 LLM 产出三维分项理由对齐 seed + 角色约束 + per_event 单位修正 |
| 08-28 | tang | 豆包驱动清除上下文流程重构 + 词级 ASR 切换为 qwen3.5-omni-plus |
| 08-28 | wjh | 适配 qwen3.5-omni-plus 音频发送格式 + 端口调整 |
| 08-28 | wjh | 词级 ASR 切回远程 Paraformer + 端口修正 8888 |
| 08-29 | Zhangbecool | **打断双阈值（用户 1.5s/模型 0.7s）+ LLM 语义判定 success** |
| 08-29 | wjh | avg_recovery_latency_s 仅统计 interruption 事件，不计入 recovery_only 首轮 |
| 08-29 | lijiahao | 多轮评估维度隔离与报告聚合 |

---

## 三、ASR 服务（asr_server）明细

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-22 | wjh | **新建 ASR 子服务**（独立部署） |
| 07-22 | lijiahao | asr_server 配置外部化与目录重构 |
| 07-22 | wjh | 远程调用 ASR 模型获取 json |
| 08-11 | Zhangbecool | **换用 Silero VAD + SenseVoiceSmall 出真实段级时间戳** |
| 08-24 | wjh | VAD 参数调优（threshold=0.6, min_speech=500ms） |
| 08-26 | wjh | 修复 Paraformer 词级时间戳标点对齐 bug |
| 08-28 | tang | 词级 ASR 切换为 qwen3.5-omni-plus |
| 08-28 | wjh | 适配 qwen3.5-omni-plus 音频发送格式（image_url+data URI） |
| 08-28 | wjh | 词级 ASR 切回远程 Paraformer + 端口修正 8888 |

**技术选型轨迹**：段级 ASR（SenseVoice）→ 词级 ASR（Paraformer）→ 尝试 qwen3.5-omni-plus → 回退远程 Paraformer。

---

## 四、评估接口/维度种子（backend）明细

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-06 | lijiahao | 维度输出字段配置（评估接口层） |
| 07-10 | lijiahao | 多轮评估三层闭环（接口层） |
| 07-13 | lijiahao | LLM Judge 多模态评估接口 |
| 07-14 | huqu-pattern | LLM Judge 计算器自定义解析（接口对接） |
| 07-16 | lijiahao | 多轮评估流程重构（接口层） |
| 08-07 | Zhangbecool | 主程序侧打断维度种子 |
| 08-11 | Zhangbecool | 打断维度种子补 LLM 入参/出参 |
| 08-13 | wjh | false_takeover 空值防护（接口层） |
| 08-16 | wjh | takeover 维度注册与种子数据 |
| 08-17 | lijiahao | env_judge/latency/interruption 种子 + turn_taking 主子维度架构 |
| 08-20 | lijiahao | 打断/小艺维度重构 + 用例参数提升 |
| 08-23 | ydz-auto | 裁判维度拆分与参数重构 |
| 08-24 | lijiahao | 补全评估维度辅助字段配置并修正 field_path |
| 08-25 | lijiahao | 子维度 task_type_code 独立，支持 sub_tasks 精确控制 |

---

## 五、关键结论

1. **评估是本期绝对核心**：主改动 94/234 ≈ 40%，6 人全部参与。
2. **维度体系从 1 个长到 6+ 个**：llm_judge → xiaoyi_metrics（接管）→ interruption_metrics（打断）→ takeover（话轮接管）→ env_judge → rejection_judge/interruption_judge → high_freq_*（高频轮换），最终形成 turn_taking 主子维度架构。
3. **ASR 方案三次迭代**：段级（Silero VAD + SenseVoice）→ 词级（Paraformer，修标点对齐 bug）→ 尝试 qwen3.5-omni-plus 后回退 Paraformer。
4. **输入源统一**：从录屏(mp4→wav)逐步迁移到 ai_wav（模型回复音频）作主输入，录屏不可用不再阻塞评估。
5. **LLM 评测深度对齐学术基准**：打断指标对齐 Full-Duplex-Bench（量表 0~5、行为四分类、双阈值 1.5s/0.7s、LLM 失败本地时序兜底）。
6. **代码质量专项**：计算器基类抽取、turn_taking/llm_judge 子包拆分、配置外部化、共享 ASR 复用。

---
*生成时间：2026-09-01，基于 git 提交记录自动统计。*
