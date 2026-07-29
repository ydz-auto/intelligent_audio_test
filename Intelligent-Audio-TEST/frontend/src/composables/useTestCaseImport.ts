import { testcasesApi } from '../utils/api'

/**
 * 测试用例导入 composable。
 *
 * 接收 testCaseStore 实例作为参数，通过 fetchTestCases 在导入完成后刷新本地
 * 用例列表，通过 handleError 统一处理错误。对外方法名与返回值与原
 * testCaseStore 中的实现保持一致。
 */
export function useTestCaseImport(store: {
  error: import('vue').Ref<string | null>
  fetchTestCases: (params?: Record<string, any>) => Promise<void>
  handleError: (err: any, errorMessage: string) => boolean
}) {
  const { error, fetchTestCases, handleError } = store

  const formatImportErrorsMessage = (title: string, errors: unknown) => {
    const list = Array.isArray(errors) ? errors.map(String).filter(Boolean) : []
    if (list.length === 0) return title
    const maxLines = 50
    const shown = list.slice(0, maxLines).join('\n')
    const more = list.length > maxLines ? `\n...（共${list.length}条）` : ''
    return `${title}\n${shown}${more}`
  }

  const importTestCases = async (formData: FormData) => {
    try {
      error.value = null
      const result: any = await testcasesApi.importCases(formData)

      const importedCount = Number(result?.importedCount ?? result?.imported_count ?? 0)
      const updatedCount = Number(result?.updatedCount ?? result?.updated_count ?? 0)
      const errors = Array.isArray(result?.errors) ? result.errors : []

      if (errors.length > 0) {
        const title = (importedCount > 0 || updatedCount > 0)
          ? `导入完成，但有 ${errors.length} 个失败（成功导入 ${importedCount}，更新 ${updatedCount}）`
          : `导入失败：${errors.length} 个失败`
        error.value = title
        alert(formatImportErrorsMessage(title, errors))
      }

      if (importedCount > 0 || updatedCount > 0) {
        await fetchTestCases()
      }

      return importedCount > 0 || updatedCount > 0 || errors.length === 0
    } catch (err: any) {
      return handleError(err, '导入测试用例失败')
    }
  }

  return {
    importTestCases
  }
}
