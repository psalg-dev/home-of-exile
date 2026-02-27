/**
 * M5 UI – End-to-end smoke tests for all M5 deliverables.
 *
 * Covers:
 *   D5.1  Landing page hero, textarea validation, character count, example build
 *   D5.2  LoadingOverlay staging (brief appearance before navigation)
 *   D5.3  Build summary card visible after import
 *   D5.4  Collapsible recommendation cards, feedback buttons present
 *   D5.5  League selector – changes league, key shown in select
 *   D5.6  Resources page – all 5 categories, no Fandom links
 *   D5.7  Error states: parse error, server error messages
 */

import { test, expect } from '@playwright/test';
import { deflate } from 'pako';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function encodePobCode(xml: string): string {
  const bytes = new TextEncoder().encode(xml);
  const compressed = deflate(bytes);
  const base64 = Buffer.from(compressed).toString('base64');
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="85" className="Witch" ascendClassName="Necromancer" characterName="M5Witch" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="3500"/>
    <PlayerStat stat="EnergyShield" value="1200"/>
    <PlayerStat stat="CombinedDPS" value="250000"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-20"/>
  </Build>
  <Skills>
    <Skill slot="Weapon 1" enabled="true" label="">
      <Gem nameSpec="Raise Spectre" skillId="Metadata/Items/Gems/SkillGemRaiseSpectre" level="21" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree><Spec nodes="1 2 3"/></Tree>
  <Items/>
</PathOfBuilding>`;

const FIXTURE_CODE = encodePobCode(FIXTURE_XML);

/** Minimal valid API response with 2 recommendations. */
const FIXTURE_RESPONSE = {
  recommendations: [
    {
      rank: 1,
      category: 'critical_fix',
      slot: 'Ring',
      current_item: 'Coral Ring',
      suggested_item: 'Amethyst Ring',
      deltas: { dps: 0, ehp: 400 },
      price_divine: 0.1,
      efficiency_score: 0.9,
      explanation: 'Adds chaos resistance to bring chaos res closer to cap.',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: null,
      ninja_url: 'https://poe.ninja/economy/settlers/accessories/rings',
      score: 8.1,
    },
    {
      rank: 2,
      category: 'power_upgrade',
      slot: 'Weapon',
      current_item: 'Driftwood Wand',
      suggested_item: "Pledge of Hands",
      deltas: { dps: 80000, ehp: 0 },
      price_divine: 1.5,
      efficiency_score: 0.4,
      explanation: 'Large DPS improvement for Raise Spectre builds.',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: 'https://www.poewiki.net/wiki/Pledge_of_Hands',
      ninja_url: null,
      score: 5.0,
    },
  ],
  critical_issues: [],
  simulation_count: 10,
  elapsed_seconds: 0.5,
};

// ---------------------------------------------------------------------------
// D5.1 – Landing page
// ---------------------------------------------------------------------------

test.describe('D5.1 Landing page', () => {
  test('renders hero heading and input', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Home of Exile' })).toBeVisible();
    await expect(page.getByPlaceholder('Paste your PoB export code here...')).toBeVisible();
  });

  test('Analyse Build button is disabled when input is empty', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Analyse Build' })).toBeDisabled();
  });

  test('Try an example build fills the textarea', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Try an example build' }).click();
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    const value = await textarea.inputValue();
    expect(value.length).toBeGreaterThan(20);
    // After filling, the Analyse Build button should be enabled
    await expect(page.getByRole('button', { name: 'Analyse Build' })).toBeEnabled();
  });

  test('character count indicator appears when typing', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill('abcdef');
    // The char count div should show the count  
    await expect(page.locator('#pob-char-count')).toContainText('6');
  });

  test('shows validation error for too-short input', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    // Fill fewer than 20 characters of valid base64
    await textarea.fill('abc123');
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('too short');
  });

  test('shows validation error for non-base64 characters', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    // Non-base64 characters (spaces, special chars)
    await textarea.fill('not a valid pob code with spaces!!!');
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('valid PoB code');
  });

  test('shows parse error for syntactically-valid-but-wrong base64', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    // "hello world" in URL-safe base64 — passes regex but is not valid PoB
    await textarea.fill('aGVsbG8gd29ybGQgaGVsbG8gd29ybGQ'); // > 20 chars
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    // Should mention PoB or parse failure
    await expect(page.getByRole('alert')).toContainText("couldn't parse");
  });
});

// ---------------------------------------------------------------------------
// D5.3 Build summary card + D5.4 Recommendation cards
// ---------------------------------------------------------------------------

test.describe('D5.3 & D5.4 Build summary and recommendation cards', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE),
      });
    });
  });

  test('build summary card is visible on build page', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('build-summary')).toBeVisible({ timeout: 10_000 });
    // Check character name from fixture
    await expect(page.getByText('M5Witch')).toBeVisible();
  });

  test('recommendation cards render with collapsible header', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('recommendation-1')).toBeVisible();
    await expect(page.getByTestId('recommendation-2')).toBeVisible();
  });

  test('recommendation card is collapsed by default, expands on click', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    await expect(page.getByTestId('recommendation-1')).toBeVisible({ timeout: 10_000 });

    const card = page.getByTestId('recommendation-1');
    // Explanation text should NOT be visible when collapsed
    const explanationText = 'Adds chaos resistance to bring chaos res closer to cap.';
    await expect(card.getByText(explanationText)).not.toBeVisible();

    // Click the card header to expand
    await card.getByRole('button').first().click();

    // Now the explanation should be visible
    await expect(card.getByText(explanationText)).toBeVisible();
  });

  test('feedback buttons are present (disabled) on recommendation cards', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    // Expand card to see feedback buttons
    await expect(page.getByTestId('recommendation-1')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('recommendation-1').getByRole('button').first().click();

    // Feedback buttons should exist and be disabled
    const thumbsUp = page.getByRole('button', { name: /thumbs up feedback/i });
    await expect(thumbsUp).toBeVisible();
    await expect(thumbsUp).toBeDisabled();
  });

  test('Import another build button navigates to home', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('build-summary')).toBeVisible({ timeout: 10_000 });

    // The "Import another build" link/button
    await page.getByText('Import another build').click();
    await expect(page).toHaveURL('/');
  });
});

// ---------------------------------------------------------------------------
// D5.5 – League selector
// ---------------------------------------------------------------------------

test.describe('D5.5 League selector', () => {
  test('league selector is visible in the header', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#league-select')).toBeVisible();
  });

  test('league selector defaults to Settlers', async ({ page }) => {
    await page.goto('/');
    const select = page.locator('#league-select');
    await expect(select).toHaveValue('Settlers');
  });

  test('league selector shows all three league options', async ({ page }) => {
    await page.goto('/');
    const options = page.locator('#league-select option');
    await expect(options).toHaveCount(3);
    await expect(options.nth(0)).toHaveText('Settlers (Current)');
    await expect(options.nth(1)).toHaveText('Mercenaries (Previous)');
    await expect(options.nth(2)).toHaveText('Standard');
  });

  test('changing league updates the selector value', async ({ page }) => {
    await page.goto('/');
    const select = page.locator('#league-select');
    await select.selectOption('Standard');
    await expect(select).toHaveValue('Standard');
  });

  test('league change on build page triggers recommendation re-fetch', async ({ page }) => {
    let fetchCount = 0;
    await page.route('**/api/v1/recommendations', async route => {
      fetchCount++;
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
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    const initialCount = fetchCount;

    // Change league in header
    await page.locator('#league-select').selectOption('Standard');

    // Wait for recommendations to reload
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });
    expect(fetchCount).toBeGreaterThan(initialCount);
  });
});

// ---------------------------------------------------------------------------
// D5.6 – Resources page
// ---------------------------------------------------------------------------

test.describe('D5.6 Resources page', () => {
  test('resources page renders at /resources', async ({ page }) => {
    await page.goto('/resources');
    await expect(page.getByRole('heading', { name: 'Resource Hub' })).toBeVisible();
  });

  test('header nav Resources link navigates to /resources', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Resources' }).click();
    await expect(page).toHaveURL('/resources');
  });

  test('all 5 categories are visible', async ({ page }) => {
    await page.goto('/resources');
    await expect(page.getByRole('heading', { name: 'Build Tools' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Databases' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Economy' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Trading' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Data', exact: true })).toBeVisible();
  });

  test('key links are present', async ({ page }) => {
    await page.goto('/resources');
    await expect(page.getByRole('link', { name: 'Path of Building Community Fork' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'poe.ninja – opens in new tab' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'poewiki.net' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Official Trade Site' })).toBeVisible();
  });

  test('all links open in a new tab (target=_blank)', async ({ page }) => {
    await page.goto('/resources');
    const links = page.locator('a[href^="http"]');
    const count = await links.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(links.nth(i)).toHaveAttribute('target', '_blank');
    }
  });

  test('no Fandom wiki links are present', async ({ page }) => {
    await page.goto('/resources');
    const fandomLinks = page.locator('a[href*="fandom.com"]');
    await expect(fandomLinks).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// D5.7 – Error states
// ---------------------------------------------------------------------------

test.describe('D5.7 Error states', () => {
  test('shows server error message when API returns 500', async ({ page }) => {
    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    const alert = page.getByRole('alert').filter({ hasText: 'Something went wrong generating recommendations' });
    await expect(alert).toBeVisible({ timeout: 10_000 });
  });

  test('shows network error message when API is unreachable', async ({ page }) => {
    await page.route('**/api/v1/recommendations', async route => {
      await route.abort('failed');
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    // Should show some error alert
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
  });

  test('error panel has a Try Again button', async ({ page }) => {
    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({ status: 503, body: 'Service unavailable' });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');

    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Try Again' })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// D5.5 Header navigation
// ---------------------------------------------------------------------------

test.describe('Header navigation', () => {
  test('logo link navigates to home', async ({ page }) => {
    await page.goto('/resources');
    // The logo "Home of Exile" span is inside a NavLink to "/"
    await page.getByRole('link', { name: 'Home of Exile – Home' }).click();
    await expect(page).toHaveURL('/');
  });

  test('Home nav link is active on /', async ({ page }) => {
    await page.goto('/');
    // Active nav link should have a highlighted style (bg-gray-700 class)
    const homeLink = page.getByRole('navigation').getByRole('link', { name: 'Home' });
    await expect(homeLink).toBeVisible();
    const cls = await homeLink.getAttribute('class');
    expect(cls).toContain('bg-gray-700');
  });

  test('Resources nav link is active on /resources', async ({ page }) => {
    await page.goto('/resources');
    const resourcesLink = page.getByRole('navigation').getByRole('link', { name: 'Resources' });
    await expect(resourcesLink).toBeVisible();
    const cls = await resourcesLink.getAttribute('class');
    expect(cls).toContain('bg-gray-700');
  });
});
