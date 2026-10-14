/**
 * INT-256：INT-250 修复本体回归锁 —— 发布 / 重命名 / 冻结报告三弹窗 overlay 显式可见性。
 *
 * 缺陷（INT-250）：全局 test-case-manager.css（经 main.css @import 全局注入）定义
 *   .modal-overlay{opacity:0;visibility:hidden}（仅 .active 才可见）与
 *   .modal{transform:translateY(-20px)}；三个弹窗自带的 .modal-overlay/.modal 从不携带
 *   .active → 打开后弹窗整体不可见、面板上移 20px。
 * 修复：三弹窗 scoped 样式显式 opacity:1;visibility:visible（overlay）+ transform:none（modal）。
 *
 * 锁定方式（真实级联断言，非快照、非类名空断言）：
 * 1. 注入真实全局串扰源全文（test-case-manager.css，与生产 main.css 全局注入同源）；
 * 2. 挂载组件读取真实 scopeId（data-v-*），用 vue/compiler-sfc compileStyle 按 vite 同规则
 *    编译 SFC scoped 块注入 —— 重建生产「全局 + scoped」级联；
 * 3. 断言 overlay 计算样式：opacity/visibility/position/display/居中、z-index 13000 压过全局 1000、
 *    modal transform:none；emit close 后卸载、卸载后无残留 overlay；
 * 4. 负例锚点：无 scopeId 的裸 .modal-overlay 仍为 hidden、裸 .modal 仍位移 ——
 *    证明全局串扰源真实加载；若修复被回退（删掉显式声明），正例断言同步翻转为失败，不会空过。
 */
import { describe, it, expect, afterEach } from 'vitest';
import { mount } from '@vue/test-utils';
import type { VueWrapper } from '@vue/test-utils';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { parse, compileStyle } from 'vue/compiler-sfc';
import PublishTaskModal from '../PublishTaskModal.vue';
import PublishedTaskNameModal from '../PublishedTaskNameModal.vue';
import ReportSnapshotModal from '../ReportSnapshotModal.vue';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(here, '../../..'); // src/components/published-task/__tests__ → src

/** 全局串扰源（test-case-manager.css 全文；生产经 main.css @import 全局注入） */
const GLOBAL_TCM_CSS = readFileSync(
  resolve(srcDir, 'assets/styles/test-case-manager/test-case-manager.css'),
  'utf8',
);

const injectedStyles: HTMLStyleElement[] = [];
function injectCss(css: string) {
  const el = document.createElement('style');
  el.textContent = css;
  document.head.appendChild(el);
  injectedStyles.push(el);
}

afterEach(() => {
  while (injectedStyles.length) injectedStyles.pop()!.remove();
});

/** 按 vite 同规则编译 SFC scoped 样式块（id = 组件挂载后的真实 scopeId） */
function compiledScopedCss(sfcPathFromSrc: string, scopeId: string): string {
  const file = resolve(srcDir, sfcPathFromSrc);
  const { descriptor, errors } = parse(readFileSync(file, 'utf8'), { filename: file });
  if (errors.length > 0) throw errors[0];
  const scoped = descriptor.styles.find((s) => s.scoped);
  if (!scoped) throw new Error(`no scoped style block: ${file}`);
  const out = compileStyle({ source: scoped.content, filename: file, id: scopeId, scoped: true });
  if (out.errors.length > 0) throw out.errors[0];
  return out.code;
}

function scopeIdOf(wrapper: VueWrapper<any>): string {
  const names = (wrapper.find('.modal-overlay').element as HTMLElement).getAttributeNames();
  const scopeId = names.find((n) => n.startsWith('data-v-'));
  if (!scopeId) throw new Error('mounted overlay lacks data-v scope id');
  return scopeId;
}

/** 挂载弹窗并重建「全局串扰源 + 组件 scoped」级联（注入次序对齐生产：全局在前） */
function mountWithCascade(component: any, props: Record<string, any>, sfcPathFromSrc: string) {
  injectCss(GLOBAL_TCM_CSS);
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: { stubs: { teleport: true } },
  });
  injectCss(compiledScopedCss(sfcPathFromSrc, scopeIdOf(wrapper)));
  return wrapper;
}

