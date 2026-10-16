/**
 * 系统选项保存 mutation（application 层）：仅脏字段逐项 PUT + toast + 缓存失效
 * （对齐 newAPI use-update-option 实测；无差异时 toast.info「没有需要保存的更改」由
 * 调用方（use-settings-form）在提交前短路）。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { putSystemOption } from '@/infrastructure/api/optionApi'
import { SYSTEM_OPTIONS_QUERY_KEY } from '@/infrastructure/api/optionApi'

export function useUpdateOption() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (entries: Array<{ key: string; value: unknown }>) => {
      for (const entry of entries) {
        await putSystemOption(entry.key, entry.value)
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SYSTEM_OPTIONS_QUERY_KEY })
      toast.success('设置已更新')
    },
    onError: () => {
      toast.error('设置保存失败')
    },
  })
}
