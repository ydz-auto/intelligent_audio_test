import { ref, type Ref } from 'vue';
import type { TestCase } from '../../shared/types';
import { normalizeTestCaseConfig } from '../../utils/utils';
import { useTestCaseStore } from '../../store/testCaseStore';

/**
 * 测试用例音频预览 composable。
 *
 * 职责：
 * - 检测用例是否包含 API / E2E 音频配置
 * - 打开音频类型选择模态框（当用例同时具有 API 和 E2E 配置时）
 * - 打开音频预览模态框 / 音频播放器
 * - 关闭各模态框并清理状态
 * - 处理用例卡片预览动作入口（handleAction 的 preview 分支）
 */
export function useTestCaseAudioPreview(
  onEditTestCase: (testCase: TestCase) => void,
  onDeleteTestCase: (testCase: TestCase) => void,
  selectedCases: Ref<(string | number)[]>
) {
  const showAudioPlayer = ref(false);
  const currentTestCaseCaseId = ref<string | number | null>(null);
  const showAudioTypeModal = ref(false);
  const currentTestCase = ref<TestCase | null>(null);
  const currentHasAPIConfig = ref(false);
  const currentHasE2eConfig = ref(false);
  const selectedAudioType = ref('');
  const showAudioPreviewModal = ref(false);
  const previewPlaybackMode = ref<'frontend' | 'backend'>('frontend');
  // 兼容原组件中 handleGlobalKeyDown 引用的状态
  const showPlaybackDeviceModal = ref(false);

  /**
   * 检查测试用例的音频配置类型：
   * 兼容 rounds-based 与 legacy flat 格式，按记录级 test_type 判断 API/E2E。
   */
  const checkTestCaseConfig = (testCase: TestCase) => {
    const normalizedConfig = normalizeTestCaseConfig(testCase.config || {});
    // Rounds-based format: collect all audios from all rounds
    const rounds = normalizedConfig.rounds || [];
    const allAudios: any[] = [];
    rounds.forEach((round: any) => {
      if (Array.isArray(round.audios)) {
        allAudios.push(...round.audios);
      }
    });

    // In dual-record architecture, test_type is at the record level
    // 后端列表接口返回字段名为 type，兼容 test_type / testType
    const recordTestType = ((testCase as any).test_type || (testCase as any).testType || (testCase as any).type || 'api').toLowerCase();
    const isApi = recordTestType === 'api';
    const isE2e = recordTestType === 'e2e' || recordTestType === 'e2e_test';

    const hasAPIConfig = isApi && allAudios.length > 0;
    const hasE2eConfig = isE2e && allAudios.length > 0;

    const apiAudioId = hasAPIConfig ? allAudios[0]?.audioId : null;
    const e2eAudioIds = hasE2eConfig ? allAudios.map((a: any) => a.audioId) : [];

    console.log('检查测试用例配置:', { hasAPIConfig, hasE2eConfig, apiAudioId, e2eAudioIds });
    return { hasAPIConfig, hasE2eConfig, apiAudioId, e2eAudioIds };
  };

  const handleCloseAudioTypeModal = () => {
    showAudioTypeModal.value = false;
    currentTestCase.value = null;
  };

  const selectAudioType = (audioType: string) => {
    selectedAudioType.value = audioType;
    showAudioTypeModal.value = false;

    if (audioType === 'api') {
      showAudioPlayer.value = true;
    } else if (audioType === 'e2e') {
      showAudioPreviewModal.value = true;
    }
  };

  const handleAudioPreviewModalClose = () => {
    showAudioPreviewModal.value = false;
  };

  const handleAudioPreviewConfirm = (previewData: any) => {
    showAudioPreviewModal.value = false;
    previewPlaybackMode.value = previewData.playbackMode || 'frontend';
    showAudioPlayer.value = true;
  };

  const handleAudioPlayerClose = () => {
    showAudioPlayer.value = false;
    currentTestCaseCaseId.value = null;
    selectedAudioType.value = '';
    previewPlaybackMode.value = 'frontend';
  };

  /**
   * 处理用例卡片操作事件（预览/复制/编辑/删除）。
   * 仅 preview 分支涉及音频预览流程；其余透传给父组件或调用 store。
   */
  const handleAction = async (actionEvent: { action: { id: string }; testCase: TestCase }, _group: string) => {
    const testCase = actionEvent.testCase;
    console.log('[TestCaseListContainer] 处理测试用例操作:', { action: actionEvent.action.id, testCase: testCase.name });

    switch (actionEvent.action.id) {
      case 'preview': {
        const config = testCase.config || {};
        // 兼容新格式 config.rounds[].audios 与旧格式 config.audios
        const rounds = config.rounds || [];
        const hasRoundsAudios = rounds.some((r: any) => Array.isArray(r.audios) && r.audios.length > 0);
        const hasAudioConfig = hasRoundsAudios || ((config as any).audios && (config as any).audios.length > 0);

        if (hasAudioConfig) {
          try {
            const { hasAPIConfig, hasE2eConfig } = checkTestCaseConfig(testCase);
            currentTestCase.value = testCase;
            currentTestCaseCaseId.value = testCase.id;
            currentHasAPIConfig.value = hasAPIConfig;
            currentHasE2eConfig.value = hasE2eConfig;

            if (hasAPIConfig && hasE2eConfig) {
              showAudioTypeModal.value = true;
            } else if (hasAPIConfig) {
              selectedAudioType.value = 'api';
              showAudioPlayer.value = true;
            } else if (hasE2eConfig) {
              selectedAudioType.value = 'e2e';
              showAudioPreviewModal.value = true;
            }
          } catch (error: any) {
            console.error('音频试听失败:', error);
          }
        }
        break;
      }
      case 'copy':
        try {
          const store = useTestCaseStore();
          await store.copyTestCase(testCase.id);
          selectedCases.value = [];
        } catch (error: any) {
          console.error('复制测试用例失败:', error);
        }
        break;
      case 'edit':
        onEditTestCase(testCase);
        break;
      case 'delete':
        onDeleteTestCase(testCase);
        break;
    }
  };

  return {
    showAudioPlayer,
    currentTestCaseCaseId,
    showAudioTypeModal,
    currentTestCase,
    currentHasAPIConfig,
    currentHasE2eConfig,
    selectedAudioType,
    showAudioPreviewModal,
    previewPlaybackMode,
    showPlaybackDeviceModal,
    checkTestCaseConfig,
    handleCloseAudioTypeModal,
    selectAudioType,
    handleAudioPreviewModalClose,
    handleAudioPreviewConfirm,
    handleAudioPlayerClose,
    handleAction
  };
}
