/**
 * 全局枚举（enum 化，拒绝魔法字符串）
 */

/** 已发布任务状态 */
export const PublishedTaskStatus = {
  PUBLISHED: 'published',
  ARCHIVED: 'archived',
} as const;

export type PublishedTaskStatusValue = (typeof PublishedTaskStatus)[keyof typeof PublishedTaskStatus];

/** 已发布任务状态文案 */
export const PublishedTaskStatusText: Record<PublishedTaskStatusValue, string> = {
  [PublishedTaskStatus.PUBLISHED]: '已发布',
  [PublishedTaskStatus.ARCHIVED]: '已归档',
};

/** 权限点（对齐后端 PermissionPoints / 主文档「资源:操作」命名） */
export const PermissionPoint = {
  TASK_PUBLISH: 'task:publish',
  PUBLISHED_TASK_READ: 'published_task:read',
  PUBLISHED_TASK_EXECUTE: 'published_task:execute',
  PUBLISHED_TASK_VERSION: 'published_task:version',
  PUBLISHED_TASK_ARCHIVE: 'published_task:archive',
} as const;

export type PermissionPointValue = (typeof PermissionPoint)[keyof typeof PermissionPoint];
