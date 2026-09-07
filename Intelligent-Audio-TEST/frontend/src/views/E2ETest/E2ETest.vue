<template>
  <TestFlow :testType="TestType.E2E" />
</template>

<script setup lang="ts">
import TestFlow from '../TestFlow/TestFlow.vue'
import { TestType } from '@/domain/enums'
</script>
