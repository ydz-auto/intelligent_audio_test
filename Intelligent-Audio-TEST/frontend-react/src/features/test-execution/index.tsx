/**
 * 测试执行页（interfaces/features/test-execution/index.tsx；10_测试执行.md §3.1，
 * INT-486 合并口径）：/start-test 单入口，单流程（2026-10-16 追加口径：不再分
 * E2E/API 两模式——步骤一选用例（不分类型），步骤二同屏选设备+API 混合，直接开始测试）。
 * 四步流程（INT-486：不再有「选择算法」步骤——算法切换已全局化 INT-436/442，
 * 测试流程不再单独选算法，用例/资源列表按全局算法自动过滤）。
 * 三段式全高骨架（照 playground/index.tsx）：顶部条 / 流程步骤条 / 内容区 / 底部动作条。
 * readOnly（§3.1.1）：骨架照常渲染，动作钮/控制/提交整体投影隐藏。
 */
import { RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { useReadOnlyMode } from '@/application/test-execution/useReadOnlyMode'
import { useFlowSteps } from '@/application/test-execution/useFlowSteps'
import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { useReportStep } from '@/application/test-execution/useReportStep'
import { useResourceSelection } from '@/application/test-execution/useResourceSelection'
import { useTestLaunch } from '@/application/test-execution/useTestLaunch'
import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

import { TEST_FLOW_CONFIG, VOICE_LLM_ALGORITHM_TYPE } from '@/features/test-execution/constants'
import { FlowSteps } from '@/features/test-execution/components/flow-steps'
import { FlowFooter } from '@/features/test-execution/components/flow-footer'
import { StepCases } from '@/features/test-execution/components/step-cases'
import { StepResources } from '@/features/test-execution/components/step-resources'
import { StepExecuting } from '@/features/test-execution/components/step-executing'
import { StepReport } from '@/features/test-execution/components/step-report'
import { TaskNameDialog } from '@/features/test-execution/modals/task-name-dialog'
import { CaseDetailDialog } from '@/features/test-execution/modals/case-detail-dialog'
import { ApiEditDialog } from '@/features/test-execution/modals/api-edit-dialog'
import { ApiHealthDialog } from '@/features/test-execution/modals/api-health-dialog'
import { ResetFlowConfirm } from '@/features/test-execution/modals/reset-flow-confirm'
import { ScanDevicesDialog } from '@/features/devices/components/modals/scan-devices-dialog'
import { DeviceMutateDrawer } from '@/features/devices/components/modals/device-mutate-drawer'
import type { DeviceMutateState } from '@/features/devices/types'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { DeviceScanSelection } from '@/domain/models/deviceScan'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ApiHealthCheckResult } from '@/domain/models/apiConfig'

interface TestExecutionPageProps {
  /** 初始视图（URL validateSearch view） */
  initialView?: 'table' | 'card'
  onViewChange: (view: 'table' | 'card') => void
}

