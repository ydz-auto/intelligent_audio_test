/**
 * AudioPlayerModal —— 多音频播放列表
 *
 * 负责多轮音频 URL 列表的连续播放编排（超过一条时通过 ended 事件接力播放下一条）。
 */
import type { Ref } from 'vue';

/** 播放列表模块依赖 */
export interface PlaylistPlayerDeps {
  audio: Ref<HTMLAudioElement | null>;
  isPlaying: Ref<boolean>;
  multiAudioPlaylist: Ref<string[]>;
  playError: Ref<string>;
}

/** 创建多音频连续播放控制 */
export function createPlaylistPlayer(deps: PlaylistPlayerDeps) {
  const { audio, isPlaying, multiAudioPlaylist, playError } = deps;

  /** 依序播放音频列表；单条时不追加 ended 接力监听 */
  const playAudioPlaylist = async (urls: string[] | undefined, singleUrl: string | undefined) => {
    if (!audio.value) return;

    // 多轮音频连续播放
    const playlist = urls && urls.length > 0 ? urls : (singleUrl ? [singleUrl] : []);
    multiAudioPlaylist.value = playlist;
    let currentIndex = 0;

    const playNext = async () => {
      if (currentIndex >= playlist.length) {
        isPlaying.value = false;
        return;
      }
      audio.value!.src = playlist[currentIndex];
      try {
        await audio.value!.load();
        await audio.value!.play();
        console.log(`Local audio playback started (${currentIndex + 1}/${playlist.length})`);
      } catch (playError: any) {
        console.error('Audio play error:', playError);
        playError.value = '音频播放失败，请检查音频文件是否有效';
        isPlaying.value = false;
      }
    };

    // 单音频时不需要 ended 事件
    if (playlist.length > 1) {
      audio.value.addEventListener('ended', () => {
        currentIndex++;
        playNext();
      });
    }

    await playNext();
  };

  return { playAudioPlaylist };
}