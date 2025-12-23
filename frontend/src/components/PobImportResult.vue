<template>
  <section>
    <h2 style="margin: 0 0 8px;">Parsed Result</h2>

    <div style="display: grid; gap: 12px;">
      <div>
        <strong>Character</strong>
        <div data-cy="pob-character">
          <div>Class: {{ result?.character?.class || '—' }}</div>
          <div>Ascendancy: {{ result?.character?.ascendancy || '—' }}</div>
          <div>Level: {{ result?.character?.level ?? '—' }}</div>
        </div>
      </div>

      <div>
        <strong>Main Skill</strong>
        <div data-cy="pob-main-skill">
          <div>Name: {{ result?.mainSkill?.name || '—' }}</div>
          <div>Confidence: {{ result?.mainSkill?.confidence || '—' }}</div>
          <div>
            Supports:
            <span v-if="(result?.mainSkill?.supportGems || []).length">
              {{ result.mainSkill.supportGems.join(', ') }}
            </span>
            <span v-else>—</span>
          </div>
        </div>
      </div>

      <div>
        <strong>Equipment</strong>
        <ul data-cy="pob-equipment" style="margin: 6px 0 0; padding-left: 18px;">
          <li v-for="(item, idx) in (result?.equipment || [])" :key="idx">
            <span>{{ item.slot || 'Unknown slot' }}:</span>
            <span> {{ item.name || '—' }}</span>
          </li>
          <li v-if="!(result?.equipment || []).length">—</li>
        </ul>
      </div>

      <div v-if="(result?.raw?.warnings || []).length" data-cy="pob-warnings">
        <strong>Warnings</strong>
        <ul style="margin: 6px 0 0; padding-left: 18px;">
          <li v-for="(w, idx) in result.raw.warnings" :key="idx">{{ w }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  result: { type: Object, required: true }
})
</script>
