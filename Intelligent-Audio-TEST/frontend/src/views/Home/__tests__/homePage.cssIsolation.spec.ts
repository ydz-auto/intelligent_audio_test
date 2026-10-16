/**
 * INT-279：Home 页 home.css 全局泄漏回归锁（.section-title / .scroll-animate / .stat-card 等裸类名串扰）。
 *
 * 背景：Home.vue 以非 scoped `<style src="./home.css">` 注入（基线 V9.7.10 是 `<style scoped>`），
 *   home.css 的 .section-title(36px 居中)/.scroll-animate(opacity:0)/.stat-card 等类名被
 *   HistoryReports / AlgorithmConfig / Tasks 等页复用——访问首页后其他页面同名标题被 36px 居中覆盖、
 *   任何 .scroll-animate 元素初始不可见（依赖首页 IntersectionObserver 加 .animate 才显现）。INT-250 同型。
 *
 * 修复口径：home.css 保持非 scoped（需样式化各 section 子组件内部），但所有选择器统一以
 *   `.home-page` 命名空间前缀隔离；initScrollAnimations 只在 Home 根作用域内查询并挂 .scroll-animate。
 *
 * 锁定用例：
 * 1. 命名空间不变量（源级守卫）：home.css 中无任何裸类名选择器行（section-title / scroll-animate /
 *    stat-card / feature-card / detail-section / info-section / quick-stats / ...），且 .home-page 前缀规则存在；
 * 2. 行为锚点：注入 home.css 后，裸类名元素不被命中（fontSize/textAlign/opacity 不受污染），
 *    `.home-page` 作用域内同名元素仍被命中（36px 居中 / opacity:0 生效）——证明命名空间既隔离又保留 Home 样式；
 * 3. 动画收敛：stub IntersectionObserver 后挂载 Home.vue，.scroll-animate 只挂在 Home 根内元素上，
 *    根外同名的 .stat-card/.feature-card 元素不被动画类污染。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(here, '../../..'); // src/views/Home/__tests__ → src

/** INT-279 泄漏清单：home.css 中曾被其他页面复用的类名（裸类名出现在选择器行首即视为泄漏） */
const LEAK_CLASSES = [
  'section-title', 'section-subtitle',
  'scroll-animate',
  'stat-card', 'feature-card',
  'detail-section', 'info-section', 'quick-stats', 'workflow-section', 'features-section',
  'test-type-card', 'detail-main-card', 'detail-side-card', 'hero-section',
];

const getStatsDetailsMock = vi.hoisted(() => vi.fn());
vi.mock('@/composables/report/statsPort', () => ({
  statsPort: { getStatsDetails: getStatsDetailsMock },
}));

const injectedStyles: HTMLStyleElement[] = [];
function injectCss(css: string) {
  const el = document.createElement('style');
  el.textContent = css;
  document.head.appendChild(el);
  injectedStyles.push(el);
}

const ioObserved: any[] = [];
class IntersectionObserverStub {
  constructor(private cb: IntersectionObserverCallback) {}
  observe(el: Element) { ioObserved.push(el); }
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}

beforeEach(() => {
  ioObserved.length = 0;
  getStatsDetailsMock.mockReset();
  getStatsDetailsMock.mockResolvedValue({});
  vi.stubGlobal('IntersectionObserver', IntersectionObserverStub as any);
});

afterEach(() => {
  while (injectedStyles.length) injectedStyles.pop()!.remove();
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

function homeCss(): string {
  return readFileSync(resolve(srcDir, 'views/Home/home.css'), 'utf8');
}

/** 挂载 Home.vue（真实 section 子组件，router-link 打桩；statsPort 由 mock 提供） */
async function mountHome() {
  const w = mount((await import('../Home.vue')).default, {
    attachTo: document.body,
    global: {
      stubs: {
        'router-link': { template: '<a><slot /></a>' },
      },
    },
  });
  await flushPromises();
  return w;
}

describe('命名空间不变量（源级守卫，INT-279）', () => {
  it('home.css 中无裸类名选择器行，且 .home-page 前缀规则存在', () => {
    const css = homeCss();
    for (const cls of LEAK_CLASSES) {
      // 行首（含缩进）出现裸 `.cls` 即泄漏；.scroll-animate.animate 等变体也命中
      expect(
        new RegExp(`^\\s*\\.${cls}\\b`, 'm').test(css),
        `home.css 不应出现裸类名选择器 .${cls}`,
      ).toBe(false);
      // 命名空间规则必须存在（Home 自己的样式不能丢）
      expect(css.includes(`.home-page .${cls}`), `.home-page .${cls} 应存在`).toBe(true);
    }
  });
});

describe('行为锚点：注入 home.css 后裸类名不污染、Home 作用域内样式保留', () => {
  it('.section-title 裸元素不被 36px 居中覆盖；.home-page 作用域内仍生效', () => {
    injectCss(homeCss());

    const bare = document.createElement('div');
    bare.className = 'section-title';
    document.body.appendChild(bare);
    expect(getComputedStyle(bare).fontSize).not.toBe('36px');
    expect(getComputedStyle(bare).textAlign).not.toBe('center');

    const home = document.createElement('div');
    home.className = 'home-page';
    const inside = document.createElement('div');
    inside.className = 'section-title';
    home.appendChild(inside);
    document.body.appendChild(home);
    expect(getComputedStyle(inside).fontSize).toBe('36px');
    expect(getComputedStyle(inside).textAlign).toBe('center');
  });

  it('.scroll-animate 裸元素初始可见（opacity 非 0）；.home-page 作用域内 opacity:0 生效', () => {
    injectCss(homeCss());

    const bare = document.createElement('div');
    bare.className = 'scroll-animate';
    document.body.appendChild(bare);
    expect(getComputedStyle(bare).opacity).not.toBe('0');

    const home = document.createElement('div');
    home.className = 'home-page';
    const inside = document.createElement('div');
    inside.className = 'scroll-animate';
    home.appendChild(inside);
    document.body.appendChild(home);
    expect(getComputedStyle(inside).opacity).toBe('0');
  });
});

describe('动画收敛：.scroll-animate 只在 Home 根作用域内挂类（INT-279）', () => {
  it('挂载 Home 后，根外同名 .stat-card/.feature-card 元素不被挂 .scroll-animate', async () => {
    // 模拟其他页面上的同名元素（访问首页前已存在于 DOM）
    const foreignStat = document.createElement('div');
    foreignStat.className = 'stat-card foreign-stat';
    document.body.appendChild(foreignStat);
    const foreignFeature = document.createElement('div');
    foreignFeature.className = 'feature-card foreign-feature';
    document.body.appendChild(foreignFeature);

    const w = await mountHome();

    // Home 根内：QuickStats 的 .stat-card 被挂 .scroll-animate
    const homeStat = document.querySelector('.home-page .stat-card') as HTMLElement;
    expect(homeStat).toBeTruthy();
    expect(homeStat.classList.contains('scroll-animate')).toBe(true);

    // 根外同名元素不被挂类
    expect(foreignStat.classList.contains('scroll-animate')).toBe(false);
    expect(foreignFeature.classList.contains('scroll-animate')).toBe(false);

    // 观察器从未观察根外元素
    expect(ioObserved.some((el) => el === foreignStat)).toBe(false);
    expect(ioObserved.some((el) => el === foreignFeature)).toBe(false);

    // 全文档 .scroll-animate 元素都必须位于 .home-page 之下
    document.querySelectorAll('.scroll-animate').forEach((el) => {
      expect(el.closest('.home-page')).toBeTruthy();
    });

    w.unmount();
  });
});
