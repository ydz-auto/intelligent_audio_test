/**
 * 站点信息分区（interfaces 层，INT-347 §4.1 母版 A）：
 * 站点名称/Logo 地址/页脚内容；随 KV 保存链（保存更改/重置）。
 */
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import type { SiteInfoSettings } from '@/domain/models/option'
import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type SiteInfoPageProps = {
  defaultValues: SiteInfoSettings
}

export function SiteInfoPage({ defaultValues }: SiteInfoPageProps) {
  return (
    <SettingsFormPage<SiteInfoSettings>
      baseline={defaultValues}
      optionKey={(field) => `site.${field as string}`}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='site-name'>站点名称</Label>
            <Input
              id='site-name'
              placeholder='智能语音测试平台'
              value={draft.name}
              onChange={(event) => setField('name', event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>站内各处显示的名称</p>
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='site-logo'>Logo 地址</Label>
            <Input
              id='site-logo'
              placeholder='https://example.com/logo.png'
              value={draft.logo}
              onChange={(event) => setField('logo', event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>Logo 图片 URL，选填</p>
          </SettingsFormGridItem>
          <SettingsFormGridItem span='full' className='grid gap-1.5'>
            <Label htmlFor='site-footer'>页脚内容</Label>
            <Input
              id='site-footer'
              placeholder='© 2026 智能语音测试平台'
              value={draft.footer}
              onChange={(event) => setField('footer', event.target.value)}
            />
          </SettingsFormGridItem>
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
