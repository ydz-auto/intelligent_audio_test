/**
 * 站点公告分区（interfaces 层，INT-347 §4.1 母版 A）：
 * 公告内容 Textarea 8 行，跨双列；随 KV 保存链。
 */
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

import type { SiteNoticeSettings } from '@/domain/models/option'
import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type SiteNoticePageProps = {
  defaultValues: SiteNoticeSettings
}

export function SiteNoticePage({ defaultValues }: SiteNoticePageProps) {
  return (
    <SettingsFormPage<SiteNoticeSettings>
      baseline={defaultValues}
      optionKey={(field) => `site.${field as string}`}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsFormGridItem span='full' className='grid gap-1.5'>
            <Label htmlFor='site-notice'>公告内容</Label>
            <Textarea
              id='site-notice'
              rows={8}
              placeholder='例如：本周五 22:00 计划性维护…'
              value={draft.notice}
              onChange={(event) => setField('notice', event.target.value)}
            />
          </SettingsFormGridItem>
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
