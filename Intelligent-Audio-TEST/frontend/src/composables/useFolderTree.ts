import { ref, computed, type Ref } from 'vue';
import { audiosApi } from '../utils/api';
import type { AudioInfo, AudioQueryParams, APIResponse } from '../shared/types';

/**
 * 文件夹树管理组合式函数
 *
 * 职责：
 * - 服务端文件夹树的获取、懒加载子树
 * - 文件夹展开/折叠状态管理
 * - 子树合并（保留已展开子节点状态）
 * - 客户端扁平文件夹树计算
 */

export interface FolderNode {
  name: string;
  path: string;
  count: number;
  file_count: number;
  has_children: boolean;
  files: any[];
  folders: FolderNode[];
}

export function useFolderTree() {
  const serverFolderTree = ref<FolderNode>({
    name: '音频文件',
    path: '',
    count: 0,
    file_count: 0,
    has_children: false,
    files: [],
    folders: []
  });
  const folderLoading = ref(false);
  // 根目录（空路径）默认展开；子文件夹懒加载展开
  const expandedFolderPaths = ref<Set<string>>(new Set(['']));

  // 旧的 expandedFolders（兼容 AudioImport.vue 的 toggleFolder）
  const expandedFolders = ref<Set<string>>(new Set());

  function normalizeFile(file: any): any {
    return {
      ...file,
      id: file.id,
      name: file.name || '',
      filename: file.filename || file.name || '',
      format: file.format || '',
      duration: file.duration || 0,
      size: file.size || 0,
      audio_type: file.audio_type || file.audioType || file.type || 'dry',
      type: file.type || file.audio_type || file.audioType || 'dry',
      created_at: file.created_at || file.createdAt || '',
    };
  }

  function normalizeTreeNode(node: any): FolderNode {
    if (!node) return { name: 'root', path: '', count: 0, file_count: 0, has_children: false, files: [], folders: [] };
    return {
      name: node.name || 'unnamed',
      path: node.path ?? '',
      count: node.count ?? node.total ?? 0,
      file_count: node.file_count ?? node.fileCount ?? (Array.isArray(node.files) ? node.files.length : 0),
      has_children: node.has_children ?? node.hasChildren ?? false,
      files: Array.isArray(node.files) ? node.files.map(normalizeFile) : [],
      folders: Array.isArray(node.folders) ? node.folders.map(normalizeTreeNode) : [],
    };
  }

  /**
   * 构建文件夹树查询参数
   */
  function buildFolderTreeParams(
    searchQuery: Ref<string>,
    filters: Ref<any>,
    selectedTags: Ref<string[]>,
    tagModes: Ref<Map<string, any>>,
    algorithmType: string,
    overrides: any = {}
  ): any {
    return {
      keyword: searchQuery.value || undefined,
      audioType: filters.value.audioType === 'all' ? undefined : filters.value.audioType,
      format: filters.value.format === 'all' ? undefined : filters.value.format,
      sampleRate: filters.value.sampleRate === 'all' ? undefined : normalizeSampleRate(filters.value.sampleRate),
      duration: filters.value.duration === 'all' ? undefined : filters.value.duration,
      tags: selectedTags.value.length > 0 ? selectedTags.value.map(tag => {
        const mode = tagModes.value?.get(tag);
        return { name: tag, mode: mode || 'and' };
      }) : undefined,
      algorithmType: algorithmType || undefined,
      ...overrides
    };
  }

  async function fetchFolderTree(
    searchQuery?: Ref<string>,
    filters?: Ref<any>,
    selectedTags?: Ref<string[]>,
    tagModes?: Ref<Map<string, any>>,
    algorithmType?: string,
    params: any = {}
  ) {
    folderLoading.value = true;
    try {
      const queryParams = (searchQuery && filters && selectedTags && tagModes)
        ? buildFolderTreeParams(searchQuery, filters, selectedTags, tagModes, algorithmType || '', { depth: 1, ...params })
        : { depth: 1, ...params };

      const response = await audiosApi.getFolderTree(queryParams, { unwrapResponse: false });

      if (response.success && response.data) {
        serverFolderTree.value = normalizeTreeNode(response.data.tree);
      }
    } catch (error) {
      console.error('获取文件夹树失败:', error);
    } finally {
      folderLoading.value = false;
    }
  }

  function toggleFolderExpand(folderPath: string) {
    const newSet = new Set(expandedFolderPaths.value);
    if (newSet.has(folderPath)) {
      newSet.delete(folderPath);
    } else {
      newSet.add(folderPath);
    }
    expandedFolderPaths.value = newSet;
  }

  function isFolderExpanded(folderPath: string): boolean {
    return expandedFolderPaths.value.has(folderPath);
  }

  async function loadSubTree(
    folderPath: string,
    searchQuery?: Ref<string>,
    filters?: Ref<any>,
    selectedTags?: Ref<string[]>,
    tagModes?: Ref<Map<string, any>>,
    algorithmType?: string
  ): Promise<FolderNode | null> {
    folderLoading.value = true;
    try {
      const queryParams = (searchQuery && filters && selectedTags && tagModes)
        ? buildFolderTreeParams(searchQuery, filters, selectedTags, tagModes, algorithmType || '', { parentPath: folderPath, depth: 10 })
        : { parentPath: folderPath, depth: 10 };

      const response = await audiosApi.getFolderTree(queryParams, { unwrapResponse: false });
      if (response.success && response.data) {
        return normalizeTreeNode(response.data.tree);
      }
    } catch (error) {
      console.error('Load sub-tree failed:', error);
    } finally {
      folderLoading.value = false;
    }
    return null;
  }

  function mergeSubTree(targetPath: string, fullTree: any) {
    // Find the node at targetPath in fullTree
    function findNode(node: any, path: string): any {
      if (node.path === path) return node;
      if (node.folders) {
        for (const child of node.folders) {
          const found = findNode(child, path);
          if (found) return found;
        }
      }
      return null;
    }
    const subNode = findNode(fullTree, targetPath);
    if (!subNode) return;

    // 浅合并：只更新 files 和 folder 元数据，按路径合并 folders，避免覆盖已展开子节点状态
    function findAndUpdate(node: any): boolean {
      if (node.path === targetPath) {
        node.files = subNode.files;
        node.file_count = subNode.file_count ?? subNode.files?.length ?? 0;
        node.has_children = subNode.has_children;
        // 按路径合并子文件夹，保留已加载的子节点
        const existingFolders = new Map<string, any>((node.folders || []).map((f: any) => [f.path as string, f]));
        const mergedFolders: any[] = [];
        for (const newFolder of (subNode.folders || [])) {
          const existing: any = existingFolders.get(newFolder.path);
          if (existing) {
            // 保留已展开子节点的数据，仅更新元数据
            existing.name = newFolder.name;
            existing.count = newFolder.count;
            existing.file_count = newFolder.file_count;
            existing.has_children = newFolder.has_children;
            // 如果新数据带了 files（深度更大），则更新
            if (newFolder.files && newFolder.files.length > 0) {
              existing.files = newFolder.files;
            }
            mergedFolders.push(existing);
          } else {
            mergedFolders.push(newFolder);
          }
        }
        node.folders = mergedFolders;
        return true;
      }
      if (node.folders) {
        for (const child of node.folders) {
          if (findAndUpdate(child)) return true;
        }
      }
      return false;
    }
    findAndUpdate(serverFolderTree.value);
  }

  /**
   * 客户端扁平文件夹树（基于 audioList 的 filepath 字段）
   */
  function computeFlattenedFolderTree(audioList: AudioInfo[]) {
    const folders: any[] = [];
    const folderMap = new Map<string, any>();

    audioList.forEach(audio => {
      const filePath = audio.filepath || '';
      if (!filePath) return;

      const normalizedPath = filePath.replace(/\\/g, '/');
      const lastSlashIndex = normalizedPath.lastIndexOf('/');

      let dir: string;
      if (lastSlashIndex === -1) {
        dir = '/';
      } else {
        dir = normalizedPath.substring(0, lastSlashIndex);
      }

      if (!folderMap.has(dir)) {
        const folderName = dir === '/' ? '根目录' : dir.split('/').pop() || '未知目录';
        folderMap.set(dir, { path: dir, name: folderName, files: [] });
        folders.push(folderMap.get(dir));
      }
      folderMap.get(dir).files.push(audio);
    });

    return folders;
  }

  /**
   * 兼容旧的 toggleFolder 方法
   */
  function toggleFolder(path: string) {
    if (expandedFolders.value.has(path)) {
      expandedFolders.value.delete(path);
    } else {
      expandedFolders.value.add(path);
    }
  }

  return {
    // 状态
    serverFolderTree,
    folderLoading,
    expandedFolderPaths,
    expandedFolders,
    // 方法
    fetchFolderTree,
    toggleFolderExpand,
    isFolderExpanded,
    loadSubTree,
    mergeSubTree,
    computeFlattenedFolderTree,
    toggleFolder,
    // 工具函数（也导出供外部使用）
    normalizeSampleRate,
    buildFolderTreeParams,
  };
}

/**
 * 采样率归一化（从 audioImport.ts 提取的工具函数）
 */
export function normalizeSampleRate(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const str = String(value).trim();
  if (!str || str === 'all') return null;
  const lower = str.toLowerCase();
  if (lower.includes('khz') || lower.includes('k hz') || lower.includes('k')) {
    const num = parseFloat(lower.replace(/[^0-9.]+/g, ''));
    if (!Number.isFinite(num)) return null;
    return String(Math.round(num * 1000));
  }
  const int = parseInt(lower.replace(/[^0-9]+/g, ''), 10);
  if (!Number.isFinite(int)) return null;
  return String(int);
}
