/**
 * INT-1105 设备 test 添加/编辑走扫描（对齐 React INT-1029 mergeScanPrefill 口径）：
 * useDeviceSelection.selectDevice 扫描回填单测——
 *  - 名称编辑态保留用户已填值（V9.7.10 `(!isEditMode || !formValues.name)` 语义），为空时取扫描值；
 *  - 硬件字段（型号/序列号/系统/系统版本/应用名/应用版本/IP）以扫描值为准；
 *  - 系统值归一（Android→android / HarmonyOS→harmony / iOS→ios，匹配表单 select 选项）；
 *  - 播放设备回填唯一ID/通道/采样率/类型，类型仅落 dry/noise 合法选项；
 *  - 非扫描字段保持原值不动。
 */
import { describe, expect, it } from 'vitest'
import { ref, type Ref } from 'vue'

import { useDeviceSelection, type DeviceFormField } from '../useDeviceSelection'

function makeForm(initial: Record<string, unknown>) {
  return ref<Record<string, unknown>>({ ...initial }) as Ref<Record<string, unknown>>
}

const testFields: DeviceFormField[] = [
  { key: 'name' },
  { key: 'model' },
  { key: 'serialNumber' },
  { key: 'system' },
  { key: 'systemVersion' },
  { key: 'appName' },
  { key: 'appVersion' },
  { key: 'ip' },
]

const playbackFields: DeviceFormField[] = [
  { key: 'name' },
  { key: 'model' },
  { key: 'deviceUniqueId' },
  { key: 'channelIndex' },
  { key: 'sampleRate' },
  { key: 'deviceType' },
]

describe('useDeviceSelection.selectDevice 扫描回填（INT-1105）', () => {
  it('测试设备：编辑态名称保留用户已填值，硬件字段以扫描值为准，IP 回填', () => {
    const { selectDevice } = useDeviceSelection()
    const form = makeForm({
      kind: 'test',
      name: '我的设备名',
      model: '原型号',
      system: 'android',
      systemVersion: '9',
      appName: '旧应用',
      appVersion: '1.0',
      serialNumber: 'OLD_SERIAL',
      ip: '10.0.0.1',
      remark: '备注保留',
      priority: 5,
    })

    selectDevice(
      {
        name: 'Android Unknown Android',
        model: 'Unknown Android',
        serial: 'List',
        system: 'Android',
        systemVersion: 'Unknown',
        appName: 'Default App',
        appVersion: '1.0',
        ip: '192.168.1.10',
      },
      testFields,
      form,
      true,
    )

    const merged = form.value
    expect(merged.name).toBe('我的设备名') // 名称保留用户已填值（V9.7.10 isEditMode 语义）
    expect(merged.model).toBe('Unknown Android')
    expect(merged.serialNumber).toBe('List')
    expect(merged.system).toBe('android') // 大写 Android 归一为表单选项小写原值
    expect(merged.systemVersion).toBe('Unknown')
    expect(merged.appName).toBe('Default App')
    expect(merged.appVersion).toBe('1.0')
    expect(merged.ip).toBe('192.168.1.10') // INT-1105：扫描 IP 回填
    expect(merged.remark).toBe('备注保留') // 非扫描字段不动
    expect(merged.priority).toBe(5)
  })

  it('测试设备：新增态名称为空时取扫描名称', () => {
    const { selectDevice } = useDeviceSelection()
    const form = makeForm({
      kind: 'test',
      name: '',
      model: '',
      system: 'android',
      systemVersion: '',
      appName: '',
      appVersion: '',
      serialNumber: '',
      ip: '',
    })

    selectDevice(
      {
        name: '扫描到的设备',
        model: 'P50',
        serial: 'SN001',
        system: 'HarmonyOS',
        systemVersion: '3.0',
        appName: 'App',
        appVersion: '2.0',
        ip: '192.168.1.20',
      },
      testFields,
      form,
      false,
    )

    const merged = form.value
    expect(merged.name).toBe('扫描到的设备')
    expect(merged.system).toBe('harmony') // HarmonyOS 归一
    expect(merged.systemVersion).toBe('3.0')
    expect(merged.ip).toBe('192.168.1.20')
  })

  it('播放设备：回填唯一ID/通道/采样率/类型，名称保留已填值', () => {
    const { selectDevice } = useDeviceSelection()
    const form = makeForm({
      kind: 'playback',
      name: '播放设备A',
      model: 'M300',
      deviceUniqueId: 'OLD_UID',
      channelIndex: '1',
      sampleRate: '48000',
      deviceType: 'dry',
    })

    selectDevice(
      {
        name: 'AudioChannel 2',
        model: 'USB Audio',
        deviceUniqueId: 'audio-2',
        channelIndex: 2,
        sampleRate: 44100,
        type: 'noise',
      },
      playbackFields,
      form,
      true,
    )

    const merged = form.value
    expect(merged.name).toBe('播放设备A')
    expect(merged.model).toBe('USB Audio')
    expect(merged.deviceUniqueId).toBe('audio-2')
    expect(merged.channelIndex).toBe(2)
    expect(merged.sampleRate).toBe(44100)
    expect(merged.deviceType).toBe('noise') // INT-1105：扫描 type → deviceType 回填
  })

  it('播放设备：扫描 type 非 dry/noise（如 output）不覆盖用户已选类型', () => {
    const { selectDevice } = useDeviceSelection()
    const form = makeForm({
      kind: 'playback',
      name: '播放设备A',
      model: 'M300',
      deviceUniqueId: 'audio-2',
      channelIndex: 0,
      sampleRate: 48000,
      deviceType: 'dry',
    })

    selectDevice(
      { name: '扬声器', model: 'Realtek', deviceUniqueId: 'audio-1', channelIndex: 0, sampleRate: 48000, type: 'output' },
      playbackFields,
      form,
      true,
    )

    expect(form.value.deviceType).toBe('dry') // 非合法选项不落值，保留原值
  })

  it('IP 字段兜底：扫描结果 ipAddress/ip_address 别名同样回填', () => {
    const { selectDevice } = useDeviceSelection()
    const form = makeForm({ kind: 'test', name: '设备A', ip: '' })
    selectDevice({ name: '设备B', model: 'M', serial: 'S1', system: 'android', ipAddress: '10.0.0.8' }, testFields, form, true)
    expect(form.value.ip).toBe('10.0.0.8')
  })
})
