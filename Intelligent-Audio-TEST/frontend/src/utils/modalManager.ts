/**
 * Modal Manager 适配器
 * 
 * 由于多个逻辑文件引用了 utils/modalManager，但实际实现在 composables/useModal 中，
 * 此文件作为中转层，确保导入路径正确。
 */

import { getModalManager as getOriginalManager } from '../composables/modal/useModal';

export const getModalManager = getOriginalManager;

export default getModalManager;
