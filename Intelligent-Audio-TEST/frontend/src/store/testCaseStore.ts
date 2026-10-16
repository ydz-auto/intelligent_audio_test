import { defineStore } from 'pinia'
import { ref } from 'vue'
import { testcasesPort } from '../composables/testCase/testcasesPort'
import { tagsPort } from '../composables/shared/tagsPort'
import { convertTestCaseFormData } from '../utils/utils'
import { useNotification } from '../composables/modal/useNotification'
import { useTestCaseBatchOps } from '../composables/testCase/useTestCaseBatchOps'
import { useTestCaseGroups } from '../composables/testCase/useTestCaseGroups'
import { useTestCaseImport } from '../composables/testCase/useTestCaseImport'
import type {
  TestCase,
  TestCaseFormData,
  TestCaseGroup,
  PaginationInfo
} from '../domain'
// 引入测试类型/视图模式枚举，消除魔法字符串
import { TestType, ViewMode } from '../domain/enums'
// INT-249：未分组虚拟分组常量（分组视图收纳无分组绑定的用例）
import { UNGROUPED_GROUP_ID, UNGROUPED_GROUP_NAME } from '../domain'

// 分组带用例数：TestCaseGroup 的展示子集（id/name/description/testCaseCount）
export type GroupWithCount = Pick<TestCaseGroup, 'id' | 'name' | 'description' | 'testCaseCount'>

/** 分组分页信息 = 分页信息 + 分组列表筛选字段（保留 filter 查询条件便于加载更多） */
export interface GroupPaginationInfo extends PaginationInfo {
  algorithmType?: string;
  testType?: string;
  keyword?: string;
  dimensionId?: number;
  // INT-526：回收站态 onlyDeleted 随首拉写入分页状态，loadMore 续拉沿用
  onlyDeleted?: boolean;
}

