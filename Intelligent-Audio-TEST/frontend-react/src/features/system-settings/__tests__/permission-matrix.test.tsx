/**
 * 权限矩阵组件测试（INT-489，INT-347 §4.4.1）：模块分组/权限行 Toggle/
 * 通配禁用/全选清空。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PermissionMatrix } from '../components/permission-matrix'

const TEST_MODULES = [
  {
    id: 'log',
    name: '日志',
    permissions: [
      { code: 'log:read', name: '查看日志/统计/归档', module: '日志' },
      { code: 'log:manage', name: '标记/刷新/清空/归档日志', module: '日志' },
    ],
  },
  {
    id: 'wildcard',
    name: '超级通配',
    permissions: [
      { code: '*', name: '超级权限（通配所有操作）', module: '超级通配' },
    ],
  },
]

describe('PermissionMatrix', () => {
  it('渲染模块分组与权限行（模块默认展开）', () => {
    render(
      <PermissionMatrix
        value={['log:read']}
        onChange={() => {}}
        permissionModules={TEST_MODULES}
      />
    )
    expect(screen.getByText('日志')).toBeInTheDocument()
    expect(screen.getByText('查看日志/统计/归档')).toBeInTheDocument()
    expect(screen.getByText('已选 1/2')).toBeInTheDocument()
  })

  it('点击权限行 Toggle 触发 onChange 增删权限码', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <PermissionMatrix
        value={['log:read']}
        onChange={onChange}
        permissionModules={TEST_MODULES}
      />
    )
    await user.click(
      screen.getByRole('checkbox', { name: '标记/刷新/清空/归档日志' })
    )
    expect(onChange).toHaveBeenCalledWith(['log:read', 'log:manage'])
  })

  it('通配 * 行禁用且不可切换（WILDCARD_FORBIDDEN）', () => {
    const onChange = vi.fn()
    render(
      <PermissionMatrix
        value={[]}
        onChange={onChange}
        permissionModules={TEST_MODULES}
      />
    )
    const wildcardInput = document.getElementById('perm-*')
    expect(wildcardInput).toBeDisabled()
  })

  it('disabled 态整块禁用且 Toggle 不触发', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <PermissionMatrix
        value={['log:read']}
        onChange={onChange}
        disabled
        permissionModules={TEST_MODULES}
      />
    )
    await user.click(
      screen.getByRole('checkbox', { name: '查看日志/统计/归档' })
    )
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText('日志')).toBeInTheDocument()
  })

  it('全选按钮整模块选中', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <PermissionMatrix
        value={[]}
        onChange={onChange}
        permissionModules={TEST_MODULES}
      />
    )
    await user.click(screen.getAllByRole('button', { name: /全选/ })[0])
    expect(onChange).toHaveBeenCalledWith(['log:read', 'log:manage'])
  })

  it('目录缺省时使用 PERMISSION_CATALOG 全量（22 模块）', () => {
    render(<PermissionMatrix value={[]} onChange={() => {}} />)
    expect(screen.getByText('任务')).toBeInTheDocument()
    expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(20)
  })
})
