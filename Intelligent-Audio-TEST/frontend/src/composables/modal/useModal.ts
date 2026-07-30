import { inject, provide, ref, shallowRef, type Component, type InjectionKey, type Ref } from 'vue'
import type { ModalConfig, ModalType } from '../../shared/types'
import { MODAL_TYPES } from '../../shared/types'

export const MODAL_MANAGER_KEY: InjectionKey<ModalManager> = Symbol('modalManager')
export const MODAL_INJECTION_KEY = MODAL_MANAGER_KEY

interface ModalInstance {
  id: string
  type: ModalType
  component: Component
  props: Record<string, any>
  resolve: (value: any) => void
  reject: (reason?: any) => void
}

export interface ModalManager {
  registerModal: (type: ModalType, config: { component: Component; defaultConfig?: Record<string, any> }) => void
  open: <T = any>(type: ModalType, props?: Record<string, any>) => Promise<T>
  close: (id?: string) => void
  closeAll: () => void
  getActiveModals: () => ModalInstance[]
  updateModalProps: (id: string, props: Record<string, any>) => void
}

let modalCounter = 0

// 使用全局变量确保registeredModals单例
const registeredModalsKey = '__registered_modals__'

declare global {
  interface Window {
    [registeredModalsKey]?: Map<ModalType, { component: Component; defaultConfig?: Record<string, any> }>
  }
}

// 获取全局registeredModals实例
const getRegisteredModals = (): Map<ModalType, { component: Component; defaultConfig?: Record<string, any> }> => {
  if (!window[registeredModalsKey]) {
    window[registeredModalsKey] = new Map()
  }
  return window[registeredModalsKey]!
}

// 使用全局变量确保单例，防止模块多次导入时创建多个实例
const globalKey = '__modal_manager_instance__'

// 扩展Window接口，添加全局模态框管理器实例
declare global {
  interface Window {
    [globalKey]?: ModalManager
  }
}

// 模块作用域的实例变量
let managerInstance: ModalManager | null = null

