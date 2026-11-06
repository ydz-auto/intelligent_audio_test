/**
 * 账号安全卡（13_个人中心.md §3.5）：对位 newAPI security 左列结构，
 * Card 内分区块标题组织。当前「登录与认证」区块仅含第三方账号绑定——
 * 修改密码行/对话框按 §3.5.1 隐藏（后端自助改密端点未落，不对用户展示不可用功能），
 * 组件 change-password-dialog.tsx 保留待接入。
 */
import { ShieldCheck } from 'lucide-react'

import {
  ACCOUNT_SECURITY_DESCRIPTION,
  ACCOUNT_SECURITY_TITLE,
  AUTH_SECTION_TITLE,
} from '../constants'
import { TitledCard } from './titled-card'
import { AccountBindings } from './account-bindings'

export function AccountSecurityCard() {
  return (
    <TitledCard
      icon={<ShieldCheck aria-hidden='true' />}
      tone='info'
      title={ACCOUNT_SECURITY_TITLE}
      description={ACCOUNT_SECURITY_DESCRIPTION}
    >
      <div className='grid gap-3'>
        <h3 className='text-sm font-semibold'>{AUTH_SECTION_TITLE}</h3>
        <AccountBindings />
      </div>
    </TitledCard>
  )
}
