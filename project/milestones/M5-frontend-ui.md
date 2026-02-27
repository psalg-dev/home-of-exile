# M5: Frontend UI

**Timeline:** Week 5
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 — MVP Blocker
**PRD Reference:** FR-1, FR-2, FR-4 (User Flows), NFR-1 (Performance)

---

## Objective

Build the user-facing frontend that allows players to paste a PoB code, view their build summary, and see 5 recommendation cards with trade links and resource deep links.

---

## Deliverables

### D5.1: Landing Page & PoB Input

- [ ] Hero section with app tagline and brief value proposition
- [ ] PoB code input:
  - Large textarea for pasting PoB export codes
  - "Analyze Build" primary action button
  - Example PoB code link ("Try an example build")
  - Character count / validation indicator
- [ ] Input validation:
  - Client-side: check non-empty, reasonable length, base64-decodable
  - Display inline error for obviously invalid input
- [ ] Responsive layout (desktop-first, mobile-friendly)

### D5.2: Loading State

- [ ] Full-screen loading overlay after "Analyze Build" click
- [ ] Progress indicators:
  - "Parsing your build..." (client-side, instant)
  - "Analyzing upgrades..." (server-side, 5-8 seconds)
- [ ] Animated skeleton cards for recommendations area
- [ ] Cancel button to abort analysis
- [ ] Timeout message if analysis exceeds 20 seconds

### D5.3: Build Summary Card

- [ ] Display after successful parse:
  - Character name
  - Class + Ascendancy (with class icon)
  - Level
  - Main skill name
  - Key stats: Life, Energy Shield, DPS
  - Elemental resistances (fire/cold/lightning) with visual indicator (green if capped, red if not)
  - Chaos resistance
- [ ] Compact layout — one horizontal card above recommendations

### D5.4: Recommendation Cards

- [ ] 5 recommendation cards displayed vertically, numbered 1-5
- [ ] Each card includes:
  - **Rank badge** (#1-#5) with category color coding:
    - Red: critical fix
    - Blue: power upgrade
    - Green: defense upgrade
    - Yellow: quality-of-life
    - Purple: cost-efficient
  - **Header:** "Upgrade: {slot} → {item name}"
  - **Stat deltas:** ΔDPS, ΔLife, ΔES, ΔResistances (color-coded: green positive, red negative)
  - **Cost:** Price in divine orbs (or "Price unknown")
  - **Efficiency:** "X DPS per divine" (when applicable)
  - **Explanation:** Template-generated paragraph
  - **Action buttons:**
    - [Search on Trade] — opens official trade site in new tab
    - [View on Wiki] — opens poewiki.net in new tab (when available)
    - [Price History] — opens poe.ninja price graph in new tab (when available)
  - **Feedback buttons:** 👍 / 👎 (wired in M6)
- [ ] Cards are collapsible (show header + deltas by default; click to expand explanation)

### D5.5: League Selector

- [ ] Dropdown in header/toolbar area
- [ ] Options: Current league name, Previous league, Standard
- [ ] Changing league triggers re-analysis with league-specific pricing
- [ ] Visual indicator of selected league near build summary

### D5.6: Resource Hub Page

- [ ] Separate `/resources` page (linked from nav)
- [ ] Categorized links:
  - **Build Tools:** Path of Building Community Fork, pob.cool
  - **Databases:** poewiki.net, poedb.tw
  - **Economy:** poe.ninja
  - **Trading:** Official trade site, Awakened PoE Trade
  - **Data:** RePoE GitHub
- [ ] Each link with brief description and "opens in new tab" indicator
- [ ] **Blacklist enforced:** No Fandom PoE Wiki links

### D5.7: Error States

- [ ] PoB parse error: "We couldn't parse this PoB code. Make sure you're using Path of Building Community Fork v2.35 or later."
- [ ] Server error: "Something went wrong generating recommendations. Please try again."
- [ ] Timeout error: "Analysis is taking longer than expected. This may happen with very complex builds."
- [ ] Network error: "Unable to reach the server. Check your connection and try again."
- [ ] Each error state has a "Try Again" button

---

## Component Tree

```
App
├── Header
│   ├── Logo + App Name
│   ├── LeagueSelector
│   └── Nav (Home | Resources)
├── HomePage
│   ├── HeroSection
│   ├── PobInput
│   │   ├── Textarea
│   │   ├── AnalyzeButton
│   │   └── ErrorMessage
│   ├── LoadingOverlay
│   ├── BuildSummaryCard
│   │   ├── CharacterInfo
│   │   ├── StatBar (Life/ES/DPS)
│   │   └── ResistanceIndicators
│   └── RecommendationList
│       └── RecommendationCard (×5)
│           ├── RankBadge
│           ├── StatDeltas
│           ├── PriceInfo
│           ├── Explanation (collapsible)
│           ├── ActionButtons
│           └── FeedbackButtons (disabled until M6)
├── ResourcesPage
│   └── ResourceCategory (×N)
│       └── ResourceLink
└── Footer
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | User can paste a PoB code and click "Analyze Build" | Manual test |
| 2 | Build summary card displays correct character info after analysis | Manual test |
| 3 | 5 recommendation cards render with all required fields | Manual test |
| 4 | "Search on Trade" button opens correct trade site URL in new tab | Manual test |
| 5 | Resource links do not include any Fandom wiki URLs | Code review |
| 6 | Loading state shows during server analysis | Manual test |
| 7 | Parse errors display user-friendly message | Manual test |
| 8 | Page loads in < 2 seconds (excluding analysis) | Lighthouse |
| 9 | Responsive: usable on 375px-wide mobile viewport | Manual test |
| 10 | League selector triggers re-analysis with correct league | Manual test |
| 11 | Resistance indicators are red when uncapped, green when capped | Manual test |
| 12 | Recommendation cards are collapsible | Manual test |

---

## Dependencies

- **Upstream:** M1 (PoB parser, BuildData types), M4 (Recommendation model, trade links)
- **Backend API:** `POST /api/v1/analyze` — full pipeline (parse → simulate → recommend)
- **Assets:** Class icons (can use placeholder SVGs initially)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| 5-8 second loading time feels too long | Engaging loading animation; progressive display (show build summary first) |
| Mobile UX for recommendation cards | Prioritize desktop; mobile shows simplified card view |
| Trade link opens blank results | Test trade URLs with real items; show disclaimer for rare items |

---

## Definition of Done

- Complete user flow: paste PoB code → see build summary → see 5 recommendations → click trade link
- All error states handled with clear messaging
- Resource hub page live with correct links (no Fandom)
- Page load under 2 seconds; responsive on mobile
- Feedback buttons present but disabled (wired in M6)
