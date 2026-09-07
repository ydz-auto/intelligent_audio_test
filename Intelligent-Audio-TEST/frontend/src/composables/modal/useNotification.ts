import { ref, readonly } from 'vue'

/** 全局通知实例接口：由 provideNotification 注入的真实组件实例（须提供 show 方法） */
export interface NotificationInstance {
  show: (message: string, type?: string, details?: string) => void
}

// 显式声明为 NotificationInstance | null，避免 ref(null) 被推断为 Ref<null> 导致属性访问收窄为 never
const notificationInstance = ref<NotificationInstance | null>(null)

export function provideNotification(instance: NotificationInstance) {
  notificationInstance.value = instance
}

export function useNotification() {
  return {
    show: (message: string, type: string = 'error', details: string = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, type, details)
      }
    },
    error: (message: string, details: string = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'error', details)
      }
    },
    warning: (message: string, details: string = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'warning', details)
      }
    },
    success: (message: string, details: string = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'success', details)
      }
    },
    info: (message: string, details: string = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'info', details)
      }
    }
  }
}