export const useTestCaseStore = defineStore('testCase', () => {
  const testCases = ref<TestCase[]>([]);
  const testCaseGroups = ref<Record<string, TestCase[]>>({});
  const tags = ref<string[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const allGroups = ref<string[]>([]);
  const fullGroupsMap = ref<Record<string, TestCaseGroup>>({});
  const groupsList = ref<GroupWithCount[]>([]);
  const loadedGroupCases = ref<Record<string, TestCase[]>>({});
  const groupLoadingStates = ref<Record<string, boolean>>({});
  const groupPagination = ref<Record<string, GroupPaginationInfo>>({});

  // 标签视图数据：按标签聚合的用例 { tagName: TestCase[] }
  const tagViewData = ref<Record<string, TestCase[]>>({});
  const tagViewPagination = ref<PaginationInfo>({
    page: 1,
    pages: 1,
    perPage: 50,
    total: 0
  });

  const paginationInfo = ref<PaginationInfo>({
    page: 1,
    pages: 1,
    perPage: 50,
    total: 0
  });

  const DEFAULT_FETCH_PAGE_SIZE = 50;
  const DEFAULT_GROUP_PAGE_SIZE = 20;

  const notification = useNotification();

  const handleError = (err: any, errorMessage: string) => {
    let fullErrorMsg = errorMessage;
    let details = '';
    if (err.message) {
      fullErrorMsg += ` - ${err.message}`;
    }
    if (err.detail) {
      details += `详情: ${JSON.stringify(err.detail)}`;
    }
    if (err.errors) {
      details += (details ? '\n' : '') + `错误列表: ${JSON.stringify(err.errors)}`;
    }
    if (err.code) {
      details += (details ? '\n' : '') + `错误码: ${err.code}`;
    }
    console.error(fullErrorMsg);
    if (details) {
      notification.error(fullErrorMsg, details);
    } else {
      notification.error(fullErrorMsg);
    }
    const msg = err.message || errorMessage;
    error.value = msg;
    return false;
  };

  // ----------------------------------------------------------------
  // 本地状态操作（核心）：分组整理 + 标签提取
  // 这两个方法被 store 内部 CRUD 使用，也通过依赖注入提供给各 composable，
  // 避免逻辑重复。同时它们继续作为 store 对外接口的一部分导出。
  // ----------------------------------------------------------------
  const organizeTestCasesByGroup = () => {
    const groups: Record<string, TestCase[]> = {};

    Object.values(fullGroupsMap.value).forEach(group => {
      const groupName = group.name || `未命名分组-${group.id}`;
      if (!groups[groupName]) {
        groups[groupName] = [];
      }
    });

    testCases.value.forEach(caseItem => {
      if (caseItem.deleted) return;

      // 无分组绑定的用例归入「未分组」虚拟桶（INT-249：不得静默吞掉）
      const groupId = caseItem.groupId || 'default';
      const group = fullGroupsMap.value[groupId.toString()];
      const groupName = group?.name || caseItem.groupName || UNGROUPED_GROUP_NAME;

      if (!groups[groupName]) {
        groups[groupName] = [];
      }
      groups[groupName].push(caseItem);
    });

    for (const groupName in groups) {
      groups[groupName].sort((a, b) => {
        // TestCase Domain 对象为 camelCase（createdAt/updatedAt）
        const timeA = a.createdAt ? new Date(a.createdAt).getTime() : (a.updatedAt ? new Date(a.updatedAt).getTime() : 0);
        const timeB = b.createdAt ? new Date(b.createdAt).getTime() : (b.updatedAt ? new Date(b.updatedAt).getTime() : 0);
        return timeB - timeA;
      });
    }

    allGroups.value = Object.keys(groups);
    testCaseGroups.value = groups;
  };

  const extractTags = () => {
    const tagSet = new Set<string>();
    testCases.value.forEach(tc => {
      if (tc.tags && Array.isArray(tc.tags)) {
        tc.tags.forEach(tag => {
          if (typeof tag === 'string') {
            tagSet.add(tag);
          } else if (tag && typeof tag === 'object' && 'name' in tag) {
            tagSet.add(tag.name);
          }
        });
      }
    });
    tags.value = Array.from(tagSet);
  };

  // ----------------------------------------------------------------
  // 核心 CRUD：拉取用例列表 / 标签视图
  // ----------------------------------------------------------------
  const fetchTestCases = async (params: Record<string, any> = {}) => {
    try {
      isLoading.value = true;
      error.value = null;

      const page = params.page || 1;
      const perPage = params.perPage || DEFAULT_FETCH_PAGE_SIZE;

      const [groupsResponse, testCasesResponse] = await Promise.all([
        testcasesPort.getGroups({ page: 1, perPage: 1000, algorithmType: params.algorithmType, testType: params.testType, keyword: params.keyword, dimensionId: params.dimensionId }),
        testcasesPort.getAll({
          page,
          perPage,
          keyword: params.keyword,
          tag: params.tag,
          groupId: params.groupId,
          testType: params.testType,
          algorithmType: params.algorithmType,
          dimensionId: params.dimensionId,
          includeDeleted: params.includeDeleted || false,
          // INT-141：收藏 / 回收站过滤
          favorite: params.favorite || false,
          onlyDeleted: params.onlyDeleted || false,
          // INT-423/467：可见性过滤（private|shared，服务端行级过滤）
          visibility: params.visibility || undefined
        })
      ]);

      let groupsData: any[] = [];

      if (groupsResponse) {
        groupsData = Array.isArray(groupsResponse.items) ? groupsResponse.items : [];
      }

      fullGroupsMap.value = groupsData.reduce((map, group) => {
        const id = group.id?.toString() || `group-${Date.now()}`;
        const name = group.name || `未命名分组-${id}`;
        map[id] = { ...group, id, name } as TestCaseGroup;
        return map;
      }, {} as Record<string, TestCaseGroup>);

      // 同步填充 groupsList：TestCaseListContainer 的分组展开/加载更多依赖它按名称查找分组 id 与用例总数，
      // 否则 fetchCasesByGroup / hasMoreGroupCases / loadMoreCases 全部失效（滚动加载更多用例不可用）。
      groupsList.value = groupsData.map((group, index) => {
        const id = group.id?.toString() || `group-${index}`;
        return {
          id,
          name: group.name || `未命名分组-${id}`,
          description: group.description,
          testCaseCount: group.testCaseCount ?? 0,
        };
      });

      // INT-249：无分组绑定的用例不属于任何后端分组，分组视图以「未分组」虚拟分组收纳
      // （仅当存在无分组用例时挂载，计数 = 用例总数 − Σ分组计数，两侧同筛选口径）。
      // 回收站/收藏/includeDeleted 下 groups 计数为活跃集合口径，与列表 total 不可比，跳过；
      // 分组数超出单页上限时 Σ 不完整，同样跳过避免虚高。
      const groupsTotal = typeof groupsResponse?.total === 'number' ? groupsResponse.total : groupsData.length;
      const canComputeUngrouped = !params.favorite && !params.onlyDeleted && !params.includeDeleted
        && !groupsData.some(g => g.name === UNGROUPED_GROUP_NAME)
        && groupsData.length >= groupsTotal;
      if (canComputeUngrouped) {
        const groupCountSum = groupsData.reduce((sum, g) => sum + (g.testCaseCount ?? 0), 0);
        const totalCount = typeof testCasesResponse?.total === 'number' ? testCasesResponse.total : 0;
        const ungroupedCount = Math.max(0, totalCount - groupCountSum);
        if (ungroupedCount > 0) {
          const virtualGroup: GroupWithCount = {
            id: UNGROUPED_GROUP_ID,
            name: UNGROUPED_GROUP_NAME,
            testCaseCount: ungroupedCount,
          };
          groupsList.value = [...groupsList.value, virtualGroup];
          fullGroupsMap.value = {
            ...fullGroupsMap.value,
            [UNGROUPED_GROUP_ID]: virtualGroup,
          };
        }
      }

      let testCasesData: TestCase[] = [];

      if (testCasesResponse) {
        testCasesData = Array.isArray(testCasesResponse.items) ? testCasesResponse.items : [];
      }

      paginationInfo.value = {
        page: testCasesResponse?.page || 1,
        pages: testCasesResponse?.pages || 1,
        perPage: testCasesResponse?.perPage || perPage,
        total: typeof testCasesResponse?.total === 'number' ? testCasesResponse.total : testCasesData.length
      };

      testCases.value = testCasesData.map(tc => {
        return {
          ...tc,
          type: tc.type || TestType.API,
          deleted: tc.deleted || false
        } as TestCase;
      });

      organizeTestCasesByGroup();
      extractTags();
    } catch (err: any) {
      console.error('获取测试用例失败:', err);
      error.value = err.message || '获取测试用例失败';
      allGroups.value = [];
      testCaseGroups.value = {};
      testCases.value = [];
      fullGroupsMap.value = {};
    } finally {
      isLoading.value = false;
    }
  };

  // 标签视图：调用 GET /testcases?view=tag，返回按标签聚合的数据。
  // 后端按 Tag 分页，前端通过 fetchTagView（重置）+ loadMoreTagView（追加）实现滚动加载。
  const tagViewLoading = ref(false);
  const tagViewLastParams = ref<Record<string, any>>({});

  const fetchTagView = async (params: Record<string, any> = {}) => {
    try {
      tagViewLoading.value = true;
      isLoading.value = true;
      error.value = null;

      const page = params.page || 1;
      const perPage = params.perPage || DEFAULT_FETCH_PAGE_SIZE;
      tagViewLastParams.value = { ...params };

      const response = await testcasesPort.getTagView({
        page,
        perPage,
        keyword: params.keyword,
        testType: params.testType,
        algorithmType: params.algorithmType,
        dimensionId: params.dimensionId,
        includeDeleted: params.includeDeleted || false,
        // INT-215：收藏 / 回收站过滤贯通标签视图
        favorite: params.favorite || false,
        onlyDeleted: params.onlyDeleted || false,
        // INT-423/467：可见性过滤贯通标签视图
        visibility: params.visibility || undefined
      });

      const items = response?.items ?? [];

      const groups: Record<string, TestCase[]> = {};
      items.forEach(item => {
        const tagName = item.tag || '未分类';
        groups[tagName] = Array.isArray(item.testCases)
          ? item.testCases
          : [];
      });

      // 重置时替换全部数据
      tagViewData.value = groups;
      tagViewPagination.value = {
        page: response?.page || 1,
        pages: response?.pages || 1,
        perPage: response?.perPage || perPage,
        total: typeof response?.total === 'number' ? response.total : items.length
      };

      // 同步提取标签列表
      const tagSet = new Set<string>();
      items.forEach(item => {
        if (item.tag) tagSet.add(item.tag);
      });
      tags.value = Array.from(tagSet);
    } catch (err: any) {
      console.error('获取标签视图数据失败:', err);
      error.value = err.message || '获取标签视图数据失败';
      tagViewData.value = {};
    } finally {
      tagViewLoading.value = false;
      isLoading.value = false;
    }
  };

  const loadMoreTagView = async () => {
    const pagination = tagViewPagination.value;
    if (tagViewLoading.value || pagination.page >= pagination.pages) return;

    try {
      tagViewLoading.value = true;
      const nextPage = pagination.page + 1;
      const params = tagViewLastParams.value;
      const perPage = pagination.perPage || DEFAULT_FETCH_PAGE_SIZE;

      const response = await testcasesPort.getTagView({
        page: nextPage,
        perPage,
        keyword: params.keyword,
        testType: params.testType,
        algorithmType: params.algorithmType,
        dimensionId: params.dimensionId,
        includeDeleted: params.includeDeleted || false,
        // INT-215：沿用首拉参数的收藏 / 回收站过滤
        favorite: params.favorite || false,
        onlyDeleted: params.onlyDeleted || false
      });

      const items = response?.items ?? [];

      // 追加到已有数据
      const merged = { ...tagViewData.value };
      items.forEach(item => {
        const tagName = item.tag || '未分类';
        const newCases = Array.isArray(item.testCases)
          ? item.testCases
          : [];
        if (merged[tagName]) {
          merged[tagName] = [...merged[tagName], ...newCases];
        } else {
          merged[tagName] = newCases;
        }
      });
      tagViewData.value = merged;

      tagViewPagination.value = {
        page: response?.page || nextPage,
        pages: response?.pages || pagination.pages,
        perPage: response?.perPage || perPage,
        total: typeof response?.total === 'number' ? response.total : pagination.total
      };

      // 累积标签列表
      const tagSet = new Set<string>(tags.value);
      items.forEach(item => {
        if (item.tag) tagSet.add(item.tag);
      });
      tags.value = Array.from(tagSet);
    } catch (err: any) {
      console.error('加载更多标签视图数据失败:', err);
      error.value = err.message || '加载更多标签视图数据失败';
    } finally {
      tagViewLoading.value = false;
    }
  };

  const isGroupLoading = (groupId: string | number) => {
    return groupLoadingStates.value[groupId.toString()] || false;
  };

  const hasMoreGroupCases = (groupId: string | number) => {
    const groupKey = groupId.toString();
    const pagination = groupPagination.value[groupKey];
    if (!pagination) return true;
    return pagination.page < pagination.pages;
  };

  const getGroupPagination = (groupId: string | number) => {
    return groupPagination.value[groupId.toString()];
  };

  // ----------------------------------------------------------------
  // 本地状态操作（核心）：upsert / remove
  // ----------------------------------------------------------------
  const upsertTestCaseLocal = (testCase: TestCase) => {
    const index = testCases.value.findIndex(tc => tc.id === testCase.id);
    if (index !== -1) {
      testCases.value[index] = {
        ...testCases.value[index],
        ...testCase,
        deleted: testCase.deleted || false
      };
    } else {
      testCases.value.push({
        ...testCase,
        type: testCase.type || TestType.API,
        deleted: testCase.deleted || false
      });
    }
    organizeTestCasesByGroup();
    extractTags();
  };

  const removeTestCaseLocal = (id: string | number) => {
    const index = testCases.value.findIndex(tc => tc.id === id);
    if (index !== -1) {
      testCases.value.splice(index, 1);
    }
    organizeTestCasesByGroup();
    extractTags();
  };

  /**
   * INT-215：收藏切换后就地回写 isFavorite（分组/标签视图共享同一行对象引用），
   * 星标态即时可见，无需整表重拉；下次列表刷新以后端返回为准。
   */
  const patchTestCaseFavorite = (id: string | number, isFavorite: boolean) => {
    const inList = testCases.value.find(tc => tc.id === id);
    if (inList) {
      inList.isFavorite = isFavorite;
    }
    for (const tagName of Object.keys(tagViewData.value)) {
      const hit = tagViewData.value[tagName]?.find(c => c.id === id);
      if (hit) {
        hit.isFavorite = isFavorite;
        break;
      }
    }
  };

  // ----------------------------------------------------------------
  // 核心 CRUD：增 / 改 / 删 / 复制 / 复制分组用例
  // ----------------------------------------------------------------
  const addTestCase = async (data: TestCaseFormData) => {
    try {
      error.value = null;
      const response = await testcasesPort.create(convertTestCaseFormData(data));

      if (response && response.id) {
        const newTestCase = await testcasesPort.getOne(response.id);
        if (newTestCase) {
          upsertTestCaseLocal(newTestCase as TestCase);
        }
      }
      notification.success('添加测试用例成功');
      return true;
    } catch (err: any) {
      return handleError(err, '添加测试用例失败');
    }
  };

  const updateTestCase = async (id: string | number, data: TestCaseFormData) => {
    try {
      error.value = null;
      await testcasesPort.update(id, convertTestCaseFormData(data));

      const updatedTestCase = await testcasesPort.getOne(id);
      if (updatedTestCase) {
        upsertTestCaseLocal(updatedTestCase as TestCase);
      }
      notification.success('更新测试用例成功');
      return true;
    } catch (err: any) {
      return handleError(err, '更新测试用例失败');
    }
  };

  const deleteTestCase = async (id: string | number) => {
    try {
      error.value = null;
      await testcasesPort.delete(id);
      removeTestCaseLocal(id);
      return true;
    } catch (err: any) {
      return handleError(err, '删除测试用例失败');
    }
  };

  const copyTestCase = async (id: string | number) => {
    try {
      error.value = null;
      const response = await testcasesPort.copy(id);

      if (response && response.id) {
        const newTestCase = await testcasesPort.getOne(response.id);
        if (newTestCase) {
          upsertTestCaseLocal(newTestCase as TestCase);
        }
      }
      notification.success('复制测试用例成功');
      return true;
    } catch (err: any) {
      return handleError(err, '复制测试用例失败');
    }
  };

  const copyGroupCases = async (groupName: string) => {
    try {
      error.value = null;
      await testcasesPort.batchAction('copy_by_group', [], { groupName });
      await fetchTestCases();
      return true;
    } catch (err: any) {
      return handleError(err, '复制分组用例失败');
    }
  };

  /** 按标签整体复制：复制标签下全部用例到 '<标签名>_copy' 标签，可另建新分组 */
  const copyTagCases = async (tagName: string, copyToNewGroup = false) => {
    try {
      error.value = null;
      await testcasesPort.batchAction('copy_by_tag', [], { tagName, copyToNewGroup });
      await refreshAfterCaseMutation();
      return true;
    } catch (err: any) {
      return handleError(err, '复制标签用例失败');
    }
  };

  /** 用例变更后统一刷新分组视图与标签视图（tagViewData 由父视图响应式透传） */
  const refreshAfterCaseMutation = async () => {
    await fetchTestCases();
    await fetchTagView(tagViewLastParams.value);
  };

  /** 按上次过滤参数刷新标签视图（无历史参数则直接抓取第一页） */
  const refreshTagView = async () => {
    await fetchTagView(tagViewLastParams.value);
  };

  /** 按当前视图模式刷新对应数据源（tag → 标签视图；group → 分组视图） */
  const refreshView = async (viewMode: string) => {
    if (viewMode === ViewMode.TAG) {
      await refreshTagView();
    } else {
      await fetchTestCases();
    }
  };

  /** 按标签级联删除：删除标签及其下所有测试用例（cascade=true） */
  const deleteTagCases = async (tagName: string, cascade = true) => {
    try {
      error.value = null;
      const tagList = await tagsPort.getTags({ keyword: tagName });
      const tagItem = tagList.items.find(item => item.name === tagName);
      if (!tagItem) {
        notification.warning(`未找到标签"${tagName}"，可能已被删除`);
        return false;
      }
      await tagsPort.deleteTag(tagItem.id, cascade);
      await refreshAfterCaseMutation();
      notification.success(`删除标签"${tagName}"成功`);
      return true;
    } catch (err: any) {
      return handleError(err, '删除标签失败');
    }
  };

  // ----------------------------------------------------------------
  // 委托给 composable 的非核心逻辑：
  // 批量操作 / 分组管理 / 导入
  // 通过依赖注入把 store 的状态与本地辅助方法传给 composable，
  // composable 内部直接修改同一份响应式状态，保证对外接口完全兼容。
  // ----------------------------------------------------------------
  const batchOps = useTestCaseBatchOps({
    testCases,
    error,
    fullGroupsMap,
    organizeTestCasesByGroup,
    extractTags,
    fetchTestCases,
    handleError
  });

  const groupsOps = useTestCaseGroups({
    testCases,
    testCaseGroups,
    tags,
    isLoading,
    error,
    allGroups,
    fullGroupsMap,
    groupsList,
    loadedGroupCases,
    groupLoadingStates,
    groupPagination,
    organizeTestCasesByGroup,
    extractTags,
    handleError,
    DEFAULT_GROUP_PAGE_SIZE
  });

  const importOps = useTestCaseImport({
    error,
    fetchTestCases,
    handleError
  });

  // 清空分组已加载用例缓存与分页,使下次展开时按最新筛选条件重新拉取
  const resetGroupCache = () => {
    loadedGroupCases.value = {};
    groupPagination.value = {};
  };

  // fetchCaseIdsByFilter 由 batchOps 委托提供（本文件旧本地实现已删——
  // 返回对象中被 ...batchOps 覆盖，从未生效且缺 onlyDeleted 参数）

  return {
    // 核心状态
    testCases,
    testCaseGroups,
    tags,
    isLoading,
    error,
    allGroups,
    fullGroupsMap,
    paginationInfo,
    groupsList,
    loadedGroupCases,
    groupLoadingStates,
    groupPagination,
    tagViewData,
    tagViewPagination,
    tagViewLoading,
    // 核心 CRUD + 本地状态操作
    fetchTestCases,
    fetchTagView,
    loadMoreTagView,
    refreshTagView,
    refreshView,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupPagination,
    addTestCase,
    updateTestCase,
    deleteTestCase,
    copyTestCase,
    copyGroupCases,
    copyTagCases,
    deleteTagCases,
    upsertTestCaseLocal,
    removeTestCaseLocal,
    patchTestCaseFavorite,
    organizeTestCasesByGroup,
    extractTags,
    resetGroupCache,
    // fetchCaseIdsByFilter 由 batchOps 委托提供（store 本地版本已收敛），避免重复键被覆盖
    // 委托：批量操作
    ...batchOps,
    // 委托：分组管理
    ...groupsOps,
    // 委托：导入
    ...importOps
  };
})
