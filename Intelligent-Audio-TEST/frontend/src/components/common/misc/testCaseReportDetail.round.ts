/**
 * TestCaseReportDetail —— 轮次编排子模块
 * 职责：轮次 Tab（roundTabs / activeRoundTab）、评分指标主维度归组表格
 * （子维度归入父维度组 + 主维度标题行）、执行结果区轮次过滤
 * （currentRoundResultTextFields / currentRoundReferenceTextFields / 轮次感知维度分组）
 */
import { computed, ref, watch } from 'vue';
import type {
  ComparisonDeviceData,
  GroupedMetricGroup,
  GroupedMetricItem,
  GroupedMetricRow,
  ReferenceTextField,
  ResultFieldGroup,
  ResultTextField,
  RoundTab,
  TestCaseReportDetailProps,
} from './testCaseReportDetail.types';
import { parseFieldRoundTag } from './testCaseReportDetail.fields';

/** 轮次编排上下文（fields / metrics 子模块产物注入，避免循环依赖） */
export interface RoundModuleContext {
  allMetricNames: { value: string[] }
  /** 取设备某指标展示值（含小数位/单位格式化） */
  getMetricDisplayValue: (device: string, metricKey: string) => number | string
  resultTextFields: { value: ResultTextField[] }
  referenceTextFields: { value: ReferenceTextField[] }
  subDimToParent: { value: Record<string, string> }
  groupFieldsByDimension: (
    fields: ResultTextField[],
    subDimParentMap: Record<string, string>
  ) => ResultFieldGroup[]
}

// 解析指标 key：提取基础名、轮次标记（'round:N' / 'overall' / null）
const parseMetricKey = (k: string): { base: string; roundTag: string | null } => {
  const m = k.match(/^(.*)@(round:(\d+)|overall)$/);
  if (!m) return { base: k, roundTag: null };
  if (m[2] === 'overall') return { base: m[1], roundTag: 'overall' };
  return { base: m[1], roundTag: `round:${m[3]}` };
};

/**
 * 轮次编排
 */
