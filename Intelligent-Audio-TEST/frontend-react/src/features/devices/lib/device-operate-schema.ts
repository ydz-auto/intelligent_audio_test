/**
 * 设备操作参数 schema（16_设备域.md §3.4.1：install/uninstall 小弹窗，AGENTS §3.7 RHF+zod）。
 * 安装应用需 file_path/package_name；卸载应用仅需 package_name（P3-31 补口）。
 */
import { z } from 'zod'

export const installAppSchema = z.object({
  filePath: z.string().min(1, '请填写应用安装包路径'),
  packageName: z.string().min(1, '请填写应用包名'),
})

export type InstallAppForm = z.infer<typeof installAppSchema>

export const uninstallAppSchema = z.object({
  packageName: z.string().min(1, '请填写应用包名'),
})

export type UninstallAppForm = z.infer<typeof uninstallAppSchema>
