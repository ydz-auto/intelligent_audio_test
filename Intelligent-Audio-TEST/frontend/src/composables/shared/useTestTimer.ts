import { ref, onUnmounted, type Ref } from 'vue'

/**
 * E2E 本地计时器：用于在任务执行期间显示已用时长
 * 仅在 e2e 模式使用；api 模式不需要本地计时器（进度由 socket 推送）
 */
export function useTestTimer(elapsedTimeRef?: Ref<string>) {
  const taskStartTime = ref<Date | null>(null)
  const taskElapsedTimeDisplay = ref('00:00:00')
  let timeUpdateTimer: ReturnType<typeof setInterval> | null = null

  const stopTimeUpdateTimer = () => {
    if (timeUpdateTimer) {
      clearInterval(timeUpdateTimer)
      timeUpdateTimer = null
    }
  }

  const startTimeUpdateTimer = () => {
    stopTimeUpdateTimer()
    timeUpdateTimer = setInterval(() => {
      if (!taskStartTime.value) return
      const now = new Date()
      const elapsedSeconds = Math.floor((now.getTime() - taskStartTime.value.getTime()) / 1000)
      const hoursStr = String(Math.floor(elapsedSeconds / 3600)).padStart(2, '0')
      const minutesStr = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, '0')
      const secondsStr = String(elapsedSeconds % 60).padStart(2, '0')
      taskElapsedTimeDisplay.value = `${hoursStr}:${minutesStr}:${secondsStr}`
      // 同步更新外部传入的 elapsedTime
      if (elapsedTimeRef) {
        if (elapsedSeconds < 60) {
          elapsedTimeRef.value = `${elapsedSeconds}秒`
        } else if (elapsedSeconds < 3600) {
          const m = Math.floor(elapsedSeconds / 60)
          const s = elapsedSeconds % 60
          elapsedTimeRef.value = s > 0 ? `${m}分钟${s}秒` : `${m}分钟`
        } else {
          const h = Math.floor(elapsedSeconds / 3600)
          const m = Math.floor((elapsedSeconds % 3600) / 60)
          elapsedTimeRef.value = m > 0 ? `${h}小时${m}分钟` : `${h}小时`
        }
      }
    }, 1000)
  }

  const setStartTime = (startTime?: string | Date | null) => {
    taskStartTime.value = startTime ? new Date(startTime) : new Date()
  }

  onUnmounted(() => {
    stopTimeUpdateTimer()
  })

  return {
    taskStartTime,
    taskElapsedTimeDisplay,
    startTimeUpdateTimer,
    stopTimeUpdateTimer,
    setStartTime,
  }
}
