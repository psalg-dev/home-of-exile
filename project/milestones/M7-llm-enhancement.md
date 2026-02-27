# M7: LLM Enhancement

**Timeline:** Weeks 7-8
**Phase:** 2 (LLM Layer)
**Priority:** P1 — Enhancement
**PRD Reference:** Technical Architecture (Phase 2), NFR-4 (Reliability)

---

## Objective

Replace template-based recommendation explanations with LLM-generated natural language that is grounded in engine-calculated data, validated against hallucination, and A/B tested against the template baseline.

---

## Deliverables

### D7.1: LLM Service Integration

- [ ] Implement `LLMExplainerService` (Python)
  - Provider: OpenAI GPT-4o-mini (cost-efficient, fast)
  - System prompt:
    ```
    You are an expert Path of Exile advisor. Explain upgrade recommendations
    to players using ONLY the provided numerical data. Do not invent stats,
    items, or mechanics not present in the input. Keep explanations concise
    (2-3 sentences), beginner-friendly, and actionable.
    ```
  - Input: structured recommendation data (slot, item, deltas, archetype, build summary)
  - Output: JSON schema enforced via `response_format`:
    ```json
    {
      "explanation": "string (2-3 sentences)",
      "beginner_tip": "string | null (optional 1-sentence tip for new players)"
    }
    ```
- [ ] Timeout: 3 seconds per LLM call; fall back to template if exceeded
- [ ] Retry: 1 retry on 5xx errors; then fall back to template
- [ ] Cost tracking: log token usage per request

### D7.2: Hallucination Validation

- [ ] Implement `validate_llm_output(llm_response, engine_data) -> ValidationResult`
- [ ] Validation checks:
  - No DPS/EHP numbers in explanation that differ >5% from engine deltas
  - No item names mentioned that aren't in the recommendation
  - No gem names or mechanics that aren't in the build data
  - No references to currency amounts that differ from pricing data
- [ ] On validation failure:
  - Log the hallucination for review
  - Fall back to template-based explanation
  - Increment hallucination counter metric

### D7.3: Template Fallback System

- [ ] Ensure M4 template system remains fully functional
- [ ] Fallback triggers:
  - OpenAI API unreachable or timeout
  - LLM response fails validation
  - Feature flag disabled
  - Rate limit exceeded (> $X/day spend cap)
- [ ] Seamless: frontend does not know/care whether explanation is LLM or template
- [ ] Response includes `explanation_source: "llm" | "template"` for analytics

### D7.4: A/B Testing Framework

- [ ] Implement session-based A/B assignment:
  - 50/50 split: sessions get either LLM or template explanations
  - Assignment stored in session (consistent within one analysis)
  - Assignment logged with feedback for analysis
- [ ] Extend feedback table:
  ```sql
  ALTER TABLE feedback ADD COLUMN explanation_source TEXT;
  ```
- [ ] Analysis query: compare thumbs-up rate between LLM and template groups

### D7.5: "Wrong Explanation" Feedback Signal

- [ ] Add a third feedback option per recommendation: "Explanation is wrong/misleading"
- [ ] Stored as `vote = 'wrong_explanation'` in feedback table
- [ ] High `wrong_explanation` rate for LLM group triggers alert
- [ ] UI: small text link below explanation ("Report incorrect explanation")

### D7.6: Cost Controls

- [ ] Daily spend cap: configurable via environment variable (`LLM_DAILY_SPEND_CAP_USD`)
  - Default: $5/day
  - When cap reached: all requests fall back to templates for remainder of day
- [ ] Token usage dashboard (admin endpoint):
  - `GET /api/v1/admin/llm-usage`
  - Returns: total tokens today, estimated cost, requests served, fallback count
- [ ] Estimated cost per analysis: $0.002-0.01 (5 recommendations × ~200 tokens each)

---

## Prompt Engineering

### System Prompt (Full)

```
You are an expert Path of Exile advisor helping players optimize their builds.

Rules:
1. Use ONLY the numbers and data provided in the input. Never invent statistics.
2. Explain WHY this upgrade matters for the player's specific build archetype.
3. Keep explanations to 2-3 sentences maximum.
4. Use language appropriate for the player's apparent experience level.
5. Mention the cost-efficiency if the upgrade is a good value.
6. If the upgrade fixes a critical issue (uncapped resistance, low life), lead with that.
7. Do not reference patch notes, meta shifts, or information not in the input.
```

### User Prompt Template

```
Build: Level {level} {ascendancy} ({damage_type} {playstyle})
Current {slot}: {current_item}
Suggested: {suggested_item}

Stat changes:
- DPS: {dps_delta:+,} ({dps_pct:+.1f}%)
- Life: {life_delta:+,}
- Energy Shield: {es_delta:+,}
- Fire Res: {fire_delta:+}%
- Cold Res: {cold_delta:+}%
- Lightning Res: {lightning_delta:+}%

Cost: {price} divine orb(s)
Category: {category}

Write a 2-3 sentence explanation for this upgrade recommendation.
If helpful, include a 1-sentence beginner tip.
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | LLM explanations render on recommendation cards | Manual test |
| 2 | LLM explanation references only stats present in engine output | Validation unit tests |
| 3 | Hallucinated numbers are caught and explanation falls back to template | Unit test (injected bad response) |
| 4 | API timeout (3s) falls back to template without user-visible error | Integration test |
| 5 | OpenAI API fully down → all explanations use templates | Fault injection |
| 6 | A/B split assigns ~50/50 across sessions | Statistical test (100 sessions) |
| 7 | Feedback records include `explanation_source` field | Database query |
| 8 | "Wrong explanation" feedback option works and stores correctly | Manual test |
| 9 | Daily spend cap stops LLM calls when reached | Unit test (mocked counter) |
| 10 | LLM adds < 1.5 seconds latency to recommendation generation (P50) | Performance test |
| 11 | Cost per analysis < $0.01 | Token usage logs |

---

## Dependencies

- **Upstream:** M4 (template system, Recommendation model), M6 (feedback system, production deployment)
- **External:** OpenAI API (GPT-4o-mini)
- **Accounts:** OpenAI API key with billing enabled

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM hallucinates plausible but wrong PoE mechanics | Strict validation; only pass numbers, never ask LLM for game knowledge |
| OpenAI pricing increases | Spend cap; template fallback; evaluate alternative models (Claude Haiku, local LLMs) |
| LLM latency degrades UX | 3-second timeout; consider generating explanations async (show template first, swap in LLM) |
| A/B test shows templates are better | Valid outcome — keep templates, save on LLM costs |
| Users abuse "wrong explanation" button | Rate limit feedback; require at least viewing the explanation for N seconds |

---

## Success Criteria (A/B Test)

The LLM enhancement is considered successful if after 2 weeks of A/B testing:

- **Thumbs-up rate:** LLM group ≥ template group (statistically significant, p < 0.05)
- **Trade link CTR:** LLM group ≥ template group
- **Wrong explanation rate:** LLM group < 5%
- **Cost:** < $5/day at projected traffic

If criteria are not met, roll back to templates and reassess prompt engineering.

---

## Definition of Done

- LLM explanations deployed behind A/B test flag
- Hallucination validation catches invalid LLM output
- Template fallback works seamlessly for all failure modes
- Cost controls enforce daily spend cap
- A/B test running with both groups receiving feedback
- 2-week evaluation plan documented and tracking active
