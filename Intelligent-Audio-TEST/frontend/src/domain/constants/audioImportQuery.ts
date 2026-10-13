/**
 * 音频导入页跨页跳转 query 参数 —— domain/constants
 *
 * 生产者：composables/testCase/useTestCaseCard.ts openImportTestCaseModal
 *   （E2E/API 测试页「导入用例」入口，TestFlow.vue @open-import-modal）
 * 消费者：views/AudioImport/AudioImport.vue onMounted（INT-275，对齐 V9.7.10 基线）
 *
 * 两端必须引用同一常量，防止再次出现参数名漂移断链。
 */

/** query 参数名：'1' 时落点页自动打开上传音频弹窗 */
export const AUDIO_IMPORT_QUERY = {
  autoOpen: 'autoOpen',
  createTestCase: 'createTestCase',
  algorithmType: 'algorithmType'
} as const;

/** autoOpen 的"真"取值（字符串 '1'，query 序列化后仅存字符串） */
export const AUDIO_IMPORT_AUTO_OPEN_VALUE = '1';
