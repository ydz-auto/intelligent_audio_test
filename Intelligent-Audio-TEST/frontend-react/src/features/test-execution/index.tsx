/**
 * 测试执行页（interfaces/features/test-execution/index.tsx；10_测试执行.md §3.1）。
 * /E2ETest 与 /APITest 共用同一组件树（testType prop 分叉文案/数据源）。
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
import { usePermissions } from '@/application/hooks/use-permissions'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import { MOCK_TESTCASES } from '@/infrastructure/mock/test-execution-mock'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

import { TEST_FLOW_CONFIG, type TestFlowConfig } from '@/features/test-execution/constants'
import { FlowSteps } from '@/features/test-execution/components/flow-steps'
import { FlowFooter } from '@/features/test-execution/components/flow-footer'
import { StepAlgorithm } from '@/features/test-execution/components/step-algorithm'
import { StepCases } from '@/features/test-execution/components/step-cases'
import { StepResources } from '@/features/test-execution/components/step-resources'
import { StepExecuting } from '@/features/test-execution/components/step-executing'
import { StepReport } from '@/features/test-execution/components/step-report'
import { TaskNameDialog } from '@/features/test-execution/modals/task-name-dialog'
import { CaseDetailDialog } from '@/features/test-execution/modals/case-detail-dialog'
import { ApiEditDialog } from '@/features/test-execution/modals/api-edit-dialog'
import { ApiHealthDialog } from '@/features/test-execution/modals/api-health-dialog'
import { ResetFlowConfirm } from '@/features/test-execution/modals/reset-flow-confirm'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ApiHealthCheckResult } from '@/domain/models/apiConfig'

interface TestExecutionPageProps {
  testType: 'e2e' | 'api'
  /** 初始视图（URL validateSearch view） */
  initialView?: 'table' | 'card'
  onViewChange: (view: 'table' | 'card') => void
}