const getModalManager = (): ModalManager => {
  // 优先使用全局实例，这是解决HMR问题的关键
  if (window[globalKey]) {
    console.log(`[getModalManager] Returning existing global instance`)
    return window[globalKey]!
  }
  
  // 其次检查模块作用域中的实例
  if (managerInstance) {
    console.log(`[getModalManager] Returning existing module instance`)
    return managerInstance
  }
  
  console.log(`[getModalManager] Creating new modal manager instance`)
  
  // 获取全局registeredModals实例
  const registeredModals = getRegisteredModals()
  const activeModals = shallowRef<ModalInstance[]>([])

  const registerModal = (type: ModalType, config: { component: Component; defaultConfig?: Record<string, any> }) => {
    registeredModals.set(type, config)
    console.log(`[ModalManager] Registered modal type: ${type}`)
    console.log(`[ModalManager] Current registered modals count: ${registeredModals.size}`)
  }

  const open = async <T = any>(type: ModalType, props: Record<string, any> = {}): Promise<T> => {
    console.log(`[ModalManager] Opening modal type: ${type} with props:`, props)
    
    const modalConfig = registeredModals.get(type)
    if (!modalConfig) {
      console.warn(`[ModalManager] Modal type "${type}" not registered`)
      console.log(`[ModalManager] Current registered modals:`, Array.from(registeredModals.keys()))
      return Promise.reject(new Error(`Modal type "${type}" not registered`))
    }

    const id = `modal-${++modalCounter}`
    const { component, defaultConfig } = modalConfig

    const mergedProps = { ...defaultConfig, ...props }
    console.log(`[ModalManager] Merged props for modal ${id}:`, mergedProps)

    let resolveCallback: (value: T) => void = () => {}
    let rejectCallback: (reason?: any) => void = () => {}

    const modalInstance: ModalInstance = {
      id,
      type,
      component,
      props: mergedProps,
      resolve: (value) => {
        console.log(`[ModalManager] Resolving modal ${id} with value:`, value)
        resolveCallback(value)
        close(id)
      },
      reject: (reason) => {
        console.log(`[ModalManager] Rejecting modal ${id} with reason:`, reason)
        rejectCallback(reason)
        close(id)
      }
    }

    console.log(`[ModalManager] Creating modal instance ${id}:`, modalInstance)
    
    // 替换整个数组以触发shallowRef更新
    activeModals.value = [...activeModals.value, modalInstance]
    console.log(`[ModalManager] Active modals after adding ${id}:`, activeModals.value.length)
    console.log(`[ModalManager] Active modals array:`, activeModals.value)

    return new Promise<T>((resolve, reject) => {
      resolveCallback = resolve
      rejectCallback = reject
    })
  }

  const openModal = (name: ModalType, data?: any, options?: any): string => {
    open(name, data);
    return `modal-${modalCounter}`;
  }

  const close = (id?: string) => {
    console.log('[ModalManager] close() called')
    console.log('[ModalManager] Stack trace:', new Error().stack)
    console.log('[ModalManager] id parameter:', id)
    console.log('[ModalManager] Current activeModals:', activeModals.value.map(m => m.id))
    if (id) {
      console.log(`[ModalManager] Closing modal with id: ${id}`)
      activeModals.value = activeModals.value.filter(m => m.id !== id)
    } else if (activeModals.value.length > 0) {
      const lastModal = activeModals.value[activeModals.value.length - 1]
      console.log(`[ModalManager] Closing last modal with id: ${lastModal?.id}`)
      activeModals.value = activeModals.value.slice(0, -1)
    }
    console.log(`[ModalManager] Active modals after close:`, activeModals.value.length)
  }

  const closeAll = () => {
    console.log(`[ModalManager] Closing all modals (${activeModals.value.length} active)`)
    activeModals.value = []
    console.log(`[ModalManager] All modals closed, active count:`, activeModals.value.length)
  }

  const getActiveModals = () => {
    console.log(`[ModalManager] getActiveModals() called, returning:`, activeModals.value)
    return activeModals.value
  }

  const updateModalProps = (id: string, props: Record<string, any>) => {
    console.log(`[ModalManager] Updating props for modal ${id}:`, props)
    const modal = activeModals.value.find(m => m.id === id)
    if (modal) {
      modal.props = { ...modal.props, ...props }
      console.log(`[ModalManager] Updated props for modal ${id}`)
    } else {
      console.warn(`[ModalManager] Modal ${id} not found for props update`)
    }
  }

  const manager = {
    registerModal,
    open,
    close,
    closeAll,
    getActiveModals,
    updateModalProps
  }
  
  // 存储实例到模块作用域和全局对象
  managerInstance = manager
  window[globalKey] = manager
  
  console.log(`[getModalManager] Created and stored new modal manager instance`)
  return manager
}

const provideModal = () => {
  if (!managerInstance) {
    managerInstance = getModalManager()
  }
  provide(MODAL_MANAGER_KEY, managerInstance)
  return managerInstance
}

const useModal = () => {
  const manager = inject(MODAL_MANAGER_KEY)
  if (!manager) {
    throw new Error('[useModal] Modal manager not provided. Please call provideModal() first.')
  }
  return manager
}

const useModalControl = () => {
  // 直接使用getModalManager()获取全局单例实例，确保所有页面使用同一个实例
  const modal = getModalManager()
  return {
    open: modal.open.bind(modal),
    close: modal.close.bind(modal),
    closeAll: modal.closeAll.bind(modal),
    getActiveModals: modal.getActiveModals.bind(modal),
    updateModalProps: modal.updateModalProps.bind(modal),
    registerModal: modal.registerModal.bind(modal)
  }
}

export {
  getModalManager,
  provideModal,
  useModal,
  useModalControl,
  MODAL_TYPES
}
