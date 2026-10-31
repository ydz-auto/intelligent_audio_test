/**
 * 设备映射区（设备「参数配置」弹窗内嵌；设备级映射编辑）。
 *
 * 视图与算法编辑模态窗同源（`features/algorithm-config/mutate/mapping-view`）：
 * 两个分节「设备映射（用例参数 → 设备输入）」「评估映射（设备输出 → 评估参数）」，
 * 各自带搜索 / 转换（评估另加维度）筛选 / 平铺-分组视图 / 分页 / 分组折叠。
 *
 * 语义（与设备参数同构的设备级覆盖）：
 * - 读：`GET /algorithm/mappings?...&device_id=Y` 返回算法级打底 + 本设备覆盖行；
 *   本区按映射键合并（设备行覆盖算法级行），徽章标注「本设备 / 算法级」；
 * - 写：新增 / 编辑 / 删除都落**设备级行**（带 device_id），算法级行只读；
 * - 删除设备级行即回落到算法级映射。
 *
 * 降级：写操作需 `algorithm:definition_manage`，缺失时只读。
 */
import { useQuery } from '@tanstack/react-query'

import { deviceMappingsQueryKey } from '@/application/devices/use-device-scope-mappings'
import { MappingCollapsible } from '@/features/algorithm-config/mutate/mapping-view'
import { fetchDeviceScopeMappings } from '@/infrastructure/api/device-param-api'
import { DeviceEvaluationMappingTable } from './device-evaluation-mapping-table'
import { DeviceMappingTable } from './device-mapping-table'

export function DeviceMappingsSection({
  open,
  algorithmType,
  deviceId,
}: {
  open: boolean
  algorithmType: string
  deviceId: number
}) {
  /** 与两个表共用同一 query key（计数不额外请求）：设备映射=case 桶，评估映射=evaluation 桶 */
  const deviceMappingsQuery = useQuery({
    queryKey: deviceMappingsQueryKey(algorithmType, deviceId, 'case'),
    queryFn: () => fetchDeviceScopeMappings(algorithmType, deviceId, 'case'),
    enabled: open && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })
  const evaluationMappingsQuery = useQuery({
    queryKey: deviceMappingsQueryKey(algorithmType, deviceId, 'evaluation'),
    queryFn: () => fetchDeviceScopeMappings(algorithmType, deviceId, 'evaluation'),
    enabled: open && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })
  const deviceCount = (deviceMappingsQuery.data ?? []).filter(
    (mapping) => mapping.source === 'case'
  ).length
  const evaluationCount = (evaluationMappingsQuery.data ?? []).filter(
    (mapping) => mapping.source === 'device'
  ).length

  if (!algorithmType) {
    return (
      <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
        选择关联算法后可查看并配置该设备的参数映射。
      </p>
    )
  }

  return (
    <div className='space-y-3 border-t border-border pt-3'>
      <p className='text-muted-foreground text-xs'>
        设备级映射覆盖同键的算法级映射；删除覆盖即回落到算法级。
      </p>
      <MappingCollapsible
        defaultOpen
        title='设备映射'
        subtitle='用例参数 → 设备输入'
        count={deviceCount}
      >
        <DeviceMappingTable open={open} algorithmType={algorithmType} deviceId={deviceId} />
      </MappingCollapsible>
      <MappingCollapsible
        title='评估映射'
        subtitle='设备输出 → 评估参数'
        count={evaluationCount}
      >
        <DeviceEvaluationMappingTable
          open={open}
          algorithmType={algorithmType}
          deviceId={deviceId}
        />
      </MappingCollapsible>
    </div>
  )
}
