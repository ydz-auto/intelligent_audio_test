/**
 * useE2eView —— 任务耗时计时器（timer）
 *
 * 本地已用时长计时：驱动 HH:mm:ss 展示，并同步进度面板的中文可读已用时长。
 */
import type { Ref } from 'vue'

/** 将已用秒数格式化为中文可读文本 */
export function formatElapsedSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return s > 0 ? `${m}分钟${s}秒` : `${m}分钟`
  }
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
}

/** 计时器依赖 */
export interface E2eViewTimerDeps {
  taskStartTime: Ref<Date | null>
  taskElapsedTimeDisplay: Ref<string>
  elapsedTime: Ref<string>
}

/** 创建任务耗时计时器 */
export function createE2eViewTimer(deps: E2eViewTimerDeps) {
  const { taskStartTime, taskElapsedTimeDisplay, elapsedTime } = deps
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
      const elapsedSeconds = Math.floor((new Date().getTime() - taskStartTime.value.getTime()) / 1000)
      const hoursStr = String(Math.floor(elapsedSeconds / 3600)).padStart(2, '0')
      const minutesStr = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, '0')
      const secondsStr = String(elapsedSeconds % 60).padStart(2, '0')
      taskElapsedTimeDisplay.value = `${hoursStr}:${minutesStr}:${secondsStr}`
      // 同步更新 elapsedTime，让组件显示已用时长
      elapsedTime.value = formatElapsedSeconds(elapsedSeconds)
    }, 1000)
  }

  return {
    stopTimeUpdateTimer,
    startTimeUpdateTimer
  }
}