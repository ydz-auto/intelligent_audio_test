import { ref } from 'vue';
import { devicesApi } from '../utils/api';
import type { PlaybackDevice, APIResponse } from '../shared/types';

/**
 * 设备管理组合式函数
 *
 * 职责：
 * - 获取播放设备列表（分页加载）
 * - 获取所有设备列表（用于下拉选择）
 */
export function useDeviceManagement() {
  const playbackDevices = ref<PlaybackDevice[]>([]);
  const playbackDevicePage = ref(1);
  const playbackDevicePages = ref(1);
  const playbackDeviceLoading = ref(false);
  const playbackDeviceHasMore = ref(true);

  const deviceList = ref<{ value: string | number; name: string }[]>([]);

  /**
   * 获取播放设备列表
   * @param reset 是否重置分页（首次加载或刷新时为 true）
   */
  async function fetchPlaybackDevices(reset = true) {
    if (reset) {
      playbackDevicePage.value = 1;
      playbackDevices.value = [];
      playbackDeviceHasMore.value = true;
    }
    if (playbackDeviceLoading.value || (!playbackDeviceHasMore.value && !reset)) return;
    playbackDeviceLoading.value = true;
    try {
      const response = await devicesApi.getPlaybackDevices({
        params: { page: playbackDevicePage.value, per_page: 50 },
        unwrapResponse: false
      }) as APIResponse<{ items: PlaybackDevice[]; pages: number }>;
      if (response.success && response.data && Array.isArray(response.data.items)) {
        if (reset) {
          playbackDevices.value = response.data.items;
        } else {
          playbackDevices.value = [...playbackDevices.value, ...response.data.items];
        }
        playbackDevicePages.value = response.data.pages || 1;
        playbackDeviceHasMore.value = playbackDevicePage.value < playbackDevicePages.value;
        if (playbackDeviceHasMore.value) {
          playbackDevicePage.value += 1;
        }
      } else {
        if (reset) playbackDevices.value = [];
      }
    } catch (e) {
      console.error('Fetch playback devices failed:', e);
      if (reset) playbackDevices.value = [];
    } finally {
      playbackDeviceLoading.value = false;
    }
  }

  /**
   * 加载更多播放设备（滚动加载）
   */
  async function loadMorePlaybackDevices() {
    if (!playbackDeviceLoading.value && playbackDeviceHasMore.value) {
      await fetchPlaybackDevices(false);
    }
  }

  /**
   * 获取所有设备列表（用于下拉选择）
   */
  async function fetchDevices() {
    try {
      const response = await devicesApi.getAll({ per_page: 100 });
      if (response && response.items) {
        deviceList.value = response.items.map((d: any) => ({
          value: d.id,
          name: d.name
        }));
      }
    } catch (e) {
      console.error('Fetch devices failed:', e);
      deviceList.value = [];
    }
  }

  return {
    // 状态
    playbackDevices,
    playbackDevicePage,
    playbackDevicePages,
    playbackDeviceLoading,
    playbackDeviceHasMore,
    deviceList,
    // 方法
    fetchPlaybackDevices,
    loadMorePlaybackDevices,
    fetchDevices,
  };
}
