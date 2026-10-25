// -*- coding: utf-8 -*-
/**
 * 容器详情「报告」区数据（INT-1837 · 规范 18 §7「无报告」态 / §8.2 线框）。
 *
 * 容器无执行过程、不自动生成报告：
 * - 已有报告：`GET /reports?task_id=` 复用既有列表端点取最新一份（不新增端点）；
 * - 空态：引导手动生成，`POST /reports/generate-task` 复用既有生成端点（不新增端点）；
 * - 生成是后端异步的（返回后报告行可能稍后才落库）→ 轮询列表直到出现，最长 60s，
 *   期间呈现「报告生成中…」，不谎报「暂无报告」。
 *
 * Application 层：只见 Domain（camelCase），API 访问收敛到 reportsPort。
 */
import { onBeforeUnmount, ref, unref, watch, type Ref } from 'vue';
import { reportsPort } from '../report/reportsPort';
import { useNotification } from '../modal/useNotification';
import type { Report } from '../../domain/model/report';

/** 生成后轮询报告列表的间隔 / 上限（后端异步落库） */
const REPORT_POLL_INTERVAL_MS = 2000;
const REPORT_POLL_TIMEOUT_MS = 60_000;

export function useContainerReport(taskId: Ref<number | null | undefined>) {
  const notification = useNotification();
  /** 本任务最新一份报告（无 → null） */
  const report = ref<Report | null>(null);
  const loading = ref(false);
  /** 报告列表加载失败（空态 + 重试，不阻断详情其余区域） */
  const error = ref(false);
  /** 已触发生成、等待后端落库（轮询中） */
  const generating = ref(false);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let pollTimeout: ReturnType<typeof setTimeout> | null = null;
  // 竞态防护：详情模态窗可连续切任务
  let token = 0;

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (pollTimeout) {
      clearTimeout(pollTimeout);
      pollTimeout = null;
    }
  }

  async function load(silent = false): Promise<void> {
    const id = Number(unref(taskId));
    if (!Number.isFinite(id) || id <= 0) {
      report.value = null;
      loading.value = false;
      error.value = false;
      return;
    }
    const current = ++token;
    if (!silent) loading.value = true;
    try {
      const page = await reportsPort.getAll({
        page: 1,
        perPage: 1,
        sortBy: 'created_at',
        order: 'desc',
        taskId: id,
        favorite: false,
        deleted: false,
      });
      if (current !== token) return;
      report.value = page.items[0] ?? null;
      error.value = false;
    } catch {
      if (current !== token) return;
      // 轮询期间的瞬时失败不清空已取到的报告
      if (!silent) {
        report.value = null;
        error.value = true;
      }
    } finally {
      if (current === token && !silent) loading.value = false;
    }
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      if (report.value) {
        generating.value = false;
        stopPolling();
        return;
      }
      void load(true);
    }, REPORT_POLL_INTERVAL_MS);
    // 超时按「暂无报告」收尾（后端可能更久，用户刷新可再查）
    pollTimeout = setTimeout(() => {
      generating.value = false;
      stopPolling();
    }, REPORT_POLL_TIMEOUT_MS);
  }

  /** 生成报告：调用既有生成端点 → 轮询列表直到报告出现 */
  async function generate(): Promise<void> {
    const id = Number(unref(taskId));
    if (!Number.isFinite(id) || id <= 0 || generating.value) return;
    generating.value = true;
    try {
      await reportsPort.generateTaskReport(id);
      notification.success('报告生成成功');
      await load(true);
      if (!report.value) startPolling();
      else generating.value = false;
    } catch (err: any) {
      generating.value = false;
      notification.error(err?.message || '生成报告失败，请重试');
    }
  }

  watch(
    () => unref(taskId),
    () => {
      stopPolling();
      generating.value = false;
      error.value = false;
      report.value = null;
      void load();
    },
    { immediate: true },
  );

  // 轮询拿到报告即停止
  watch(report, (value) => {
    if (value && generating.value) {
      generating.value = false;
      stopPolling();
    }
  });

  onBeforeUnmount(stopPolling);

  return {
    report,
    loading,
    error,
    generating,
    retry: () => load(),
    generate,
  };
}
