/**
 * 站内文档内容（INT-745 A06）—— 结构化内容（降级纯 HTML 渲染）
 *
 * markdown 渲染依赖评估结论（写回交付评论）：原 Vue 无 marked/shiki，新增依赖
 * 引入构建/网络风险；本卡选用结构化内容 + 模板渲染（等价「降级纯 HTML 内容」），
 * 代码块用原 card 深色块，标题锚点/目录由结构驱动。
 */
export interface GuideSection {
  id: string
  title: string
  blocks: GuideBlock[]
}

export type GuideBlock =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; items: string[] }
  | { kind: 'code'; language: string; code: string }
  | { kind: 'table'; headers: string[]; rows: string[][] }

export interface GuideDocument {
  title: string
  subtitle: string
  sections: GuideSection[]
}

/** 平台使用手册（/user-guide） */
export const USER_GUIDE: GuideDocument = {
  title: '平台使用手册',
  subtitle: '从准备资产到看懂报告，覆盖平台全部功能页的操作说明。',
  sections: [
    {
      id: 'quick-start',
      title: '快速开始',
      blocks: [
        {
          kind: 'paragraph',
          text: '按以下顺序准备资产并完成第一次测试：登录平台 → 配置评估维度 → 管理设备 → 导入测试音频 → 创建用例 → 执行测试 → 查看报告。',
        },
        {
          kind: 'list',
          items: [
            '登录平台（右上角「登录」）。',
            '在「评估维度」配置评估指标与权重（/Evaluation）。',
            '在「设备管理」连接被测真机或播放设备（/Device）。',
            '在「音频管理」导入测试音频，可勾选自动生成测试用例（/AudioImport）。',
            '在「用例管理」创建或选择测试用例（/TestCaseManager）。',
            '执行测试：在「开始测试」按四步向导完成配置与执行（/start-test）。',
            '在报告页查看结果（/history-reports）。',
          ],
        },
      ],
    },
    {
      id: 'concepts',
      title: '核心概念',
      blocks: [
        {
          kind: 'paragraph',
          text: '平台的核心对象与一句话解释：',
        },
        {
          kind: 'table',
          headers: ['概念', '一句话解释', '所在页面'],
          rows: [
            ['测试执行', '统一的测试入口，选择用例与资源（设备/API）后执行测试', '/start-test'],
            ['测试用例', '一次测试的脚本与参数集合', '/TestCaseManager'],
            ['任务', '一次用例在设备/API 上的执行记录', '/tasks'],
            ['报告', '任务执行结果的多维度分析', '/history-reports'],
            ['评估维度', '准确率、召回率等指标口径配置', '/Evaluation'],
            ['SPL 映射', '数字增益与声压级的换算关系', '/SPLMapping'],
          ],
        },
      ],
    },
    {
      id: 'prepare',
      title: '准备工作',
      blocks: [
        {
          kind: 'paragraph',
          text: '首次使用请先配置评估维度和播放设备，然后导入测试音频。',
        },
        {
          kind: 'list',
          items: [
            '评估维度管理（/Evaluation）：配置 ASR 准确率、翻译质量（COMET）、流畅度（气泡率/停顿率）等指标口径与权重。',
            '设备管理（/Device）：通过 ADB/HDC 连接 Android/鸿蒙真机，配置播放设备声卡通道与采样率。',
            '导入音频管理（/AudioImport）：本地上传或文件夹批量导入，导入时可选择自动生成测试用例并设置声压级。',
          ],
        },
      ],
    },
    {
      id: 'testcases',
      title: '用例管理',
      blocks: [
        {
          kind: 'paragraph',
          text: '用例管理页（/TestCaseManager）支持分组、标签筛选、参考参数与批量导入导出，用例可被各类测试执行流程复用。',
        },
        {
          kind: 'list',
          items: [
            '分组与标签：按测试类型/场景组织，标签支持多选筛选。',
            '批量操作：批量导入（文件/文件夹）、批量导出（Excel/JSON）、批量复制与移动。',
            '参考参数：为算法类型配置参数模板，用例继承后按需覆盖。',
          ],
        },
      ],
    },
    {
      id: 'execute',
      title: '执行测试',
      blocks: [
        {
          kind: 'paragraph',
          text: '「开始测试」（/start-test）四步向导：选择测试用例 → 选择设备/API → 执行测试 → 查看结果。',
        },
        {
          kind: 'list',
          items: [
            '在真实设备上运行完整语音链路测试，支持多设备并行，实时查看进度与日志。',
            '支持批量测试语音识别/翻译端点，统计响应时间、并发数与成功率。',
            '任务执行后可回到任务页（/tasks）查看进度、结果统计与日志，支持失败用例重试/跳过。',
          ],
        },
      ],
    },
    {
      id: 'tasks',
      title: '任务与发布',
      blocks: [
        {
          kind: 'paragraph',
          text: '任务页（/tasks）提供日常任务、已发布任务等页签：日常任务记录全部执行历史；已发布任务支持将任务发布为固定版本供他人执行。',
        },
        {
          kind: 'list',
          items: [
            '筛选与批量：按时间、状态、测试类型筛选，支持批量删除/合并/导出。',
            '已发布任务：发布/执行/新版本/归档，Benchmark 徽章可链入排行榜。',
            '结果挑选合并：在购物车中收集任务/用例结果，生成合并对比报告。',
          ],
        },
      ],
    },
    {
      id: 'reports',
      title: '查看报告',
      blocks: [
        {
          kind: 'paragraph',
          text: '报告中心（/history-reports）管理全部报告：单任务报告、跨任务对比报告与 Benchmark 报告。报告详情页支持发布、导出、复制链接与下载日志。',
        },
        {
          kind: 'list',
          items: [
            '报告展示页（顶部导航「报告」直达）：已发布报告的对外展示列表。',
            '报告详情（/report/:id）：类型分发任务/对比/Benchmark，阅读优先版式。',
            '导出：支持 CSV/PDF 等格式，跨任务对比报告一键生成。',
          ],
        },
      ],
    },
    {
      id: 'troubleshooting',
      title: '执行失败自查',
      blocks: [
        {
          kind: 'table',
          headers: ['现象', '检查方式'],
          rows: [
            ['设备离线', '设备管理页确认设备在线状态，检查 ADB/HDC 连接'],
            ['音频格式不支持', '确认音频为 MP3/WAV/FLAC/AAC 等受支持格式'],
            ['算法参数不匹配', '核对用例的算法参数与算法定义是否一致'],
            ['任务状态冲突（203）', '确认任务未被并发执行或已停止'],
            ['报告生成失败', '查看任务详情日志，确认评估维度端点可用'],
          ],
        },
      ],
    },
    {
      id: 'faq',
      title: '常见问题',
      blocks: [
        {
          kind: 'list',
          items: [
            '需要写代码才能用吗？——不需要，在页面上完成 选择用例 → 选择设备 → 执行 三步即可发起测试。',
            '首次使用先准备什么？——按顺序配置评估维度、连接设备、导入测试音频。',
            '怎么选择测试资源？——验证整机语音链路用设备；只验证识别/翻译服务指标用 API 资源。',
            '测试失败了怎么排查？——先看任务详情失败统计与日志（/LogView），常见原因见「执行失败自查」。',
            '报告能导出吗？——支持单任务报告与跨任务对比报告导出（CSV/PDF）。',
          ],
        },
      ],
    },
    {
      id: 'support',
      title: '联系支持',
      blocks: [
        {
          kind: 'paragraph',
          text: '遇到问题请联系平台管理员。反馈模板（请隐藏敏感信息）：',
        },
        {
          kind: 'code',
          language: 'text',
          code: '功能模块：\n操作步骤：\n发生时间：\n错误提示：',
        },
      ],
    },
  ],
}

