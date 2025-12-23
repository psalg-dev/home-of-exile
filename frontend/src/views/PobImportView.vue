<template>
  <section>
    <PobImportForm
      :export-code="exportCode"
      :loading="loading"
      :error="error"
      @update:export-code="(v) => (exportCode = v)"
      @submit="onSubmit"
    />

    <div style="margin-top: 16px;">
      <PobImportResult v-if="result" :result="result" />
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { importPob } from '../api/importPob'
import PobImportForm from '../components/PobImportForm.vue'
import PobImportResult from '../components/PobImportResult.vue'

const exportCode = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)

async function onSubmit() {
  error.value = ''
  result.value = null

  if (!exportCode.value.trim()) {
    error.value = 'Please paste a PoB export code.'
    return
  }

  loading.value = true
  try {
    result.value = await importPob(exportCode.value)
  } catch (e) {
    error.value = e?.message || 'Import failed.'
  } finally {
    loading.value = false
  }
}
</script>
