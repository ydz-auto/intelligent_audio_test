/**
 * DataTransferPort —— 任务数据导入导出的应用层出口
 *
 * Infrastructure 的 dataTransferApi / transferChannel 单点收敛于此，
 * Presentation/Application 只许 import 本 Port（与 tasksPort 一致）。
 */
import { dataTransferApi } from '../../infrastructure/api/dataTransferApi'
import { onImportProgress } from '../../infrastructure/socket/transferChannel'

export const dataTransferPort = {
  exportTasks: dataTransferApi.exportTasks,
  previewImport: dataTransferApi.previewImport,
  executeImport: dataTransferApi.executeImport,
  getImportProgress: dataTransferApi.getImportProgress,
  onImportProgress,
}