/** INT-250 修复点断言：overlay 计算样式可见 + 居中 + 层级压制，modal 无位移 */
function expectOverlayVisibleAndCentered(wrapper: VueWrapper<any>) {
  const overlayCs = window.getComputedStyle(wrapper.find('.modal-overlay').element);
  expect(overlayCs.opacity).toBe('1');
  expect(overlayCs.visibility).toBe('visible');
  expect(overlayCs.position).toBe('fixed');
  expect(overlayCs.display).toBe('flex');
  expect(overlayCs.alignItems).toBe('center');
  expect(overlayCs.justifyContent).toBe('center');
  expect(overlayCs.zIndex).toBe('13000'); // scoped 显式层级，压过全局 .modal-overlay{z-index:1000}
  const modalCs = window.getComputedStyle(wrapper.find('.modal').element);
  expect(modalCs.transform).toBe('none'); // 全局 .modal{transform:translateY(-20px)} 被显式抹平
}

const SOURCE_TASKS = [{ id: 1, name: '来源任务A', status: 'completed', caseCount: 3 } as any];

/** 存量空快照（无 summary/cases → 空态分支；本文件断言目标为弹窗 chrome，非报告体） */
const EMPTY_SNAPSHOT = {
  reportId: 9,
  name: '冻结报告',
  status: 'completed',
  summary: {},
  cases: [],
} as any;

describe('全局串扰源负例锚点（无 scopeId → 全局规则生效，证明断言不空转）', () => {
  it('裸 .modal-overlay 计算样式为隐藏，裸 .modal 保留 translateY(-20px) 位移', () => {
    injectCss(GLOBAL_TCM_CSS);
    const bareOverlay = document.createElement('div');
    bareOverlay.className = 'modal-overlay';
    const bareModal = document.createElement('div');
    bareModal.className = 'modal';
    bareOverlay.appendChild(bareModal);
    document.body.appendChild(bareOverlay);

    const cs = window.getComputedStyle(bareOverlay);
    expect(cs.opacity).toBe('0');
    expect(cs.visibility).toBe('hidden');
    expect(window.getComputedStyle(bareModal).transform).toBe('translateY(-20px)');

    bareOverlay.remove();
  });
});

describe('PublishTaskModal（INT-250 overlay 显式可见性）', () => {
  it('打开后 overlay 计算样式可见且居中、modal 无位移；卸载后无残留', () => {
    const w = mountWithCascade(
      PublishTaskModal,
      { tasks: SOURCE_TASKS, presetSourceTaskId: 1 },
      'components/published-task/PublishTaskModal.vue',
    );
    expectOverlayVisibleAndCentered(w);
    w.unmount();
    expect(document.querySelectorAll('.modal-overlay')).toHaveLength(0);
  });

  it('点击关闭按钮 → emit close（宿主据此 v-if 卸载弹窗）', async () => {
    const w = mountWithCascade(
      PublishTaskModal,
      { tasks: SOURCE_TASKS, presetSourceTaskId: 1 },
      'components/published-task/PublishTaskModal.vue',
    );
    await w.find('.modal-close').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
    w.unmount();
  });
});

describe('PublishedTaskNameModal（INT-250 overlay 显式可见性）', () => {
  it('打开后 overlay 计算样式可见且居中、modal 无位移；卸载后无残留', () => {
    const w = mountWithCascade(
      PublishedTaskNameModal,
      { title: '重命名', label: '新的任务名称', initialValue: '回归任务' },
      'components/published-task/PublishedTaskNameModal.vue',
    );
    expectOverlayVisibleAndCentered(w);
    w.unmount();
    expect(document.querySelectorAll('.modal-overlay')).toHaveLength(0);
  });

  it('点击关闭按钮 → emit close', async () => {
    const w = mountWithCascade(
      PublishedTaskNameModal,
      { title: '重命名', label: '新的任务名称', initialValue: '回归任务' },
      'components/published-task/PublishedTaskNameModal.vue',
    );
    await w.find('.modal-close').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
    w.unmount();
  });
});

describe('ReportSnapshotModal（INT-250 overlay 显式可见性）', () => {
  it('打开后 overlay 计算样式可见且居中、modal 无位移；卸载后无残留', () => {
    const w = mountWithCascade(
      ReportSnapshotModal,
      { snapshot: EMPTY_SNAPSHOT },
      'components/published-task/ReportSnapshotModal.vue',
    );
    expectOverlayVisibleAndCentered(w);
    w.unmount();
    expect(document.querySelectorAll('.modal-overlay')).toHaveLength(0);
  });

  it('点击关闭按钮 → emit close', async () => {
    const w = mountWithCascade(
      ReportSnapshotModal,
      { snapshot: EMPTY_SNAPSHOT },
      'components/published-task/ReportSnapshotModal.vue',
    );
    await w.find('.modal-close').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
    w.unmount();
  });
});
