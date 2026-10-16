/**
 * 访问控制分区（interfaces 层，INT-347 §4.1 母版 A + §6 预留壳）：
 * 接口速率限制开关行；随后端能力补齐。
 */
import type { AccessControlSettings } from '@/domain/models/option'
import { SettingsFormGrid, SettingsSwitchField } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type AccessControlPageProps = {
  defaultValues: AccessControlSettings
}

export function AccessControlPage({ defaultValues }: AccessControlPageProps) {
  return (
    <SettingsFormPage<AccessControlSettings>
      baseline={defaultValues}
      optionKey={(field) => `security.${field as string}`}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsSwitchField
            controlId='security-rate-limit'
            label='接口速率限制'
            description='启用后按用户与接口限制调用频率'
            checked={draft.rateLimit}
            onCheckedChange={(checked) => setField('rateLimit', checked)}
          />
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
