/**
 * API integration barrel module
 * Re-exports all API domain modules and core HTTP utilities
 */

// Core HTTP request utilities
export { request, apiBaseUrl, addRequestInterceptor, addResponseInterceptor, type RequestOptions } from '../http/client';

// API domain modules
export { authApi } from './authApi';
export { accessTokenApi } from './accessTokenApi';
export { tasksApi } from './tasksApi';
export { cherryPickApi } from './cherryPickApi';
export type {
  PickCartItem, PickCart, PickCandidate, PickPreview, PickCheckoutAction,
} from './cherryPickApi';
export { publishedTasksApi } from './publishedTasksApi';
export { logsApi } from './logsApi';
export { devicesApi, BATCH_LIST_PARAMS } from './devicesApi';
export type { DeviceListQueryParams } from './devicesApi';
export { laboratoriesApi } from './laboratoriesApi';
export type { LaboratoryListQueryParams } from './laboratoriesApi';
export { playbackApi } from './playbackApi';
export { apisApi } from './apisApi';
export { audiosApi } from './audiosApi';
export { groupsApi } from './groupsApi';
export { testcasesApi } from './testcasesApi';
export { evaluationApi } from './evaluationApi';
export { reportsApi } from './reportsApi';
export { reportStatisticsApi } from './reportStatisticsApi';
export { benchmarkApi } from './benchmarkApi';
export { benchmarkReportsApi } from './benchmarkReportsApi';
export { splApi } from './splApi';
export { apiRmsSplApi } from './apiRmsSplApi';
export { statsApi } from './statsApi';
export { algorithmApi } from './algorithmApi';
export { tagsApi } from './tagsApi';
export { llmProviderApi } from './llmProviderApi';
export { agentApi, AGENT_BACKEND_STATUS } from './agentApi';
export { downloadSkillPackage } from './agentSkillApi';
export type { DownloadSkillOptions } from './agentSkillApi';
export { optionsApi } from './optionsApi';
export { usersApi } from './usersApi';
export { rolesApi } from './rolesApi';
export { reviewApi } from './reviewApi';
export * from './reviewAiApi';

// Shared types (re-exported for backward compatibility with existing imports)
// TagCategory/TagItem 单一来源已收敛到 domain/model/tag.ts（businessTypes 链路）
export type { TagCategory, TagItem } from '../../domain/model/tag';
export type {
  AlgorithmDefinition,
  AlgorithmDeviceParam as AlgorithmParam,
  AlgorithmGroup,
  ParamMapping,
  FormSchema,
  FormField
} from '../../domain/model/algorithm';

// Default export mapping (matches the original api.ts default export)
import { tasksApi } from './tasksApi';
import { publishedTasksApi } from './publishedTasksApi';
import { logsApi } from './logsApi';
import { devicesApi } from './devicesApi';
import { laboratoriesApi } from './laboratoriesApi';
import { playbackApi } from './playbackApi';
import { apisApi } from './apisApi';
import { audiosApi } from './audiosApi';
import { groupsApi } from './groupsApi';
import { testcasesApi } from './testcasesApi';
import { evaluationApi } from './evaluationApi';
import { reportsApi } from './reportsApi';
import { benchmarkApi } from './benchmarkApi';
import { splApi } from './splApi';
import { apiRmsSplApi } from './apiRmsSplApi';
import { statsApi } from './statsApi';
import { algorithmApi } from './algorithmApi';
import { tagsApi } from './tagsApi';
import { optionsApi } from './optionsApi';
import { usersApi } from './usersApi';
import { rolesApi } from './rolesApi';

export default {
  tasks: tasksApi,
  publishedTasks: publishedTasksApi,
  logs: logsApi,
  devices: devicesApi,
  playback: playbackApi,
  laboratories: laboratoriesApi,
  apis: apisApi,
  audios: audiosApi,
  groups: groupsApi,
  testcases: testcasesApi,
  reports: reportsApi,
  benchmark: benchmarkApi,
  spl: splApi,
  apiRmsSpl: apiRmsSplApi,
  evaluation: evaluationApi,
  stats: statsApi,
  algorithm: algorithmApi,
  tags: tagsApi,
  options: optionsApi,
  users: usersApi,
  roles: rolesApi
};