/** 平台 API 手册（/user-guide-api） */
export const API_GUIDE: GuideDocument = {
  title: '平台 API 手册',
  subtitle: '接口认证、响应格式、错误码与核心接口 curl 示例。',
  sections: [
    {
      id: 'api-prepare',
      title: '准备接入信息',
      blocks: [
        {
          kind: 'paragraph',
          text: 'Base URL = 站点根 + /api/v1（如 http://<host>:5000/api/v1）；认证使用 JWT Bearer Token；后端 AUTH_MODE=off 时免令牌。',
        },
        {
          kind: 'code',
          language: 'bash',
          code: 'export API_BASE_URL="{{API_BASE_URL}}"\nexport TOKEN="替换为你的访问令牌"',
        },
      ],
    },
    {
      id: 'api-auth',
      title: '认证',
      blocks: [
        {
          kind: 'paragraph',
          text: '调用 POST /api/v1/auth/login 获取 access_token，之后在请求头携带 Authorization: Bearer {token}。',
        },
        {
          kind: 'code',
          language: 'bash',
          code: 'curl -X POST "$API_BASE_URL/auth/login" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"username":"admin","password":"******"}\'',
        },
        {
          kind: 'code',
          language: 'bash',
          code: 'curl "$API_BASE_URL/tasks" \\\n  -H "Authorization: Bearer $TOKEN"',
        },
      ],
    },
    {
      id: 'api-response',
      title: '响应格式与错误码',
      blocks: [
        {
          kind: 'paragraph',
          text: '统一响应结构：{ code, message, data, detail }。code=0 表示成功；非 0 为业务错误码。',
        },
        {
          kind: 'table',
          headers: ['错误码', '含义'],
          rows: [
            ['0', '成功'],
            ['101', '参数错误'],
            ['102', '未授权'],
            ['103', '权限不足'],
            ['201', '资源锁定'],
            ['202', '资源不存在'],
            ['203', '状态冲突'],
            ['204', '引擎异常'],
            ['301', '上游超时'],
            ['302', '硬件超时'],
            ['303', '系统繁忙'],
          ],
        },
      ],
    },
    {
      id: 'api-tasks',
      title: '任务接口',
      blocks: [
        {
          kind: 'paragraph',
          text: '任务接口覆盖创建、启动、停止与进度查询：',
        },
        {
          kind: 'code',
          language: 'bash',
          code: '# 分页查询任务（支持 status/algorithm_type/时间范围筛选）\ncurl "$API_BASE_URL/tasks?page=1&page_size=10" \\\n  -H "Authorization: Bearer $TOKEN"\n\n# 创建任务\ncurl -X POST "$API_BASE_URL/tasks" \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"name":"示例任务","test_case_ids":[1,2]}\'',
        },
        {
          kind: 'code',
          language: 'bash',
          code: '# 启动任务 / 停止任务 / 进度查询\ncurl -X POST "$API_BASE_URL/tasks/1/start" -H "Authorization: Bearer $TOKEN"\ncurl -X POST "$API_BASE_URL/tasks/1/stop" -H "Authorization: Bearer $TOKEN"\ncurl "$API_BASE_URL/tasks/1/progress" -H "Authorization: Bearer $TOKEN"',
        },
      ],
    },
    {
      id: 'api-assets',
      title: '用例 / 音频 / 设备 / 报告接口',
      blocks: [
        {
          kind: 'paragraph',
          text: '每类资产取代表性端点：',
        },
        {
          kind: 'code',
          language: 'bash',
          code: '# 用例列表\ncurl "$API_BASE_URL/testcases?page=1&page_size=10" -H "Authorization: Bearer $TOKEN"\n\n# 音频列表\ncurl "$API_BASE_URL/audios" -H "Authorization: Bearer $TOKEN"\n\n# 设备列表\ncurl "$API_BASE_URL/test-devices" -H "Authorization: Bearer $TOKEN"\n\n# 报告列表\ncurl "$API_BASE_URL/reports?page=1&page_size=10" -H "Authorization: Bearer $TOKEN"',
        },
      ],
    },
    {
      id: 'api-realtime',
      title: '实时推送',
      blocks: [
        {
          kind: 'paragraph',
          text: '任务进度事件走 SSE：GET /api/v1/sse/events（需 sse:read）；任务日志走 WebSocket 订阅（log:websocket）。',
        },
        {
          kind: 'code',
          language: 'bash',
          code: '# SSE 事件流（保持连接）\ncurl -N "$API_BASE_URL/sse/events" \\\n  -H "Authorization: Bearer $TOKEN"',
        },
      ],
    },
    {
      id: 'api-retry',
      title: '错误处理与重试',
      blocks: [
        {
          kind: 'list',
          items: [
            '429/5xx：采用指数退避重试（如 1s → 2s → 4s），最大 5 次。',
            '幂等与重复提交：创建类接口注意幂等，避免重复提交产生重复任务。',
            '流式断开：SSE 断线后按 Last-Event-ID 续接或重新订阅。',
          ],
        },
      ],
    },
    {
      id: 'api-faq',
      title: '常见问题',
      blocks: [
        {
          kind: 'table',
          headers: ['状态/错误码', '处理建议'],
          rows: [
            ['401', 'Token 失效或未携带，重新登录获取'],
            ['403', '无该接口权限，联系管理员授权'],
            ['202', '资源不存在，检查 ID 是否正确'],
            ['203', '状态冲突，确认任务/资源状态'],
            ['302', '硬件超时，检查设备在线状态'],
            ['303', '系统繁忙，稍后重试'],
          ],
        },
      ],
    },
    {
      id: 'api-windows',
      title: 'Windows 与调用环境',
      blocks: [
        {
          kind: 'paragraph',
          text: 'Windows 环境使用 curl.exe（Win10+ 自带），PowerShell 中注意引号转义：',
        },
        {
          kind: 'code',
          language: 'powershell',
          code: 'curl.exe -X POST "$env:API_BASE_URL/auth/login" `\n  -H "Content-Type: application/json" `\n  -d \'{"username":"admin","password":"******"}\'',
        },
      ],
    },
  ],
}

