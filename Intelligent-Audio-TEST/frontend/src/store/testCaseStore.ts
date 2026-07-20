import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { testcasesApi, groupsApi } from '../utils/api'
import { convertTestCaseFormData } from '../utils/utils'
import { useNotification } from '../composables/useNotification'
import type { 
  TestCase, 
  TestCaseFormData,
  GroupFormData,
  TestCaseGroup
} from '../shared/types'
import type { PaginatedData } from '../shared/types'

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

  const formatImportErrorsMessage = (title: string, errors: unknown) => {
    const list = Array.isArray(errors) ? errors.map(String).filter(Boolean) : [];
    if (list.length === 0) return title;
    const maxLines = 50;
    const shown = list.slice(0, maxLines).join('\n');
    const more = list.length > maxLines ? `\n...（共${list.length}条）` : '';
    return `${title}\n${shown}${more}`;
  };

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

  const fetchTestCases = async (params: Record<string, any> = {}) => {
    try {
      isLoading.value = true;
      error.value = null;
      
      const page = params.page || 1;
      const perPage = params.perPage || DEFAULT_FETCH_PAGE_SIZE;
      
      const [groupsResponse, testCasesResponse] = await Promise.all([
        testcasesApi.getGroups({ page: 1, perPage: 1000, algorithm_type: params.algorithmType }),
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
      
      testCases.value = testCasesData.map(tc => ({
        ...tc,
        type: tc.type || 'api',
        deleted: tc.deleted || false
      }));
      
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
        groups[tagName] = Array.isArray(item.testCases) ? item.testCases : [];
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

  const fetchGroupsList = async (params: Record<string, any> = {}) => {
    try {
      isLoading.value = true;
      error.value = null;
      
      const page = params.page || 1;
      const perPage = params.perPage || 100;
      
      const response = await groupsApi.getAll({ 
        page, 
        perPage, 
        algorithmType: params.algorithmType 
      });
      
      if (response && response.items) {
        groupsList.value = response.items.map((g: any) => ({
          id: g.id,
          name: g.name,
          description: g.description,
          testCaseCount: g.testCaseCount ?? g.test_case_count ?? 0
        }));
        
        fullGroupsMap.value = response.items.reduce((map: Record<string, TestCaseGroup>, g: any) => {
          const id = g.id?.toString() || `group-${Date.now()}`;
          map[id] = { ...g, id, name: g.name } as TestCaseGroup;
          return map;
        }, {} as Record<string, TestCaseGroup>);
        
        allGroups.value = groupsList.value.map(g => g.name);
        
        const initialGroups: Record<string, TestCase[]> = {};
        groupsList.value.forEach(g => {
          initialGroups[g.name] = [];
        });
        testCaseGroups.value = initialGroups;
      }
      
      return groupsList.value;
    } catch (err: any) {
      console.error('获取分组列表失败:', err);
      error.value = err.message || '获取分组列表失败';
      return [];
    } finally {
      isLoading.value = false;
    }
  };

  const fetchCasesByGroup = async (groupId: string | number, params: Record<string, any> = {}) => {
    const groupKey = groupId.toString();
    
    if (groupLoadingStates.value[groupKey]) {
      return;
    }
    
    try {
      groupLoadingStates.value[groupKey] = true;
      error.value = null;
      
      const page = params.page || 1;
      const perPage = params.perPage || DEFAULT_GROUP_PAGE_SIZE;
      
      const response = await testcasesApi.getAll({
        page,
        perPage,
        group_id: groupId,
        keyword: params.keyword,
        tag: params.tag,
        algorithm_type: params.algorithmType,
        include_deleted: params.includeDeleted || false
      });
      
      let casesData: TestCase[] = [];
      if (response && response.items) {
        casesData = response.items.map((tc: any) => ({
          ...tc,
          type: tc.type || 'api',
          deleted: tc.deleted || false
        }));
      }
      
      if (page === 1) {
        loadedGroupCases.value[groupKey] = casesData;
      } else {
        loadedGroupCases.value[groupKey] = [
          ...(loadedGroupCases.value[groupKey] || []),
          ...casesData
        ];
      }
      
      groupPagination.value[groupKey] = {
        page: response?.page || page,
        pages: response?.pages || 1,
        perPage: response?.perPage || perPage,
        total: response?.total || 0
      };
      
      const group = fullGroupsMap.value[groupKey];
      const groupName = group?.name || `分组-${groupKey}`;
      testCaseGroups.value[groupName] = [...(loadedGroupCases.value[groupKey] || [])];
      
      casesData.forEach(tc => {
        const existingIndex = testCases.value.findIndex(t => t.id === tc.id);
        if (existingIndex === -1) {
          testCases.value.push(tc);
        } else {
          testCases.value[existingIndex] = tc;
        }
      });
      
      extractTags();
      
      return {
        cases: casesData,
        pagination: groupPagination.value[groupKey],
        hasMore: (response?.page || 1) < (response?.pages || 1)
      };
    } catch (err: any) {
      console.error(`获取分组 ${groupId} 用例失败:`, err);
      error.value = err.message || `获取分组用例失败`;
      return null;
    } finally {
      groupLoadingStates.value[groupKey] = false;
    }
  };

  const loadMoreGroupCases = async (groupId: string | number) => {
    const groupKey = groupId.toString();
    const currentPagination = groupPagination.value[groupKey];
    
    if (!currentPagination || currentPagination.page >= currentPagination.pages) {
      return null;
    }
    
    return fetchCasesByGroup(groupId, { page: currentPagination.page + 1 });
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

  const batchUpdateAlgorithmParams = async (ids: (string | number)[], algorithmParams: Record<string, any>) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('update_algorithm_params', ids, { algorithmParams });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc) {
          tc.algorithmParams = algorithmParams;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量更新用例专属参数失败');
    }
  };

  const batchUpdatePlaybackDevices = async (ids: (string | number)[], playbackDevices: Record<string, any>) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('update_playback_devices', ids, { playbackDevices });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc && tc.config) {
          const config = { ...tc.config };
          // Rounds-based format
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              audios: Array.isArray(round.audios)
                ? round.audios.map((audio: any) => ({
                    ...audio,
                    playbackDeviceId: playbackDevices.deviceId
                  }))
                : round.audios
            }));
          }
          // Legacy flat format fallback
          else if (config.audios) {
            config.audios = config.audios.map((audio: any) => {
              const audioType = (audio.testType || audio.test_type || '').toLowerCase();
              if (audioType === 'e2e') {
                return { ...audio, testType: 'e2e', playbackDeviceId: playbackDevices.deviceId };
              }
              return audio;
            });
          }
          tc.config = config;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量更新播放设备失败');
    }
  };

  const batchUpdateSPL = async (ids: (string | number)[], spl: Record<string, any>) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('update_spl', ids, { spl });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc && tc.config) {
          const config = { ...tc.config };
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              audios: Array.isArray(round.audios)
                ? round.audios.map((audio: any) => ({ ...audio, spl: spl.value }))
                : round.audios
            }));
          } else if (config.audios) {
            config.audios = config.audios.map((audio: any) => {
              const audioType = (audio.testType || audio.test_type || '').toLowerCase();
              if (audioType === 'e2e') {
                return { ...audio, testType: 'e2e', spl: spl.value };
              }
              return audio;
            });
          }
          tc.config = config;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量更新声压失败');
    }
  };

  const batchMoveCases = async (ids: (string | number)[], groupId: string) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('move_to_group', ids, { target_group_id: groupId });
      
      const group = fullGroupsMap.value[groupId];
      const groupName = group?.name || '未知分组';
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc) {
          tc.groupId = groupId;
          tc.groupName = groupName;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量移动用例失败');
    }
  };

  const batchCopyCases = async (ids: (string | number)[], groupId: string) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('copy_to_group', ids, { target_group_id: groupId });
      await fetchTestCases();
      return true;
    } catch (err: any) {
      return handleError(err, '批量复制用例失败');
    }
  };

  const batchUpdateDimensions = async (ids: (string | number)[], dimensions: any[], testType: string) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('update_dimensions', ids, { dimensions, test_type: testType });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc && tc.config) {
          const config = { ...tc.config };
          // Both rounds and legacy formats store dimensions at top level
          config.dimensions = dimensions;
          // For rounds format, also update evaluation within each round
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              evaluation: round.evaluation
                ? { ...round.evaluation, dimensions: dimensions }
                : { dimensions: dimensions }
            }));
          }
          tc.config = config;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量更新评价维度失败');
    }
  };

  const batchUpdateNoise = async (ids: (string | number)[], audioId: string, spl: number, deviceIds: string[]) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('update_noise', ids, { noise_audio_id: audioId, noise_spl: spl, noise_device_ids: deviceIds });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc) {
          const config = tc.config ? { ...tc.config } : {};
          const noiseConfig = {
            audioId: audioId,
            spl: spl,
            deviceIds: deviceIds,
            loop: false,
          };
          // Rounds-based format: update backgroundNoise in each round
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              backgroundNoise: noiseConfig
            }));
          } else {
            // Legacy flat format
            config.backgroundNoise = { audioId: audioId, spl: spl, deviceIds: deviceIds };
          }
          tc.config = config;
        }
      });
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量更新噪声配置失败');
    }
  };

  const batchAutoGenerateName = async (ids: (string | number)[]) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('auto_generate_name', ids, {});
      await fetchTestCases();
      return true;
    } catch (err: any) {
      return handleError(err, '批量自动生成用例名失败');
    }
  };

  const batchAddTags = async (ids: (string | number)[], newTags: string[]) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('add_tags', ids, { tags: newTags });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc) {
          const existingTagNames = new Set(tc.tags?.map(t => typeof t === 'string' ? t : t.name) || []);
          newTags.forEach(tagName => {
            if (!existingTagNames.has(tagName)) {
              if (!tc.tags) tc.tags = [];
              tc.tags.push(tagName as any);
            }
          });
        }
      });
      extractTags();
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量添加标签失败');
    }
  };

  const batchRemoveTags = async (ids: (string | number)[], tagsToRemove: string[]) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('remove_tags', ids, { tags: tagsToRemove });
      
      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id);
        if (tc && tc.tags) {
          tc.tags = tc.tags.filter((tag): tag is string | { id: number; name: string } => {
            const tagName = typeof tag === 'string' ? tag : tag.name;
            return !tagsToRemove.includes(tagName);
          }) as typeof tc.tags;
        }
      });
      extractTags();
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '批量移除标签失败');
    }
  };

  const batchRenameTag = async (oldTagName: string, newTagName: string) => {
    try {
      error.value = null;
      await testcasesApi.batchAction('rename_tag', [], { old_tag_name: oldTagName, new_tag_name: newTagName });
      
      testCases.value.forEach(tc => {
        if (tc.tags) {
          tc.tags = tc.tags.map(tag => {
            const tagName = typeof tag === 'string' ? tag : tag.name;
            if (tagName === oldTagName) {
              return newTagName as any;
            }
            return tag;
          });
        }
      });
      extractTags();
      return true;
    } catch (err: any) {
      return handleError(err, '重命名标签失败');
    }
  };

  const batchRefreshReference = async (ids: (string | number)[]) => {
    try {
      error.value = null;
      const result: any = await testcasesApi.batchAction('refresh_reference', ids, {});
      if (result?.task_id) {
        return { taskId: result.task_id };
      }
      await fetchTestCases();
      return true;
    } catch (err: any) {
      return handleError(err, '刷新用例参考失败');
    }
  };

  const pollRefreshTaskStatus = async (taskId: string, onProgress?: (progress: number) => void): Promise<{ success: boolean; updated: number; failed: number }> => {
    return new Promise((resolve) => {
      const poll = async () => {
        try {
          const status: any = await testcasesApi.getRefreshTaskStatus(taskId);

          if (status.status === 'not_found') {
            resolve({ success: false, updated: 0, failed: 0 });
            return;
          }

          if (onProgress && typeof status.progress === 'number') {
            onProgress(status.progress);
          }

          if (status.status === 'completed' || status.status === 'failed') {
            resolve({
              success: status.status === 'completed',
              updated: status.updated || 0,
              failed: status.failed || 0
            });
            return;
          }

          setTimeout(poll, 1000);
        } catch (err) {
          console.error('[pollRefreshTaskStatus] 查询任务状态失败:', err);
          resolve({ success: false, updated: 0, failed: 0 });
        }
      };

      poll();
    });
  };

  const addGroup = async (data: GroupFormData) => {
    try {
      error.value = null;
      const response = await testcasesApi.createGroup(data);
      if (response) {
        const id = (response as any).id || `group-${Date.now()}`;
        fullGroupsMap.value[id] = { 
          ...response, 
          id, 
          name: data.name 
        } as TestCaseGroup;
        allGroups.value = Object.keys(fullGroupsMap.value).map(k => fullGroupsMap.value[k].name);
      }
      return true;
    } catch (err: any) {
      return handleError(err, '添加分组失败');
    }
  };

  const updateGroup = async (idOrName: string | number, data: GroupFormData) => {
    try {
      error.value = null;
      let groupId: string | number;

      if (typeof idOrName === 'string') {
        const groupEntry = Object.entries(fullGroupsMap.value).find(([_, group]) => group.name === idOrName);
        if (groupEntry) {
          groupId = groupEntry[0];
        } else {
          // fullGroupsMap 为空时（如按 algorithm_type 过滤后分组不匹配），从后端查找
          try {
            const resp = await testcasesApi.getGroups({ page: 1, perPage: 1000 });
            const found = resp?.items?.find((g: any) => g.name === idOrName);
            if (found) {
              groupId = found.id;
            } else {
              throw new Error(`未找到名为 "${idOrName}" 的分组`);
            }
          } catch {
            throw new Error(`未找到名为 "${idOrName}" 的分组`);
          }
        }
      } else {
        groupId = idOrName;
      }

      await testcasesApi.updateGroup(groupId, data);

      if (fullGroupsMap.value[groupId.toString()]) {
        fullGroupsMap.value[groupId.toString()].name = data.name;
        fullGroupsMap.value[groupId.toString()].description = data.description;
        if (data.algorithmType !== undefined) {
          fullGroupsMap.value[groupId.toString()].algorithmType = data.algorithmType;
        }
      }
      organizeTestCasesByGroup();
      return true;
    } catch (err: any) {
      return handleError(err, '更新分组失败');
    }
  };

  const deleteGroup = async (idOrName: string | number) => {
    try {
      error.value = null;
      let groupId: string | number;

      if (typeof idOrName === 'string') {
        const groupEntry = Object.entries(fullGroupsMap.value).find(([_, group]) => group.name === idOrName);
        if (groupEntry) {
          groupId = groupEntry[0];
        } else {
          // fullGroupsMap 为空时，从后端查找
          try {
            const resp = await testcasesApi.getGroups({ page: 1, perPage: 1000 });
            const found = resp?.items?.find((g: any) => g.name === idOrName);
            if (found) {
              groupId = found.id;
            } else {
              throw new Error(`未找到名为 "${idOrName}" 的分组`);
            }
          } catch {
            throw new Error(`未找到名为 "${idOrName}" 的分组`);
          }
        }
      } else {
        groupId = idOrName;
      }

      await testcasesApi.deleteGroup(groupId);
      
      delete fullGroupsMap.value[groupId.toString()];
      testCases.value = testCases.value.filter(tc => tc.groupId?.toString() !== groupId.toString());
      
      organizeTestCasesByGroup();
      notification.success('删除分组成功');
      return true;
    } catch (err: any) {
      return handleError(err, '删除分组失败');
    }
  };

  const importTestCases = async (formData: FormData) => {
    try {
      error.value = null;
      const result: any = await testcasesApi.importCases(formData);

      const importedCount = Number(result?.importedCount ?? result?.imported_count ?? 0);
      const updatedCount = Number(result?.updatedCount ?? result?.updated_count ?? 0);
      const errors = Array.isArray(result?.errors) ? result.errors : [];

      if (errors.length > 0) {
        const title = (importedCount > 0 || updatedCount > 0)
          ? `导入完成，但有 ${errors.length} 个失败（成功导入 ${importedCount}，更新 ${updatedCount}）`
          : `导入失败：${errors.length} 个失败`;
        error.value = title;
        alert(formatImportErrorsMessage(title, errors));
      }

      if (importedCount > 0 || updatedCount > 0) {
        await fetchTestCases();
      }

      return importedCount > 0 || updatedCount > 0 || errors.length === 0;
    } catch (err: any) {
      return handleError(err, '导入测试用例失败');
    }
  };

  return {
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
    fetchTestCases,
    fetchTagView,
    fetchGroupsList,
    fetchCasesByGroup,
    loadMoreGroupCases,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupPagination,
    addTestCase,
    updateTestCase,
    deleteTestCase,
    copyTestCase,
    copyGroupCases,
    batchUpdateAlgorithmParams,
    batchUpdatePlaybackDevices,
    batchUpdateSPL,
    batchMoveCases,
    batchCopyCases,
    batchUpdateDimensions,
    batchUpdateNoise,
    batchAutoGenerateName,
    batchAddTags,
    batchRemoveTags,
    batchRenameTag,
    batchRefreshReference,
    pollRefreshTaskStatus,
    addGroup,
    updateGroup,
    deleteGroup,
    importTestCases,
    upsertTestCaseLocal,
    removeTestCaseLocal
  };
})
