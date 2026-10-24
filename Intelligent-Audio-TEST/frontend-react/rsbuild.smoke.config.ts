// 临时冒烟配置（INT-1702 集成冒烟用，不提交，用毕即删）
// /api 代理指向 docker 真实库栈 15000（wiring/react 集成冒烟），端口 5395。
import base from './rsbuild.config'

export default (env: any) => {
  const cfg: any = typeof base === 'function' ? (base as any)(env) : base
  return {
    ...cfg,
    server: {
      ...cfg.server,
      port: 5395,
      strictPort: true,
      proxy: {
        '/api': { target: 'http://127.0.0.1:15000', changeOrigin: true },
        '/ws': { target: 'http://127.0.0.1:15000', changeOrigin: true, ws: true },
        '/socket.io': { target: 'http://127.0.0.1:15000', changeOrigin: true, ws: true },
      },
    },
  }
}
