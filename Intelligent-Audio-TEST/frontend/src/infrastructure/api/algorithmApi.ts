/**
 * Algorithm API module
 * HTTP 通道层：所有方法经 algorithmAdapter 做 snake_case ⇄ camelCase 转换
 * 对外只暴露 camelCase Domain 类型（domain/model/algorithm）
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
  AlgorithmOption,
  AlgorithmDimensions,
  AlgorithmCaseParam,
  AlgorithmDeviceParam,
  AlgorithmParamList,
  ParamMapping,
  FormSchema,
  ReloadConfigResult,
  AlgorithmImportResult,
  AlgorithmBulkDeleteResult,
  DimensionParam,
  ReferenceParam,
} from '../../domain/model/algorithm';
import { request, type RequestOptions } from '../http/client';
import {
  toAlgorithmDefinition,
  toAlgorithmDefinitionList,
  toAlgorithmGroup,
  toAlgorithmGroupList,
  toAlgorithmParamList,
  toParamMapping,
  toParamMappingList,
  toAlgorithmOptionList,
  toAlgorithmDimensions,
  toFormSchema,
  toAlgorithmCaseParam,
  toDimensionParamList,
  toReloadConfigResult,
  toAlgorithmImportResult,
  toAlgorithmBulkDeleteResult,
  toReferenceParamList,
  toReferenceParam,
  toCaseParamUpsertDto,
  toAlgorithmDefinitionDto,
  toParamMappingDto,
} from '../adapters/algorithmAdapter';

export const algorithmApi = {
  async getDefinitions(params: Record<string, any> = {}, options: RequestOptions = {}) {
    const raw = await request<{ data: any[]; total: number }>('GET', '/algorithm/definitions', null, { ...options, params });
    return { data: toAlgorithmDefinitionList(raw), total: raw?.total ?? 0 };
  },

  async getDefinition(algoType: string) {
    const raw = await request<any>('GET', `/algorithm/definitions/${algoType}`);
    return toAlgorithmDefinition(raw);
  },

  async createDefinition(data: Partial<AlgorithmDefinition>) {
    const raw = await request<any>('POST', '/algorithm/definitions', toAlgorithmDefinitionDto(data));
    return toAlgorithmDefinition(raw);
  },

  async updateDefinition(algoType: string, data: Partial<AlgorithmDefinition>) {
    const raw = await request<any>('PUT', `/algorithm/definitions/${algoType}`, toAlgorithmDefinitionDto(data));
    return toAlgorithmDefinition(raw);
  },

  async deleteDefinition(algoType: string) {
    return request<void>('DELETE', `/algorithm/definitions/${algoType}`);
  },

  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}) {
    const raw = await request<{ data: any[]; total: number }>('GET', '/algorithm/groups', null, { ...options, params });
    return { data: toAlgorithmGroupList(raw), total: raw?.total ?? 0 };
  },

  async getGroup(groupId: number) {
    const raw = await request<any>('GET', `/algorithm/groups/${groupId}`);
    return toAlgorithmGroup(raw);
  },

  async createGroup(data: Partial<AlgorithmGroup>) {
    const raw = await request<any>('POST', '/algorithm/groups', {
      name: data.name,
      description: data.description,
      icon: data.icon,
      display_order: data.displayOrder,
    });
    return toAlgorithmGroup(raw);
  },

  async updateGroup(groupId: number, data: Partial<AlgorithmGroup>) {
    const raw = await request<any>('PUT', `/algorithm/groups/${groupId}`, {
      name: data.name,
      description: data.description,
      icon: data.icon,
      display_order: data.displayOrder,
    });
    return toAlgorithmGroup(raw);
  },

  async deleteGroup(groupId: number) {
    return request<void>('DELETE', `/algorithm/groups/${groupId}`);
  },

  async getParams(params: Record<string, any> = {}, options: RequestOptions = {}) {
    const raw = await request<{ parameters: any[]; total: number }>('GET', '/algorithm/params', null, { ...options, params });
    return toAlgorithmParamList(raw);
  },

  async getParam(paramId: number) {
    const raw = await request<any>('GET', `/algorithm/params/${paramId}`);
    return toAlgorithmCaseParam(raw) as unknown as AlgorithmDeviceParam;
  },

  async createParam(data: Partial<AlgorithmDeviceParam>) {
    const raw = await request<any>('POST', '/algorithm/params', toCaseParamUpsertDto(data as Partial<AlgorithmCaseParam>));
    return toAlgorithmCaseParam(raw) as unknown as AlgorithmDeviceParam;
  },

  async updateParam(paramId: number, data: Partial<AlgorithmDeviceParam>) {
    const raw = await request<any>('PUT', `/algorithm/params/${paramId}`, toCaseParamUpsertDto(data as Partial<AlgorithmCaseParam>));
    return toAlgorithmCaseParam(raw) as unknown as AlgorithmDeviceParam;
  },

  async deleteParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/params/${paramId}`);
  },

  async getMappings(params: Record<string, any> = {}, options: RequestOptions = {}) {
    const raw = await request<{ mappings: any[]; total: number }>('GET', '/algorithm/mappings', null, { ...options, params });
    return { mappings: toParamMappingList(raw), total: raw?.total ?? 0 };
  },

  async createMapping(data: Partial<ParamMapping>) {
    const raw = await request<any>('POST', '/algorithm/mappings', toParamMappingDto(data));
    return toParamMapping(raw) as unknown as ParamMapping;
  },

  async updateMapping(mappingId: number, data: Partial<ParamMapping>) {
    const raw = await request<any>('PUT', `/algorithm/mappings/${mappingId}`, toParamMappingDto(data));
    return toParamMapping(raw) as unknown as ParamMapping;
  },

  async deleteMapping(mappingId: number) {
    return request<void>('DELETE', `/algorithm/mappings/${mappingId}`);
  },

  async getOptions() {
    const raw = await request<{ algorithms: any[] }>('GET', '/algorithm/options');
    return { algorithms: toAlgorithmOptionList(raw?.algorithms) };
  },

  async getFormSchema(algoType: string) {
    const raw = await request<any>('GET', `/algorithm/form-schema/${algoType}`);
    return toFormSchema(raw);
  },

  async getDimensions(algoType: string) {
    const raw = await request<any>('GET', `/algorithm/dimensions/${algoType}`);
    return toAlgorithmDimensions(raw);
  },

  async associateDimensions(algoType: string, dimensions: Array<{ dimensionId: number; weight?: number; isDefault?: boolean }>) {
    return request<void>('POST', `/algorithm/dimensions/${algoType}`, {
      dimensions: dimensions.map(d => ({
        dimension_id: d.dimensionId,
        weight: d.weight,
        is_default: d.isDefault,
      })),
    });
  },

  async createDimensionRelation(data: { algorithmType: string; dimensionId: number; weight?: number; isDefault?: boolean }) {
    const raw = await request<any>('POST', '/algorithm/dimension-relations', {
      algorithm_type: data.algorithmType,
      dimension_id: data.dimensionId,
      weight: data.weight,
      is_default: data.isDefault,
    });
    return {
      id: raw?.id ?? 0,
      algorithmType: raw?.algorithm_type ?? '',
      dimensionId: raw?.dimension_id ?? 0,
      weight: raw?.weight ?? 1,
      isDefault: raw?.is_default ?? false,
    };
  },

  async updateDimensionRelation(relationId: number, data: { weight?: number; isDefault?: boolean; dimensionId?: number }) {
    const raw = await request<any>('PUT', `/algorithm/dimension-relations/${relationId}`, {
      weight: data.weight,
      is_default: data.isDefault,
      dimension_id: data.dimensionId,
    });
    return {
      id: raw?.id ?? 0,
      algorithmType: raw?.algorithm_type ?? '',
      dimensionId: raw?.dimension_id ?? 0,
      weight: raw?.weight ?? 1,
      isDefault: raw?.is_default ?? false,
    };
  },

  async deleteDimensionRelation(relationId: number) {
    return request<void>('DELETE', `/algorithm/dimension-relations/${relationId}`);
  },

  async reloadConfig() {
    const raw = await request<any>('POST', '/algorithm/reload');
    return toReloadConfigResult(raw);
  },

  async importAlgorithms(data: { algorithms: any[] }) {
    const raw = await request<{ imported: string[] }>('POST', '/algorithm/import', data);
    return toAlgorithmImportResult(raw);
  },

  async bulkDelete(algorithmTypes: string[]) {
    const raw = await request<{ deleted_types: string[] }>('POST', '/algorithm/bulk-delete', { algorithm_types: algorithmTypes });
    return toAlgorithmBulkDeleteResult(raw);
  },

  async extractParams(caseConfig: Record<string, any>) {
    return request<Record<string, any>>('POST', '/algorithm/extract-params', { case_config: caseConfig });
  },

  async getDimensionParams(dimensionId: number) {
    const raw = await request<{ params: any[] }>('GET', `/algorithm/dimension-params/${dimensionId}`);
    return { params: toDimensionParamList(raw) };
  },

  async getCaseParams(algorithmType: string, scope?: string, options: RequestOptions = {}) {
    const params: Record<string, any> = {};
    if (algorithmType) params.algorithm_type = algorithmType;
    if (scope) params.scope = scope;
    const raw = await request<{ parameters: any[]; total: number }>('GET', '/algorithm/case-params', null, { ...options, params });
    return {
      parameters: (raw?.parameters ?? []).map((p: any) => toAlgorithmCaseParam(p)),
      total: raw?.total ?? 0,
    };
  },

  async getCaseParam(paramId: number) {
    const raw = await request<any>('GET', `/algorithm/case-params/${paramId}`);
    return toAlgorithmCaseParam(raw);
  },

  async createCaseParam(data: Partial<AlgorithmCaseParam>) {
    const raw = await request<any>('POST', '/algorithm/case-params', toCaseParamUpsertDto(data));
    return toAlgorithmCaseParam(raw);
  },

  async updateCaseParam(paramId: number, data: Partial<AlgorithmCaseParam>) {
    const raw = await request<any>('PUT', `/algorithm/case-params/${paramId}`, toCaseParamUpsertDto(data));
    return toAlgorithmCaseParam(raw);
  },

  async deleteCaseParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/case-params/${paramId}`);
  },

  async getReferenceParams(algoType: string, options: RequestOptions = {}) {
    const raw = await request<{ data: any[]; total: number }>('GET', '/algorithm/reference-params', null, { ...options, params: { algorithm_type: algoType } });
    return { data: toReferenceParamList(raw?.data), total: raw?.total ?? 0 };
  },

  async getReferenceParam(paramId: number, algoType: string) {
    const raw = await request<any>('GET', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
    return raw ? toReferenceParam(raw) : null;
  },

  async createReferenceParam(data: Partial<ReferenceParam> & { algorithmType?: string }) {
    const raw = await request<any>('POST', '/algorithm/reference-params', {
      code: data.code,
      name: data.name,
      type: data.type,
      help_text: data.helpText,
      algorithm_type: data.algorithmType,
      annotation_code: data.annotationCode,
      annotation_format: data.annotationFormat,
      field_path: data.fieldPath,
      merge_mode: data.mergeMode,
    });
    return toReferenceParam(raw);
  },

  async updateReferenceParam(paramId: number, algoType: string, data: Partial<ReferenceParam>) {
    const raw = await request<any>('PUT', `/algorithm/reference-params/${paramId}`, {
      code: data.code,
      name: data.name,
      type: data.type,
      help_text: data.helpText,
      annotation_code: data.annotationCode,
      annotation_format: data.annotationFormat,
      field_path: data.fieldPath,
      merge_mode: data.mergeMode,
      algorithm_type: algoType,
    });
    return toReferenceParam(raw);
  },

  async deleteReferenceParam(paramId: number, algoType: string) {
    return request<void>('DELETE', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
  }
};
