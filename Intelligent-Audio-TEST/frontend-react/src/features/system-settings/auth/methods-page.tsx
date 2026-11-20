/**
 * 认证方式分区（interfaces 层，INT-347 §4.1 母版 A）：
 * 密码登录 / 注册开关 / 邮箱验证 / 邀请码注册 / 首页注册后可见，随 KV 保存链；
 * 邀请码注册开启时展开邀请码输入，并强制「首页注册后可见」。
 */
import type { AuthMethodSettings } from '@/domain/models/option'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  SettingsFormGrid,
  SettingsFormGridItem,
  SettingsSwitchField,
} from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'

type AuthMethodsPageProps = {
  defaultValues: AuthMethodSettings
}

/** 字段 → 系统选项 KV 键（camelCase 域字段与 snake_case KV 的唯一映射点） */
const AUTH_METHOD_OPTION_KEYS: Record<keyof AuthMethodSettings, string> = {
  passwordLogin: 'auth.password_login',
  registration: 'auth.registration',
  emailVerification: 'auth.email_verification',
  inviteCodeRegistration: 'auth.invite_code_registration',
  inviteCode: 'auth.invite_code',
  homeRequireRegistration: 'site.home_require_registration',
}

export function AuthMethodsPage({ defaultValues }: AuthMethodsPageProps) {
  return (
    <SettingsFormPage<AuthMethodSettings>
      baseline={defaultValues}
      optionKey={(field) => AUTH_METHOD_OPTION_KEYS[field]}
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
          <SettingsSwitchField
            controlId='auth-invite-code-registration'
            label='邀请码注册'
            description='开启后注册必须填写邀请码'
            checked={draft.inviteCodeRegistration}
            onCheckedChange={(checked) =>
              setField('inviteCodeRegistration', checked)
            }
          />
          {draft.inviteCodeRegistration && (
            <SettingsFormGridItem span='full' className='grid gap-1.5'>
              <Label htmlFor='auth-invite-code'>邀请码</Label>
              <Input
                id='auth-invite-code'
                placeholder='请输入邀请码'
                value={draft.inviteCode}
                onChange={(event) =>
                  setField('inviteCode', event.target.value)
                }
              />
              <p className='text-muted-foreground text-xs'>
                注册时必须输入完全一致的邀请码，可重复使用；未配置时用户将无法注册
              </p>
            </SettingsFormGridItem>
          )}
          <SettingsSwitchField
            controlId='auth-home-require-registration'
            label='首页注册后可见'
            description={
              draft.inviteCodeRegistration
                ? '邀请码注册开启时强制生效：未登录访问首页将跳转登录页'
                : '开启后未登录访问首页将跳转登录页'
            }
            checked={
              draft.inviteCodeRegistration || draft.homeRequireRegistration
            }
            onCheckedChange={(checked) =>
              setField('homeRequireRegistration', checked)
            }
            disabled={draft.inviteCodeRegistration}
          />
        </SettingsFormGrid>
      )}
    </SettingsFormPage>
  )
}
