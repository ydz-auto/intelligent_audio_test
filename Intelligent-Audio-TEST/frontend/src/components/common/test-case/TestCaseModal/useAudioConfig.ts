import { ref, computed, nextTick } from 'vue';
import { playbackApi, audiosApi } from '../../../../utils/api';
import type { AudioItem, PlaybackDevice, AudioConfig, BackgroundNoiseConfig } from './types';

export function useAudioConfig() {
  const playbackDevices = ref<PlaybackDevice[]>([]);
  const dryAudios = ref<AudioItem[]>([]);
  const noiseAudios = ref<AudioItem[]>([]);

  const showAudioModal = ref(false);
  const showDeviceModal = ref(false);
  const showNoiseDeviceModal = ref(false);
  const showBatchDeviceModal = ref(false);
  const showCrossDeviceModal = ref(false);
  const showBatchSplModal = ref(false);
  const showAudioPreviewModal = ref(false);

  const currentAudioType = ref<'dry' | 'noise'>('dry');
  const currentAudioIndex = ref<number | null>(null);
  const currentDeviceAudioIndex = ref<number | null>(null);
  const initialSelectedDevices = ref<string[]>([]);
  const noiseInitialSelectedDevices = ref<string[]>([]);
  const batchInitialSelectedDevices = ref<string[]>([]);
  const crossDeviceInitialSelectedDevices = ref<string[]>([]);
  const batchSplValue = ref(65);

  const currentPreviewAudioId = ref<string | null>(null);
  const currentPreviewAudioType = ref<'dry' | 'noise'>('dry');
  const currentPreviewDeviceId = ref<string | null>(null);
  const currentPreviewSpl = ref(65);
  const currentPreviewOffset = ref(0);

  const draggedAudioIndex = ref<number | null>(null);
  const dragOverAudioIndex = ref<number | null>(null);

  const MAX_AUDIO_TAGS = 8;
  const expandedAudioTags = ref<Record<string, boolean>>({});
  const showTagSelector = ref(false);
  const selectedTagsForInterleave = ref<string[]>([]);
  const interleaveOrder = ref<'asc' | 'desc'>('asc');
  const showTagDeviceSelector = ref(false);
  const tagDeviceMapping = ref<Record<string, string>>({});

  async function loadResources(configuredAudioIds: (string | number)[] = []) {
    try {
      const [devicesRes, allAudiosRes] = await Promise.all([
        playbackApi.getAll({ perPage: 1000 }),
        audiosApi.getAll({ perPage: 1000 })
      ]);

      playbackDevices.value = Array.isArray(devicesRes?.items)
        ? devicesRes.items as PlaybackDevice[]
        : [];
      const audios: AudioItem[] = Array.isArray(allAudiosRes?.items)
        ? allAudiosRes.items
        : [];
      
      console.log('[useAudioConfig] loaded audios count:', audios.length);
      if (audios.length > 0) {
        console.log('[useAudioConfig] first audio sample:', audios[0]);
        console.log('[useAudioConfig] first audio tags:', (audios[0] as any).tags, (audios[0] as any).tag);
      }

      let dryAudioList: AudioItem[] = audios.filter((a: AudioItem) => a.audioType === 'dry');
      let noiseAudioList: AudioItem[] = audios.filter((a: AudioItem) => a.audioType === 'noise');

      const firstPageIds = new Set(audios.map((a: AudioItem) => a.id));
      const missingAudioIds = configuredAudioIds.filter(id => !firstPageIds.has(id));

      if (missingAudioIds.length > 0) {
        try {
          const missingAudiosRes = await audiosApi.getByIds(missingAudioIds);
          const missingAudios: AudioItem[] = Array.isArray(missingAudiosRes)
            ? missingAudiosRes
            : (missingAudiosRes?.data ? missingAudiosRes.data : []);

          for (const missingAudio of missingAudios) {
            if (missingAudio.audioType === 'dry') {
              dryAudioList.push(missingAudio);
            } else if (missingAudio.audioType === 'noise') {
              noiseAudioList.push(missingAudio);
            } else {
              dryAudioList.push(missingAudio);
            }
          }
        } catch (err) {
          console.error('批量获取音频失败:', err);
        }
      }

      dryAudios.value = dryAudioList;
      noiseAudios.value = noiseAudioList;
    } catch (err) {
      console.error('加载资源失败:', err);
    }
  }

  function getAudioName(audioId: string | number): string {
    const allAudios = [...dryAudios.value, ...noiseAudios.value];
    const audio = allAudios.find(a => String(a.id) === String(audioId));
    return audio ? audio.name : '未知音频';
  }

  function getAudioTags(audioId: string | number): string {
    const allAudios = [...dryAudios.value, ...noiseAudios.value];
    const audio = allAudios.find(a => String(a.id) === String(audioId));
    if (!audio) return '';
    
    const rawTags = (audio as any).tags || (audio as any).tag || '';
    if (Array.isArray(rawTags)) {
      return rawTags.join(', ');
    }
    return String(rawTags);
  }

  function getAudioDuration(audioId: string | number): number {
    const allAudios = [...dryAudios.value, ...noiseAudios.value];
    const audio = allAudios.find(a => String(a.id) === String(audioId));
    if (!audio || !audio.duration) return 0;
    if (typeof audio.duration === 'number') return audio.duration;
    // Parse "MM:SS" or "HH:MM:SS" format
    const parts = String(audio.duration).split(':').map(Number);
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    const num = parseFloat(String(audio.duration));
    return isNaN(num) ? 0 : num;
  }

  function formatDuration(totalSeconds: number): string {
    if (!totalSeconds || totalSeconds <= 0) return '0s';
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.round(totalSeconds % 60);
    const parts: string[] = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (seconds > 0 || parts.length === 0) parts.push(`${seconds}s`);
    return parts.join(' ');
  }

  function getNormalizedTags(tagsStr: string): string[] {
    if (!tagsStr) return [];
    if (typeof tagsStr === 'string') {
      return tagsStr.split(',').map(t => t.trim()).filter(t => t);
    }
    return [];
  }

  function getDeviceName(deviceId: string | number): string {
    const device = playbackDevices.value.find(d => String(d.id) === String(deviceId));
    if (device) {
      return `${device.name} (通道 ${device.channelIndex})`;
    }
    const deviceIdStr = String(deviceId);
    const scanDeviceMatch = deviceIdStr.match(/^(.*)-(\d+)$/);
    if (scanDeviceMatch) {
      return `${scanDeviceMatch[1]} (通道 ${scanDeviceMatch[2]}) [扫描]`;
    }
    return '未知设备';
  }

  function toggleAudioTags(audioId: string | number) {
    const key = String(audioId);
    expandedAudioTags.value[key] = !expandedAudioTags.value[key];
  }

  function openAudioSelectModal(audioType: 'dry' | 'noise', index: number | null = null) {
    currentAudioType.value = audioType;
    currentAudioIndex.value = index;
    showAudioModal.value = true;
  }

  function openDeviceSelectModal(audioIndex: number, currentDeviceId?: string) {
    currentDeviceAudioIndex.value = audioIndex;
    initialSelectedDevices.value = currentDeviceId ? [currentDeviceId] : [];
    showDeviceModal.value = true;
  }

  function openNoiseDeviceSelectModal(currentDeviceIds: string[] = []) {
    noiseInitialSelectedDevices.value = currentDeviceIds;
    showNoiseDeviceModal.value = true;
  }

  function openBatchDeviceModal(currentDeviceId?: string) {
    batchInitialSelectedDevices.value = currentDeviceId ? [currentDeviceId] : [];
    showBatchDeviceModal.value = true;
  }

  function openCrossDeviceModal(currentDeviceIds: string[] = []) {
    crossDeviceInitialSelectedDevices.value = currentDeviceIds;
    showCrossDeviceModal.value = true;
  }

  function openBatchSplModal(currentSpl: number = 65) {
    batchSplValue.value = currentSpl;
    showBatchSplModal.value = true;
  }

  function handleAudioSelect(audio: AudioItem, audios: AudioConfig[], backgroundNoise: BackgroundNoiseConfig) {
    const audioId = audio.id;
    if (currentAudioType.value === 'dry' && currentAudioIndex.value !== null) {
      audios[currentAudioIndex.value].audioId = String(audioId);
      if (!dryAudios.value.find(a => String(a.id) === String(audioId))) {
        dryAudios.value.push(audio);
      }
    } else if (currentAudioType.value === 'noise') {
      backgroundNoise.audioId = String(audioId);
      if (!noiseAudios.value.find(a => String(a.id) === String(audioId))) {
        noiseAudios.value.push(audio);
      }
    }
    showAudioModal.value = false;
  }

  function handleMultipleAudioSelect(selectedAudios: AudioItem[], audios: AudioConfig[], backgroundNoise: BackgroundNoiseConfig) {
    const sortedAudios = [...selectedAudios].sort((a, b) => {
      const nameA = (a.name || '').toLowerCase();
      const nameB = (b.name || '').toLowerCase();
      return nameA.localeCompare(nameB);
    });

    if (currentAudioType.value === 'dry') {
      if (currentAudioIndex.value !== null) {
        const sourceAudio = audios[currentAudioIndex.value];
        audios[currentAudioIndex.value].audioId = String(sortedAudios[0].id);
        if (!dryAudios.value.find(a => String(a.id) === String(sortedAudios[0].id))) {
          dryAudios.value.push(sortedAudios[0]);
        }
        for (let i = 1; i < sortedAudios.length; i++) {
          audios.push({
            audioId: String(sortedAudios[i].id),
            testType: sourceAudio.testType || 'api',
            playbackDeviceId: sourceAudio.playbackDeviceId || '',
            spl: sourceAudio.spl ?? 65,
            playOrder: audios.length
          });
          if (!dryAudios.value.find(a => String(a.id) === String(sortedAudios[i].id))) {
            dryAudios.value.push(sortedAudios[i]);
          }
        }
      } else {
        for (const audio of sortedAudios) {
          audios.push({
            audioId: String(audio.id),
            testType: 'api',
            playbackDeviceId: '',
            spl: 65,
            playOrder: audios.length
          });
          if (!dryAudios.value.find(a => String(a.id) === String(audio.id))) {
            dryAudios.value.push(audio);
          }
        }
      }
    } else if (currentAudioType.value === 'noise') {
      backgroundNoise.audioId = String(sortedAudios[0].id);
      if (!noiseAudios.value.find(a => String(a.id) === String(sortedAudios[0].id))) {
        noiseAudios.value.push(sortedAudios[0]);
      }
    }
    showAudioModal.value = false;
  }

  function handleDeviceSelect(selectedDevices: string[], audios: AudioConfig[]) {
    if (currentDeviceAudioIndex.value !== null && selectedDevices.length > 0) {
      audios[currentDeviceAudioIndex.value].playbackDeviceId = selectedDevices[0];
    }
    showDeviceModal.value = false;
  }

  function handleNoiseDeviceSelect(selectedDevices: string[], backgroundNoise: BackgroundNoiseConfig) {
    backgroundNoise.deviceIds = selectedDevices;
    showNoiseDeviceModal.value = false;
  }

  function handleBatchDeviceSelect(selectedDevices: string[], audios: AudioConfig[]) {
    if (selectedDevices.length > 0) {
      const deviceId = selectedDevices[0];
      audios.forEach(audio => {
        if (audio.testType === 'e2e') {
          audio.playbackDeviceId = deviceId;
        }
      });
    }
    showBatchDeviceModal.value = false;
  }

  function handleCrossDeviceSelect(selectedDevices: string[], audios: AudioConfig[]) {
    if (selectedDevices.length > 0) {
      const e2eAudioConfigs = audios.filter(audio => audio.testType === 'e2e');
      e2eAudioConfigs.forEach((audio, index) => {
        audio.playbackDeviceId = selectedDevices[index % selectedDevices.length];
      });
    }
    showCrossDeviceModal.value = false;
  }

  function handleBatchSplConfirm(spl: number, audios: AudioConfig[]) {
    audios.forEach(audio => {
      if (audio.testType === 'e2e') {
        audio.spl = spl;
      }
    });
    showBatchSplModal.value = false;
  }

  function addAudioConfig(audios: AudioConfig[]) {
    audios.push({
      audioId: '',
      testType: 'api',
      playbackDeviceId: '',
      spl: 65,
      playOrder: audios.length
    });
  }

  function removeAudioConfig(index: number, audios: AudioConfig[]) {
    if (audios.length > 0) {
      audios.splice(index, 1);
      audios.forEach((audio, i) => {
        audio.playOrder = i;
      });
    }
  }

  function copyAudioConfig(index: number, audios: AudioConfig[]) {
    const sourceConfig = audios[index];
    audios.splice(index + 1, 0, {
      audioId: sourceConfig.audioId || '',
      testType: sourceConfig.testType || 'api',
      playbackDeviceId: sourceConfig.playbackDeviceId || '',
      spl: sourceConfig.spl || 65,
      playOrder: sourceConfig.playOrder + 1
    });
    audios.forEach((audio, i) => {
      audio.playOrder = i;
    });
  }

  function clearAllAudioConfigs(audios: AudioConfig[]) {
    if (audios.length > 0 && confirm('确定要清空所有音频配置吗？')) {
      audios.length = 0;
    }
  }

  function handleAudioDragStart(index: number, event: DragEvent) {
    draggedAudioIndex.value = index;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', String(index));
    }
  }

  function handleAudioDragEnd() {
    draggedAudioIndex.value = null;
    dragOverAudioIndex.value = null;
  }

  function handleAudioDragOver(index: number, event: DragEvent) {
    event.preventDefault();
    if (draggedAudioIndex.value !== null && draggedAudioIndex.value !== index) {
      dragOverAudioIndex.value = index;
    }
  }

  function handleAudioDrop(index: number, audios: AudioConfig[]) {
    if (draggedAudioIndex.value === null || draggedAudioIndex.value === index) {
      draggedAudioIndex.value = null;
      dragOverAudioIndex.value = null;
      return;
    }

    if (audios.length <= 1) {
      draggedAudioIndex.value = null;
      dragOverAudioIndex.value = null;
      return;
    }

    const oldExpandedStates: Record<string, boolean> = {};
    audios.forEach(config => {
      if (config.audioId) {
        oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
      }
    });

    const draggedItem = audios[draggedAudioIndex.value];
    audios.splice(draggedAudioIndex.value, 1);
    audios.splice(index, 0, draggedItem);

    audios.forEach((audio, i) => {
      audio.playOrder = i;
    });

    draggedAudioIndex.value = null;
    dragOverAudioIndex.value = null;

    nextTick(() => {
      Object.keys(oldExpandedStates).forEach((id: string) => {
        expandedAudioTags.value[id] = oldExpandedStates[id];
      });
    });
  }

  function shuffleAudioConfigs(audios: AudioConfig[]) {
    if (audios.length <= 1) return;

    const oldExpandedStates: Record<string, boolean> = {};
    audios.forEach(config => {
      if (config.audioId) {
        oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
      }
    });

    for (let i = audios.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [audios[i], audios[j]] = [audios[j], audios[i]];
    }

    audios.forEach((audio, i) => {
      audio.playOrder = i;
    });

    nextTick(() => {
      Object.keys(oldExpandedStates).forEach((id: string) => {
        expandedAudioTags.value[id] = oldExpandedStates[id];
      });
    });
  }

  function sortByFileName(audios: AudioConfig[], order: 'asc' | 'desc') {
    if (audios.length <= 1) return;

    const audioNames: Record<string, string> = {};
    audios.forEach(config => {
      if (config.audioId) {
        audioNames[config.audioId] = getAudioName(config.audioId) || '';
      }
    });

    const oldExpandedStates: Record<string, boolean> = {};
    audios.forEach(config => {
      if (config.audioId) {
        oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
      }
    });

    audios.sort((a, b) => {
      const nameA = audioNames[a.audioId] || '';
      const nameB = audioNames[b.audioId] || '';
      return order === 'asc' ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
    });

    audios.forEach((audio, i) => {
      audio.playOrder = i;
    });

    nextTick(() => {
      Object.keys(oldExpandedStates).forEach((id: string) => {
        expandedAudioTags.value[id] = oldExpandedStates[id];
      });
    });
  }

  function getUniqueTagsFromConfigs(audios: AudioConfig[]): string[] {
    if (!audios || audios.length === 0) return [];
    const tagSet = new Set<string>();
    audios.forEach(config => {
      if (config.audioId) {
        const tagsStr = getAudioTags(config.audioId);
        console.log('[useAudioConfig] audioId:', config.audioId, 'tagsStr:', tagsStr);
        const tags = getNormalizedTags(tagsStr);
        console.log('[useAudioConfig] normalized tags:', tags);
        tags.forEach(tag => tagSet.add(tag));
      }
    });
    const result = Array.from(tagSet);
    console.log('[useAudioConfig] getUniqueTagsFromConfigs result:', result);
    return result;
  }

  function toggleTagSelector() {
    showTagSelector.value = !showTagSelector.value;
    if (showTagSelector.value) {
      selectedTagsForInterleave.value = [];
    }
  }

  function toggleTagSelection(tag: string) {
    const index = selectedTagsForInterleave.value.indexOf(tag);
    if (index === -1) {
      selectedTagsForInterleave.value.push(tag);
    } else {
      selectedTagsForInterleave.value.splice(index, 1);
    }
  }

  function interleaveByTags(audios: AudioConfig[]) {
    if (audios.length <= 1) return;
    const selectedTags = [...selectedTagsForInterleave.value];
    if (selectedTags.length < 2) return;

    if (interleaveOrder.value === 'desc') {
      selectedTags.reverse();
    }

    const matchedConfigs: AudioConfig[] = [];
    const unmatchedConfigs: AudioConfig[] = [];

    audios.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId));
        const hasAnySelectedTag = selectedTags.some(tag => tags.includes(tag));
        if (hasAnySelectedTag) {
          matchedConfigs.push({ ...config });
        } else {
          unmatchedConfigs.push({ ...config });
        }
      } else {
        unmatchedConfigs.push({ ...config });
      }
    });

    if (matchedConfigs.length < 2) return;

    const groupedByTag: Record<string, AudioConfig[]> = {};
    selectedTags.forEach(tag => {
      groupedByTag[tag] = matchedConfigs.filter(config => {
        const tags = getNormalizedTags(getAudioTags(config.audioId));
        return tags.includes(tag);
      });
    });

    const maxGroupSize = Math.max(...Object.values(groupedByTag).map(g => g.length));
    const interleaved: AudioConfig[] = [];
    const usedIndices = new Set<number>();

    for (let i = 0; i < maxGroupSize; i++) {
      for (const tag of selectedTags) {
        if (i < groupedByTag[tag].length) {
          const config = groupedByTag[tag][i];
          const originalIdx = matchedConfigs.indexOf(config);
          if (!usedIndices.has(originalIdx)) {
            usedIndices.add(originalIdx);
            interleaved.push(config);
          }
        }
      }
    }

    const remainingMatched = matchedConfigs.filter((_, idx) => !usedIndices.has(idx));
    interleaved.push(...remainingMatched);
    interleaved.push(...unmatchedConfigs);

    const oldExpandedStates: Record<string, boolean> = {};
    audios.forEach(config => {
      if (config.audioId) {
        oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
      }
    });

    interleaved.forEach((audio, i) => {
      audio.playOrder = i;
    });

    audios.length = 0;
    audios.push(...interleaved);

    showTagSelector.value = false;
    selectedTagsForInterleave.value = [];
    interleaveOrder.value = 'asc';

    nextTick(() => {
      Object.keys(oldExpandedStates).forEach((id: string) => {
        expandedAudioTags.value[id] = oldExpandedStates[id];
      });
    });
  }

  function toggleTagDeviceSelector(audios: AudioConfig[]) {
    showTagDeviceSelector.value = !showTagDeviceSelector.value;
    if (showTagDeviceSelector.value) {
      const tags = getUniqueTagsFromConfigs(audios);
      const mapping: Record<string, string> = {};
      tags.forEach(tag => {
        mapping[tag] = '';
      });
      tagDeviceMapping.value = mapping;
    }
  }

  function getDeviceForTag(tag: string): string {
    return tagDeviceMapping.value[tag] || '';
  }

  function updateTagDeviceMapping(tag: string, deviceId: string) {
    tagDeviceMapping.value[tag] = deviceId;
  }

  function getTagAudioCount(tag: string, audios: AudioConfig[]): number {
    if (!audios) return 0;
    let count = 0;
    audios.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId));
        const firstMatchedTag = tags.find(t => tagDeviceMapping.value[t] && tagDeviceMapping.value[t].length > 0);
        if (firstMatchedTag === tag) {
          count++;
        }
      }
    });
    return count;
  }

  const hasValidTagDeviceMapping = computed(() => {
    return Object.values(tagDeviceMapping.value || {}).some(v => v && v.length > 0);
  });

  const getTagDeviceMapping = computed(() => {
    return Object.entries(tagDeviceMapping.value || {}).filter(([_, deviceId]) => deviceId && deviceId.length > 0);
  });

  function assignDeviceByTags(audios: AudioConfig[]) {
    if (!hasValidTagDeviceMapping.value || !audios) return;

    audios.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId));
        const firstMatchedTag = tags.find(tag => tagDeviceMapping.value[tag] && tagDeviceMapping.value[tag].length > 0);
        if (firstMatchedTag) {
          config.playbackDeviceId = tagDeviceMapping.value[firstMatchedTag];
        }
      }
    });

    showTagDeviceSelector.value = false;
    tagDeviceMapping.value = {};
  }

  function clearNoiseConfig(backgroundNoise: BackgroundNoiseConfig) {
    backgroundNoise.audioId = '';
    backgroundNoise.deviceIds = [];
    backgroundNoise.spl = 0;
  }

  function getNoiseDeviceNames(backgroundNoise: BackgroundNoiseConfig | undefined): string {
    if (!backgroundNoise) return '';
    const deviceIds = backgroundNoise.deviceIds || [];
    if (deviceIds.length === 0) return '';
    return deviceIds.map(id => getDeviceName(id)).join(', ');
  }

  function syncAudioTagsToCase(audios: AudioConfig[], caseTags: string[]) {
    const allTags = new Set<string>();
    audios.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId));
        tags.forEach(tag => allTags.add(tag));
      }
    });
    allTags.forEach(tag => {
      if (!caseTags.includes(tag)) {
        caseTags.push(tag);
      }
    });
  }

  return {
    playbackDevices,
    dryAudios,
    noiseAudios,
    showAudioModal,
    showDeviceModal,
    showNoiseDeviceModal,
    showBatchDeviceModal,
    showCrossDeviceModal,
    showBatchSplModal,
    showAudioPreviewModal,
    currentAudioType,
    currentAudioIndex,
    currentDeviceAudioIndex,
    initialSelectedDevices,
    noiseInitialSelectedDevices,
    batchInitialSelectedDevices,
    crossDeviceInitialSelectedDevices,
    batchSplValue,
    currentPreviewAudioId,
    currentPreviewAudioType,
    currentPreviewDeviceId,
    currentPreviewSpl,
    currentPreviewOffset,
    draggedAudioIndex,
    dragOverAudioIndex,
    MAX_AUDIO_TAGS,
    expandedAudioTags,
    showTagSelector,
    selectedTagsForInterleave,
    interleaveOrder,
    showTagDeviceSelector,
    tagDeviceMapping,
    hasValidTagDeviceMapping,
    getTagDeviceMapping,
    loadResources,
    getAudioName,
    getAudioTags,
    getAudioDuration,
    formatDuration,
    getNormalizedTags,
    getDeviceName,
    toggleAudioTags,
    openAudioSelectModal,
    openDeviceSelectModal,
    openNoiseDeviceSelectModal,
    openBatchDeviceModal,
    openCrossDeviceModal,
    openBatchSplModal,
    handleAudioSelect,
    handleMultipleAudioSelect,
    handleDeviceSelect,
    handleNoiseDeviceSelect,
    handleBatchDeviceSelect,
    handleCrossDeviceSelect,
    handleBatchSplConfirm,
    addAudioConfig,
    removeAudioConfig,
    copyAudioConfig,
    clearAllAudioConfigs,
    handleAudioDragStart,
    handleAudioDragEnd,
    handleAudioDragOver,
    handleAudioDrop,
    shuffleAudioConfigs,
    sortByFileName,
    getUniqueTagsFromConfigs,
    toggleTagSelector,
    toggleTagSelection,
    interleaveByTags,
    toggleTagDeviceSelector,
    getDeviceForTag,
    updateTagDeviceMapping,
    getTagAudioCount,
    assignDeviceByTags,
    clearNoiseConfig,
    getNoiseDeviceNames,
    syncAudioTagsToCase
  };
}
