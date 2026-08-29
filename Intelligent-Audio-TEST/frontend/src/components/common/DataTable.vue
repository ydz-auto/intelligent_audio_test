<template>
  <div class="data-table-wrapper">
    <table
      ref="tableRef"
      :class="props.tableClass ? props.tableClass : 'data-table'"
      :style="tableStyle"
    >
      <thead>
        <tr>
          <th
            v-for="(column, colIndex) in columns"
            :key="column.key || colIndex"
            :class="getHeaderClass(column, colIndex)"
            :style="getHeaderStyle(column, colIndex)"
            @mousedown="handleResizeStart($event, colIndex, column)"
          >
            <slot :name="`header-${column.key}`" :column="column" :index="colIndex">
              <span
                v-if="column.editable && editingHeaderIndex === -1"
                class="editable"
                @click.stop="handleHeaderClick(colIndex, column)"
              >
                {{ column.label }}
                <span v-if="column.resize !== false" class="resize-handle"></span>
              </span>
              <template v-else-if="editingHeaderIndex === -1">
                {{ column.label }}
                <span v-if="column.resize !== false" class="resize-handle"></span>
              </template>
            </slot>

            <!-- 可编辑的列头输入框 -->
            <input
              v-if="editingHeaderIndex === colIndex"
              ref="headerInputRef"
              v-model="editingHeaderValue"
              class="filter-input"
              @keyup.enter="handleHeaderSave(colIndex, column)"
              @blur="handleHeaderSave(colIndex, column)"
              @click.stop
            />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!data || data.length === 0">
          <td :colspan="columns.length" class="data-table-empty">
            <slot name="empty">
              暂无数据
            </slot>
          </td>
        </tr>
        <tr
          v-for="(row, rowIndex) in data"
          :key="getRowKey(row, rowIndex)"
        >
          <td
            v-for="(column, colIndex) in columns"
            :key="column.key || colIndex"
            :class="getCellClass(row, column, colIndex)"
            :style="getCellStyle(row, column, colIndex)"
          >
            <!-- 可编辑单元格 -->
            <template v-if="column.editable && editingCell.row === rowIndex && editingCell.col === colIndex">
              <input
                ref="cellInputRef"
                v-model="editingCellValue"
                @keyup.enter="handleCellSave(rowIndex, colIndex, column)"
                @blur="handleCellSave(rowIndex, colIndex, column)"
                @click.stop
              />
            </template>
            <template v-else>
              <slot
                :name="`cell-${column.key}`"
                :row="row"
                :column="column"
                :value="getCellValue(row, column)"
                :rowIndex="rowIndex"
                :colIndex="colIndex"
              >
                <span
                  v-if="column.editable"
                  class="editable-cell"
                  @click.stop="handleCellClick(rowIndex, colIndex, row, column)"
                >
                  {{ formatCellValue(getCellValue(row, column), column) }}
                </span>
                <template v-else>
                  {{ formatCellValue(getCellValue(row, column), column) }}
                </template>
              </slot>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  columns: {
    type: Array,
    required: true,
    default: () => []
  },
  data: {
    type: Array,
    default: () => []
  },
  rowKey: {
    type: [String, Function],
    default: 'id'
  },
  resizable: {
    type: Boolean,
    default: true
  },
  minColumnWidth: {
    type: Number,
    default: 60
  },
  defaultColumnWidth: {
    type: [Number, Object],
    default: () => ({ first: 200, others: 150 })
  },
  stripe: {
    type: Boolean,
    default: false
  },
  hover: {
    type: Boolean,
    default: true
  },
  tableClass: {
    type: String,
    default: ''
  }
})

const emit = defineEmits([
  'cell-click',
  'cell-save',
  'header-click',
  'header-save',
  'resize',
  'row-click',
  'sort'
])

const tableRef = ref(null)
const headerInputRef = ref(null)
const cellInputRef = ref(null)

// 拖动调整列宽
const resizing = ref({ active: false, columnIndex: -1, startX: 0, startWidth: 0 })
let resizeMoveHandler = null
let resizeUpHandler = null

// 编辑状态
const editingHeaderIndex = ref(-1)
const editingHeaderValue = ref('')
const editingCell = ref({ row: -1, col: -1 })
const editingCellValue = ref('')

const tableStyle = computed(() => ({
  width: '100%'
}))

// 获取行的唯一键
const getRowKey = (row, index) => {
  if (typeof props.rowKey === 'function') {
    return props.rowKey(row)
  }
  return row[props.rowKey] || index
}

// 获取单元格的值
const getCellValue = (row, column) => {
  if (column.key) {
    return row[column.key]
  }
  return ''
}

// 格式化单元格值
const formatCellValue = (value, column) => {
  if (value === null || value === undefined || value === '-') {
    return column.placeholder || '-'
  }
  let formattedValue = value
  if (column.formatter) {
    formattedValue = column.formatter(value)
  }

  if (formattedValue === '-' || formattedValue === null || formattedValue === undefined) {
    return '-'
  }

  if (column.unit && column.key !== 'category' && column.key !== 'tag') {
    return `${formattedValue}${column.unit}`
  }

  return formattedValue
}

// 获取表头类名
const getHeaderClass = (column, colIndex) => {
  const classes = []

  if (props.resizable && column.resize !== false) {
    classes.push('resizable')
  }

  if (column.class) {
    classes.push(column.class)
  }

  return classes.join(' ')
}

// 获取单元格类名
const getCellClass = (row, column, colIndex) => {
  const classes = []

  if (column.editable) {
    classes.push('editable')
  }

  if (column.class) {
    classes.push(column.class)
  }

  if (colIndex === 0) {
    classes.push('first-column')
  }

  return classes.join(' ')
}

