# 用例执行工作记录（2026-07 ~ 2026-08）

> 统计范围：2026-07-01 ~ 2026-08-31，用例执行共涉及 **81 次提交**（主改动 47 次）。
> 包含：设备驱动（小艺/豆包/ChatGPT/Modbus 等）、执行引擎/任务编排、音频播放（audio_driver）、设备服务。
> 人员分布：lijiahao(40), Zhangbecool(22), ydz-auto(12), tang(4), wjh(3)

## 一、总览

| 子模块 | 涉及提交 | 时间跨度（活跃天数） | 主力人员 |
|---|---|---|---|
| 设备驱动 | 54 | 07-06 ~ 08-28（26 天） | Zhangbecool(22), lijiahao(21), tang(4), ydz-auto(4), wjh(3) |
| 执行引擎/任务编排 | 41 | 07-01 ~ 08-29（24 天） | lijiahao(28), ydz-auto(9), Zhangbecool(4) |
| 音频播放（audio_driver） | 21 | 07-07 ~ 08-19（11 天） | lijiahao(16), ydz-auto(5) |
| 设备服务 | 4 | 07-10 ~ 08-24（2 天） | lijiahao(4) |

**驱动版图演进**：小艺基础驱动（期初已有）→ XiaoyilivechatV2（7-28）→ ChatGPT 语音通话驱动（8-07）→ 豆包 HarmonyOS 驱动（8-13）→ Modbus 设备（7-16）→ DSP 层 PCM 抓取（8-28）。

---

## 二、设备驱动明细

### 7 月：小艺驱动打磨与新设备接入

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-06 | lijiahao | 标签视图修复（执行链路适配） |
| 07-13 | lijiahao | **补全设备驱动 teardown 生命周期调用** |
| 07-16 | lijiahao | **修复小艺录屏启动误判失败及多轮 toggle 问题**；同步 round_aggregator/e2e_device_manager/event_manager/report_utils 修复 |
| 07-16 | lijiahao | **新增 Modbus 设备支持** |
| 07-20 | lijiahao | 记录音频播放毫秒级起止时间并透传至设备驱动 |
| 07-20 | wjh | mp4 转 wav 文件 |
| 07-22 | wjh | **新增音箱播放开始/结束时间戳、录屏首帧写入时间戳，录屏转 wav** |
| 07-27 | ydz-auto | 优化设备驱动、执行器和前端视图的实现 |
| 07-28 | tang | **新增小艺通话 live 专用驱动（XiaoyilivechatV2），支持无回复判定** |
| 07-28 | tang | 更改回复延时运算逻辑：模型首字 - 输入首字 |
| 07-30 | tang | 增加模型未回复识别 |
| 08-04 | Zhangbecool | **小艺通话多轮合并录屏（record_mode=case）与 hypium 导入容错** |

### 8 月上旬：ChatGPT 与豆包驱动上线

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-05 | Zhangbecool | 小艺对话 pcm 抓取/转 wav/按 app 参数化 |
| 08-07 | Zhangbecool | **新增 ChatGPT 语音通话驱动** |
| 08-11 | Zhangbecool | 打断轮跳过等 AI 回复 + 回到原话题配置传执行系统 |
| 08-11 | Zhangbecool | **ChatGPT 多轮连续通话/点 orb 取文本/录屏真实路径** |
| 08-13 | Zhangbecool | **新增豆包 HarmonyOS 语音通话驱动并注册到平台** |
| 08-13 | Zhangbecool | ChatGPT 驱动修复相机 bug + 重做退语音 + record_mode 默认 case |
| 08-13 | Zhangbecool | 豆包/ChatGPT 移除录屏改用 ai_wav 喂评估；修复豆包 ai pcm 后缀 |
| 08-13 | ydz-auto | **用例参数透传至设备驱动，声纹注册改为每轮独立执行** |
| 08-13 | ydz-auto | initialize_devices 参数 key 统一为 round_algo_params |

