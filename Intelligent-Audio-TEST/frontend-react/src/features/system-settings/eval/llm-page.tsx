/**
 * 评估服务 · LLM 裁判分区（interfaces 层）。
 * 普通项走 KV；API Key 走密钥接口（只回掩码）。分维度模型一维一键。
 */
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  EVAL_LLM_DIMENSIONS,
  EVAL_LLM_OPTION_KEYS,
  EVAL_SECRET_KEYS,
  evalDimensionModelKey,
  type EvalLlmSettings,
} from '@/domain/models/evalSettings'

import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { EvalFormPage } from './eval-form-page'
import { SecretInput } from './secret-input'

type EvalLlmPageProps = {
  defaultValues: EvalLlmSettings
}

export function EvalLlmPage({ defaultValues }: EvalLlmPageProps) {
  return (
    <EvalFormPage<EvalLlmSettings>
      baseline={defaultValues}
      optionKey={(field) => EVAL_LLM_OPTION_KEYS[field]}
      secretKeys={[EVAL_SECRET_KEYS.llmApiKey]}
      collectChanges={(draft, dirtyFields) => {
        const changes = dirtyFields
          .filter((field) => field.key !== EVAL_LLM_OPTION_KEYS.dimensionModels)
          .map((field) => ({ key: field.key, value: field.value }))
        if (
          dirtyFields.some(
            (field) => field.key === EVAL_LLM_OPTION_KEYS.dimensionModels
          )
        ) {
          for (const dimension of EVAL_LLM_DIMENSIONS) {
            changes.push({
              key: evalDimensionModelKey(dimension.id),
              value: draft.dimensionModels[dimension.id] ?? '',
            })
          }
        }
        return changes
      }}
    >
      {(draft, setField, secret) => (
        <SettingsFormGrid>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-api-base'>API Base</Label>
            <Input
              id='eval-llm-api-base'
              placeholder='https://az.gptplus5.com/v1（留空=env 配置）'
              value={draft.apiBase}
              onChange={(event) => setField('apiBase', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <SecretInput
              id='eval-llm-api-key'
              label='API Key'
              mask={secret.mask(EVAL_SECRET_KEYS.llmApiKey)}
              value={secret.value(EVAL_SECRET_KEYS.llmApiKey)}
              onChange={(value) => secret.set(EVAL_SECRET_KEYS.llmApiKey, value)}
              hint='加密存储；保存后仅显示掩码'
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-default-model'>默认模型</Label>
            <Input
              id='eval-llm-default-model'
              placeholder='留空=env 配置（LLM_JUDGE_DEFAULT_MODEL）'
              value={draft.defaultModel}
              onChange={(event) => setField('defaultModel', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-audio-compress'>音频预处理</Label>
            <Input
              id='eval-llm-audio-compress'
              placeholder='off / 16k_mono（留空=服务端默认）'
              value={draft.audioCompress}
              onChange={(event) => setField('audioCompress', event.target.value)}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-max-tokens'>max_tokens</Label>
            <Input
              id='eval-llm-max-tokens'
              type='number'
              min={0}
              placeholder='0 = 不覆盖'
              value={draft.maxTokens || ''}
              onChange={(event) =>
                setField('maxTokens', Number(event.target.value) || 0)
              }
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-timeout'>超时（秒）</Label>
            <Input
              id='eval-llm-timeout'
              type='number'
              min={0}
              placeholder='0 = 不覆盖'
              value={draft.timeout || ''}
              onChange={(event) =>
                setField('timeout', Number(event.target.value) || 0)
              }
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem className='grid gap-1.5'>
            <Label htmlFor='eval-llm-temperature'>temperature</Label>
            <Input
              id='eval-llm-temperature'
              type='number'
              step={0.1}
              min={-1}
              placeholder='-1 = 不覆盖'
              value={draft.temperature >= 0 ? draft.temperature : ''}
              onChange={(event) => {
                const raw = event.target.value
                setField('temperature', raw === '' ? -1 : Number(raw))
              }}
            />
          </SettingsFormGridItem>
          <SettingsFormGridItem span='full' className='grid gap-2'>
            <Label>分维度模型（留空=默认模型）</Label>
            <div className='grid gap-2 sm:grid-cols-2'>
              {EVAL_LLM_DIMENSIONS.map((dimension) => (
                <div key={dimension.id} className='grid gap-1'>
                  <span className='text-muted-foreground text-xs'>
                    {dimension.label}
                  </span>
                  <Input
                    aria-label={`${dimension.label} 模型`}
                    value={draft.dimensionModels[dimension.id] ?? ''}
                    onChange={(event) =>
                      setField('dimensionModels', {
                        ...draft.dimensionModels,
                        [dimension.id]: event.target.value,
                      })
                    }
                  />
                </div>
              ))}
            </div>
          </SettingsFormGridItem>
        </SettingsFormGrid>
      )}
    </EvalFormPage>
  )
}
