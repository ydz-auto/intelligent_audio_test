/**
 * 算法配置页常量（features/algorithm-config；17_配置运维.md §10 中文文案源）。
 * 枚举/状态 + 展示文案直接存中文，组件直接渲染（AGENTS.md §3.1 全中文硬编码）。
 */

/** 算法状态选项（§3.4 状态 facet + 列表 StatusBadge） */
export const ALGORITHM_STATUS_OPTIONS = [
  { value: 'online', label: '上线' },
  { value: 'offline', label: '下线' },
] as const

/** 算法状态 → StatusBadge 语义（§8：online=success 上线 / offline=neutral 下线） */
export const ALGORITHM_STATUS_META: Record<
  'online' | 'offline',
  { label: string; badgeVariant: 'success' | 'neutral' }
> = {
  online: { label: '上线', badgeVariant: 'success' },
  offline: { label: '下线', badgeVariant: 'neutral' },
}

/** 参数方向选项（§6.3 设备参数表格） */
export const PARAM_DIRECTION_OPTIONS = [
  { value: 'input', label: '输入' },
  { value: 'output', label: '输出' },
] as const

/** 设备参数类型选项（§6.3；API 参数改由 API 实例作用域维护） */
export const DEVICE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'audio_stream', label: '音频流' },
  { value: 'audio_file', label: '音频文件' },
  { value: 'text_file', label: '文本文件' },
  { value: 'rttm', label: 'RTTM标注' },
  { value: 'stm', label: 'STM标注' },
  { value: 'json', label: 'JSON结构化' },
] as const

/** 用例参数类型选项（§6.3） */
export const CASE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'textarea', label: '多行文本' },
  { value: 'switch', label: '开关' },
  { value: 'slider', label: '滑块' },
  { value: 'audio_select', label: '音频选择' },
  { value: 'device_select', label: '设备选择' },
  { value: 'json', label: 'JSON结构化' },
] as const

/**
 * 用例参数适用范围选项（§6.3；词表对齐后端 `CaseParamScope` = common + DeviceType 三值。
 * 注意与参数策略的 `param_profiles.scope`（api / device）无关，两者不可混用）。
 */
export const CASE_PARAM_SCOPE_OPTIONS = [
  { value: 'common', label: '通用' },
  { value: 'physical', label: '真机' },
  { value: 'http_api', label: 'HTTP API' },
  { value: 'websocket_api', label: 'Realtime WS' },
] as const

/** 参考参数类型选项（§6.4） */
export const REFERENCE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'audio', label: '音频' },
  { value: 'json', label: 'JSON' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' },
] as const

/** 参考参数合并方式选项（§6.4；V9.7.10/V9.7.31 Vue 同款 join=拼接，非 concat） */
export const REFERENCE_PARAM_MERGE_OPTIONS = [
  { value: 'join', label: '拼接' },
  { value: 'collect', label: '收集数组' },
  { value: 'first', label: '取第一个' },
] as const

/** 转换类型枚举（§6.5 + V9.7.10 MappingEditor transformOptions） */
export const TRANSFORM_TYPE_OPTIONS = [
  { value: 'none', label: '无转换' },
  { value: 'uppercase', label: '转大写' },
  { value: 'lowercase', label: '转小写' },
  { value: 'json_parse', label: 'JSON解析' },
  { value: 'rttm_to_obj', label: 'RTTM转对象' },
  { value: 'stm_to_obj', label: 'STM转对象' },
] as const

/** 列表页分页每页条数选项（§3.7 PAGE_SIZE_OPTIONS 语义） */
export const PAGE_SIZE_OPTIONS = [10, 20, 30, 50, 100]

/** 列表默认每页条数（§3.2 validateSearch pageSize catch 20） */
export const DEFAULT_PAGE_SIZE = 20

/** 搜索防抖毫秒 */
export const ALGORITHM_SEARCH_DEBOUNCE_MS = 300

/** 分组 facet 全部分组哨兵值 */
export const GROUP_FILTER_ALL = 'all'

/** 状态 facet 全部状态哨兵值 */
export const STATUS_FILTER_ALL = 'all'

/** 用例参数页签「功能特性快捷开关」hint（§6.3） */
export const FEATURE_BUNDLES_HINT = '勾选后自动批量添加/删除对应参数'

/** 参考参数分节说明（§6.4） */
export const REFERENCE_PARAMS_DESCRIPTION =
  '配置算法的参考参数，用于存储参考文本、音频、文件等数据。参考类型支持：文本、音频、RTTM、STM 等。配置的参考字段可参与评估参数映射。'

/** 评估维度分节说明（§6.6） */
export const DIMENSIONS_DESCRIPTION =
  '关联算法到评估维度，设置权重与默认维度。'

/** 导入算法说明（§7.6） */
export const IMPORT_DIALOG_DESCRIPTION =
  '粘贴或上传算法定义 JSON（与导出格式一致），导入后立即生效。'

