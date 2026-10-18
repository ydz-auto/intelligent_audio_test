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
            '执行测试：端到端测试（/E2ETest）或 API 测试（/APITest），五步向导完成配置与执行。',
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
            ['端到端测试', '在真实设备上执行完整语音链路测试', '/E2ETest'],
            ['API 测试', '测试语音识别/翻译 API 的性能与准确率', '/APITest'],
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
          text: '用例管理页（/TestCaseManager）支持按测试类型分组、标签筛选、参考参数与批量导入导出。用例可被端到端测试与 API 测试复用。',
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
          text: '端到端测试（/E2ETest）与 API 测试（/APITest）共用五步向导：选择算法 → 选择用例 → 选择资源（设备/API）→ 执行测试 → 查看结果。',
        },
        {
          kind: 'list',
          items: [
            '端到端测试：在真实设备上运行完整语音链路，支持多设备并行，实时查看进度与日志。',
            'API 测试：批量测试语音识别/翻译端点，统计响应时间、并发数与成功率。',
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
            '端到端测试和 API 测试怎么选？——验证整机语音链路选端到端；只验证识别/翻译服务指标选 API 测试。',
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
