/**
 * 导入算法弹窗（§7.6；Dialog sm:max-w-2xl，补现状缺口）。
 * 粘贴或上传算法定义 JSON（与导出格式一致），解析校验内联「JSON 格式错误：{detail}」，
 * 主钮「导入」（POST /algorithm/import）→ toast「成功导入 {n} 个算法」。
 */
import { Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { importAlgorithms } from '@/infrastructure/api/algorithm-config-api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { IMPORT_DIALOG_DESCRIPTION } from '@/features/algorithm-config/constants'

export type AlgorithmImportDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported: () => void
}

export function AlgorithmImportDialog(props: AlgorithmImportDialogProps) {
  const [json, setJson] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const handleFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      setJson(String(reader.result ?? ''))
      setError(null)
    }
    reader.readAsText(file)
  }

  const handleImport = async () => {
    let parsed: unknown
    try {
      parsed = JSON.parse(json)
    } catch (e) {
      setError(
        `JSON 格式错误：${e instanceof Error ? e.message : '解析失败'}`
      )
      return
    }
    if (!Array.isArray(parsed)) {
      setError('JSON 格式错误：期望算法定义数组')
      return
    }
    setPending(true)
    try {
      const result = await importAlgorithms(parsed)
      toast.success(`成功导入 ${result.importedCount} 个算法`)
      setJson('')
      setError(null)
      props.onImported()
      props.onOpenChange(false)
    } catch {
      toast.error('导入失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) {
          setJson('')
          setError(null)
        }
      }}
    >
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>导入算法</DialogTitle>
          <DialogDescription>{IMPORT_DIALOG_DESCRIPTION}</DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <Textarea
            aria-label='算法定义 JSON'
            value={json}
            onChange={(e) => {
              setJson(e.target.value)
              if (error) setError(null)
            }}
            rows={10}
            placeholder='[{ "type": "asr-v3", "name": "通用识别引擎", ... }]'
            className='font-mono text-xs'
            aria-invalid={Boolean(error)}
          />

          <div className='flex items-center gap-2'>
            <Button
              variant='outline'
              size='sm'
              type='button'
              onClick={() => fileRef.current?.click()}
            >
              <Upload aria-hidden='true' />
              选择文件
            </Button>
            <input
              ref={fileRef}
              type='file'
              accept='.json,application/json'
              className='hidden'
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFile(file)
                e.target.value = ''
              }}
            />
            <p className='text-muted-foreground text-xs'>
              支持 .json 文件，格式与导出算法一致
            </p>
          </div>

          {error && (
            <p role='alert' className='text-destructive text-xs'>
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' type='button' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button type='button' disabled={pending || json.trim() === ''} onClick={handleImport}>
            {pending ? '导入中…' : '导入'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
