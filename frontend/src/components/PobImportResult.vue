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
          <li v-for="(item, idx) in (result?.equipment || [])" :key="idx" data-cy="pob-equipment-item">
            <div>
              <span>{{ item.slot || 'Unknown slot' }}:</span>
              <span> {{ item.name || '—' }}</span>
            </div>

            <div style="margin: 4px 0 10px 12px;">
              <div data-cy="pob-equipment-implicit">
                Implicits:
                <span v-if="(item.implicitMods || []).length">{{ item.implicitMods.join(' • ') }}</span>
                <span v-else>—</span>
              </div>

              <div data-cy="pob-equipment-prefixes">
                Prefixes:
                <span v-if="(item.prefixMods || []).length">{{ item.prefixMods.join(' • ') }}</span>
                <span v-else>—</span>
              </div>

              <div data-cy="pob-equipment-suffixes">
                Suffixes:
                <span v-if="(item.suffixMods || []).length">{{ item.suffixMods.join(' • ') }}</span>
                <span v-else>—</span>
              </div>

              <div data-cy="pob-equipment-explicit">
                Explicit:
                <span v-if="(item.explicitMods || []).length">{{ item.explicitMods.join(' • ') }}</span>
                <span v-else>—</span>
              </div>
            </div>
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
