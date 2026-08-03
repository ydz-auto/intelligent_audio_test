import { defineStore } from 'pinia'
import { ref } from 'vue'
import { testcasesApi } from '../utils/api'
import { convertTestCaseFormData } from '../utils/utils'
import { snakeToCamelObject } from '../utils/fieldNaming'
import { useNotification } from '../composables/modal/useNotification'
import { useTestCaseBatchOps } from '../composables/testCase/useTestCaseBatchOps'
import { useTestCaseGroups } from '../composables/testCase/useTestCaseGroups'
import { useTestCaseImport } from '../composables/testCase/useTestCaseImport'
import type {
  TestCase,
  TestCaseFormData,
  TestCaseGroup
} from '../shared/types'

interface GroupWithCount {
  id: string | number;
  name: string;
  description?: string;
  testCaseCount: number;
}

interface GroupPaginationInfo {
  page: number;
  pages: number;
  perPage: number;
  total: number;
  algorithmType?: string;
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
  const tagViewPagination = ref<{ page: number; pages: number; perPage: number; total: number }>({
    page: 1,
    pages: 1,
    perPage: 50,
    total: 0
  });

  interface LocalPaginationInfo {
    page: number;
    pages: number;
    perPage: number;
    total: number;
  }

  const paginationInfo = ref<LocalPaginationInfo>({
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

      const groupId = caseItem.groupId || 'default';
      const group = fullGroupsMap.value[groupId.toString()];
      const groupName = group?.name || caseItem.groupName || '默认分组';

      if (!groups[groupName]) {
        groups[groupName] = [];
      }
      groups[groupName].push(caseItem);
    });

    for (const groupName in groups) {
      groups[groupName].sort((a, b) => {
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
        testcasesApi.getGroups({ page: 1, perPage: 1000, algorithm_type: params.algorithmType, type: params.testType }),
        testcasesApi.getAll({
          page,
          perPage,
          keyword: params.keyword,
          tag: params.tag,
          group_id: params.groupId,
          type: params.testType,
          algorithm_type: params.algorithmType,
          include_deleted: params.includeDeleted || false
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
          testCaseCount: group.testCaseCount ?? group.test_case_count ?? 0
        };
      });

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
        const normalized = snakeToCamelObject(tc);
        return {
          ...normalized,
          type: normalized.type || 'api',
          deleted: normalized.deleted || false
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

  // 标签视图：调用 GET /testcases?view=tag，返回按标签聚合的数据
  const fetchTagView = async (params: Record<string, any> = {}) => {
    try {
      isLoading.value = true;
      error.value = null;

      const page = params.page || 1;
      const perPage = params.perPage || DEFAULT_FETCH_PAGE_SIZE;

      const response = await testcasesApi.getAll({
        page,
        perPage,
        view: 'tag',
        keyword: params.keyword,
        type: params.testType,
        algorithm_type: params.algorithmType,
        include_deleted: params.includeDeleted || false
      });

      const items: Array<{ tag: string; testCases: TestCase[] }> =
        response && Array.isArray((response as any).items) ? (response as any).items : [];

      const groups: Record<string, TestCase[]> = {};
      items.forEach(item => {
        const tagName = item.tag || '未分类';
        groups[tagName] = Array.isArray(item.testCases)
          ? item.testCases.map((tc: any) => snakeToCamelObject(tc) as TestCase)
          : [];
      });

      tagViewData.value = groups;
      tagViewPagination.value = {
        page: (response as any)?.page || 1,
        pages: (response as any)?.pages || 1,
        perPage: (response as any)?.perPage || perPage,
        total: typeof (response as any)?.total === 'number' ? (response as any).total : items.length
      };

      // 同步提取标签列表
      const tagSet = new Set<string>();
      items.forEach(item => {
        if (item.tag) tagSet.add(item.tag);
      });
      if (tagSet.size > 0) {
        tags.value = Array.from(tagSet);
      }
    } catch (err: any) {
      console.error('获取标签视图数据失败:', err);
      error.value = err.message || '获取标签视图数据失败';
      tagViewData.value = {};
    } finally {
      isLoading.value = false;
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
        type: testCase.type || 'api',
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

  // ----------------------------------------------------------------
  // 核心 CRUD：增 / 改 / 删 / 复制 / 复制分组用例
  // ----------------------------------------------------------------
  const addTestCase = async (data: TestCaseFormData) => {
    try {
      error.value = null;
      const response = await testcasesApi.create(convertTestCaseFormData(data));

      if (response && response.id) {
        const newTestCase = await testcasesApi.getOne(response.id);
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
      await testcasesApi.update(id, convertTestCaseFormData(data));

      const updatedTestCase = await testcasesApi.getOne(id);
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
      await testcasesApi.delete(id);
      removeTestCaseLocal(id);
      return true;
    } catch (err: any) {
      return handleError(err, '删除测试用例失败');
    }
  };

  const copyTestCase = async (id: string | number) => {
    try {
      error.value = null;
      const response = await testcasesApi.copy(id);

      if (response && response.id) {
        const newTestCase = await testcasesApi.getOne(response.id);
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
      await testcasesApi.batchAction('copy_by_group', [], { groupName });
      await fetchTestCases();
      return true;
    } catch (err: any) {
      return handleError(err, '复制分组用例失败');
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
    // 核心 CRUD + 本地状态操作
    fetchTestCases,
    fetchTagView,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupPagination,
    addTestCase,
    updateTestCase,
    deleteTestCase,
    copyTestCase,
    copyGroupCases,
    upsertTestCaseLocal,
    removeTestCaseLocal,
    organizeTestCasesByGroup,
    extractTags,
    resetGroupCache,
    // 委托：批量操作
    ...batchOps,
    // 委托：分组管理
    ...groupsOps,
    // 委托：导入
    ...importOps
  };
})
