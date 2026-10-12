import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './utils/logger'
import './assets/styles/index.css'
import App from './App.vue'
import router from './router'
import { runAuthModeSelfCheck } from './infrastructure/selfCheck/authModeSelfCheck'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.mount('#app')

// INT-180：认证模式启动自检（提示型，不阻塞启动与登录）
runAuthModeSelfCheck()
