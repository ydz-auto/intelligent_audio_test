/**
 * 评估服务 · ASR 分区（interfaces 层）：ASR 地址与超时（运行时可改，无需重启）。
 */
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  EVAL_ASR_OPTION_KEYS,
  type EvalAsrSettings,
} from '@/domain/models/evalSettings'

import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { EvalFormPage } from './eval-form-page'

type EvalAsrPageProps = {
  defaultValues: EvalAsrSettings
}

export function EvalAsrPage({ defaultValues }: EvalAsrPageProps) {
  return (
    <EvalFormPage<EvalAsrSettings>
      baseline={defaultValues}
      optionKey={(field) => EVAL_ASR_OPTION_KEYS[field]}
      secretKeys={[]}
    >
      {(draft, setField) => (
        <SettingsFormGrid>
          <SettingsFormGridItem span='full' className='grid gap-1.5'>
            <Label htmlFor='eval-asr-url'>ASR 服务地址</Label>
            <Input
              id='eval-asr-url'
              placeholder='http://100.103.97.108:10095（留空=env 配置）'
              value={draft.url}
              onChange={(event) => setField('url', event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>
              eval_server 调用 asr_server 的地址；保存后 5 秒内生效。
            </p>
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-asr-timeout'>超时（秒）</Label>
            <Input
              id='eval-asr-timeout'
              type='number'
              min={0}
              placeholder='0 = 不覆盖（env ASR_TIMEOUT）'
              value={draft.timeout || ''}
              onChange={(event) =>
                setField('timeout', Number(event.target.value) || 0)
              }
            />
          </SettingsFormGridItem>
        </SettingsFormGrid>
      )}
    </EvalFormPage>
  )
}
