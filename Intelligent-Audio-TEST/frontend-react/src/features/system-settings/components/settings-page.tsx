/**
 * 通用设置分区页（interfaces 层，对齐 newAPI SettingsPage/SettingsPageFrame 实测）：
 * - 分区懒加载（lazy() + Suspense fallback LoadingState，settings-page.tsx 同款）；
 * - 页头 = 分区中文名 + 动作区 Portal（重置/保存）+ 标题状态位（脏徽标）；
 * - 加载「正在加载设置…」/ 错误「设置加载失败」+「重试」。
 */
import { useParams } from '@tanstack/react-router'
import { Loader2, Lock } from 'lucide-react'
import { Suspense, useMemo, useState, type ReactNode } from 'react'

import { ErrorState } from '@/components/error-state'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import type { SystemOptions } from '@/domain/models/option'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useSystemOptions } from '@/application/settings/use-system-options'

import { SettingsPageProvider } from './settings-page-context'

function SettingsLoadingState(props: { message?: string }) {
  return (
    <div className='flex min-h-[50vh] flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-8 text-center'>
      <Loader2 className='text-muted-foreground size-5 animate-spin' aria-hidden='true' />
      <p className='text-muted-foreground text-sm'>{props.message ?? '正在加载设置…'}</p>
    </div>
  )
}

type SettingsPageFrameProps = {
  title: ReactNode
  children: ReactNode
}

/** 分区页框：标题 + 动作区/状态位 Portal 槽 + 内容区（照 newAPI settings-page.tsx 结构） */
function SettingsPageFrame(props: SettingsPageFrameProps) {
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(null)
  const [titleStatusContainer, setTitleStatusContainer] =
    useState<HTMLSpanElement | null>(null)

  return (
    <SettingsPageProvider
      actionsContainer={actionsContainer}
      titleStatusContainer={titleStatusContainer}
    >
      <SectionPageLayout>
        <SectionPageLayout.Title>
          <span className='inline-flex max-w-full min-w-0 items-center gap-2 align-middle'>
            <span className='truncate'>{props.title}</span>
            <span
              ref={setTitleStatusContainer}
              className='inline-flex min-w-0 shrink-0 items-center'
            />
          </span>
        </SectionPageLayout.Title>
        <SectionPageLayout.Actions>
          <div
            ref={setActionsContainer}
            className='flex flex-wrap items-center justify-end gap-2'
          />
        </SectionPageLayout.Actions>
        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 w-full flex-col gap-4'>
            {props.children}
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>
    </SettingsPageProvider>
  )
}

export type SettingsPageProps<
  TSettings extends Record<string, unknown>,
  TSectionId extends string,
> = {
  /** 分区路由路径（useParams 取当前 section） */
  routePath: string
  defaultSettings: TSettings
  defaultSection: TSectionId
  getSectionContent: (sectionId: TSectionId, settings: TSettings) => ReactNode
  getSectionMeta: (sectionId: TSectionId) => { title: string }
  /** KV 选项 → 类型化设置（缺省按默认值） */
  resolveSettings?: (raw: SystemOptions | undefined) => TSettings
  loadingMessage?: string
}

export function SettingsPage<
  TSettings extends Record<string, unknown>,
  TSectionId extends string,
>(props: SettingsPageProps<TSettings, TSectionId>) {
  const { data, isLoading, isError, refetch } = useSystemOptions()
  // INT-1585：分区设置全部来自 GET /api/option/（option:read）。无该权限时 query
  // 被门禁关掉（不发 403），此处必须给明确的无权限提示，不能落「可重试」错误态
  // ——403 不是可重试故障，重试仍 403。半权限账号（有 user:read 无 option:read）
  // 可经路由守卫进入本页，故按权限码显式判定。
  const { hasPermission } = usePermissions()
  const canReadOptions = hasPermission('option:read')
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const params = useParams({ from: props.routePath as any })
  const activeSection = (params?.section ?? props.defaultSection) as TSectionId
  const sectionMeta = props.getSectionMeta(activeSection)

  const settings = useMemo<TSettings>(() => {
    if (props.resolveSettings) return props.resolveSettings(data)
    return props.defaultSettings
  }, [props, data])

  if (!canReadOptions) {
    return (
      <SettingsPageFrame title={sectionMeta.title}>
        <ErrorState
          icon={Lock}
          title='无权限查看系统设置'
          description='当前账号缺少 option:read 权限，无法读取站点选项。如需查看或修改，请联系管理员分配权限。'
        />
      </SettingsPageFrame>
    )
  }

  if (isLoading) {
    return (
      <SettingsPageFrame title={sectionMeta.title}>
        <SettingsLoadingState message={props.loadingMessage ?? '正在加载设置…'} />
      </SettingsPageFrame>
    )
  }

  if (isError) {
    return (
      <SettingsPageFrame title={sectionMeta.title}>
        <ErrorState
          icon={undefined}
          title='设置加载失败'
          description='系统选项加载失败，请重试'
          onRetry={() => void refetch()}
        />
      </SettingsPageFrame>
    )
  }

  return (
    <SettingsPageFrame title={sectionMeta.title}>
      <Suspense fallback={<SettingsLoadingState />}>
        {props.getSectionContent(activeSection, settings)}
      </Suspense>
    </SettingsPageFrame>
  )
}
