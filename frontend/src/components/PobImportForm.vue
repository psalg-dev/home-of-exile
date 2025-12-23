<template>
  <form @submit.prevent="emit('submit')">
    <label for="exportCode" style="display: block; margin-bottom: 8px;">
      Path of Building export code
    </label>

    <textarea
      id="exportCode"
      data-cy="pob-export-code"
      :value="exportCode"
      @input="emit('update:exportCode', $event.target.value)"
      rows="10"
      style="width: 100%; resize: vertical;"
      placeholder="Paste your PoB export code here"
    />

    <div style="margin-top: 12px; display: flex; gap: 12px; align-items: center;">
      <button
        type="submit"
        data-cy="pob-import"
        :disabled="loading"
      >
        {{ loading ? 'Importing…' : 'Import' }}
      </button>

      <span v-if="error" data-cy="pob-error" style="color: #b00020;">
        {{ error }}
      </span>
    </div>
  </form>
</template>

<script setup>
defineProps({
  exportCode: { type: String, required: true },
  loading: { type: Boolean, required: true },
  error: { type: String, required: true }
})

const emit = defineEmits(['update:exportCode', 'submit'])
</script>
