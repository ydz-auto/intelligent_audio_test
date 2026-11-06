/**
 * 导航模块分区（interfaces 层，INT-347 §4.1 母版 A）：
 * 开关行（面包屑导航 / 全局算法切换器），随 KV 保存链。
 */
import type { SiteNavigationSettings } from '@/domain/models/option'
import { SettingsFormGrid, SettingsSwitchField } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type SiteNavigationPageProps = {
  defaultValues: SiteNavigationSettings
}

export function SiteNavigationPage({ defaultValues }: SiteNavigationPageProps) {
  return (
    <SettingsFormPage<SiteNavigationSettings>
      baseline={defaultValues}
      optionKey={(field) => `site.navigation.${field as string}`}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsSwitchField
            controlId='nav-breadcrumb'
            label='面包屑导航'
            description='页面顶部显示当前所在位置'
            checked={draft.showBreadcrumb}
            onCheckedChange={(checked) => setField('showBreadcrumb', checked)}
          />
          <SettingsSwitchField
            controlId='nav-algorithm-switcher'
            label='全局算法切换器'
            description='导航栏右上角显示全局算法切换入口'
            checked={draft.showAlgorithmSwitcher}
            onCheckedChange={(checked) => setField('showAlgorithmSwitcher', checked)}
          />
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
