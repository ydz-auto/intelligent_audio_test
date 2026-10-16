/**
 * 人工复核覆盖提醒（INT-340）
 *
 * 对存在人工复核结果的任务发起重新执行/重新评估时，硬确认提醒
 * 「人工复核填写的结果将被覆盖」——不做静默覆盖（设计文档 §4）。
 *
 * 选择性（INT-302）语义：仅当重跑覆盖范围内存在复核结果才提醒；
 * 未选中用例的复核结果不受影响，不弹提醒。
 *
 * 详情读取失败时放行（降级不阻断主流程，覆盖提醒为辅助确认）。
 */
import { tasksPort } from './tasksPort';
import { MODAL_TYPES } from '../modal/useModal';

/** 重执行/重评估范围选择（与 useTaskControl.ReexecuteSelection 结构对齐） */
export interface ReviewOverwriteSelection {
  mode?: 'selected' | 'failed_only' | 'all'
  caseIds?: (string | number)[]
}

/**
 * 检查并确认覆盖提醒。
 *
 * @param modalControl 模态窗控制器（调用方注入，避免循环依赖）
 * @param taskId 任务 ID
 * @param selection 重执行/重评估范围（selected 时仅按选中用例判定）
 * @param actionText 动作文案（「重新执行」/「重新评估」）
 * @returns true=放行（无复核结果或用户确认）；false=用户取消
 */
export async function confirmReviewOverwrite(
  modalControl: any,
  taskId: string | number,
  selection: ReviewOverwriteSelection | undefined,
  actionText: string,
): Promise<boolean> {
  try {
    const detail = await tasksPort.getOne(taskId);
    const reviewedCount = detail.reviewCount ?? 0;
    if (reviewedCount <= 0) return true;

    // 选择性：仅当选中用例命中复核结果才提醒
    let affected = reviewedCount;
    if (selection?.mode === 'selected' && selection.caseIds?.length) {
      const caseIds = new Set(selection.caseIds.map(String));
      const selectedReviewed = (detail.cases ?? [])
        .filter(c => c.reviewed && caseIds.has(String(c.caseId))).length;
      if (selectedReviewed <= 0) return true;
      affected = selectedReviewed;
    }

    try {
      const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '覆盖提醒',
        content: `该任务存在 ${affected} 条人工复核结果，${actionText}后人工复核填写的结果将被覆盖，是否继续？`,
        confirmText: '确认覆盖',
        cancelText: '取消',
        danger: true,
      });
      return confirmed?.confirmed === true;
    } catch {
      // 关闭/ESC 视为取消
      return false;
    }
  } catch (error) {
    console.error('Failed to check review overwrite:', error);
    return true;
  }
}
