<template>
  <TestFlow :testType="TestType.API" />
</template>

<script setup lang="ts">
import TestFlow from '../TestFlow/TestFlow.vue'
import { TestType } from '@/shared/types/enums'
</script>
