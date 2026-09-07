/**
 * Groups API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 查询参数/请求体显式 snake_case（per_page/algorithm_type/test_type/case_ids 等）。
 */
import { request, type RequestOptions } from '../http/client';
import { toPaginated } from '../adapters/commonAdapter';
import {
  toGroup,
  toGroupQueryDto,
  toGroupCreateDto,
  toGroupUpdateDto,
  toGroupMoveCasesDto,
} from '../adapters/groupAdapter';
import type { GroupListDto } from '../dto/groupDto';
import type { TestCaseGroup } from '../../domain/model/testCase';

/** 分组列表查询入参（camelCase Domain） */
export interface GroupListQuery {
  page?: number
  perPage?: number
  algorithmType?: string
  /** 测试类型过滤（后端 test_type，兼容 type 别名） */
  testType?: string
  keyword?: string
}

export const groupsApi = {
  /** 分组列表 → Paginated<TestCaseGroup>（camelCase，含 testCaseCount） */
  async getAll(params: GroupListQuery = {}, options: RequestOptions = {}) {
    const dto = await request<GroupListDto>('GET', '/groups', null, {
      ...options,
      params: toGroupQueryDto(params),
    });
    return toPaginated(dto, toGroup);
  },

  /**
   * 创建分组（请求体 name/description/algorithm_type）
   * 后端仅返回 StringIdData（{ id }，无字段名转换需求），不含完整分组对象；
   * 完整分组信息由调用方通过 getAll 回查。
   */
  async create(groupData: { name: string; description?: string; algorithmType?: string }, options: RequestOptions = {}): Promise<{ id: string }> {
    return request<{ id: string }>('POST', '/groups', toGroupCreateDto(groupData), options);
  },

  /** 更新分组（后端仅返回 StringIdData：{ id }） */
  async update(id: string | number, groupData: { name?: string; description?: string; algorithmType?: string }, options: RequestOptions = {}): Promise<{ id: string }> {
    return request<{ id: string }>('PUT', `/groups/${id}`, toGroupUpdateDto(groupData), options);
  },

  /** 删除分组（cascade 查询参数；默认 true 兼容旧调用行为） */
  async delete(id: string | number, cascade: boolean = true, options: RequestOptions = {}) {
    return request<void>('DELETE', `/groups/${id}`, null, {
      ...options,
      params: { cascade },
    });
  },

  /** 移动用例到目标分组（请求体 case_ids + target_group_id） */
  async moveCases(_sourceId: string | number, targetId: string | number, caseIds: (string | number)[]) {
    return request('POST', '/groups/move-cases', toGroupMoveCasesDto(String(targetId), caseIds));
  }
};

export type { TestCaseGroup };
