/**
 * Backend API Integration Service (barrel)
 *
 * This file is kept for backward compatibility.
 * The actual implementation has been split into per-domain files under ./api/
 * - Core HTTP request logic: ./api/http.ts
 * - Each API domain module: ./api/<domain>Api.ts
 * - Shared types: ../shared/types/algorithmTypes.ts
 */
export * from './api/index';
export { default } from './api/index';
