/**
 * INT-1983：标注 JSON 顶层 tags 解析（rounds 多轮 / flat 单轮 / txt 数组单轮）
 *
 * 契约：
 * - 三种形态的顶层 tags 均被解析进 TestCaseGroupStrategy.tags；
 * - 无 tags / 非数组 / 含非字符串项 → tags = []，轮次与分组照常解析，不抛异常；
 * - 数组内过滤非字符串、trim、去空、去重（保序）；
 * - 跨分组不串：同一目录下两个 JSON 各自 tags 不同，落到各自分组。
 */
import { describe, it, expect } from 'vitest';
import { buildTestCaseGroups } from '../testCaseStrategy';

function makeJsonFile(name: string, data: unknown): File {
  return new File([JSON.stringify(data)], name, { type: 'application/json' });
}

describe('INT-1983 标注 JSON 顶层 tags 解析', () => {
  it('rounds 多轮形态：顶层 tags 被解析，轮次照常', async () => {
    const file = makeJsonFile('rounds_case.json', {
      rounds: [{ roundNumber: 1, segments: [{ audioName: 'a.wav' }] }],
      tags: ['A', 'B'],
    });

    const groups = await buildTestCaseGroups([file]);

    const group = groups.get('rounds_case');
    expect(group).toBeTruthy();
    expect(group!.tags).toEqual(['A', 'B']);
    expect(group!.rounds).toHaveLength(1);
  });

  it('flat 单轮形态：顶层 tags 被解析', async () => {
    const file = makeJsonFile('flat_case.json', {
      audioName: 'x.wav',
      tags: ['C'],
    });

    const groups = await buildTestCaseGroups([file]);

    const group = groups.get('flat_case');
    expect(group).toBeTruthy();
    expect(group!.tags).toEqual(['C']);
    expect(group!.rounds).toHaveLength(1);
  });

  it('txt 数组单轮形态：顶层 tags 被解析', async () => {
    const file = makeJsonFile('txt_case.json', {
      txt: [{ audioName: 'x.wav' }],
      tags: ['D'],
    });

    const groups = await buildTestCaseGroups([file]);

    const group = groups.get('txt_case');
    expect(group).toBeTruthy();
    expect(group!.tags).toEqual(['D']);
    expect(group!.rounds).toHaveLength(1);
  });

  it('无 tags 字段 → tags = []，轮次与分组照常', async () => {
    const file = makeJsonFile('no_tags.json', {
      rounds: [{ roundNumber: 1, segments: [{ audioName: 'a.wav' }] }],
    });

    const groups = await buildTestCaseGroups([file]);

    const group = groups.get('no_tags');
    expect(group).toBeTruthy();
    expect(group!.tags).toEqual([]);
    expect(group!.rounds).toHaveLength(1);
  });

  it('tags 非数组（字符串）→ tags = []，不丢整组/轮次', async () => {
    const file = makeJsonFile('tags_not_array.json', {
      rounds: [{ roundNumber: 1, segments: [{ audioName: 'a.wav' }] }],
      tags: 'A,B',
    });

    const groups = await buildTestCaseGroups([file]);

    const group = groups.get('tags_not_array');
    expect(group!.tags).toEqual([]);
    expect(group!.rounds).toHaveLength(1);
  });

  it('tags 含非字符串 / 空白 / 重复项 → 过滤、trim、去重（保序）', async () => {
    const file = makeJsonFile('tags_dirty.json', {
      audioName: 'x.wav',
      tags: ['A', 1, null, ' ', ' A ', 'B', { k: 1 }, 'B'],
    });

    const groups = await buildTestCaseGroups([file]);

    expect(groups.get('tags_dirty')!.tags).toEqual(['A', 'B']);
  });

  it('跨分组不串：同一目录两个 JSON 的 tags 各自归属', async () => {
    const fileA = makeJsonFile('group_a.json', {
      audioName: 'a.wav',
      tags: ['标签A'],
    });
    const fileB = makeJsonFile('group_b.json', {
      audioName: 'b.wav',
      tags: ['标签B'],
    });

    const groups = await buildTestCaseGroups([fileA, fileB]);

    expect(groups.get('group_a')!.tags).toEqual(['标签A']);
    expect(groups.get('group_b')!.tags).toEqual(['标签B']);
  });
});
