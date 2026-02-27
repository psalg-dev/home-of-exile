/**
 * M7 LLM Enhancement — E2E tests.
 *
 * Covers:
 *   D7.3  A/B routing: session_id included in recommendations request
 *   D7.4  UI shows template explanations when explanation_source='template'
 *   D7.5  "Report incorrect explanation" button appears only for LLM-sourced
 *          recommendations, submits wrong_explanation feedback vote
 */

import { test, expect, type Page } from '@playwright/test';
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
  <Build level="85" className="Witch" ascendClassName="Occultist" characterName="M7Tester" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="4200"/>
    <PlayerStat stat="EnergyShield" value="800"/>
    <PlayerStat stat="CombinedDPS" value="600000"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-20"/>
  </Build>
  <Skills>
    <Skill slot="Body Armour" enabled="true" label="">
      <Gem nameSpec="Fireball" skillId="Metadata/Items/Gems/SkillGemFireball" level="20" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree><Spec nodes="1 2 3"/></Tree>
  <Items/>
</PathOfBuilding>`;

const FIXTURE_CODE = encodePobCode(FIXTURE_XML);

/** Fixture response with one LLM-sourced and one template-sourced recommendation. */
const FIXTURE_RESPONSE_LLM = {
  recommendations: [
    {
      rank: 1,
      category: 'power_upgrade',
      slot: 'Helmet',
      current_item: 'Rare Helmet',
      suggested_item: "Starkonja's Head",
      deltas: { dps: 200000, life: 300 },
      price_divine: 2.0,
      efficiency_score: 0.7,
      explanation: 'This LLM-generated explanation is very insightful.',
      explanation_source: 'llm',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: 'https://www.poewiki.net/wiki/Starkonja%27s_Head',
      ninja_url: null,
      score: 8.5,
    },
    {
      rank: 2,
      category: 'efficiency',
      slot: 'Boots',
      current_item: 'Rare Boots',
      suggested_item: 'Rainbowstride',
      deltas: { dps: 0, fire_res: 15, cold_res: 15 },
      price_divine: 0.5,
      efficiency_score: 0.9,
      explanation: 'Template explanation for boots upgrade.',
      explanation_source: 'template',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: null,
      ninja_url: null,
      score: 5.0,
    },
  ],
  critical_issues: [],
  simulation_count: 8,
  elapsed_seconds: 0.4,
};

/** Fixture response where all recommendations are template-sourced. */
const FIXTURE_RESPONSE_TEMPLATE = {
  recommendations: [
    {
      rank: 1,
      category: 'power_upgrade',
      slot: 'Weapon',
      current_item: 'Driftwood Wand',
      suggested_item: "Pledge of Hands",
      deltas: { dps: 150000 },
      price_divine: 1.5,
      efficiency_score: 0.5,
      explanation: 'Template explanation for weapon upgrade.',
      explanation_source: 'template',
      trade_url: 'https://www.pathofexile.com/trade/search/Settlers?q=%7B%7D',
      wiki_url: null,
      ninja_url: null,
      score: 7.0,
    },
  ],
  critical_issues: [],
  simulation_count: 5,
  elapsed_seconds: 0.3,
};

// ---------------------------------------------------------------------------
// Helper: navigate to build page with intercepted response
// ---------------------------------------------------------------------------

async function navigateToBuildPage(
  page: Page,
  fixture: typeof FIXTURE_RESPONSE_LLM,
) {
  await page.route('**/api/v1/recommendations', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fixture),
    });
  });

  await page.route('**/api/v1/feedback', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    });
  });

  await page.goto('/');
  await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
  await page.getByRole('button', { name: 'Analyse Build' }).click();
  await expect(page).toHaveURL('/build');
  await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });
}

// ---------------------------------------------------------------------------
// D7.3 — session_id in recommendations request
// ---------------------------------------------------------------------------

test.describe('D7.3 session_id in recommendations request', () => {
  test('recommendations request body includes session_id', async ({ page }) => {
    let capturedBody: Record<string, unknown> | null = null;

    await page.route('**/api/v1/recommendations', async route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      capturedBody = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE_TEMPLATE),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Verify session_id was sent
    expect(capturedBody).not.toBeNull();
    expect(capturedBody).toHaveProperty('session_id');
    expect(typeof capturedBody!['session_id']).toBe('string');
    expect((capturedBody!['session_id'] as string).length).toBeGreaterThan(0);
  });

  test('session_id is stable across multiple requests in same session', async ({ page }) => {
    const capturedSessionIds: string[] = [];

    await page.route('**/api/v1/recommendations', async route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      if (body['session_id']) {
        capturedSessionIds.push(body['session_id'] as string);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE_TEMPLATE),
      });
    });

    // First request
    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Navigate back and make a second request
    await page.getByText('Import another build').click();
    await expect(page).toHaveURL('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Both requests should use the same session_id
    expect(capturedSessionIds).toHaveLength(2);
    expect(capturedSessionIds[0]).toBe(capturedSessionIds[1]);
  });
});

// ---------------------------------------------------------------------------
// D7.4 — Template vs LLM explanation rendering
// ---------------------------------------------------------------------------

test.describe('D7.4 Template vs LLM explanation rendering', () => {
  test('template-sourced explanation renders without report button', async ({ page }) => {
    await navigateToBuildPage(page, FIXTURE_RESPONSE_TEMPLATE);

    // Expand the first recommendation card
    await page.getByTestId('recommendation-1').getByRole('button').first().click();

    // Template explanation text should be visible
    await expect(
      page.getByText('Template explanation for weapon upgrade.')
    ).toBeVisible();

    // Report button should NOT be present for template source
    await expect(
      page.getByTestId('report-explanation-1')
    ).not.toBeAttached();
  });

  test('LLM-sourced explanation renders with report button visible', async ({ page }) => {
    await navigateToBuildPage(page, FIXTURE_RESPONSE_LLM);

    // Expand the first recommendation card (rank 1 = LLM)
    await page.getByTestId('recommendation-1').getByRole('button').first().click();

    // LLM explanation text should be visible
    await expect(
      page.getByText('This LLM-generated explanation is very insightful.')
    ).toBeVisible();

    // Report button SHOULD be present for LLM source
    await expect(
      page.getByTestId('report-explanation-1')
    ).toBeVisible();
    await expect(
      page.getByTestId('report-explanation-1')
    ).toContainText('Report incorrect explanation');
  });

  test('template-sourced rank 2 does not show report button', async ({ page }) => {
    await navigateToBuildPage(page, FIXTURE_RESPONSE_LLM);

    // Expand the second recommendation card (rank 2 = template)
    await page.getByTestId('recommendation-2').getByRole('button').first().click();

    // Template explanation should be visible
    await expect(
      page.getByText('Template explanation for boots upgrade.')
    ).toBeVisible();

    // Report button should NOT be present for template source
    await expect(
      page.getByTestId('report-explanation-2')
    ).not.toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// D7.5 — "Report incorrect explanation" wrong_explanation feedback vote
// ---------------------------------------------------------------------------

test.describe('D7.5 Report incorrect explanation', () => {
  test('clicking report button submits wrong_explanation vote', async ({ page }) => {
    let capturedFeedbackBody: Record<string, unknown> | null = null;

    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE_LLM),
      });
    });

    await page.route('**/api/v1/feedback', async route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      capturedFeedbackBody = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Expand the LLM recommendation card
    await page.getByTestId('recommendation-1').getByRole('button').first().click();

    // Click the report button
    await page.getByTestId('report-explanation-1').click();

    // Wait for feedback API call
    await page.waitForTimeout(500);

    // Verify feedback body
    expect(capturedFeedbackBody).not.toBeNull();
    // vote is at the top level, context is nested
    expect(capturedFeedbackBody!['vote']).toBe('wrong_explanation');
    const ctx = capturedFeedbackBody!['context'] as Record<string, unknown>;
    expect(ctx).toBeDefined();
    expect(ctx['explanation_source']).toBe('llm');
    expect(ctx['slot']).toBe('Helmet');
  });

  test('report button shows thank you after clicking', async ({ page }) => {
    await navigateToBuildPage(page, FIXTURE_RESPONSE_LLM);

    // Expand the LLM recommendation card
    await page.getByTestId('recommendation-1').getByRole('button').first().click();

    // Ensure report button is visible before clicking
    await expect(page.getByTestId('report-explanation-1')).toBeVisible();

    // Click the report button
    await page.getByTestId('report-explanation-1').click();

    // Button should disappear and "Thank you" message should appear
    await expect(page.getByTestId('report-explanation-1')).not.toBeAttached();
    await expect(page.getByText('Thank you for the report.')).toBeVisible();
  });

  test('report button cannot be clicked twice (idempotent)', async ({ page }) => {
    let feedbackCallCount = 0;

    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE_LLM),
      });
    });

    await page.route('**/api/v1/feedback', async route => {
      feedbackCallCount++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Expand and click report
    await page.getByTestId('recommendation-1').getByRole('button').first().click();
    await page.getByTestId('report-explanation-1').click();

    // After reporting, the button is gone — cannot click again
    await expect(page.getByTestId('report-explanation-1')).not.toBeAttached();
    await page.waitForTimeout(300);

    // Should only have been called once
    expect(feedbackCallCount).toBe(1);
  });

  test('explanation_source: llm is included in feedback context', async ({ page }) => {
    let capturedBody: Record<string, unknown> | null = null;

    await page.route('**/api/v1/recommendations', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FIXTURE_RESPONSE_LLM),
      });
    });

    await page.route('**/api/v1/feedback', async route => {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Paste your PoB export code here...').fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page).toHaveURL('/build');
    await expect(page.getByTestId('recommendations-list')).toBeVisible({ timeout: 10_000 });

    // Expand and click report
    await page.getByTestId('recommendation-1').getByRole('button').first().click();
    await page.getByTestId('report-explanation-1').click();

    await page.waitForTimeout(500);

    expect(capturedBody).not.toBeNull();
    const ctx = capturedBody!['context'] as Record<string, unknown>;
    expect(ctx['explanation_source']).toBe('llm');
  });
});
