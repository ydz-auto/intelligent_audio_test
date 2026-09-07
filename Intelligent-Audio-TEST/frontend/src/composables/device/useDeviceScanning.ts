import { ref } from 'vue'
import { devicesPort, BATCH_LIST_PARAMS } from './devicesPort'
import { playbackPort } from './playbackPort'
import type { PlaybackDevice, ScannedDevice } from '../../domain/model/device'

/** 展示条目（本模块组装的 camelCase 视图对象，非 Domain 数据流） */
type DeviceDisplayItem = {
  displayKey: string | number | undefined
  serial?: string | number
  deviceUniqueId: string | number | undefined
  name: string
  model: string
  system?: string
  systemVersion?: string
  sampleRate?: number
  channelIndex?: number
  index: number
  isAdded: boolean
  isCurrent: boolean
}

/**
 * 设备标识结构类型 —— PlaybackDevice 与 ScannedDevice 的公共子集。
 * 用于辅助函数签名，使两类设备可共用同一套标识收集 / 查找 / 兜底逻辑。
 */
interface DeviceIdentifier {
  id?: string | number
  name?: string
  deviceUniqueId?: string
  serial?: string
  model?: string
  system?: string
  systemVersion?: string
  sampleRate?: number
  channelIndex?: number
}

/** 展示条目默认文案配置（配置化，避免魔法字符串散落） */
const DISPLAY_LABELS = {
  playbackNameFallback: '播放设备',
  testDeviceNameFallback: '测试设备',
  unknownModel: '未知型号',
  unknownVersion: '未知版本',
  unknownDevice: '未知设备',
  defaultSystemVersion: '1.0.0',
} as const

