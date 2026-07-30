import { ref, type Ref } from 'vue';

/**
 * 可复用的文件夹音频批量勾选逻辑。
 *
 * 用法：
 *   const { toggleFolderSelection, isFolderAllSelected, isFolderPartialSelected } =
 *     useFolderSelection(selectedAudios);
 *
 * 说明：
 *   - selectedAudios 是外部维护的已选 ID 数组（ref），本 composable 只读/写它
 *   - 递归收集 folder.files 与 folder.folders 的所有文件 ID
 *   - 全选/半选状态基于 selectedAudios 实时计算
 */
export function useFolderSelection(selectedAudios: Ref<(string | number)[]>) {
  /**
   * 递归收集文件夹（含子文件夹）下所有文件 ID。
   * 仅收集当前已加载到前端的文件；未懒加载的子文件夹需先展开加载。
   */
  function collectFolderFileIds(folder: any): (string | number)[] {
    const ids: (string | number)[] = [];
    if (Array.isArray(folder?.files)) {
      for (const f of folder.files) {
        if (f?.id !== undefined && f?.id !== null) ids.push(f.id);
      }
    }
    if (Array.isArray(folder?.folders)) {
      for (const sub of folder.folders) {
        ids.push(...collectFolderFileIds(sub));
      }
    }
    return ids;
  }

  /**
   * 按文件夹批量勾选：切换该文件夹下所有文件的选择状态。
   * 若文件夹下有未选中的文件，则全部选中；否则全部取消选中。
   */
  function toggleFolderSelection(folder: any) {
    const fileIds = collectFolderFileIds(folder);
    if (fileIds.length === 0) return;
    const selectedSet = new Set(selectedAudios.value);
    const allSelected = fileIds.every((id: string | number) => selectedSet.has(id));
    if (allSelected) {
      const removeSet = new Set(fileIds);
      selectedAudios.value = selectedAudios.value.filter(id => !removeSet.has(id));
    } else {
      const newSelected = [...selectedAudios.value];
      for (const id of fileIds) {
        if (!selectedSet.has(id)) {
          newSelected.push(id);
          selectedSet.add(id);
        }
      }
      selectedAudios.value = newSelected;
    }
  }

  /** 该文件夹下所有文件是否全部选中 */
  function isFolderAllSelected(folder: any): boolean {
    const ids = collectFolderFileIds(folder);
    if (ids.length === 0) return false;
    const selectedSet = new Set(selectedAudios.value);
    return ids.every((id: string | number) => selectedSet.has(id));
  }

  /** 该文件夹下是否存在部分选中（非全选且至少一个选中） */
  function isFolderPartialSelected(folder: any): boolean {
    const ids = collectFolderFileIds(folder);
    if (ids.length === 0) return false;
    const selectedSet = new Set(selectedAudios.value);
    return ids.some((id: string | number) => selectedSet.has(id))
      && !ids.every((id: string | number) => selectedSet.has(id));
  }

  return {
    collectFolderFileIds,
    toggleFolderSelection,
    isFolderAllSelected,
    isFolderPartialSelected,
  };
}