export function TestExecutionPage({
  testType,
  initialView = 'table',
  onViewChange,
}: TestExecutionPageProps) {
  const navigate = useNavigate()
  const readOnly = useReadOnlyMode()
  const { hasPermission } = usePermissions()
  const { step, goToStep, nextStep, prevStep, canBrowseStep, hasProgress } = useFlowSteps()
  const { algorithmType, current: currentAlgorithm } = useAlgorithmChannel()
  const reportStep = useReportStep()
  const launch = useTestLaunch()
  const resources = useResourceSelection(testType, algorithmType)

  const config: TestFlowConfig = TEST_FLOW_CONFIG[testType]

  const params = useExecutionStore((s) => s.params)
  const taskId = useExecutionStore((s) => s.taskId)
  const taskDeviceTypes = useExecutionStore((s) => s.deviceTypes)
  const reportStatus = useExecutionStore((s) => s.reportStatus)
  const resetFlow = useExecutionStore((s) => s.resetFlow)
  const manualCaseIds = useCaseSelectionStore((s) => s.manualCaseIds)
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
  }>({ open: false, result: null })
  const [resetOpen, setResetOpen] = useState(false)
  const [newTestOpen, setNewTestOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [savingReport, setSavingReport] = useState(false)

  const canPublishReport = hasPermission('report:publish')
  const canSaveReport = hasPermission('report:update')

  /** 步骤 1-2 上下文提示（voice_llm 场景 / 校验错误摘要） */
  const footerHint = useMemo(() => {
    if (step === 1 && algorithmType === 'tts_eval') return config.voiceLlmAlert
    if (step === 2 && testType === 'e2e' && algorithmType === 'tts_eval')
      return 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。'
    return undefined
  }, [step, algorithmType, config.voiceLlmAlert, testType])

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

  const handleDeviceEntry = () => {
    // 扫描/新增设备弹窗归 INT-361（设备域卡）；本卡留入口
    toast.info('设备管理弹窗随设备域卡 INT-361 落地')
  }

  const handleSaveReport = () => {
    setSavingReport(true)
    window.setTimeout(() => {
      setSavingReport(false)
      toast.success('报告已成功保存')
    }, 600)
  }

  /** 步骤三「开始测试」校验链（§3.7：失败 toast.warning，通过才开任务名称弹窗） */
  const handleStartTest = () => {
    const caseState = useCaseSelectionStore.getState()
    // 用例校验：filterAll（未手动选择按筛选全量圈定）或已勾选任一用例
    if (caseState.filterAllMode === false && caseState.manualCaseIds.length === 0) {
      toast.warning('当前筛选条件下没有可用的测试用例，请选择用例或调整筛选条件')
      return
    }
    const errors = launch.validate({
      type: testType,
      cases: caseState.filterAllMode ? MOCK_TESTCASES.filter((c) => c.type === testType) : [],
      devices: resources.devices,
      apis: resources.apis,
      deviceIds,
      apiIds,
      algorithmType,
    })
    // filterAll 模式用例已满足，跳过空用例报错
    const filteredErrors = caseState.filterAllMode
      ? errors.filter((e) => !e.includes('没有可用的测试用例'))
      : errors
    if (filteredErrors.length > 0) {
      filteredErrors.forEach((error) => toast.warning(error))
      return
    }
    setTaskNameOpen(true)
  }

  return (
    <div className='flex size-full min-h-0 flex-col overflow-hidden'>
      {/* 顶部条 */}
      <div className='shrink-0 border-b px-4 py-3 sm:px-6'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div className='min-w-0'>
            <h1 className='text-sm font-semibold sm:text-base'>{config.title}</h1>
            <p className='text-muted-foreground mt-0.5 hidden text-xs sm:block'>
              {config.subtitle}
            </p>
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
            if ((index === 1 || index === 2) && !currentAlgorithm) return '请先选择算法'
            if (index === 3 && taskId == null) return '请先启动测试任务'
            if (index === 4 && reportStatus !== 'ready') return '请等待报告生成完成'
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
            step === 3 || step === 4 ? 'max-w-none' : 'max-w-5xl'
          )}
        >
          {step === 0 && (
            <StepAlgorithm
              readOnly={readOnly}
              onOpenAlgorithmDetail={() => {
                // 算法详情弹窗归 INT-362（算法配置域只读视图）；本卡入口占位
                toast.info('算法详情弹窗随算法配置域卡落地')
              }}
              onGoAlgorithmConfig={() => {
                // 步骤0「新增算法」→ 算法配置页 /AlgorithmConfig（INT-417 测试域组，路由待落地）
                ;(navigate as (opts: { to: string }) => void)({ to: '/algorithm-config' })
              }}
            />
          )}

          {step === 1 && (
            <StepCases
              type={testType}
              lockedTypeBadge={config.lockedTypeBadge}
              readOnly={readOnly}
              view={initialView}
              onViewChange={onViewChange}
            />
          )}

          {step === 2 && (
            <StepResources
              type={testType}
              resourceNoun={config.resourceNoun}
              voiceLlmAlert={config.voiceLlmAlert}
              readOnly={readOnly}
              onOpenApiEdit={(api) => setApiEdit({ open: true, api })}
              onOpenApiHealth={(api) => {
                // 触发连接测试（§5.4）；mock 700ms 后回结果
                setApiHealth({ open: true, result: null })
                window.setTimeout(() => {
                  setApiHealth({
                    open: true,
                    result: {
                      id: api.id,
                      status: 'online',
                      healthScore: api.healthScore ?? 92,
                      apiUrlStatus: 'online',
                      endpointsStatus: 'online',
                      statusCode: 200,
                      responseTime: '214ms',
                      error: null,
                      warning: null,
                    },
                  })
                }, 700)
              }}
              onScanDevices={handleDeviceEntry}
              onAddDevice={handleDeviceEntry}
            />
          )}

          {step === 3 && (taskId != null || readOnly) && (
            <StepExecuting
              taskId={taskId ?? 1042}
              readOnly={readOnly}
              onBackToResources={() => goToStep(2, { force: true })}
              onCaseSelect={(caseId) => setCaseDetail({ caseId })}
              deviceTypes={
                taskId != null ? taskDeviceTypes : ['smart_speaker', 'http_api', 'websocket_api']
              }
            />
          )}

          {step === 3 && taskId == null && !readOnly && (
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

          {step === 4 && taskId != null && <StepReport taskId={taskId} readOnly={readOnly} />}
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
        onGoReportCenter={() => void navigate({ to: '/reports' })}
        onNewTest={() => setNewTestOpen(true)}
      />

      {/* 模态窗群（§5） */}
      <TaskNameDialog
        open={taskNameOpen}
        onOpenChange={setTaskNameOpen}
        type={testType}
        algorithmType={algorithmType}
        caseCount={manualCaseIds.length}
        deviceCount={deviceIds.length}
        apiCount={apiIds.length}
        deviceIds={deviceIds}
        apiIds={apiIds}
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
        onRetest={() => {
          setApiHealth((s) => ({ ...s, result: null }))
          window.setTimeout(() => {
            setApiHealth({
              open: true,
              result: {
                id: 11,
                status: 'online',
                healthScore: 95,
                apiUrlStatus: 'online',
                endpointsStatus: 'online',
                statusCode: 200,
                responseTime: '188ms',
                error: null,
                warning: null,
              },
            })
          }, 600)
        }}
      />

      <ResetFlowConfirm
        open={resetOpen}
        onOpenChange={setResetOpen}
        onConfirm={handleResetConfirm}
      />

      {/* 步骤四「开始新测试」确认（§3.8：将开始新的测试流程，当前报告不受影响） */}
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