// 获取表头样式
const getHeaderStyle = (column, colIndex) => {
  const style = {}

  if (column.width) {
    style.width = typeof column.width === 'number' ? `${column.width}px` : column.width
    style.minWidth = style.width
  } else {
    const defaultWidth = typeof props.defaultColumnWidth === 'object'
      ? (colIndex === 0 ? props.defaultColumnWidth.first : props.defaultColumnWidth.others)
      : props.defaultColumnWidth
    style.minWidth = `${defaultWidth}px`
  }

  if (column.align) {
    style.textAlign = column.align
  } else if (colIndex === 0) {
    style.textAlign = 'left'
  } else {
    style.textAlign = 'center'
  }

  return style
}

// 获取单元格样式
const getCellStyle = (row, column, colIndex) => {
  const style = {}

  if (column.align) {
    style.textAlign = column.align
  } else if (colIndex === 0) {
    style.textAlign = 'left'
  } else {
    style.textAlign = 'center'
  }

  if (column.color) {
    style.color = typeof column.color === 'function' ? column.color(row) : column.color
  }

  return style
}

// 拖动调整列宽开始
const handleResizeStart = (event, colIndex, column) => {
  if (!props.resizable || column.resize === false) {
    return
  }

  if (event.target.tagName === 'INPUT') {
    return
  }

  const target = event.target.closest('th')
  if (!target) return

  resizing.value = {
    active: true,
    columnIndex: colIndex,
    startX: event.pageX,
    startWidth: target.offsetWidth
  }

  event.preventDefault()
  event.stopPropagation()

  resizeMoveHandler = (e) => {
    if (!resizing.value.active) return
    const diff = e.pageX - resizing.value.startX
    const newWidth = Math.max(props.minColumnWidth, resizing.value.startWidth + diff)

    if (tableRef.value) {
      const ths = tableRef.value.querySelectorAll('th')
      if (ths[colIndex]) {
        ths[colIndex].style.width = `${newWidth}px`
        ths[colIndex].style.minWidth = `${newWidth}px`
      }
    }
  }

  resizeUpHandler = () => {
    resizing.value.active = false
    document.removeEventListener('mousemove', resizeMoveHandler)
    document.removeEventListener('mouseup', resizeUpHandler)

    emit('resize', {
      columnIndex: resizing.value.columnIndex,
      width: resizing.value.startWidth
    })

    resizeMoveHandler = null
    resizeUpHandler = null
  }

  document.addEventListener('mousemove', resizeMoveHandler)
  document.addEventListener('mouseup', resizeUpHandler)
}

// 表头点击
const handleHeaderClick = (colIndex, column) => {
  if (column.sortable) {
    emit('sort', { column: column.key, direction: 'asc' })
  }
  emit('header-click', { column: column.key, index: colIndex, column })
  
  if (column.editable) {
    editingHeaderIndex.value = colIndex
    editingHeaderValue.value = column.label
    nextTick(() => {
      if (headerInputRef.value) {
        const input = Array.isArray(headerInputRef.value) ? headerInputRef.value[0] : headerInputRef.value
        if (input) {
          input.focus()
          input.select()
        }
      }
    })
  }
}

// 表头编辑保存
const handleHeaderSave = async (colIndex, column) => {
  if (editingHeaderIndex.value !== colIndex) return

  const value = editingHeaderValue.value
  editingHeaderIndex.value = -1
  editingHeaderValue.value = ''

  emit('header-save', {
    column: column.key,
    index: colIndex,
    column,
    value,
    originalValue: column.label
  })
}

// 单元格点击
const handleCellClick = (rowIndex, colIndex, row, column) => {
  if (!column.editable) {
    emit('cell-click', { row, column: column.key, rowIndex, colIndex, value: getCellValue(row, column) })
    return
  }

  editingCell.value = { row: rowIndex, col: colIndex }
  editingCellValue.value = formatCellValue(getCellValue(row, column), column)

  nextTick(() => {
    if (cellInputRef.value) {
      const input = Array.isArray(cellInputRef.value) ? cellInputRef.value[0] : cellInputRef.value
      if (input) {
        input.focus()
        input.select()
      }
    }
  })
}

// 单元格编辑保存
const handleCellSave = (rowIndex, colIndex, column) => {
  if (editingCell.value.row !== rowIndex || editingCell.value.col !== colIndex) return

  const row = props.data[rowIndex]
  const value = editingCellValue.value
  const originalValue = getCellValue(row, column)

  editingCell.value = { row: -1, col: -1 }
  editingCellValue.value = ''

  emit('cell-save', {
    row,
    column: column.key,
    rowIndex,
    colIndex,
    value,
    originalValue
  })
}

// 清理
onUnmounted(() => {
  if (resizeMoveHandler) {
    document.removeEventListener('mousemove', resizeMoveHandler)
  }
  if (resizeUpHandler) {
    document.removeEventListener('mouseup', resizeUpHandler)
  }
})

// 暴露方法给父组件
defineExpose({
  startEditHeader: (index, value) => {
    editingHeaderIndex.value = index
    editingHeaderValue.value = value
    nextTick(() => {
      if (headerInputRef.value) {
        const input = Array.isArray(headerInputRef.value) ? headerInputRef.value[0] : headerInputRef.value
        if (input) {
          input.focus()
          input.select()
        }
      }
    })
  },
  startEditCell: (rowIndex, colIndex) => {
    const row = props.data[rowIndex]
    const column = props.columns[colIndex]
    if (row && column) {
      handleCellClick(rowIndex, colIndex, row, column)
    }
  },
  getTableRef: () => tableRef.value
})
</script>

<style scoped>
@import '@/assets/styles/components/data-table.css';

.data-table-wrapper {
  background: white;
}
</style>
