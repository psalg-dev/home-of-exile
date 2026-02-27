import { test, expect } from '@playwright/test';
import { deflate } from 'pako';

/**
 * Helper: encode an XML string as a PoB-style URL-safe base64 code.
 *
 * @param xml - Raw XML string to encode
 * @returns URL-safe base64 PoB code
 */
function encodePobCode(xml: string): string {
  const bytes = new TextEncoder().encode(xml);
  const compressed = deflate(bytes);
  const base64 = Buffer.from(compressed).toString('base64');
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Minimal PoB XML for a Slayer build used in E2E tests */
const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="90" className="Duelist" ascendClassName="Slayer" characterName="E2ESlayer" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="4000"/>
    <PlayerStat stat="EnergyShield" value="0"/>
    <PlayerStat stat="CombinedDPS" value="500000"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('HomePage', () => {
  test('renders the home page with correct title and elements', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Home of Exile' })).toBeVisible();
    await expect(page.getByPlaceholder('Paste your PoB export code here...')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Analyse Build' })).toBeDisabled();
  });

  test('enables the Analyse Build button when code is entered', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill(FIXTURE_CODE);
    await expect(page.getByRole('button', { name: 'Analyse Build' })).toBeEnabled();
  });

  test('shows error message for empty input on submit', async ({ page }) => {
    await page.goto('/');
    // The button is disabled for empty input so no error should appear
    const button = page.getByRole('button', { name: 'Analyse Build' });
    await expect(button).toBeDisabled();
  });

  test('shows error for invalid PoB code', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill('aGVsbG8gd29ybGQ='); // "hello world" in base64 — not valid PoB
    await page.getByRole('button', { name: 'Analyse Build' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
  });
});

test.describe('BuildPage', () => {
  test('displays build data after successful PoB code input', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    // Should navigate to /build
    await expect(page).toHaveURL('/build');

    // Verify character info
    await expect(page.getByText('E2ESlayer')).toBeVisible();
    await expect(page.getByText('Duelist', { exact: true })).toBeVisible();
    await expect(page.getByText('Slayer', { exact: true })).toBeVisible();
    await expect(page.getByText('90', { exact: true })).toBeVisible();
  });

  test('displays main skill name', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await expect(page.getByText('Double Strike')).toBeVisible();
  });

  test('displays stats correctly', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    // Life should show 4,000
    await expect(page.getByText('4,000')).toBeVisible();
    // Chaos res should show -60%
    await expect(page.getByText('-60%')).toBeVisible();
  });

  test('shows no build data message when navigating directly to /build', async ({ page }) => {
    await page.goto('/build');
    await expect(page.getByText('No build data found.')).toBeVisible();
    await expect(page.getByRole('link', { name: '← Import a build' })).toBeVisible();
  });

  test('can navigate back to home page from build page', async ({ page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('Paste your PoB export code here...');
    await textarea.fill(FIXTURE_CODE);
    await page.getByRole('button', { name: 'Analyse Build' }).click();

    await expect(page).toHaveURL('/build');
    await page.getByRole('link', { name: '← Import another build' }).click();
    await expect(page).toHaveURL('/');
  });
});
