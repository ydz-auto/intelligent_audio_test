/**
 * INT-1402：系统设置站点信息「站点名称」必填校验不生效
 *
 * 原缺陷：SettingsFormPage 保存按钮只按 `saving || !dirty` 禁用，useOptionForm.save()
 * 也只收集「脏且不同」的键直接 PUT /api/option/ —— 清空必填的站点名称后仍可保存，
 * 后端落 site.name=''。
 *
 * 本用例锁定 composable 层必填校验：
 * - required 字段去空白后为空 → valid=false、requiredErrors[key] = 「label不能为空」；
 * - save() 前置拦截：必填留空不发 PUT（optionsPort.update 不被调用）、error 置「站点名称不能为空」；
 * - 必填字段填值后 valid=true，save() 正常走 PUT；
 * - 非必填字段留空不产生错误。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useOptionForm, type OptionFieldDef } from '../useSettingsForm'

const optionsPortMocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  update: vi.fn(),
}))

vi.mock('@/composables/system/optionsPort', () => ({
  optionsPort: optionsPortMocks,
}))

/** 站点信息字段定义（与 SiteInfoSection.vue 口径一致） */
const str = (key: string) => (o: Record<string, unknown>) =>
  typeof o[key] === 'string' ? String(o[key]) : ''

const siteName: OptionFieldDef = {
  key: 'site.name', label: '站点名称', type: 'text', required: true,
  toValue: str('site.name'),
}
const siteLogo: OptionFieldDef = {
  key: 'site.logo', label: 'Logo 地址', type: 'text',
  toValue: str('site.logo'),
}

/** 挂载一个调用 useOptionForm 的最小组件，返回暴露状态与函数 */
function mountForm(fields: OptionFieldDef[]) {
  const ctx = {} as ReturnType<typeof useOptionForm>
  const wrapper = mount(
    defineComponent({
      setup() {
        const form = useOptionForm(fields)
        Object.assign(ctx, form)
        return { form }
      },
      template: '<div />',
    })
  )
  return { wrapper, ctx }
}

beforeEach(() => {
  vi.clearAllMocks()
  optionsPortMocks.getAll.mockResolvedValue({
    'site.name': '智能语音测试平台',
    'site.logo': 'https://example.com/logo.png',
  })
})

describe('useOptionForm 必填校验（INT-1402）', () => {
  it('必填字段去空白后为空 → valid=false，requiredErrors 含「站点名称不能为空」', async () => {
    optionsPortMocks.getAll.mockResolvedValue({ 'site.name': '', 'site.logo': '' })
    const { ctx } = mountForm([siteName, siteLogo])
    await vi.waitFor(() => expect(ctx.loading.value).toBe(false))

    ctx.values.value['site.name'] = ''
    expect(ctx.valid.value).toBe(false)
    expect(ctx.requiredErrors.value['site.name']).toBe('站点名称不能为空')
    expect(ctx.requiredErrors.value['site.logo']).toBeUndefined()
  })

  it('纯空白字符串也视为必填未填（trim 语义）', async () => {
    optionsPortMocks.getAll.mockResolvedValue({ 'site.name': '智能语音测试平台', 'site.logo': '' })
    const { ctx } = mountForm([siteName, siteLogo])
    await vi.waitFor(() => expect(ctx.loading.value).toBe(false))

    ctx.values.value['site.name'] = '   '
    expect(ctx.valid.value).toBe(false)
    expect(ctx.requiredErrors.value['site.name']).toBe('站点名称不能为空')
  })

  it('必填字段有值 → valid=true，无错误', async () => {
    const { ctx } = mountForm([siteName, siteLogo])
    await vi.waitFor(() => expect(ctx.loading.value).toBe(false))

    ctx.values.value['site.name'] = '智能语音测试平台'
    expect(ctx.valid.value).toBe(true)
    expect(ctx.requiredErrors.value['site.name']).toBeUndefined()
  })

  it('save() 必填留空时拦截：不发 PUT、error 置「站点名称不能为空」', async () => {
    optionsPortMocks.getAll.mockResolvedValue({ 'site.name': '智能语音测试平台', 'site.logo': '' })
    const { ctx } = mountForm([siteName, siteLogo])
    await vi.waitFor(() => expect(ctx.loading.value).toBe(false))

    // 清空必填字段并保存
    ctx.values.value['site.name'] = ''
    await ctx.save()
    expect(optionsPortMocks.update).not.toHaveBeenCalled()
    expect(ctx.error.value).toBe('站点名称不能为空')
  })

  it('必填字段有值 → save() 正常 PUT，notice「设置已更新」', async () => {
    optionsPortMocks.getAll.mockResolvedValue({ 'site.name': '智能语音测试平台', 'site.logo': '' })
    optionsPortMocks.update.mockResolvedValue('设置已更新')
    const { ctx } = mountForm([siteName, siteLogo])
    await vi.waitFor(() => expect(ctx.loading.value).toBe(false))

    ctx.values.value['site.name'] = '智能语音测试平台-改'
    await ctx.save()
    expect(optionsPortMocks.update).toHaveBeenCalledWith('site.name', '智能语音测试平台-改')
    expect(ctx.error.value).toBe('')
  })
})
