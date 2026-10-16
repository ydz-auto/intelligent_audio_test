/**
 * 系统选项 query（application 层）：KV 全量拉取 + 类型化解析（对齐 newAPI
 * use-system-options 实测：布尔/数字/数组安全解析失败回退默认）。
 * staleTime 5min（对齐 use-system-options.ts）；保存后 invalidate 见 use-update-option。
 */
import { useQuery } from '@tanstack/react-query'

import {
  getSystemOptions,
  SYSTEM_OPTIONS_QUERY_KEY,
} from '@/infrastructure/api/optionApi'

export function useSystemOptions() {
  return useQuery({
    queryKey: [...SYSTEM_OPTIONS_QUERY_KEY],
    queryFn: getSystemOptions,
    staleTime: 5 * 60_000,
  })
}
