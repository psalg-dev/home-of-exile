import { test, expect } from '@playwright/test';
import { deflate } from 'pako';

/**
 * Helper: encode an XML string as a PoB-style URL-safe base64 code.
 */
function encodePobCode(xml: string): string {
  const bytes = new TextEncoder().encode(xml);
  const compressed = deflate(bytes);
  const base64 = Buffer.from(compressed).toString('base64');
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Minimal PoB XML — Slayer with uncapped chaos res (to trigger a critical issue) */
const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="90" className="Duelist" ascendClassName="Slayer" characterName="E2ESlayer" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="4000"/>
    <PlayerStat stat="EnergyShield" value="0"/>
    <PlayerStat stat="CombinedDPS" value="500000"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="50"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-60"/>
  </Build>
  <Skills>
    <Skill slot="Weapon 1" enabled="true" label="">
      <Gem nameSpec="Double Strike" skillId="Metadata/Items/Gems/SkillGemDoubleStrike" level="20" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree>
    <Spec nodes="1 2 3"/>
  </Tree>
  <Items/>
</PathOfBuilding>`;

const FIXTURE_CODE = encodePobCode(FIXTURE_XML);

/** Fixture API response with 3 recommendations and 2 critical issues */
const FIXTURE_RESPONSE = {
  recommendations: [
    {
      rank: 1,
      category: 'critical_fix',
      slot: 'Ring',
      current_item: 'Iron Ring',
      suggested_item: "Topaz Ring",
      deltas: { dps: 0, ehp: 500 },
      price_divine: 0.3,
      efficiency_score: 0.77,
      explanation: 'Adds cold resistance to cap your cold res.',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: null,
      ninja_url: 'https://poe.ninja/economy/settlers/accessories/rings',
      score: 6.5,
    },
    {
      rank: 2,
      category: 'power_upgrade',
      slot: 'Weapon',
      current_item: 'Rusted Sword',
      suggested_item: 'Ahn\'s Might',
      deltas: { dps: 120000, ehp: 0 },
      price_divine: 2.5,
      efficiency_score: 0.29,
      explanation: 'Significant DPS improvement for Slayer builds.',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: 'https://www.poewiki.net/wiki/Ahn%27s_Might',
      ninja_url: null,
      score: 4.2,
    },
    {
      rank: 3,
      category: 'efficiency',
      slot: 'Chest',
      current_item: 'Simple Robe',
      suggested_item: 'Tabula Rasa',
      deltas: { dps: 50000, ehp: 200 },
      price_divine: 0.5,
      efficiency_score: 0.67,
      explanation: 'Budget chest upgrade with 6-link for skill progression.',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: null,
      ninja_url: null,
      score: 3.1,
    },
  ],
  critical_issues: [
    {
      category: 'uncapped_res',
      severity: 'critical',
      description: 'Cold resistance is below cap',
      affected_stat: 'cold_res',
      current_value: 50,
      target_value: 75,
    },
    {
      category: 'uncapped_res',
      severity: 'warning',
      description: 'Chaos resistance is below expected',
      affected_stat: 'chaos_res',
      current_value: -60,
      target_value: 0,
    },
  ],
  simulation_count: 42,
  elapsed_seconds: 1.23,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Recommendations flow', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept the recommendations API call and return fixture data
    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE),
      });
    });
  });

  test('shows recommendations panel after build import', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');

    // Recommendations list should appear
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });
  });

  test('renders 3 recommendation cards', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    await expect(page.getByTestId('recommendation-1')).toBeVisible();
    await expect(page.getByTestId('recommendation-2')).toBeVisible();
    await expect(page.getByTestId('recommendation-3')).toBeVisible();
  });

  test('recommendation cards show item names and explanation', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendation-1')).toBeVisible({ timeout: 10_000 });

    // Check card #1 content
    const card1 = page.getByTestId('recommendation-1');
    await expect(card1.getByText('Iron Ring')).toBeVisible();
    await expect(card1.getByText('Topaz Ring')).toBeVisible();
    // Explanation is inside the collapsible body — expand first
    await card1.getByRole('button').first().click();
    await expect(card1.getByText('Adds cold resistance to cap your cold res.')).toBeVisible();
    await expect(card1.getByText('~0.3 div')).toBeVisible();
  });

  test('trade links are rendered for each recommendation', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Expand all cards to reveal trade links (cards are collapsed by default)
    await page.getByTestId('recommendation-1').getByRole('button').first().click();
    await page.getByTestId('recommendation-2').getByRole('button').first().click();
    await page.getByTestId('recommendation-3').getByRole('button').first().click();

    // Each card should have a trade link
    await expect(page.getByTestId('trade-link-1')).toBeVisible();
    await expect(page.getByTestId('trade-link-2')).toBeVisible();
    await expect(page.getByTestId('trade-link-3')).toBeVisible();
  });

  test('simulation stats are shown in the header', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('42 simulations')).toBeVisible();
  });

  test('critical issues panel is displayed', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('critical-issues')).toBeVisible({ timeout: 10_000 });

    // Both issues should render
    await expect(page.getByTestId('critical-issue-uncapped_res').first()).toBeVisible();
    await expect(page.getByText('Cold resistance is below cap')).toBeVisible();
    await expect(page.getByText('Chaos resistance is below expected')).toBeVisible();
  });

  test('shows loading spinner while fetching recommendations', async ({ page }) => {
    // Use a slow route to observe the loading state
    await page.unroute('**/api/v1/recommendations');
    await page.route('**/api/v1/recommendations', async route => {
      await new Promise(r => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    // Loading status should appear briefly
    await expect(page.getByRole('status', { name: 'Loading recommendations' })).toBeVisible();
    // Then resolve to the recommendations list
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });
  });

  test('shows error when recommendations API fails', async ({ page }) => {
    await page.unroute('**/api/v1/recommendations');
    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({ status: 503, body: 'Service unavailable' });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    // Error alert should appear
    const alert = page.getByRole('alert').filter({ hasText: 'Something went wrong generating recommendations' });
    await expect(alert).toBeVisible({ timeout: 10_000 });
  });

  test('category badge colours match spec', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendation-1')).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('Critical Fix')).toBeVisible();   // rank 1
    await expect(page.getByText('Power Upgrade')).toBeVisible();  // rank 2
    await expect(page.getByText('Efficiency')).toBeVisible();     // rank 3
  });
});
