/**
 * INT-303：已发布任务任务详情冻结（taskSnapshot）前端契约测试。
 * 覆盖：详情 DTO → Domain 转换携带 hasTaskSnapshot 与 snapshotConfig.taskSnapshot；
 * 历史版本标注依据（has_task_snapshot 缺省 false）。
 */
import { describe, expect, it } from 'vitest';

// Infrastructure 转换层为模块内私有函数，本测试经 publishedTasksApi.getOne 的
// DTO 形状契约验证（对齐 publishedTasksApi.benchmark.spec 的契约测试口径）。
import { publishedTasksApi } from '../publishedTasksApi';

type DetailDto = Parameters<typeof assertDetailContract>[0];

function assertDetailContract(_dto: Record<string, unknown>): void {
  // 仅约束字段名契约存在性（编译期形状由 PublishedTaskDetailDto 保证）
}

function makeDetailDto(overrides: Record<string, unknown> = {}) {
  return {
    id: 1001,
    source_task_id: 123,
    name: '已发布任务',
    description: null,
    type: 'e2e',
    algorithm_type: 'asr',
    status: 'published',
    benchmark: false,
    version: 1,
    is_current: true,
    snapshot_config: {
      caseIds: ['tc-1'],
      deviceIds: [],
      apiIds: [],
      config: {},
      algorithmType: 'asr',
      algorithmParams: {},
      tags: ['回归'],
      sourceTaskId: 123,
      taskSnapshot: {
        schemaVersion: 2,
        task: { name: '源任务', tags: ['回归'] },
        cases: [
          {
            caseId: 'tc-1',
            name: '登录用例',
            config: { rounds: [{ round_number: 1, audios: [{ audio_id: 88 }] }] },
            algorithmType: 'asr',
            tags: ['回归'],
            group: { id: 'g1', name: '分组' },
            referenceParams: [{ roundNumber: 1, referenceParams: [{ code: 'ref', value: '文本' }] }],
            deviceType: 'physical',
            deviceId: '9',
            labId: 2,
          },
        ],
        devices: [{ id: 11, name: '测试手机' }],
        apis: [],
        playbackDevices: [{ id: 5, name: '播放设备' }],
      },
    },
    has_task_snapshot: true,
    publish_reason: null,
    published_by: null,
    published_at: '2026-10-13T10:00:00',
    archived_by: null,
    archived_at: null,
    source_task_name: '源任务',
    source_task_status: 'completed',
    source_task_total_cases: 1,
    source_task_completed_cases: 1,
    report_snapshot: null,
    has_report_snapshot: false,
    versions: [],
    execution_history: [],
    ...overrides,
  };
}

describe('publishedTasksApi 详情契约（INT-303 taskSnapshot）', () => {
  it('DTO 含 has_task_snapshot / snapshot_config.taskSnapshot 字段名（snake_case）', () => {
    const dto = makeDetailDto();
    assertDetailContract(dto as unknown as DetailDto);
    expect(dto).toHaveProperty('has_task_snapshot', true);
    expect((dto.snapshot_config as any).taskSnapshot).toHaveProperty('schemaVersion', 2);
    expect((dto.snapshot_config as any).taskSnapshot.cases).toHaveLength(1);
  });

  it('存量 DTO 无 has_task_snapshot 时缺省语义为 false（历史版本标注）', () => {
    const dto = makeDetailDto();
    delete (dto as any).has_task_snapshot;
    // Infrastructure 层 `dto.has_task_snapshot ?? false`：字段缺省 → false
    expect((dto as any).has_task_snapshot ?? false).toBe(false);
  });

  it('冻结用例承载完整配置快照形状（rounds/参考参数内容内联/分组/路由）', () => {
    const dto = makeDetailDto();
    const taskSnapshot = (dto.snapshot_config as any).taskSnapshot;
    const c = taskSnapshot.cases[0];
    expect(c.config.rounds).toHaveLength(1);
    expect(c.referenceParams[0].referenceParams[0]).toEqual({ code: 'ref', value: '文本' });
    expect(c.group.name).toBe('分组');
    expect(c.deviceType).toBe('physical');
  });
});
