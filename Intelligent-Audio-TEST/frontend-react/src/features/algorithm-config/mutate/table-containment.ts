/**
 * INT-2121：算法编辑 Sheet 内大表的 paint/layout containment。
 *
 * 背景（实测）：编辑 Sheet 单页滚动容器里同时装着参数表（本库 17 行）、参考参数表、
 * 设备/API/评估三张映射表与关联维度表；展开「高级配置 → 评估参数映射」后整片 DOM
 * 约 8900 节点、783 个 Select 触发器。滚动时浏览器每帧都要为滚动容器内全部后代重算
 * draw properties（trace：LayerTreeHostImpl::CalculateRenderPasses / CalculateDrawProperties
 * 占 70%+），帧时长数百毫秒。
 *
 * 给表格加 `contain: layout paint` 后，表格子树成为独立布局/绘制单元，滚动容器的
 * 合成器不再逐后代重算：同机同数据量级实测平均帧时长 103~111ms → 17.6ms，
 * P95 478~524ms → 20.2ms，长任务 491~564ms → 0。
 *
 * 只做 containment（不加 content-visibility），不改变表格尺寸估算，滚动条与
 * 分组展开/折叠、分页、行内下拉的行为一律不变。
 */
import './table-containment.css'

/** 见 table-containment.css 注释：大表 paint/layout containment，解决滚动掉帧。 */
export const CONTAINED_TABLE_CLASS = 'alg-table-contain'
