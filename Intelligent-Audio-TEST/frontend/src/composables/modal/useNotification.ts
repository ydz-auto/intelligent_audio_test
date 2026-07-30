import { ref, readonly } from 'vue'

const notificationInstance = ref(null)

export function provideNotification(instance) {
  notificationInstance.value = instance
}

export function useNotification() {
  return {
    show: (message, type = 'error', details = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, type, details)
      }
    },
    error: (message, details = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'error', details)
      }
    },
    warning: (message, details = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'warning', details)
      }
    },
    success: (message, details = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'success', details)
      }
    },
    info: (message, details = '') => {
      if (notificationInstance.value) {
        notificationInstance.value.show(message, 'info', details)
      }
    }
  }
}
