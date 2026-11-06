import { describe, expect, it } from 'vitest'

import {
  deviceGroupFromDto,
  deviceGroupsToTree,
} from '@/infrastructure/adapters/deviceGroupAdapter'
import type { DeviceGroupItemDto } from '@/infrastructure/dto/device-group.dto'

const BASE_DTO: DeviceGroupItemDto = {
  id: 'grp-root',
  name: '客厅场景组',
  description: '客厅远场测试',
  group_type: 'test',
  parent_id: null,
  created_by_user_id: null,
  updated_by_user_id: null,
  created_at: '2026-09-01T09:00:00',
  updated_at: '2026-10-17T08:40:00',
  device_ids: null,
  device_count: 2,
}

describe('deviceGroupFromDto', () => {
  it('parent_id → parentId（字符串语义，根分组为 null）', () => {
    expect(deviceGroupFromDto(BASE_DTO).parentId).toBeNull()
    expect(deviceGroupFromDto({ ...BASE_DTO, parent_id: 'grp-root' }).parentId).toBe('grp-root')
    // 数字 parent_id 归一为字符串（与 id 同口径）
    expect(deviceGroupFromDto({ ...BASE_DTO, parent_id: 5 }).parentId).toBe('5')
  })

  it('group_type/device_count 映射（播放组归 playback、缺省归 test）', () => {
    expect(deviceGroupFromDto(BASE_DTO).groupType).toBe('test')
    expect(deviceGroupFromDto({ ...BASE_DTO, group_type: 'playback' }).groupType).toBe('playback')
    expect(deviceGroupFromDto({ ...BASE_DTO, device_count: 7 }).memberCount).toBe(7)
  })
})

describe('deviceGroupsToTree', () => {
  it('按 parent_id 建树：根分组挂顶层、子分组挂父级 children', () => {
    const groups = [
      deviceGroupFromDto({ ...BASE_DTO, id: 'g1', name: '根A', parent_id: null }),
      deviceGroupFromDto({ ...BASE_DTO, id: 'g2', name: '子B', parent_id: 'g1' }),
      deviceGroupFromDto({ ...BASE_DTO, id: 'g3', name: '孙C', parent_id: 'g2' }),
      deviceGroupFromDto({ ...BASE_DTO, id: 'g4', name: '根D', parent_id: null }),
    ]
    const tree = deviceGroupsToTree(groups)
    expect(tree.map((g) => g.id)).toEqual(['g1', 'g4'])
    expect(tree[0].children.map((g) => g.id)).toEqual(['g2'])
    expect(tree[0].children[0].children.map((g) => g.id)).toEqual(['g3'])
    expect(tree[1].children).toEqual([])
  })

  it('父分组不在列表（分页截断/脏数据）时降级为根分组', () => {
    const groups = [
      deviceGroupFromDto({ ...BASE_DTO, id: 'g1', name: '孤儿', parent_id: 'missing-parent' }),
    ]
    const tree = deviceGroupsToTree(groups)
    expect(tree.map((g) => g.id)).toEqual(['g1'])
  })

  it('保持原数组顺序，仅挂载 children 不改变根顺序', () => {
    const groups = [
      deviceGroupFromDto({ ...BASE_DTO, id: 'g1', name: '根A', parent_id: null }),
      deviceGroupFromDto({ ...BASE_DTO, id: 'g2', name: '子B', parent_id: 'g1' }),
      deviceGroupFromDto({ ...BASE_DTO, id: 'g3', name: '根C', parent_id: null }),
    ]
    const tree = deviceGroupsToTree(groups)
    expect(tree.map((g) => g.id)).toEqual(['g1', 'g3'])
  })
})