### 8 月中旬：打断判定与稳定性

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-14 | lijiahao | 音频文件名保留中文 + base_driver get_final_results |
| 08-17 | Zhangbecool | **is_interruption 打断判定改显式白名单，避免字符串假阳性** |
| 08-17 | Zhangbecool | 恢复豆包/ChatGPT 录屏 + 修复豆包录屏时序 bug |
| 08-17 | lijiahao | 小艺驱动更新、豆包更新删除记录功能 |
| 08-17 | lijiahao | 修复重采样启动瞬态吃首字 |
| 08-18 | Zhangbecool | _pick_pcm 改按文件 size 取最大，修 ChatGPT user_wav 静音 |
| 08-19 | Zhangbecool | case 模式每轮拉对话 pcm + 打断轮非末轮延迟 5s |
| 08-20 | Zhangbecool | 小艺/豆包/ChatGPT 驱动加华为音乐 stop_app 防护 |
| 08-20 | lijiahao | **鸿蒙驱动 RPC 自动恢复** |
| 08-20 | Zhangbecool | 清理 ChatGPT 多余等待 + 压缩回复完成检测超时 |
| 08-20 | wjh | 录屏失败时字段映射器不再覆盖有效音频路径 |

### 8 月下旬：PCM 抓取深化与打断精度

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 08-21 | Zhangbecool | **first_frame_ms 改为 ai_wav 首帧时间戳（小艺/豆包/ChatGPT 三驱动统一）** |
| 08-23 | Zhangbecool | 打断评估加 5 类行为判断 + ChatGPT barge-in 简化 |
| 08-23 | Zhangbecool | 鸿蒙驱动开启 PCM dump / ChatGPT barge-in 阶段拆分 |
| 08-23 | ydz-auto | 小艺驱动增加闹钟清理逻辑 + 裁判维度参数重构适配 |
| 08-23 | Zhangbecool | **小艺驱动加停止闹钟 app（CLOCK_BUNDLE），防止闹钟声污染录屏/pcm** |
| 08-24 | lijiahao | pcm 缓存清理重构 + 多轮文件命名 + _stop_recorder 日志增强 |
| 08-24 | lijiahao | result_data 存储路径用设备序列号 + 小艺回复等待超时缩短 |
| 08-27 | Zhangbecool | **小艺 RMS 回复检测 + barge-in + 清 PCM + ai_suffix/ch 适配** |
| 08-28 | Zhangbecool | 修复 _clear_dsp_audio_hook 双重 shell 致 audio_hook 从未清除（多用例抓到同一 pcm） |
| 08-28 | Zhangbecool | **小艺接入 DSP 层 audio_hook PCM 替换 fwk 层（6YF 真机实测通过）** |
| 08-28 | tang | 豆包驱动清除上下文流程重构 |

---

## 三、执行引擎/任务编排明细

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-01 | lijiahao | 算法配置与测试用例模块重构优化（执行引擎初始化） |
| 07-06 | lijiahao | 维度输出字段配置（执行结果链路） |
| 07-07 | lijiahao | 音频导入重构 + 多轮用例与执行优化 |
| 07-08 | lijiahao | 蛇形 key 统一（执行参数链路） |
| 07-10 | lijiahao | 拆分大函数/大文件、处理重复代码（执行引擎代码质量专项） |
| 07-10 | lijiahao | 提交重构基线 |
| 07-10 | lijiahao | **文件夹视图批量勾选 + file_path 斜杠规范化 + 执行引擎重构** |
| 07-10 | lijiahao | **多轮评估改为轮次内即采即评 + 预创建 TestResult** |
| 07-10 | lijiahao | B1-B4 消除重复代码 |
| 07-10 | lijiahao | 修复单轮评估 rounds 索引越界 + 端点 Worker local_db_session 未定义 |
| 07-13 | lijiahao | 补回被误删的 logger 定义 |
| 07-23 | lijiahao | **完善多轮评估聚合与音频维度过滤，增强 e2e 复评与设备驱动** |
| 07-27 | ydz-auto | 优化设备驱动、执行器和前端视图的实现 |
| 07-28 | lijiahao | 修复用例不显示问题 + 重新评估死锁问题 |
| 08-11 | lijiahao | mapping 唯一约束冲突处理（执行参数链路） |
| 08-14 | lijiahao | **e2e 支持按轮跳过评估 + resample temp_dir 简化去 RuntimeError** |
| 08-14 | lijiahao | e2e 多轮最终结果获取 |
| 08-20 | lijiahao | 用例参数提升（执行链路） |
| 08-21 | ydz-auto | **完善 ASR/并发/执行引擎** |
| 08-24 | lijiahao | 评估等待超时保护 |
| 08-26 | lijiahao | **执行失败处理 + 报告后端分页 + 端口配置统一** |
| 08-28 | lijiahao | E2E 整体评估修正 |

