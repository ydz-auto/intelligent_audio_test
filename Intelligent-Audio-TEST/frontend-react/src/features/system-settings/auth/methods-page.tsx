/**
 * 认证方式分区（interfaces 层，INT-347 §4.1 母版 A）：
 * 密码登录 / 注册开关 / 邮箱验证 三开关行，随 KV 保存链。
 */
import type { AuthMethodSettings } from '@/domain/models/option'
import { SettingsFormGrid, SettingsSwitchField } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type AuthMethodsPageProps = {
  defaultValues: AuthMethodSettings
}

export function AuthMethodsPage({ defaultValues }: AuthMethodsPageProps) {
  return (
    <SettingsFormPage<AuthMethodSettings>
      baseline={defaultValues}
      optionKey={(field) => `auth.${field as string}`}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsSwitchField
            controlId='auth-password-login'
            label='密码登录'
            description='允许用户使用密码登录'
            checked={draft.passwordLogin}
            onCheckedChange={(checked) => setField('passwordLogin', checked)}
          />
          <SettingsSwitchField
            controlId='auth-registration'
            label='注册开关'
            description='允许新用户注册'
            checked={draft.registration}
            onCheckedChange={(checked) => setField('registration', checked)}
          />
          <SettingsSwitchField
            controlId='auth-email-verification'
            label='邮箱验证'
            description='注册需邮箱验证码'
            checked={draft.emailVerification}
            onCheckedChange={(checked) => setField('emailVerification', checked)}
          />
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
