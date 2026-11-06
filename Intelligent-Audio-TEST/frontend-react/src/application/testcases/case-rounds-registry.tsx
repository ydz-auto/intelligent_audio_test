/**
 * 用例轮次登记表（application 层；INT-1506 审返 P2 修复）。
 *
 * 批量设置评估维度的轮次页签必须按「所选用例自身」的 config.rounds 渲染，但弹窗只拿到
 * 选中 id：列表首页 items（GET /testcases?page=1&per_page=100）只覆盖前 100 条，分组视图
 * 的组内用例来自独立懒加载分页、开始测试页另有筛选口径，按首页查轮次会把已选中的用例
 * 判成「轮次未知」并给出假空态（并禁用「确定」）。
 *
 * 因此凡是拿到真实 TestCaseListItem 的列表（页面列表 items、分组卡懒加载页）都登记
 * id → rounds；弹窗打开时按登记表解析选中用例：
 * - roundCount = 已登记用例的最大轮次数（各用例 config.rounds 并集上限）；
 * - unknownCount = 选中但尚未登记的条数（「未加载」不是「无轮次」，由弹窗显式提示）。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react'

/** 选中用例的轮次解析结果 */
export interface CaseRoundsSnapshot {
  /** 已登记用例的最大轮次数；0 = 一条都取不到 */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数 */
  unknownCount: number
}

interface CaseRoundsRegistryValue {
  /** 登记一批用例的 id → rounds（rounds ≤ 0 的条目不登记） */
  register: (cases: ReadonlyArray<{ id: string; rounds: number }>) => void
  /** 按选中 id 解析轮次快照 */
  resolve: (ids: readonly string[]) => CaseRoundsSnapshot
}

/** 未挂 Provider 时的兜底：不登记、全部视为未知（不编造轮次） */
const EMPTY_REGISTRY: CaseRoundsRegistryValue = {
  register: () => {},
  resolve: (ids) => ({ roundCount: 0, unknownCount: ids.length }),
}

const CaseRoundsContext = createContext<CaseRoundsRegistryValue>(EMPTY_REGISTRY)

/**
 * 轮次登记表 Provider（页级挂载，包住列表与批量弹窗 host）。
 * `cases` 传页面当前列表（首页 items），挂载/变化时自动登记；分组卡等子列表
 * 用 useCaseRoundsRegistry().register 自行补登记。
 */
export function CaseRoundsProvider({
  cases,
  children,
}: {
  cases?: ReadonlyArray<{ id: string; rounds: number }>
  children: ReactNode
}) {
  const store = useRef(new Map<string, number>())

  const register = useCallback(
    (list: ReadonlyArray<{ id: string; rounds: number }>) => {
      for (const item of list) {
        if (typeof item.rounds === 'number' && item.rounds > 0) {
          store.current.set(item.id, item.rounds)
        }
      }
    },
    []
  )

  const resolve = useCallback((ids: readonly string[]): CaseRoundsSnapshot => {
    let roundCount = 0
    let knownCount = 0
    for (const id of ids) {
      const rounds = store.current.get(id) ?? 0
      if (rounds > 0) {
        knownCount += 1
        if (rounds > roundCount) roundCount = rounds
      }
    }
    return { roundCount, unknownCount: ids.length - knownCount }
  }, [])

  useEffect(() => {
    register(cases ?? [])
  }, [cases, register])

  const value = useMemo(() => ({ register, resolve }), [register, resolve])
  return <CaseRoundsContext.Provider value={value}>{children}</CaseRoundsContext.Provider>
}

/** 取轮次登记表（含 register / resolve） */
export function useCaseRoundsRegistry(): CaseRoundsRegistryValue {
  return useContext(CaseRoundsContext)
}