export function TestExecutionPage({
  initialView = 'table',
  onViewChange,
}: TestExecutionPageProps) {
  const navigate = useNavigate()
  const readOnly = useReadOnlyMode()
  const { hasPermission } = usePermissions()
  const { step, goToStep, nextStep, prevStep, canBrowseStep, hasProgress } = useFlowSteps()
  const { algorithmType } = useAlgorithmChannel()
  const reportStep = useReportStep()
  const launch = useTestLaunch()
  const resources = useResourceSelection(algorithmType)
  const apisCrud = useApisCrud()

  const config = TEST_FLOW_CONFIG

  const params = useExecutionStore((s) => s.params)
  const taskId = useExecutionStore((s) => s.taskId)
  const taskDeviceTypes = useExecutionStore((s) => s.deviceTypes)
  const reportStatus = useExecutionStore((s) => s.reportStatus)
  const resetFlow = useExecutionStore((s) => s.resetFlow)
  const manualCaseIds = useCaseSelectionStore((s) => s.manualCaseIds)
  const caseFilterAllMode = useCaseSelectionStore((s) => s.filterAllMode)
  const filterAllTotal = useCaseSelectionStore((s) => s.filterAllTotal)
  const clearCases = useCaseSelectionStore((s) => s.clearSelection)
  const deviceIds = useResourceSelectionStore((s) => s.deviceIds)
  const apiIds = useResourceSelectionStore((s) => s.apiIds)
  const clearResources = useResourceSelectionStore((s) => s.clearResources)

  // 弹窗态
  const [taskNameOpen, setTaskNameOpen] = useState(false)
  const [caseDetail, setCaseDetail] = useState<{ caseId: string } | null>(null)
  const [apiEdit, setApiEdit] = useState<{ open: boolean; api?: ApiConfig }>({ open: false })
  const [apiHealth, setApiHealth] = useState<{
    open: boolean
    result: ApiHealthCheckResult | null
    /** 当前被测 API id（连接测试/重新测试共用；INT-646 代码审计 P1 真实端点口径） */
    apiId?: number
  }>({ open: false, result: null })
  const [resetOpen, setResetOpen] = useState(false)
  const [newTestOpen, setNewTestOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [savingReport, setSavingReport] = useState(false)
  // 添加设备（合一入口）：扫描弹窗 + 设备登记抽屉（扫描 fillMode 回填 → 填信息保存入库）
  const [scanOpen, setScanOpen] = useState(false)
  const [mutateState, setMutateState] = useState<DeviceMutateState>({ open: false, mode: 'create', kind: 'test' })
  const [mutatePrefill, setMutatePrefill] = useState<Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null>(null)
  const [scanInvoker, setScanInvoker] = useState<'header' | 'drawer'>('header')
  const [mutateScanFill, setMutateScanFill] = useState<{ nonce: number; kind: DevicesTabKey; prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> } | null>(null)

  const canPublishReport = hasPermission('report:publish')
  const canSaveReport = hasPermission('report:update')

  /** 步骤 0-1 上下文提示（voice_llm 场景 / 校验错误摘要） */
  const footerHint = useMemo(() => {
    if (step === 0 && algorithmType === VOICE_LLM_ALGORITHM_TYPE) return config.voiceLlmAlert
    if (step === 1 && algorithmType === VOICE_LLM_ALGORITHM_TYPE)
      return 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。'
    return undefined
  }, [step, algorithmType, config.voiceLlmAlert])

  const clearFlowState = () => {
    resetFlow()
    clearCases()
    clearResources()
  }

  const handleResetConfirm = () => {
    clearFlowState()
    setResetOpen(false)
    navigateWithSearch(navigate, { step: 0 })
  }

  const handleStartNewTest = () => {
    clearFlowState()
    setNewTestOpen(false)
    navigateWithSearch(navigate, { step: 0 })
  }

  /** 添加设备入口（合一：先扫描 → 选设备回填 → 填信息保存入库） */
  const handleDeviceEntry = () => {
    setScanInvoker('header')
    setScanOpen(true)
  }

  /** 抽屉内扫描「选择」→ 回填当前登记表单；无抽屉时 → 开新增抽屉 */
  const handleScanAdd = (
    kind: DevicesTabKey,
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  ) => {
    // INT-2153：设备抽屉只承载测试设备 / 播放设备（API 登记走 §5.3 API 编辑弹窗，不属于启动页流程）
    if (kind === 'api') return
    if (scanInvoker === 'drawer' && mutateState.open) {
      setMutateScanFill({ nonce: Date.now(), kind, prefill })
      setScanOpen(false)
      setScanInvoker('header')
      return
    }
    setScanOpen(false)
    setMutateState({ open: true, mode: 'create', kind })
    setMutatePrefill(prefill)
  }

  /** 连接测试（§5.4；INT-646 代码审计 P1：经 useApisCrud.testConnection → 真实
   *  POST /apis/{id}/health，进行中 Spinner；失败已 toast，关闭弹窗） */
  const runApiHealthTest = async (apiId: number) => {
    setApiHealth({ open: true, result: null, apiId })
    const result = await apisCrud.testConnection(apiId)
    if (result) {
      setApiHealth({ open: true, result, apiId })
    } else {
      setApiHealth({ open: false, result: null })
    }
  }

  const handleSaveReport = () => {
    // 报告保存归报告域卡（本卡 API 面未列 PUT /reports；同设备连接测试留证口径），
    // 暂以本地 600ms 保存动画占位，待报告域卡接线后收敛真实端点。
    setSavingReport(true)
    window.setTimeout(() => {
      setSavingReport(false)
      toast.success('报告已成功保存')
    }, 600)
  }

  /** 步骤一「开始测试」校验链（§3.7：失败 toast.warning，通过才开任务名称弹窗） */
  const handleStartTest = () => {
    const caseState = useCaseSelectionStore.getState()
    // 用例校验（INT-1542）：filter-all 圈定（后端按筛选展开全量）或手动勾选至少 1 条。
    // 手动勾选后 filterAllMode 为 false，必须以真实选中集为准，不能再用空用例集 + filter-all 过滤。
    const hasCases =
      caseState.filterAllMode || caseState.manualCaseIds.length > 0
    // INT-1544：filter-all 圈定现在真的按筛选条件取数——筛选结果为空时不再放行
    // （否则提交 case_ids=[] 由后端报错），与列表「全部 0 条用例」一致地拦在入口
    if (caseState.filterAllMode && caseState.filterAllTotal === 0) {
      toast.warning('当前筛选条件下没有可用的测试用例，请调整筛选条件')
      return
    }
    const errors = launch.validate({
      hasCases,
      devices: resources.devices,
      apis: resources.apis,
      deviceIds,
      apiIds,
      algorithmType,
    })
    if (errors.length > 0) {
      errors.forEach((error) => toast.warning(error))
      return
    }
    setTaskNameOpen(true)
  }

  return (
    <div className='flex size-full min-h-0 flex-col overflow-hidden'>
      {/* 顶部条 */}
      <div className='shrink-0 border-b px-4 py-3 sm:px-6'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div className='flex min-w-0 items-center gap-3'>
            <div className='min-w-0'>
              <h1 className='text-sm font-semibold sm:text-base'>{config.title}</h1>
              <p className='text-muted-foreground mt-0.5 hidden text-xs sm:block'>
                {config.subtitle}
              </p>
            </div>
          </div>
          {!readOnly && hasProgress && (
            <Button variant='ghost' size='sm' onClick={() => setResetOpen(true)}>
              <RotateCcw aria-hidden='true' className='size-3.5' />
              重置流程
            </Button>
          )}
        </div>
      </div>

      {/* 流程步骤条 */}
      <div className='shrink-0 px-4 pt-3'>
        <FlowSteps
          steps={config.steps}
          current={step}
          done={(index) => canBrowseStep(index) && index < step}
          onNavigate={(index) => goToStep(index)}
          readOnly={readOnly}
          disabledHint={(index) => {
            if (index <= step) return null
            if (index === 2 && taskId == null) return '请先启动测试任务'
            if (index === 3 && reportStatus !== 'ready') return '请等待报告生成完成'
            return null
          }}
        />
      </div>

      {/* 内容区 */}
      <div className='min-h-0 flex-1 overflow-y-auto px-4 py-4'>
        <div
          key={step}
          className={cn(
            'mx-auto w-full animate-in fade-in-0 duration-250',
            step === 2 || step === 3 ? 'max-w-none' : 'max-w-5xl'
          )}
        >
          {step === 0 && (
            <StepCases
              readOnly={readOnly}
              view={initialView}
              onViewChange={onViewChange}
            />
          )}

          {step === 1 && (
            <StepResources
              voiceLlmAlert={config.voiceLlmAlert}
              readOnly={readOnly}
              onOpenApiEdit={(api) => setApiEdit({ open: true, api })}
              onOpenApiHealth={(api) => runApiHealthTest(api.id)}
              onScanDevices={handleDeviceEntry}
              onAddDevice={handleDeviceEntry}
            />
          )}

          {step === 2 && (taskId != null || readOnly) && (
            <StepExecuting
              taskId={taskId ?? 1042}
              readOnly={readOnly}
              onBackToResources={() => goToStep(1, { force: true })}
              onCaseSelect={(caseId) => setCaseDetail({ caseId })}
              deviceTypes={
                taskId != null ? taskDeviceTypes : ['smart_speaker', 'http_api', 'websocket_api']
              }
            />
          )}

          {step === 2 && taskId == null && !readOnly && (
            <div className='flex justify-center py-12'>
              <Alert className='max-w-lg py-3'>
                <AlertDescription className='text-sm'>
                  存在进行中的任务，可在{' '}
                  <Link
                    to='/tasks/$tab'
                    params={{ tab: 'daily' }}
                    className='text-primary underline underline-offset-3'
                  >
                    任务管理
                  </Link>{' '}
                  中查看
                </AlertDescription>
              </Alert>
            </div>
          )}

          {step === 3 && taskId != null && <StepReport taskId={taskId} readOnly={readOnly} />}
        </div>
      </div>

      {/* 底部动作条 */}
      <FlowFooter
        step={step}
        readOnly={readOnly}
        hint={footerHint}
        onPrev={prevStep}
        onNext={nextStep}
        onStart={handleStartTest}
        canSaveReport={canSaveReport}
        onSaveReport={handleSaveReport}
        savingReport={savingReport}
        onExportReport={() => void reportStep.doExport('csv')}
        canPublishReport={canPublishReport}
        onPublishReport={() => setPublishOpen(true)}
        onGoReportCenter={() => void navigate({ to: '/report-center' })}
        onNewTest={() => setNewTestOpen(true)}
      />

      {/* 模态窗群（§5） */}
      <TaskNameDialog
        open={taskNameOpen}
        onOpenChange={setTaskNameOpen}
        algorithmType={algorithmType}
        // INT-1544：filter-all（未手动勾选）时按当前筛选条件的用例总数显示，
        // 与步骤一「全部 N 条用例」及实际提交的 case_ids 一致
        caseCount={caseFilterAllMode ? filterAllTotal : manualCaseIds.length}
        deviceCount={deviceIds.length}
        apiCount={apiIds.length}
        deviceIds={deviceIds}
        apiIds={apiIds}
        apis={resources.allApis}
        params={params}
      />

      <CaseDetailDialog
        open={caseDetail != null}
        onOpenChange={(open) => {
          if (!open) setCaseDetail(null)
        }}
        taskId={taskId ?? 0}
        caseId={caseDetail?.caseId ?? ''}
      />

      {/* 添加设备（合一入口）：设备登记抽屉 + 扫描 fillMode 回填 */}
      <DeviceMutateDrawer
        state={mutateState}
        prefill={mutatePrefill}
        onOpenChange={(open) =>
          setMutateState((prev) => ({ ...prev, open, mode: open ? prev.mode : 'create' }))
        }
        onScan={() => {
          setScanInvoker('drawer')
          setScanOpen(true)
        }}
        scanFill={mutateScanFill}
      />
      <ScanDevicesDialog
        open={scanOpen}
        onOpenChange={(open) => {
          setScanOpen(open)
          if (!open) setScanInvoker('header')
        }}
        tab='test'
        onAddToMutate={handleScanAdd}
        fillMode={scanInvoker === 'drawer'}
      />

      <ApiEditDialog
        open={apiEdit.open}
        onOpenChange={(open) => setApiEdit((s) => ({ ...s, open }))}
        api={apiEdit.api}
      />

      <ApiHealthDialog
        open={apiHealth.open}
        onOpenChange={(open) => {
          if (!open) setApiHealth((s) => ({ ...s, open: false, result: null }))
        }}
        result={apiHealth.result}
        testing={apiHealth.open && apiHealth.result == null}
        // A3（INT-1791 §二.5）：按协议给提示——gRPC / SSE 的正式探测归 INT-1953，
        // 现状后端按 URL scheme 分支，结果不代表该协议可执行
        protocol={
          resources.allApis.find((item) => item.id === apiHealth.apiId)?.protocol ?? null
        }
        onRetest={() => {
          // 重新测试同走真实端点（复用当前被测 apiId；INT-646 代码审计 P1）
          if (apiHealth.apiId != null) void runApiHealthTest(apiHealth.apiId)
        }}
      />

      <ResetFlowConfirm
        open={resetOpen}
        onOpenChange={setResetOpen}
        onConfirm={handleResetConfirm}
      />

      {/* 步骤三「开始新测试」确认（§3.8：将开始新的测试流程，当前报告不受影响） */}
      <ResetFlowConfirm
        open={newTestOpen}
        onOpenChange={setNewTestOpen}
        onConfirm={handleStartNewTest}
      />

      {/* 发布报告确认（§3.8：report:publish 仅 admin/algo_engineer） */}
      <ConfirmDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title='发布报告'
        desc='发布后报告将进入报告中心，对有权限的成员可见。是否发布？'
        confirmText='发布'
        handleConfirm={() => {
          setPublishOpen(false)
          reportStep.doPublish()
        }}
      />
    </div>
  )
}
