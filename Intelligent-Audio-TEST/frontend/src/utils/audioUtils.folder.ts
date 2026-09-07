/**
 * audioUtils —— 文件夹树构建与音频筛选
 *
 * 提供文件夹树构建（buildFolderTree）、标签提取（extractAllTags）、
 * 文件夹展开状态（toggleFolder / isFolderOpen）与音频筛选（filterAudios）。
 */
import type { FolderNode } from '@/domain/model/audio';
import { DURATION_SHORT_MAX, DURATION_MEDIUM_MAX } from './audioUtils.constants';

// FolderNode 统一定义见 domain/model/audio.ts（原内联定义已收敛至 Domain）

/**
 * 构建文件夹树结构
 * @param audios - 音频文件列表
 * @returns 文件夹树结构
 */
export const buildFolderTree = (audios: any[]): FolderNode => {
  const root : FolderNode = {name: '音频文件', files: [], folders: []};

  audios.forEach(audio => {
    const filePath = audio.filepath || audio.path || audio.filePath;
    if (!filePath) {
      root.files.push(audio);
      return;
    }

    let pathParts = filePath.split('/').filter((part: string) => part);
    if (pathParts.length === 0) {
      root.files.push(audio);
      return;
    }

    // 跳过第一层目录（如 'audios'）
    if (pathParts.length > 1 && (pathParts[0] === 'audios' || pathParts[0] === 'audio')) {
      pathParts = pathParts.slice(1);
    }

    // 如果去掉第一层后只剩文件名，则放到根目录
    if (pathParts.length <= 1) {
      root.files.push(audio);
      return;
    }

    let currentFolder = root;
    for (let i = 0; i < pathParts.length - 1; i++) {
      const folderName = pathParts[i];
      let folder = currentFolder.folders.find(f => f.name === folderName);
      if (!folder) {
        folder = {name: folderName, files: [], folders: []};
        currentFolder.folders.push(folder);
      }
      currentFolder = folder;
    }
    currentFolder.files.push(audio);
  });

  return root;
};

/**
 * 提取所有不重复的标签
 * @param audios - 音频列表
 * @returns 标签数组
 */
export const extractAllTags = (audios: any[]): string[] => {
  const tagsSet = new Set<string>();
  audios.forEach(audio => {
    if (audio.tags && Array.isArray(audio.tags)) {
      audio.tags.forEach((tag: string) => tagsSet.add(tag));
    }
  });
  return Array.from(tagsSet);
};

/**
 * 切换文件夹展开状态
 * @param folder - 文件夹节点
 * @param expandedFolders - 展开文件夹集合
 */
export const toggleFolder = (folder: FolderNode, expandedFolders: Set<string>): void => {
  if (expandedFolders.has(folder.name)) {
    expandedFolders.delete(folder.name);
  } else {
    expandedFolders.add(folder.name);
  }
};

/**
 * 检查文件夹是否展开
 * @param folder - 文件夹节点
 * @param expandedFolders - 展开文件夹集合
 * @returns 是否展开
 */
export const isFolderOpen = (folder: FolderNode, expandedFolders: Set<string>): boolean => {
  return expandedFolders.has(folder.name);
};

/**
 * 筛选音频文件
 * @param audios - 音频列表
 * @param query - 搜索关键词
 * @param filters - 筛选条件
 * @param selectedTags - 选中的标签
 * @returns 筛选后的音频列表
 */
export const filterAudios = (
  audios: any[],
  query: string,
  filters: any,
  selectedTags: string[]
): any[] => {
  return audios.filter(audio => {
    const matchesSearch = !query || 
      (audio.filename && audio.filename.toLowerCase().includes(query.toLowerCase())) ||
      (audio.name && audio.name.toLowerCase().includes(query.toLowerCase()));
    
    if (!matchesSearch) return false;

    if (filters.audioType !== 'all' && audio.type !== filters.audioType) {
      return false;
    }

    if (selectedTags.length > 0) {
      // 处理标签过滤 - 支持数组类型和字符串类型的 tags
      let audioTags = [];
      if (Array.isArray(audio.tags)) {
        audioTags = audio.tags;
      } else if (typeof audio.tags === 'string') {
        audioTags = audio.tags.split(',').map((tag: string) => tag.trim());
      }
      
      // 使用 some 方法，只要音频包含至少一个选中的标签就匹配
      const hasMatchingTag = selectedTags.some(tag => audioTags.includes(tag));
      if (!hasMatchingTag) return false;
    }

    if (filters.duration !== 'all') {
      const duration = parseFloat(audio.duration) || 0;
      if (filters.duration === 'short' && duration > DURATION_SHORT_MAX) return false;
      if (filters.duration === 'medium' && (duration <= DURATION_SHORT_MAX || duration > DURATION_MEDIUM_MAX)) return false;
      if (filters.duration === 'long' && duration <= DURATION_MEDIUM_MAX) return false;
    }

    if (filters.format !== 'all' && audio.format !== filters.format) {
      return false;
    }

    return true;
  });
};