/**
 * 接入指南（INT-1435）—— 面向接入方开发者，三章：Realtime API / 普通 HTTP API / 实体设备 E2E。
 * 内容转写自 INT-1291 产出（doc/ 下三份接入指南 md，统一结构：接入总览3件事 →
 * 写适配器/驱动（继承谁+模板+覆写点）→ 用例特殊处理（含『适用算法』列）→ 注册配置 → 验证 → FAQ）。
 */
export const INTEGRATION_GUIDE: GuideDocument = {
  title: '接入指南',
  subtitle: '面向接入方开发者：Realtime API（websocket_api）/ 普通 HTTP API（http_api）/ 实体设备 E2E（physical）三类被测对象的接入方法。',
  sections: [
    {
      id: 'realtime-api',
      title: 'Realtime API 接入（websocket_api）',
      blocks: [
        { kind: 'heading', text: '一、接入总览（3 件事）' },
        {
          kind: 'table',
          headers: ['你要做的事', '放哪', '写代码？'],
          rows: [
            ['① 厂商协议适配器（WS 事件/握手/输出）', 'api_test_service/infrastructure/adapters/vendors/你的厂商.py', '✅'],
            ['② 厂商注册（枚举 + 映射 + @register）', 'common_enums.py + registry.py', '✅（约 5 行）'],
            ['③ 参数配置（评估字段/会话/用例）', '算法配置 field_mapper + APIs 表 + 用例配置', '❌ 纯配置'],
          ],
        },
        {
          kind: 'paragraph',
          text: '执行器（RealtimeSessionExecutor）是通用的：正常轮/打断轮/推流节奏/等待全是通用编排，用例配置驱动。接任何厂商都不改执行器。',
        },
        { kind: 'heading', text: '二、写适配器（= Realtime 的 driver）' },
        { kind: 'heading', text: '2.1 继承谁' },
        {
          kind: 'code',
          language: 'text',
          code: 'ApiVendorAdapter (Port，抽象契约，domain/ports/)\n   ├── RealtimeAdapterBase   ← Realtime 厂商继承这个（协议级，protocol/）\n   │      └── OpenAIRealtimeAdapter  （官方样例：5 个类属性，零覆写）\n   │      └── 你的厂商适配器\n   └── (HTTP 厂商) 直接实现 Port（见《接入指南·普通 HTTP API》）',
        },
        {
          kind: 'paragraph',
          text: '继承 RealtimeAdapterBase 白拿：WS 连接、事件队列、pre_process/send/recv/output/close 同形方法面、代理透传、密钥链、会话亲和。',
        },
        { kind: 'heading', text: '2.2 最小模板（事件协议与 OpenAI 相同 → 5 行就够）' },
        {
          kind: 'code',
          language: 'python',
          code: `# adapters/vendors/my_vendor_adapter.py
from shared.models.common_enums import AdapterProtocol, AdapterVendor, VendorAdapterType
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import RealtimeAdapterBase
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

@register_vendor_adapter
class MyVendorRealtimeAdapter(RealtimeAdapterBase):
    protocol = AdapterProtocol.REALTIME
    vendor = AdapterVendor.MY_VENDOR
    adapter_type = VendorAdapterType.MY_VENDOR
    display_name = 'xx Realtime 适配器'
    _transport_vendor = 'openai'   # 事件协议与 OpenAI 相同 → 到此结束`,
        },
        { kind: 'heading', text: '2.3 协议不同 → 覆写点表' },
        {
          kind: 'table',
          headers: ['厂商差异', '覆写方法', '写什么'],
          rows: [
            ['握手载荷不同', 'pre_process', '你的 session.update 字段'],
            ['事件字段不同', 'recv', '厂商事件 → 归一化 RealtimeFrameType（打断依赖 user_speech_started / response_cancelled）'],
            ['输出结构不同', 'output / post_process', '聚合 audio/text/frame'],
            ['等待语义不同', 'wait_ai_speaking / wait_ai_complete', 'AI 开口/完成判定'],
            ['打断字段方言不同', 'resolve_round_mode', '默认读 is_interruption（_as_bool 兼容 int/bool/str）；厂商用 barge_in 等覆写'],
            ['传输完全私有', '_build_client', '替换默认 WS 客户端'],
          ],
        },
        {
          kind: 'code',
          language: 'python',
          code: `# 覆写示例：厂商打断事件名不同 → 归一化
def recv(self, timeout=5.0):
    evt = self._client.recv(timeout)
    if evt.get('type') == 'vendor_a_barge':   # 厂商自己的打断事件
        return {'type': RealtimeFrameType.USER_SPEECH_STARTED.value, ...}
    return evt`,
        },
        { kind: 'heading', text: '三、注册（20 家也就这几行）' },
        {
          kind: 'code',
          language: 'python',
          code: `# common_enums.py
class AdapterVendor(str, Enum):     MY_VENDOR = 'my_vendor'
class VendorAdapterType(str, Enum): MY_VENDOR = 'my_vendor'

# registry.py
_FLAT_KEY_DIMENSIONS = { ..., VendorAdapterType.MY_VENDOR: (AdapterProtocol.REALTIME, AdapterVendor.MY_VENDOR) }`,
        },
        {
          kind: 'paragraph',
          text: '分发是表驱动的（resolve_for）：配置了 vendor_adapter=my_vendor 走你的适配器；未配置走默认。执行器零改动。',
        },
        { kind: 'heading', text: '四、用例特殊处理（纯配置）' },
        {
          kind: 'table',
          headers: ['用例场景', '配什么', '适用算法', '谁来处理'],
          rows: [
            ['正常对话轮', '每轮输入音频 + query', '全部', '执行器通用编排'],
            ['打断轮（插话）', 'is_interruption: true + interruption_delay_ms（默认 1000ms）', '仅 voice_llm 等对话类', '执行器 _execute_interruption_round 通用编排'],
            ['推流中打断', 'API 配置 allow_barge_in 节奏策略', '仅 voice_llm 等对话类', '执行器 _pacing_gate'],
            ['拒识', 'is_reject: true + timing（静默/回复过程中）', '仅 voice_llm（reject_judge 维度）', '评估侧计算器'],
            ['评估字段名/映射', 'param_mapping（source→target）', '按算法各自声明', 'field_mapper（配置）'],
          ],
        },
        {
          kind: 'paragraph',
          text: '打断轮 / 拒识 / 推流中打断是 voice_llm 这类「对话/拒识算法」的用例语义，其他算法（asr/der/wer 等）不需要，各自有自己的字段与评估计算器，字段区分靠 field_mapper 按 algorithm_type 的 param_mapping。',
        },
        {
          kind: 'paragraph',
          text: '关键：这些特殊处理你不需要写代码。打断轮时序（等 AI 开口 → 延时 → 推打断音频 → 检测窗口）由通用执行器编排；拒识判定由评估侧 reject_judge 计算器负责；字段名映射由 field_mapper 配置驱动。适配器唯一要保证：厂商事件正确归一到 user_speech_started / response_cancelled（打断）和如实采集轮次结果（拒识）。',
        },
        { kind: 'heading', text: '五、APIs 表 + 建任务（配置）' },
        {
          kind: 'list',
          items: [
            'APIs 表一行：vendor=my_vendor、api_url（ws:// 或 wss://）、device_type=websocket_api、meta（session_config / audio_config / ws_headers / api_key）、proxy_type / proxy_url',
            '建任务：选用例 + 选 API（可同时选多个 API 和物理设备混跑）→ 用例在选中目标上分别执行（case_devices 指派 device_type）',
          ],
        },
        { kind: 'heading', text: '六、验证' },
        {
          kind: 'list',
          items: [
            'mock 冒烟：mock_realtime_api.py --barge-in（预置「AI 说话 + 打断」事件序列）→ 正常轮 + 打断轮跑通',
            '真机：换 api_url 为被测端点，核对事件协议与归一化（response.audio.delta 等）',
            '回归：test_int497_openai_realtime_e2e.py（分发 + 打断轮）、test_int475_realtime_pacing.py（节奏策略）',
          ],
        },
        { kind: 'heading', text: '七、FAQ' },
        {
          kind: 'list',
          items: [
            '我的服务事件字段和 OpenAI 不同？在适配器 recv 归一化即可，用户侧能力不受影响。',
            '怎么确认打断测试生效？看轮次结果打断指标（barge_in 统计）；页面有实时帧可观察。',
            '被测端要满足什么才能测打断？会话跨轮保持且会自主回复；VAD 能检出用户开口（发 user_speech_started）或主动取消回复（发 response.cancelled）。不满足也能跑正常对话轮。',
          ],
        },
      ],
    },
    {
      id: 'http-api',
      title: '普通 HTTP API 接入（http_api）',
      blocks: [
        { kind: 'heading', text: '一、接入总览（3 件事）' },
        {
          kind: 'table',
          headers: ['你要做的事', '放哪', '写代码？'],
          rows: [
            ['① 适配器（实现 Port 抽象方法）', 'api_test_service/infrastructure/adapters/vendors/你的厂商.py', '✅'],
            ['② 注册（枚举 + 映射 + @register）', 'common_enums.py + registry.py', '✅（约 5 行）'],
            ['③ 参数配置（请求模板/输出字段/用例）', 'APIs 表 meta + field_mapper + 用例', '❌ 纯配置'],
          ],
        },
        { kind: 'heading', text: '二、写适配器（HTTP 无协议基类，直接实现 Port）' },
        {
          kind: 'code',
          language: 'python',
          code: `# adapters/vendors/my_http_adapter.py
from shared.models.common_enums import AdapterVendor, VendorAdapterType
from api_test_service.domain.ports.api_vendor_adapter import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

@register_vendor_adapter
class MyHttpAdapter(ApiVendorAdapter):
    vendor = AdapterVendor.MY_VENDOR
    adapter_type = VendorAdapterType.MY_VENDOR

    def render_request_parts(self, context_data):        # 请求头/体（按厂商协议）
        return headers, body                              # (rendered_headers, rendered_body)

    def execute(self, context_data, files=None, method=None):   # 发请求 → 结构化结果
        return {'success': True, 'latency_ms': ..., 'status_code': 200,
                'json': {...}, 'text': ...}

    def execute_voice_llm_chat(self, **kwargs):           # 多轮会话默认路径（可选覆写）
        ...`,
        },
        {
          kind: 'list',
          items: [
            '请求模板参数来自 field_mapper build_api_request_data（注入 context_data）',
            '输出字段按 api 输出字段定义提取（output_field_keys 模式，对齐 api_task_runner）',
            '密钥链 / 代理透传',
          ],
        },
        { kind: 'heading', text: '三、注册 + 配置' },
        {
          kind: 'code',
          language: 'python',
          code: `# common_enums.py
class AdapterVendor(str, Enum):     MY_VENDOR = 'my_vendor'
class VendorAdapterType(str, Enum): MY_VENDOR = 'my_vendor'

# registry.py
_FLAT_KEY_DIMENSIONS = { ..., VendorAdapterType.MY_VENDOR: (协议维度, AdapterVendor.MY_VENDOR) }`,
        },
        {
          kind: 'list',
          items: [
            'APIs 表：vendor=my_vendor、api_url（http(s):// → 自动识别 http_api）、meta（请求模板 / 密钥 / 代理）',
            '用例特殊处理（纯配置）：单轮 = execute；多轮 = execute_voice_llm_chat；评估字段映射走 field_mapper（param_mapping）',
          ],
        },
        { kind: 'heading', text: '四、用例特殊处理（适用算法）' },
        {
          kind: 'table',
          headers: ['用例场景', '配什么', '适用算法', '谁来处理'],
          rows: [
            ['单轮一问一答', '输入 query + 期望 answer', '全部', '执行器通用'],
            ['多轮会话', 'rounds 列表（execute_voice_llm_chat）', '对话类（voice_llm 等）', '适配器 execute_voice_llm_chat'],
            ['拒识 / 打断', 'is_reject / timing / is_interruption', '仅 voice_llm 等对话/拒识算法', '评估侧计算器 / 执行器编排'],
            ['评估字段名/映射', 'param_mapping（source→target）', '按算法各自声明', 'field_mapper（配置）'],
          ],
        },
        {
          kind: 'paragraph',
          text: '打断 / 拒识仅 voice_llm 这类「对话/拒识算法」需要，其他算法（asr/der/wer 等）不需要，各自有自己的字段与评估计算器。',
        },
        { kind: 'heading', text: '五、验证' },
        {
          kind: 'list',
          items: [
            'mock 冒烟：mock_dut_api.py 跑通单轮/多轮',
            '真机：换 api_url，核对请求/响应结构与 field_mapper 输出字段提取',
            '回归：API 测试集成用例不回归',
          ],
        },
        { kind: 'heading', text: '六、FAQ' },
        {
          kind: 'list',
          items: [
            '流式响应（SSE）怎么接？在 execute 内消费流式响应，聚合为结构化结果返回。',
            '厂商鉴权特殊？走密钥链（case_config → meta → env），或适配器 render_request_parts 自定义头。',
          ],
        },
      ],
    },
    {
      id: 'physical-e2e',
      title: '实体设备 E2E 接入（physical）',
      blocks: [
        { kind: 'heading', text: '一、接入总览（3 件事）' },
        {
          kind: 'table',
          headers: ['你要做的事', '放哪', '写代码？'],
          rows: [
            ['① 设备驱动（连接/放音/采集/操作）', 'device_service/infrastructure/drivers/你的设备.py', '✅'],
            ['② 注册（@register_driver）', '同文件装饰器', '✅（几行）'],
            ['③ 配置（设备记录/驱动参数/用例）', 'Devices 表 + 设备配置 + 用例', '❌ 纯配置'],
          ],
        },
        { kind: 'heading', text: '二、写驱动（继承 BaseDeviceDriver）' },
        {
          kind: 'code',
          language: 'python',
          code: `# drivers/my_device_driver.py
from device_service.infrastructure.drivers.base_driver import BaseDeviceDriver
from device_service.infrastructure.drivers.registry import register_driver
from device_service.infrastructure.drivers.driver_types import DevicePlatform

@register_driver
class MyDeviceDriver(BaseDeviceDriver):
    app_type = 'my_device'                        # 自定义开放字符串
    version = 'v1'
    platform = DevicePlatform.ANDROID             # 封闭枚举: android / harmonyos / ios
    dependencies = []                             # 可选: SDK 依赖（缺失自动标记）

    def initialize(self, device_sn, task_id=None, test_case_id=None, **kw): ...
    def pre_process(self, device_sn, **kw): ...   # 每轮前（音量/App 状态/噪声环境设置）
    def post_process(self, device_sn, **kw): ...  # 每轮后（采集结果/回采检测）
    def get_results(self, device_sn, **kw): ...   # 本轮输出（音频/文本/SPL）
    def teardown(self, device_sn, **kw): ...      # 关 App/清理`,
        },
        {
          kind: 'list',
          items: [
            'Redis 分布式停止/暂停（多实例一致，降级进程内注册表）',
            'UI 抓取降级标记、teardown 自动关 App',
            '播放时间戳提取（_extract_playback_timestamps）',
            '_wait_for_condition（超时 + 停止检查）、统一日志',
          ],
        },
        { kind: 'heading', text: '三、注册（Key 三元组）' },
        {
          kind: 'code',
          language: 'python',
          code: `# Key = (app_type, version, platform)
# driver_registry.resolve(app_type, version, platform)  版本可降级 v1
# @register_driver 装饰即注册；依赖缺失自动标记 MISSING_DEPENDENCY（仍展示）`,
        },
        {
          kind: 'list',
          items: [
            'app_type / version：自定义开放字符串（每个新 App 驱动自声明，不需改枚举）',
            'platform：封闭枚举（DevicePlatform：android / harmonyos / ios）',
          ],
        },
        { kind: 'heading', text: '四、用例特殊处理（适用算法）' },
        {
          kind: 'table',
          headers: ['用例场景', '配什么', '适用算法', '谁来处理'],
          rows: [
            ['正常轮', '每轮输入音频', '全部', 'rounds_loop 通用编排'],
            ['打断轮（插话）', 'is_interruption: true（+ai_start_timeout）', '仅 voice_llm 等对话类', '执行器透传 → 驱动 post_process 回采 PCM 检测 AI 开口（参照 harmony_xiaoyichat _wait_ai_reply_start_via_pcm）'],
            ['拒识', 'is_reject: true + timing', '仅 voice_llm（reject_judge）', '评估侧计算器；驱动如实采集'],
            ['设备输出字段', 'field_mapper get_mapped_device_output_fields', '按算法各自声明', '配置'],
          ],
        },
        {
          kind: 'paragraph',
          text: '打断检测是驱动能力（只有驱动能回采设备声学）——对应 Realtime 适配器的 wait_ai_speaking。打断/拒识仅 voice_llm 这类对话/拒识算法需要，其他算法不需要。',
        },
        { kind: 'heading', text: '五、配置 + 建任务' },
        {
          kind: 'list',
          items: [
            'Devices 表：设备类型 / 序列号 / 驱动参数（app_type 关联驱动）',
            '建任务：case_devices device_type=physical + device_id（设备侧），可与 API 目标混跑（同一用例设备侧 + API 侧分别执行）',
          ],
        },
        { kind: 'heading', text: '六、验证' },
        {
          kind: 'list',
          items: [
            '扫描/初始化冒烟：driver_registry.list_drivers() 可见、依赖无缺失、设备可初始化',
            '单用例跑通：正常轮 → 打断轮（验证回采检测）',
            '回归：E2E 集成测试不回归',
          ],
        },
        { kind: 'heading', text: '七、FAQ' },
        {
          kind: 'list',
          items: [
            '设备版本差异大？resolve(app_type, version, platform) 支持版本降级 v1，同 app_type+platform 下任意可用版本兜底。',
            '驱动依赖 SDK 缺失？注册时自动标记 MISSING_DEPENDENCY，管理界面可见，不影响其他驱动。',
            '打断检测必须回采 PCM？是——只有驱动能访问设备声学数据；Realtime 侧对应的是协议事件 wait_ai_speaking。',
          ],
        },
      ],
    },
  ],
}
