/**
 * Modal 控制类型 —— Application 层
 *
 * 定义弹窗注册、打开、保存等契约类型。
 */

import type { MODAL_TYPES } from './constants'

/** Modal 类型（派生自 MODAL_TYPES 常量键值，保证与常量一致） */
export type ModalType = typeof MODAL_TYPES[keyof typeof MODAL_TYPES]

/** Modal 保存模式 */
export type ModalSaveMode = 'create' | 'edit' | 'import' | 'export' | 'case' | 'group'

/** Modal 保存数据 */
export interface ModalSaveData<T = any> {
  mode: ModalSaveMode
  entity: string
  isEdit?: boolean
  id?: string | number
  data: T
}

/** Modal 保存结果 */
export interface ModalSaveResult<T = any> {
  success: boolean
  data?: T
  message?: string
  needRefresh?: boolean
}

/** Modal 配置 */
export interface ModalConfig {
  component: any
  title?: string
  width?: string
  props?: Record<string, any>
  options?: Record<string, any>
  defaultConfig?: Record<string, any>
}

/** 活跃 Modal 实例 */
export interface ActiveModal extends ModalConfig {
  id: string
  visible: boolean
  type: string
  confirmed?: boolean
  processing?: boolean
}
