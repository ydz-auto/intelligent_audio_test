# 表格样式问题修复文档

## 问题描述

在用例分组对比卡片的表格中，表头（th）和数据单元格（td）之间的竖线没有对齐。

## 问题原因

### 1. th 和 td 使用不同的竖线实现方式

- **th（表头）**：使用 `::after` 伪元素绘制竖线
  ```css
  .report-data-table th:first-child::after {
    content: '';
    position: absolute;
    right: 0;
    top: 0;
    height: 100%;
    width: 1px;
    background-color: #e2e8f0;
  }
  ```

- **td（数据单元格）**：使用 `border-right` 绘制竖线
  ```css
  .report-data-table td {
    border-right: 1px solid #f1f5f9;
  }
  ```

### 2. th 缺少上框线

`.report-data-table th` 只设置了 `border-bottom`，没有设置 `border-top`，导致表头没有上框线。

## 解决方案

### 1. 统一竖线实现方式

将 td 的竖线也改为使用 `::after` 伪元素，确保与 th 的竖线对齐：

```css
/* 移除 td 的 border-right */
.report-data-table td {
  border-right: none;
  position: relative;
}

/* 为 td 第一列添加竖线 */
.report-data-table td:first-child::after {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  height: 100%;
  width: 1px;
  background-color: #f1f5f9;
}
```

### 2. 添加 th 上框线

```css
.report-data-table th {
  border-top: 1px solid #e2e8f0;
  border-bottom: 2px solid #e2e8f0;
}
```

## 相关文件

- `src/assets/styles/components/comparison-common.css` - 主要的表格样式定义
- `src/assets/styles/components/data-table.css` - 通用数据表格样式

## 注意事项

1. 使用 `::after` 伪元素绘制竖线时，父元素必须设置 `position: relative`
2. `z-index` 需要设置合适的值，避免被其他元素（如 resize-handle）遮挡
3. 竖线颜色应该与边框颜色保持一致（`#e2e8f0` 或 `#f1f5f9`）