export function useDeviceScanning() {
  // 状态：全部为 camelCase Domain 类型（Application 层不感知 snake_case）
  const isScanning = ref(false)
  const scanResults = ref<ScannedDevice[]>([])
  const availableSerials = ref<ScannedDevice[]>([])
  const addedPlaybackDevices = ref<PlaybackDevice[]>([])
  const addedTestDevices = ref<ScannedDevice[]>([])
  const apiPlaybackDevices = ref<ScannedDevice[]>([])

  /** 收集已添加设备的多重标识集合（serial / deviceUniqueId / id / name，两处展示逻辑共用） */
  const collectAddedIdentifiers = (devices: DeviceIdentifier[]): Set<string | number> => {
    const addedIds = new Set<string | number>()
    devices.forEach(d => {
      if (d.serial) addedIds.add(d.serial)
      if (d.deviceUniqueId) addedIds.add(d.deviceUniqueId)
      if (d.id) addedIds.add(d.id)
      if (d.name) addedIds.add(d.name)
    })
    return addedIds
  }

  /** 收集单个设备的多重标识集合（含 displayKey 兜底） */
  const collectDeviceIdentifiers = (
    device: DeviceIdentifier,
    displayKey: string | number | undefined
  ): Set<string | number> => {
    const identifiers = new Set<string | number>()
    if (displayKey) identifiers.add(displayKey)
    if (device.name) identifiers.add(device.name)
    if (device.deviceUniqueId) identifiers.add(device.deviceUniqueId)
    if (device.serial) identifiers.add(device.serial)
    if (device.id) identifiers.add(device.id)
    return identifiers
  }

  /** 当前设备判定（displayKey / name / 标识集合多重匹配，两处展示逻辑共用） */
  const isCurrentDevice = (
    currentDeviceId: string | number | undefined,
    displayKey: string | number | undefined,
    deviceName: string,
    identifiers: Set<string | number>
  ): boolean => {
    return Boolean(
      currentDeviceId === displayKey ||
      currentDeviceId === deviceName ||
      (currentDeviceId && identifiers.has(currentDeviceId))
    )
  }

  /** 展示排序：当前设备 → 未添加 → 已添加（两处展示逻辑共用） */
  const sortDisplayList = (devices: DeviceDisplayItem[]): DeviceDisplayItem[] => {
    return [
      ...devices.filter(d => d.isCurrent),
      ...devices.filter(d => !d.isCurrent && !d.isAdded),
      ...devices.filter(d => !d.isCurrent && d.isAdded),
    ]
  }

  /**
   * 构建播放设备展示列表：map 转换 + 去重 + isAdded/isCurrent 标记。
   * 原实现中 scanResults 与 apiPlaybackDevices 两段重复逻辑合并于此。
   */
  const buildPlaybackDisplayList = (
    source: DeviceIdentifier[],
    addedIds: Set<string | number>,
    currentDeviceId: string | number | undefined
  ): DeviceDisplayItem[] => {
    const seen = new Set<string | number>()
    return source
      .filter(device => {
        const id = device.deviceUniqueId || device.id || device.name
        if (id === undefined) return false
        if (seen.has(id)) return false
        seen.add(id)
        return true
      })
      .map((device, index) => {
        const deviceId = device.deviceUniqueId || device.id || device.name
        const name = device.name || `${DISPLAY_LABELS.playbackNameFallback} ${index + 1}`
        const identifiers = collectDeviceIdentifiers(device, deviceId)

        return {
          displayKey: deviceId,
          deviceUniqueId: deviceId,
          name,
          model: device.model || DISPLAY_LABELS.unknownModel,
          sampleRate: device.sampleRate,
          channelIndex: device.channelIndex,
          index,
          isAdded: [...identifiers].some(id => addedIds.has(id)),
          isCurrent: isCurrentDevice(currentDeviceId, deviceId, name, identifiers),
        }
      })
  }

  /** 从已添加设备中按标识查找（编辑模式补齐当前设备用） */
  const findAddedByCurrentId = <T extends DeviceIdentifier>(
    added: T[],
    currentDeviceId: string | number
  ): T | undefined => {
    return added.find(d => d.deviceUniqueId === currentDeviceId || d.id === currentDeviceId || d.name === currentDeviceId)
  }

  /** 已添加设备兜底标识（deviceUniqueId → id → name → serial） */
  const resolveAddedDeviceId = (device: DeviceIdentifier): string | number | undefined => {
    return device.deviceUniqueId || device.id || device.name || device.serial
  }

  /** 获取已添加的播放设备（走 infrastructure：playbackPort.getAll，已展平为 Domain 数组） */
  const fetchAddedPlaybackDevices = async (): Promise<PlaybackDevice[]> => {
    try {
      const devices = await playbackPort.getAll(BATCH_LIST_PARAMS)
      addedPlaybackDevices.value = devices
      return devices
    } catch (error) {
      console.error('[useDeviceScanning] 获取已添加设备失败:', error)
      addedPlaybackDevices.value = []
      return []
    }
  }

  /** 获取已添加的测试设备（走 infrastructure：devicesPort.getAllFlat → Device → ScannedDevice 映射） */
  const fetchAddedTestDevices = async (): Promise<ScannedDevice[]> => {
    try {
      const devices = await devicesPort.getAllFlat(BATCH_LIST_PARAMS)
      // Device 有 serialNumber 而非 serial，映射为 ScannedDevice 统一标识字段
      const mapped: ScannedDevice[] = devices.map(d => ({
        id: d.id != null ? String(d.id) : undefined,
        name: d.name,
        model: d.model,
        system: d.system,
        systemVersion: d.systemVersion,
        serial: d.serialNumber,
        status: d.status,
        type: d.type,
      }))
      addedTestDevices.value = mapped
      return mapped
    } catch (error) {
      console.error('[useDeviceScanning] 获取已添加测试设备失败:', error)
      addedTestDevices.value = []
      return []
    }
  }

  /** 扫描播放设备（走 infrastructure：playbackPort.scan，已转 Domain） */
  const scanPlaybackDevices = async (): Promise<ScannedDevice[]> => {
    try {
      isScanning.value = true
      const scannedDevices = await playbackPort.scan()

      scanResults.value = scannedDevices
      apiPlaybackDevices.value = scannedDevices
      await fetchAddedPlaybackDevices()

      return scannedDevices
    } catch (error) {
      console.error('[useDeviceScanning] 扫描播放设备失败:', error)
      return []
    } finally {
      isScanning.value = false
    }
  }

  /** 扫描测试设备序列号（走 infrastructure：devicesPort.getAvailableSerials，已转 Domain） */
  const scanTestDeviceSerials = async (): Promise<ScannedDevice[]> => {
    try {
      isScanning.value = true
      availableSerials.value = await devicesPort.getAvailableSerials()

      await fetchAddedTestDevices()

      return availableSerials.value
    } catch (error) {
      console.error('[useDeviceScanning] 扫描测试设备失败:', error)
      return []
    } finally {
      isScanning.value = false
    }
  }

  /** 播放设备展示列表：扫描结果优先，扫描为空回退 api 列表，再补齐已添加设备 */
  const getPlaybackDevicesDisplay = (
    currentDeviceId?: string | number,
    isEditMode?: boolean
  ): DeviceDisplayItem[] => {
    const addedIds = collectAddedIdentifiers(addedPlaybackDevices.value)

    // 展示列表（本模块组装的视图对象，非 Domain 数据流）
    let devices: DeviceDisplayItem[] = []

    if (scanResults.value && scanResults.value.length > 0) {
      devices = buildPlaybackDisplayList(scanResults.value, addedIds, currentDeviceId)
    }

    if (devices.length === 0 && apiPlaybackDevices.value && apiPlaybackDevices.value.length > 0) {
      devices = buildPlaybackDisplayList(apiPlaybackDevices.value, addedIds, currentDeviceId)
    }

    // 编辑模式：当前设备不在列表中时补齐到首位
    if (isEditMode && currentDeviceId && !devices.find(d => d.displayKey === currentDeviceId)) {
      const currentDevice = findAddedByCurrentId(addedPlaybackDevices.value, currentDeviceId)
      if (currentDevice) {
        devices.unshift({
          displayKey: currentDeviceId,
          deviceUniqueId: currentDeviceId,
          // name 要求 string 类型，currentDeviceId 可能为 number，需显式转换
          name: currentDevice.name || String(currentDeviceId),
          model: currentDevice.model || DISPLAY_LABELS.unknownModel,
          sampleRate: currentDevice.sampleRate,
          channelIndex: currentDevice.channelIndex,
          index: -1,
          isAdded: true,
          isCurrent: true,
        })
      }
    }

    // 补齐扫描结果中缺失的已添加设备
    const displayedDeviceIds = new Set(devices.map(d => d.displayKey))
    addedPlaybackDevices.value
      .filter(d => !displayedDeviceIds.has(resolveAddedDeviceId(d)))
      .forEach(d => {
        const deviceId = resolveAddedDeviceId(d)
        devices.push({
          displayKey: deviceId,
          deviceUniqueId: deviceId,
          name: d.name || DISPLAY_LABELS.unknownDevice,
          model: d.model || DISPLAY_LABELS.unknownModel,
          sampleRate: d.sampleRate,
          channelIndex: d.channelIndex,
          index: devices.length,
          isAdded: true,
          isCurrent: currentDeviceId === deviceId,
        })
      })

    return sortDisplayList(devices)
  }

  /** 测试设备展示列表：扫描出的序列号条目 + 编辑模式补齐当前设备 */
  const getTestDevicesDisplay = (
    currentDeviceId?: string | number,
    isEditMode?: boolean
  ): DeviceDisplayItem[] => {
    const addedIds = collectAddedIdentifiers(addedTestDevices.value)

    // 展示列表（本模块组装的视图对象，非 Domain 数据流）
    let devices: DeviceDisplayItem[] = []

    if (availableSerials.value && availableSerials.value.length > 0) {
      const seen = new Set<string | number>()
      const uniqueDevices = availableSerials.value.filter(device => {
        const serial = device.serial || device.deviceUniqueId || device.id || device.name
        if (serial === undefined) return false
        if (seen.has(serial)) return false
        seen.add(serial)
        return true
      })

      devices = uniqueDevices.map((device, index) => {
        const serial = device.serial || device.deviceUniqueId || device.id || device.name
        const deviceId = device.deviceUniqueId || device.id || device.name
        const identifiers = collectDeviceIdentifiers(device, serial)

        return {
          displayKey: serial,
          serial,
          deviceUniqueId: deviceId,
          name: device.name || `${DISPLAY_LABELS.testDeviceNameFallback} ${index + 1}`,
          model: device.model || DISPLAY_LABELS.unknownModel,
          system: device.system,
          systemVersion: device.systemVersion,
          index,
          isAdded: [...identifiers].some(id => addedIds.has(id)),
          isCurrent: currentDeviceId === serial || currentDeviceId === deviceId,
        }
      })
    }

    // 编辑模式：当前设备不在列表中时补齐到首位
    if (isEditMode && currentDeviceId && !devices.find(d => d.displayKey === currentDeviceId)) {
      const currentDevice = findAddedByCurrentId(addedTestDevices.value, currentDeviceId)
      if (currentDevice) {
        devices.unshift({
          displayKey: currentDeviceId,
          serial: currentDeviceId,
          deviceUniqueId: currentDevice.deviceUniqueId || currentDevice.id || currentDevice.name,
          // name 要求 string 类型，currentDeviceId 可能为 number，需显式转换
          name: currentDevice.name || String(currentDeviceId),
          model: currentDevice.model || DISPLAY_LABELS.unknownModel,
          system: currentDevice.system,
          systemVersion: currentDevice.systemVersion || DISPLAY_LABELS.unknownVersion,
          index: -1,
          isAdded: true,
          isCurrent: true,
        })
      }
    }

    return sortDisplayList(devices)
  }

  return {
    isScanning,
    scanResults,
    availableSerials,
    addedPlaybackDevices,
    addedTestDevices,
    apiPlaybackDevices,
    fetchAddedPlaybackDevices,
    fetchAddedTestDevices,
    scanPlaybackDevices,
    scanTestDeviceSerials,
    getPlaybackDevicesDisplay,
    getTestDevicesDisplay,
  }
}
