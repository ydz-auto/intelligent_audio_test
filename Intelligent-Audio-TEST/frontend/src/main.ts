import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './utils/logger'
import './assets/styles/index.css'
import App from './App.vue'
import router from './router'
import { runAuthModeSelfCheck } from './infrastructure/selfCheck/authModeSelfCheck'
import { useThemeStore } from './store/themeStore'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 主题初始化：渲染前挂 .dark（localStorage iatp:theme:v1），避免首帧闪白/闪暗
useThemeStore(pinia).init()

app.mount('#app')

// INT-180：认证模式启动自检（提示型，不阻塞启动与登录）
runAuthModeSelfCheck()
