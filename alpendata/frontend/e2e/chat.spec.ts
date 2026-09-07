import { test, expect } from '@playwright/test';

test('chat keeps composition visible, renders results, and exposes personal tools on desktop and mobile', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const organization = { id: 'example-org', name: 'Atelier Exemple' };
  const person = { id: 'example-user', display_name: 'Alex Exemple', memberships: [{ organization_id: organization.id, user_id: 'example-user', role: 'member', active: true, licensed: true }] };
  let conversations: { id: string; title: string; language: string; created_at: number; model: string; tool_revision: number }[] = [];
  let turns: object[] = [], sent = 0;
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname, method = route.request().method();
    let result: unknown;
    if (path.endsWith('/auth/options')) result = { password: true, microsoft: false, invitation_email: false };
    else if (path === '/api/me') result = person;
    else if (path === '/api/organizations/example-org') result = organization;
    else if (path.endsWith('/onboarding')) result = { step: 'first_result', answers: { role: 'Coach', needs: 'Préparer les ateliers' } };
    else if (path.endsWith('/notifications')) result = { notifications: [], next_before: null, unread_count: 0 };
    else if (path.endsWith('/microsoft')) result = { available: false, status: 'disconnected', capabilities: [] };
    else if (path.endsWith('/action-policy')) result = { version: 0, email_mode: 'confirm', automatic_allowed: true, automatic_available: false };
    else if (path.endsWith('/memory')) result = { available: true, memory: { version: 'a', entries: ['Vérifier les objectifs avant chaque atelier.'], limit: 2200 }, user: { version: 'b', entries: [], limit: 1300 } };
    else if (path.endsWith('/chat/projects')) result = { projects: [] };
    else if (path.endsWith('/chat/conversations') && method === 'POST') { conversations = [{ id: 'example-chat', title: 'Nouvelle conversation', language: 'fr', created_at: Date.now() / 1000, model: 'zai-glm-5-2', tool_revision: 6 }]; result = conversations[0]; }
    else if (path.endsWith('/chat')) result = { available: true, model: 'zai-glm-5-2', conversations, next_offset: null };
    else if (path.endsWith('/turns')) {
      sent++;
      const body = route.request().postDataJSON();
      const response = '## Plan de l’atelier\n\nVoici les étapes **vérifiées**.\n\n| Étape | Durée |\n| --- | --- |\n| Accueil | 15 min |\n| Mise en pratique | 45 min |\n\n' + Array.from({ length: 10 }, (_, i) => `### Séquence ${i + 1}\n\nPréparez les objectifs et les questions à poser.\n\n`).join('');
      turns = [{ ...body, id: 'turn-one', sequence: 1, status: 'completed', response, cancel_requested: false, artifacts: [{ id: 'doc-one', filename: 'atelier.docx', media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: 12000 }] }];
      result = turns[0];
    }
    else if (path.includes('/chat/conversations/')) result = { ...conversations[0], turns, next_after: null };
    else { await route.fulfill({ status: 404, json: { detail: 'unconfigured_fixture' } }); return; }
    await route.fulfill({ json: result });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Assistant', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Qu’allons-nous accomplir ?' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Créer un livrable/ })).toBeEnabled();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: testInfo.outputPath('welcome.png') });
  await page.getByRole('button', { name: /Créer un livrable/ }).click();
  const input = page.getByLabel('Votre message', { exact: true });
  await expect(input).toHaveValue(/Aide-moi à créer un document/);
  expect(sent).toBe(0);
  await input.fill('Prépare mon atelier');
  await input.press('Shift+Enter');
  await expect(input).toHaveValue('Prépare mon atelier\n');
  expect(sent).toBe(0);
  await input.press('Enter');
  await expect(page.getByRole('heading', { name: 'Plan de l’atelier' })).toBeAttached();
  expect(sent).toBe(1);
  await expect(page.getByRole('table')).toBeAttached();
  await expect(input).toBeInViewport();
  const transcript = page.locator('.transcript-scroll');
  await transcript.evaluate(el => { el.scrollTop = 0; });
  await expect(page.getByRole('button', { name: 'Derniers messages' })).toBeVisible();
  await expect(input).toBeInViewport();
  await page.getByRole('button', { name: 'Livrables de la discussion' }).click();
  await expect(page.getByRole('button', { name: 'Télécharger atelier.docx' })).toBeVisible();
  await page.getByRole('button', { name: 'Mémoire', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Élément 1' })).toHaveValue('Vérifier les objectifs avant chaque atelier.');
  await page.getByRole('button', { name: 'Connexions', exact: true }).click();
  await expect(page.getByText('La connexion aux outils n’est pas encore configurée dans cet environnement.')).toBeVisible();
  await page.getByRole('button', { name: 'Fermer le volet' }).click();
  await input.fill('Mon brouillon reste ici');
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Afficher les discussions' }).click();
  await page.getByRole('searchbox').fill('introuvable');
  await expect(input).toHaveValue('Mon brouillon reste ici');
  await page.getByRole('button', { name: 'Masquer les discussions' }).click();
  await expect(input).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('chat.png') });
  expect(errors).toEqual([]);
});