/** 功能特性快捷开关（§6.3 用例参数页签；勾选自动批量添加/删除对应参数；前端 UI 常量非接口数据） */
export const FEATURE_BUNDLES = [
  {
    key: 'translation',
    label: '翻译',
    params: ['source_language', 'target_language'],
  },
  {
    key: 'noise',
    label: '噪声',
    params: ['noise_level'],
  },
  {
    key: 'speaker',
    label: '说话人',
    params: ['speaker_count', 'max_idle_ms'],
  },
  {
    key: 'streaming',
    label: '流式',
    params: ['vad_sensitivity', 'continuity_mode'],
  },
]

/** 用例参数代码预设（§6.3 datalist 预设，新建用例参数 placeholder 建议；前端 UI 常量非接口数据） */
export const CASE_PARAM_CODE_PRESETS = [
  'source_language',
  'target_language',
  'noise_level',
  'speaker_count',
  'audio_file',
  'vad_sensitivity',
  'max_idle_ms',
  'continuity_mode',
  'wake_word',
  'speech_speed',
]

/** 自动保存倒计时秒数（§6.2；30 秒档位同 newAPI EMAIL_VERIFICATION_COUNTDOWN/PASSWORD_RESET_COUNTDOWN = 30） */
export const AUTO_SAVE_COUNTDOWN_SECONDS = 30

/** 参数行失焦防抖保存毫秒（§6.2；对照旧 Vue useAlgorithmParamOps.ts:114 实测 1500ms） */
export const PARAM_BLUR_DEBOUNCE_MS = 1500

/** 作用域 chips（§6.4 统一参数表过滤；ToggleGroup 单选计数，默认「全部」） */
export const PARAM_SCOPE_CHIPS = [
  { value: 'all', label: '全部' },
  { value: 'device', label: '设备' },
  { value: 'case', label: '用例' },
] as const

export type ParamScopeChip = (typeof PARAM_SCOPE_CHIPS)[number]['value']

/** 统一参数表列头（§6.4 桌面 min-w-[1100px] 横向滚动） */
export const PARAM_TABLE_COLUMN_HEADERS = {
  scope: '作用域',
  paramCode: '参数代码',
  paramName: '参数名称',
  paramType: '参数类型',
  direction: '方向',
  applicableScope: '适用范围',
  required: '必填',
  defaultValue: '默认值',
  range: '范围约束',
  annotationCode: '标注代码',
  fieldPath: '字段路径',
  helpText: '帮助文本',
} as const

/** §6.2 草稿保存文案组（§10 指定文案，全中文硬编码） */
export const DRAFT_MESSAGES = {
  /** footer 倒计时「将在 {n} 秒后自动保存草稿」（n 30→0 递减） */
  countdown: (secondsLeft: number) => `将在 ${secondsLeft} 秒后自动保存草稿`,
  /** 保存中形态（footer Spinner） */
  saving: '正在保存草稿…',
  /** 成功时间戳形态（footer 常驻「上次保存 HH:mm:ss」） */
  lastSaved: (time: string) => `上次保存 ${time}`,
  /** 手动/失焦草稿保存成功 toast；30s 自动保存静默（仅时间戳更新） */
  saved: '草稿已保存',
  /** 结构校验不过 → 倒计时暂停 + footer 内联 Alert（不可手动关闭） */
  validationBlocked: '有校验未通过，草稿暂存暂停',
  /** 失败 toast/内联 Alert（不自动重试，防重试风暴；保留编辑态转手动） */
  failure: '草稿保存失败，请检查网络后重试',
  /** 乐观锁冲突 footer inline Alert（§6.2a） */
  conflict: '草稿已过期：该算法已被他人修改',
  /** 冲突就地动作 */
  refresh: '立即刷新',
  continueEdit: '继续编辑',
  /** 刷新前确认（§6.2a：刷新丢弃当前草稿） */
  refreshConfirm: '刷新将丢弃当前草稿，确定？',
  /** 刷新成功 toast */
  refreshed: '已刷新为最新版本',
  /** 编辑打开时草稿存在提示（§6.1，后端 has_draft 语义） */
  hasUnpublishedDraft: '该算法存在未发布的草稿',
} as const

/** §6.2 发布文案组（§10 指定文案，全中文硬编码） */
export const PUBLISH_MESSAGES = {
  /** 发布成功 toast（新建态走「算法已创建」） */
  published: '算法已发布',
  created: '算法已创建',
  /** 发布中按钮文案 */
  publishing: '发布中…',
  /** 发布失败 toast/内联 Alert */
  failure: '发布失败，请重试',
  /** 发布冲突 AlertDialog（§6.2a） */
  conflictTitle: '发布冲突',
  conflictDescription: '发布冲突：该算法已被他人修改。',
  refreshDiscard: '刷新并丢弃我的更改',
  continueEdit: '继续编辑',
  /** 后端 RPC force 参数支持后启用（未定则隐藏） */
  forcePublish: '强制发布覆盖',
  /** 后端 409 算法代码已存在 */
  codeExists: '算法代码已存在',
} as const
