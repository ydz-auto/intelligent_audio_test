<template>
  <TestFlow :testType="TestType.API" />
</template>

<script setup lang="ts">
import TestFlow from '../TestFlow/TestFlow.vue'
import { TestType } from '@/domain/enums'
</script>