export function useTestCaseReportDetailRound(
  props: TestCaseReportDetailProps,
  ctx: RoundModuleContext
) {
  const { allMetricNames, getMetricDisplayValue, resultTextFields, referenceTextFields, subDimToParent, groupFieldsByDimension } = ctx;

  // 从 comparisonData 指标条目中获取某 key 对应的维度层级信息
  const getDimInfo = (k: string): { dimType: string; parentName: string; parentId: number | string | null } => {
    for (const d of Object.values(props.comparisonData || {}) as ComparisonDeviceData[]) {
      const entry = d?.metrics?.[k];
      if (entry && typeof entry === 'object') {
        // 指标条目为 camelCase ReadModel（经 Infrastructure adapter 归一化），直读即可
        return {
          dimType: entry.dimensionType ?? 'main',
          parentName: entry.parentDimensionName ?? '',
          parentId: entry.parentDimensionId ?? null,
        };
      }
    }
    return { dimType: 'main', parentName: '', parentId: null };
  };

  // 解包指标条目值：对象值形态 { value } 取内层，裸值原样返回
  const resolveMetricRaw = (device: string, metricKey: string): number | string | null | undefined => {
    const entry = props.comparisonData?.[device]?.metrics?.[metricKey];
    if (entry === null || entry === undefined) return entry;
    if (typeof entry === 'object') return (entry as { value?: number | string }).value ?? null;
    return entry;
  };

  // 判断指定轮次 Tab 是否有评估数据（至少一个设备有非空指标值）
  const tabHasMetricData = (roundTag: string | null) => {
    const keys = allMetricNames.value.filter(k => {
      const { roundTag: rt } = parseMetricKey(k);
      if (roundTag === null) return true;
      return rt === roundTag;
    });
    if (keys.length === 0) return false;
    return keys.some(k => (props.devices || []).some(device => {
      const raw = resolveMetricRaw(device, k);
      return raw !== '-' && raw !== null && raw !== undefined && raw !== '';
    }));
  };

  // 轮次 Tab 列表：从指标 key + 执行结果/参考字段中提取出现的轮次
  const roundTabs = computed<RoundTab[]>(() => {
    const tabs: RoundTab[] = [];
    const seen = new Set<string>();
    const pushTab = (roundTag: string) => {
      if (seen.has(roundTag)) return;
      seen.add(roundTag);
      if (roundTag === 'overall') {
        tabs.push({ key: 'overall', label: '整体', roundTag: 'overall', order: 9999 });
      } else {
        const rn = parseInt(roundTag.split(':')[1], 10);
        tabs.push({ key: roundTag, label: `第${rn}轮`, roundTag, order: rn });
      }
    };
    // 1. 从指标 key 中提取轮次
    allMetricNames.value.forEach(k => {
      const { roundTag } = parseMetricKey(k);
      if (roundTag) pushTab(roundTag);
    });
    // 2. 从执行结果/参考字段中提取轮次
    [...resultTextFields.value, ...referenceTextFields.value].forEach(field => {
      const roundTag = parseFieldRoundTag(field);
      if (roundTag) pushTab(roundTag);
    });
    // 如果有指标或字段但没有任何 roundTag（全部无后缀），就放一个默认 tab
    if (tabs.length === 0 && (allMetricNames.value.length > 0 || resultTextFields.value.length > 0 || referenceTextFields.value.length > 0)) {
      tabs.push({ key: 'all', label: '指标', roundTag: null, order: 0 });
    }
    tabs.sort((a, b) => a.order - b.order);
    // 过滤掉没有评估数据的"整体" Tab（只有配置了整体评估维度才显示）
    return tabs.filter(tab => tab.roundTag !== 'overall' || tabHasMetricData('overall'));
  });

  const activeRoundTab = ref(0);

  // 当前轮次 Tab 对应的指标 key 列表
  const currentRoundMetricKeys = computed<string[]>(() => {
    const tab = roundTabs.value[activeRoundTab.value];
    if (!tab) return [];
    return allMetricNames.value.filter(k => {
      const { roundTag } = parseMetricKey(k);
      // roundTag 为 null 的指标（无轮次标记）在所有 Tab 下都显示
      if (roundTag === null) return true;
      // 'all' tab 显示全部
      if (tab.roundTag === null) return true;
      return roundTag === tab.roundTag;
    });
  });

  // 按主维度分组的指标列表（子维度归入父维度组，用于层级显示）
  const groupedMetricsForCurrentRound = computed<GroupedMetricGroup[]>(() => {
    const keys = currentRoundMetricKeys.value;
    if (keys.length === 0) return [];

    // 收集每个 key 的基础名和层级信息
    const items: GroupedMetricItem[] = keys.map(k => {
      const { base } = parseMetricKey(k);
      const info = getDimInfo(k);
      return { metricKey: k, base, ...info };
    });

    // 构建分组：主维度自身为一组，子维度归入父维度组
    // groupKey = 子维度用 parentName，主维度用自身 base
    // 如果子维度的 parentName 为空（找不到父维度），则当作独立主维度处理
    const groupMap = new Map<string, GroupedMetricGroup>();
    items.forEach(item => {
      let effectiveType = item.dimType;
      let groupKey: string;
      if (item.dimType === 'sub' && item.parentName) {
        groupKey = item.parentName;
      } else {
        // 主维度或没有父维度名的子维度 → 当作独立主维度
        effectiveType = 'main';
        groupKey = item.base;
      }
      if (!groupMap.has(groupKey)) {
        groupMap.set(groupKey, {
          groupLabel: groupKey,
          mainItem: null,
          subItems: [],
        });
      }
      const group = groupMap.get(groupKey)!;
      if (effectiveType === 'main') {
        // 如果该组已有 mainItem（说明是空名子维度提升的），追加为子维度
        if (group.mainItem) {
          group.subItems.push(item);
        } else {
          group.mainItem = item;
        }
      } else {
        group.subItems.push(item);
      }
    });

    // 子维度按名称排序
    groupMap.forEach(g => {
      g.subItems.sort((a, b) => a.base.localeCompare(b.base, 'zh'));
    });

    // 分组按名称排序
    return Array.from(groupMap.values()).sort((a, b) =>
      a.groupLabel.localeCompare(b.groupLabel, 'zh')
    );
  });

  // 当前轮次的表格数据：仅当组内有子维度时插入分组标题行
  const currentRoundTableData = computed<GroupedMetricRow[]>(() => {
    const rows: GroupedMetricRow[] = [];
    let rowSeq = 0;
    groupedMetricsForCurrentRound.value.forEach(group => {
      // 当主维度名与分组名相同时，主维度行直接作为分组标题行，避免同名重复行
      const mainItemIsHeader = !!group.mainItem && group.mainItem.base === group.groupLabel;
      // 仅当组内有子维度且主维度名与分组名不同时，才插入独立分组标题行
      if (group.subItems.length > 0 && !mainItemIsHeader) {
        const headerRow: GroupedMetricRow = {
          _rowId: `hdr_${rowSeq++}`,
          metricName: group.groupLabel,
          isGroupHeader: true,
        };
        (props.devices || []).forEach(device => {
          headerRow[device] = '';
        });
        rows.push(headerRow);
      }
      // 主维度行（如有）
      if (group.mainItem) {
        const row: GroupedMetricRow = {
          _rowId: `main_${rowSeq++}`,
          metricName: group.mainItem.base,
          isSubDim: false,
          // 主维度名与分组名相同时，主维度行兼作分组标题
          isGroupHeader: mainItemIsHeader,
        };
        (props.devices || []).forEach(device => {
          row[device] = getMetricDisplayValue(device, group.mainItem!.metricKey);
        });
        rows.push(row);
      }
      // 子维度行
      group.subItems.forEach(sub => {
        const row: GroupedMetricRow = {
          _rowId: `sub_${rowSeq++}`,
          metricName: sub.base,
          isSubDim: true,
        };
        (props.devices || []).forEach(device => {
          row[device] = getMetricDisplayValue(device, sub.metricKey);
        });
        rows.push(row);
      });
    });
    return rows;
  });

  // 判断是否多轮场景：任一字段（结果/参考）带轮次标记
  const isMultiRoundFields = computed(() => {
    return resultTextFields.value.some(f => parseFieldRoundTag(f) !== null)
      || referenceTextFields.value.some(f => parseFieldRoundTag(f) !== null);
  });

  // 当前轮次 Tab 对应的结果文本字段
  const currentRoundResultTextFields = computed<ResultTextField[]>(() => {
    const fields = resultTextFields.value;
    const tab = roundTabs.value[activeRoundTab.value];
    if (!tab) return fields;
    // 非多轮场景：返回全部
    if (!isMultiRoundFields.value) return fields;
    // 整体 Tab：
    // - 无维度归属的字段（设备/API执行结果）：显示所有轮次
    // - 有维度归属的字段（评估结果）：只显示 roundTag === 'overall' 的字段
    if (tab.roundTag === 'overall') {
      return fields.filter(field => {
        if (!field.dimensionName) return true;
        return parseFieldRoundTag(field) === 'overall';
      });
    }
    // 按轮次过滤：有明确轮次标记的字段按轮次匹配，无轮次标记的字段在所有轮次 Tab 下都显示
    return fields.filter(field => {
      const roundTag = parseFieldRoundTag(field);
      if (tab.roundTag === null) return true;
      return roundTag === null || roundTag === tab.roundTag;
    });
  });

  // 当前轮次 Tab 对应的参考文本字段
  const currentRoundReferenceTextFields = computed<ReferenceTextField[]>(() => {
    const fields = referenceTextFields.value;
    const tab = roundTabs.value[activeRoundTab.value];
    if (!tab) return fields;
    if (!isMultiRoundFields.value) return fields;
    // 整体 Tab：显示所有轮次的参考数据
    if (tab.roundTag === 'overall') return fields;
    return fields.filter(field => {
      const roundTag = parseFieldRoundTag(field);
      if (tab.roundTag === null) return true;
      return roundTag === null || roundTag === tab.roundTag;
    });
  });

  // 轮次感知的维度分组（子维度归入父维度组），随轮次 Tab 切换
  const roundDimResultGroups = computed<ResultFieldGroup[]>(() => {
    return groupFieldsByDimension(currentRoundResultTextFields.value, subDimToParent.value)
      .filter(g => g.key !== '_general');
  });

  // 轮次感知的通用分组（设备/API 执行结果），随轮次 Tab 切换
  const roundGeneralResultGroup = computed<ResultFieldGroup>(() => {
    const groups = groupFieldsByDimension(currentRoundResultTextFields.value, subDimToParent.value);
    const found = groups.find(g => g.key === '_general');
    return found || { key: '_general', label: '设备/API 执行结果', fields: [] };
  });

  // 是否正在初始化（用于 watch 中判断是否需要自动选择第一个有评估数据的 Tab）
  const roundTabInitialized = ref(false);
  watch(roundTabs, (newTabs) => {
    const selectFirstWithData = () => {
      const firstWithDataIdx = newTabs.findIndex(tab => tabHasMetricData(tab.roundTag));
      activeRoundTab.value = firstWithDataIdx >= 0 ? firstWithDataIdx : 0;
    };
    if (!roundTabInitialized.value) {
      // 首次初始化时，选中第一个有评估数据的 Tab
      selectFirstWithData();
      roundTabInitialized.value = true;
    } else if (activeRoundTab.value >= newTabs.length) {
      // Tab 列表变化后，当前选中超出范围则重置
      selectFirstWithData();
    }
  }, { flush: 'post', immediate: true });

  return {
    roundTabs,
    activeRoundTab,
    currentRoundMetricKeys,
    groupedMetricsForCurrentRound,
    currentRoundTableData,
    isMultiRoundFields,
    currentRoundResultTextFields,
    currentRoundReferenceTextFields,
    roundDimResultGroups,
    roundGeneralResultGroup,
  };
}
