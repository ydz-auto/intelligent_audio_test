import { ref, computed } from 'vue';
import { algorithmApi } from '../../utils/api';

const algorithms = ref<{ value: string; label: string }[]>([]);
let isLoaded = false;
let loadingPromise: Promise<void> | null = null;

const DEFAULT_ALGORITHMS = [
  { value: 'translation', label: '翻译' },
  { value: 'asr', label: 'ASR' },
  { value: 'speaker_recognition', label: '说话人识别' },
  { value: 'tts', label: 'TTS' },
  { value: 'asr_eval', label: 'ASR评估' }
];

export function useAlgorithmLabels() {
  const loadAlgorithms = async () => {
    if (isLoaded && algorithms.value.length > 0) {
      return;
    }
    
    if (loadingPromise) {
      return loadingPromise;
    }
    
    loadingPromise = (async () => {
      try {
        const data = await algorithmApi.getOptions();
        const algoList = data?.algorithms || [];
        if (algoList.length > 0) {
          algorithms.value = algoList.map((algo: any) => ({
            value: algo?.value || '',
            label: algo?.name || algo?.value || ''
          }));
        } else {
          algorithms.value = DEFAULT_ALGORITHMS;
        }
        isLoaded = true;
      } catch (error) {
        console.error('Failed to load algorithm options:', error);
        if (!isLoaded) {
          algorithms.value = DEFAULT_ALGORITHMS;
        }
      } finally {
        loadingPromise = null;
      }
    })();
    
    return loadingPromise;
  };

  const getAlgorithmLabel = (algorithmType: string): string => {
    if (!algorithmType) return '';
    if (algorithms.value.length > 0) {
      const algo = algorithms.value.find(a => a.value === algorithmType);
      if (algo) return algo.label;
    }
    return algorithmType;
  };

  const algorithmOptions = computed(() => {
    if (algorithms.value.length > 0) {
      return algorithms.value;
    }
    return DEFAULT_ALGORITHMS;
  });

  return {
    algorithms,
    algorithmOptions,
    loadAlgorithms,
    getAlgorithmLabel
  };
}