**阶段摘要**：7-10 完成执行引擎重构 + 轮次内即采即评（多轮评估架构定型）；8 月补齐按轮跳过评估、并发完善、执行失败处理与超时保护。

---

## 四、音频播放（audio_driver）明细

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-07 | lijiahao | 音频导入/SPL 映射重构（播放链路） |
| 07-08 | lijiahao | spl/playback_device_name 从标注提取 |
| 07-10 | lijiahao | 执行引擎重构（播放侧） |
| 07-16 | lijiahao | 多轮 toggle 修复（播放侧） |
| 07-20 | lijiahao | **记录音频播放毫秒级起止时间** |
| 08-18 | lijiahao | 背景噪声/干扰人多设备兼容（播放侧） |
| 08-18 | ydz-auto | **全局背景噪声独立启停，跨轮次持续播放** |
| 08-18 | ydz-auto | **audio_engine: 修复音频播放异常问题，WASAPI 限制过多** |
| 08-19 | ydz-auto | **WASAPI 线程 COM 初始化 + 设备匹配修复** |
| 08-19 | ydz-auto | 音频播放修复 |
| 08-19 | lijiahao | **audio_driver 多声道支持** |

**阶段摘要**：8 月中旬集中解决 WASAPI 播放稳定性（COM 初始化、设备匹配、异常处理），并新增全局背景噪声独立启停与多声道支持，支撑噪声/干扰人测试场景。

---

## 五、设备服务明细

| 日期 | 作者 | 工作内容 |
|---|---|---|
| 07-10 | lijiahao | 重构基线（设备服务层） |
| 08-13 | ydz-auto | initialize_devices 参数 key 统一 |
| 08-24 | ydz-auto | 报告用例详情重构（设备服务适配） |

---

## 六、关键结论

1. **驱动版图三端成型**：本期从单一小艺驱动扩展为 小艺（含 live V2）/ ChatGPT / 豆包 HarmonyOS / Modbus 四类驱动，覆盖主流语音助手与竞品。
2. **打断（barge-in）能力贯穿后半程**：打断判定白名单化 → ChatGPT barge-in 阶段拆分 → 小艺 RMS 回复检测 + barge-in → 双阈值（用户 1.5s/模型 0.7s），与评估模块的 interruption_metrics 紧密联动。
3. **音频抓取链路升级**：录屏(mp4)→wav → 双路 wav 时间戳 → PCM 抓取 → DSP 层 audio_hook（8-28 真机验证），录音精度和抗污染能力（闹钟清理、华为音乐 stop_app 防护）持续增强。
4. **时间戳体系统一**：播放起止毫秒时间戳 → 音箱播放/录屏首帧时间戳 → first_frame_ms 统一改用 ai_wav 首帧，为时延类指标（回复延时、接管时延）提供一致基准。
5. **执行架构稳定化**：轮次内即采即评 + 预创建 TestResult（7-10 定型）→ 按轮跳过评估 → 并发完善 → 执行失败处理与超时保护，多轮执行的可靠性逐步收敛。

---
*生成时间：2026-09-01，基于 git 提交记录自动统计。*
