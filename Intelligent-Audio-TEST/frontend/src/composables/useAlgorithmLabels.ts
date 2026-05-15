import { ref, computed } from 'vue';
import { algorithmApi } from '../utils/api';

const algorithms = ref<{ value: string; label: string }[]>([]);
let isLoaded = false;
let loadingPromise: Promise<void> | null = null;

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
        algorithms.value = (data?.algorithms || []).map((algo: any) => ({
          value: algo.value,
          label: algo.name || algo.value
        }));
        isLoaded = true;
      } catch (error) {
        console.error('Failed to load algorithm options:', error);
        if (!isLoaded) {
          algorithms.value = [
            { value: 'translation', label: '翻译' },
            { value: 'asr', label: 'ASR' },
            { value: 'speaker_recognition', label: '说话人识别' },
            { value: 'tts', label: 'TTS' },
            { value: 'asr_eval', label: 'ASR评估' }
          ];
        }
      } finally {
        loadingPromise = null;
      }
    })();
    
    return loadingPromise;
  };

  const getAlgorithmLabel = (algorithmType: string): string => {
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
    return [
      { value: 'translation', label: '翻译' },
      { value: 'asr', label: 'ASR' },
      { value: 'speaker_recognition', label: '说话人识别' },
      { value: 'tts', label: 'TTS' }
    ];
  });

  return {
    algorithms,
    algorithmOptions,
    loadAlgorithms,
    getAlgorithmLabel
  };
}
