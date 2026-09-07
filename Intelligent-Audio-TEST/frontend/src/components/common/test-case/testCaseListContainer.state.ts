/**
 * TestCaseListContainer —— 组件级本地状态
 *
 * 集中声明跨 composable / 跨子模块共享的响应式状态（选择集、筛选器、视图模式、分页占位等）。
 */
import { ref } from 'vue';
import { ViewMode } from '@/domain/enums';
import type { PlaybackDevice } from '../../../domain';

/** 创建容器本地共享状态 */
export function createContainerState(props: any) {
  // ===== 本地状态（组件级，跨 composable 共享） =====
  const selectedCases = ref<(string | number)[]>([]);
  const playbackDevices = ref<PlaybackDevice[]>([]);
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);

  // 视图模式：'group' 分组视图 | 'tag' 标签视图
  const innerViewMode = ref<typeof ViewMode[keyof typeof ViewMode]>(props.viewMode || ViewMode.GROUP);

  // 筛选状态在组件级声明，供 groupExpand / filters / batchActions 共享同一份响应式状态
  const searchQuery = ref('');
  const testTypeFilter = ref('all');
  const algorithmTypeFilter = ref('all');
  const groupFilter = ref('all');
  const tagFilter = ref('all');
  const sortBy = ref('count');
  const sortOrder = ref('desc');
  const dimensionFilter = ref<number | 'all'>('all');
  const dimensionOptions = ref<{ id: number; name: string }[]>([]);

  // hasMoreGroups 由分组分页计算属性驱动，先占位再被 composable 引用
  const hasMoreGroups = ref(true);

  // ===== 分组展开/加载 composable 的占位 ref =====
  // 预先创建占位 ref，待分组/标签分页计算属性定义后再同步。
  const paginatedGroupsRef = ref<string[]>([]);
  const paginatedTagsRef = ref<string[]>([]);
  const hasMoreTagsRef = ref(false);

  return {
    selectedCases,
    playbackDevices,
    algorithmOptions,
    innerViewMode,
    searchQuery,
    testTypeFilter,
    algorithmTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    dimensionFilter,
    dimensionOptions,
    hasMoreGroups,
    paginatedGroupsRef,
    paginatedTagsRef,
    hasMoreTagsRef,
  };
}

/** 容器本地状态类型（由工厂推断） */
export type ContainerState = ReturnType<typeof createContainerState>;