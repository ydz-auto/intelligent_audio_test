/**
 * 「需要登录」受限项交互（UX设计-VUE 总表 §2.2）
 *
 * 未登录点击受限导航项（如工作台）→ 弹 Dialog + 5 秒倒计时 → 跳 /login?redirect=。
 * 状态由本 composable 持有（布局组件共享），RequireLoginDialog.vue 渲染。
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const visible = ref(false)
const countdown = ref(5)
let timer: ReturnType<typeof setInterval> | null = null
let targetPath = '/'

export function useRequireLogin() {
  const router = useRouter()
  const route = useRoute()

  function clearTimer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function open(path?: string) {
    targetPath = path || route.fullPath
    countdown.value = 5
    visible.value = true
    clearTimer()
    timer = setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0) {
        clearTimer()
        goLogin()
      }
    }, 1000)
  }

  function goLogin() {
    clearTimer()
    visible.value = false
    router.push({ name: 'login', query: { redirect: targetPath } })
  }

  function close() {
    clearTimer()
    visible.value = false
  }

  return {
    visible,
    countdown,
    open,
    goLogin,
    close,
  }
}
