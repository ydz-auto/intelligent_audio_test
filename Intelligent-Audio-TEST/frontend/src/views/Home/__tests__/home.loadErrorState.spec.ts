/**
 * INT-288：Home 统计加载 / 错误 / 成功态回归。
 *
 * 缺陷：统计接口失败仅 console.error('获取统计数据失败')，无用户可见错误态/
 * 重试，页面以全 0 统计误导用户。验收（issue 原文）：加载态、错误态（错误条
 * + 重试）、失败保留旧数据不清空。
 * 锁定契约：
 * 1. 拉取失败（未加载过）→ .load-error-state + 重试按钮，不显示全 0 统计；
 * 2. 重试成功 → 错误条消失，渲染统计（QuickStats）；
 * 3. 拉取期间 → .home-stats-loading spinner；
 * 4. 成功态 → 无错误条，渲染统计。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const statsPort = vi.hoisted(() => ({ getStatsDetails: vi.fn() }));
vi.mock('@/composables/report/statsPort', () => ({ statsPort }));

import Home from '../Home.vue';
import QuickStats from '../sections/QuickStats.vue';

const STATS = {
  testCases: { total: 100, groups: 5 },
  tasks: { total: 10, completed: 8, running: 1, failed: 1 },
  devices: { online: 4, offline: 1, total: 5 },
  audioFiles: { total: 300, dry: 100, noise: 100, prompt: 100, duration: { total: 3600, dry: 1200, noise: 1200, prompt: 1200 } },
  apis: { online: 3, offline: 1, total: 4 },
  dimensions: { total: 5, withEndpoints: 3, endpoints: 8 },
};

beforeEach(() => {
  vi.clearAllMocks();
  // animateNumber 依赖 requestAnimationFrame；用远超当前时间的时钟一次性推进到终点。
  // 不能写死小数值（如 5000）：多文件合并跑时 performance.now() 已超过该值，
  // elapsed 变负 → progress<1 → 递归 requestAnimationFrame → 栈溢出 → 误置 statsError。
  vi.stubGlobal('requestAnimationFrame', (cb: any) => { cb(Number.MAX_SAFE_INTEGER); return 1; });
  // initScrollAnimations 依赖 IntersectionObserver（jsdom 未提供）
  class MockObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', MockObserver);
});

function mountHome() {
  return mount(Home, {
    global: {
      stubs: {
        QuickStats: true,
        WorkflowSection: true,
        DetailSection: true,
        FeaturesSection: true,
        InfoSection: true,
      },
    },
  });
}

describe('Home 统计加载 / 错误态（INT-288）', () => {
  it('错误态：统计接口失败 → 错误条 + 重试（不显示全 0 统计）', async () => {
    statsPort.getStatsDetails.mockRejectedValue(new Error('net down'));
    const wrapper = mountHome();
    await flushPromises();

    const err = wrapper.find('.load-error-state');
    expect(err.exists(), '失败后应渲染错误条（不再仅 console.error）').toBe(true);
    expect(err.text()).toContain('获取统计数据失败');
    expect(wrapper.find('.home-stats-loading').exists()).toBe(false);

    statsPort.getStatsDetails.mockResolvedValue(STATS);
    await err.find('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('.load-error-state').exists(), '重试成功后错误条消失').toBe(false);
    expect(wrapper.findComponent(QuickStats).exists(), '重试成功后渲染统计').toBe(true);
  });

  it('加载态：拉取期间显示 spinner', async () => {
    statsPort.getStatsDetails.mockReturnValue(new Promise(() => {}));
    const wrapper = mountHome();
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.home-stats-loading').exists(), '拉取期间应渲染加载态容器').toBe(true);
    expect(wrapper.find('.home-stats-spinner').exists()).toBe(true);
  });

  it('成功态：渲染统计卡片，无错误条', async () => {
    statsPort.getStatsDetails.mockResolvedValue(STATS);
    const wrapper = mountHome();
    await flushPromises();
    expect(wrapper.find('.load-error-state').exists()).toBe(false);
    expect(wrapper.findComponent(QuickStats).exists()).toBe(true);
  });
});
