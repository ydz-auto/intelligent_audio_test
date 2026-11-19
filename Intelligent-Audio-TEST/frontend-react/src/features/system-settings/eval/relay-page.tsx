/**
 * 评估服务 · 第三方评估中转分区（interfaces 层）。
 * 区角色 / 触发器 / C 端地址 / 兜底端点 / 区间 token；token 走密钥接口。
 */
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  EVAL_RELAY_OPTION_KEYS,
  EVAL_SECRET_KEYS,
  type EvalRelaySettings,
} from '@/domain/models/evalSettings'

import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { EvalFormPage } from './eval-form-page'
import { SecretInput } from './secret-input'

type EvalRelayPageProps = {
  defaultValues: EvalRelaySettings
}

export function EvalRelayPage({ defaultValues }: EvalRelayPageProps) {
  return (
    <EvalFormPage<EvalRelaySettings>
      baseline={defaultValues}
      optionKey={(field) => EVAL_RELAY_OPTION_KEYS[field]}
      secretKeys={[EVAL_SECRET_KEYS.relayTokenAB, EVAL_SECRET_KEYS.relayTokenBC]}
    >
      {(draft, setField, secret) => (
        <SettingsFormGrid>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-relay-self-zone'>本区角色</Label>
            <Input
              id='eval-relay-self-zone'
              placeholder='B（留空=env 配置）'
              value={draft.selfZone}
              onChange={(event) => setField('selfZone', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-relay-hub-zone'>评估中枢区</Label>
            <Input
              id='eval-relay-hub-zone'
              placeholder='B（留空=env 配置）'
              value={draft.hubZone}
              onChange={(event) => setField('hubZone', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-relay-sync-zone'>结果回同步区</Label>
            <Input
              id='eval-relay-sync-zone'
              placeholder='A（留空=env 配置）'
              value={draft.syncBackZone}
              onChange={(event) => setField('syncBackZone', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-relay-c-base'>第三方 C 端地址</Label>
            <Input
              id='eval-relay-c-base'
              placeholder='http://127.0.0.1:5101（留空=env 配置）'
              value={draft.cApiBaseUrl}
              onChange={(event) => setField('cApiBaseUrl', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem span='full' className='grid gap-1.5'>
            <Label htmlFor='eval-relay-fallback'>兜底评估端点</Label>
            <Input
              id='eval-relay-fallback'
              placeholder='多个用英文逗号分隔；留空=不降级'
              value={draft.fallbackUrls}
              onChange={(event) => setField('fallbackUrls', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <SecretInput
              id='eval-relay-token-ab'
              label='区间 token A↔B'
              mask={secret.mask(EVAL_SECRET_KEYS.relayTokenAB)}
              value={secret.value(EVAL_SECRET_KEYS.relayTokenAB)}
              onChange={(value) => secret.set(EVAL_SECRET_KEYS.relayTokenAB, value)}
              hint='跨区中转 HMAC 签名密钥；加密存储'
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <SecretInput
              id='eval-relay-token-bc'
              label='区间 token B↔C'
              mask={secret.mask(EVAL_SECRET_KEYS.relayTokenBC)}
              value={secret.value(EVAL_SECRET_KEYS.relayTokenBC)}
              onChange={(value) => secret.set(EVAL_SECRET_KEYS.relayTokenBC, value)}
              hint='第三方执行区间签名密钥；加密存储'
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem span='full' className='flex items-center gap-2'>
            <Checkbox
              id='eval-relay-trigger'
              checked={draft.triggerEnabled}
              onCheckedChange={(checked) =>
                setField('triggerEnabled', Boolean(checked))
              }
            />
            <Label htmlFor='eval-relay-trigger'>启用中枢侧中转执行触发器</Label>
          </SettingsFormGridItem>
        </SettingsFormGrid>
      )}
    </EvalFormPage>
  )
}
