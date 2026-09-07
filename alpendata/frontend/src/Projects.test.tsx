import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Chat } from './Chat';
import { FirstTasks } from './FirstTasks';
import { copy } from './locale';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

test('creates a project, starts a project conversation and archives it with persisted metadata', async () => {
  const base = '/api/organizations/company-a/chat';
  let projects: { id: string; name: string; instructions: string }[] = [];
  let conversation: { id: string; title: string; language: string; project_id: string; archived: boolean; created_at: number } | null = null;
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path === base + '/projects') {
      if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); projects = [{ ...body, id: 'project-a' }]; return json(projects[0], 201); }
      return json({ projects });
    }
    if (path === base + '/conversations' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); expect(body.project_id).toBe('project-a');
      conversation = { ...body, id: 'chat-a', title: 'Nouvelle conversation', archived: false, created_at: 1 };
      return json(conversation, 201);
    }
    if (path.startsWith(base + '/conversations/chat-a')) {
      if (init?.method === 'PUT') conversation = { ...conversation!, ...JSON.parse(String(init.body)) };
      return json({ ...conversation, turns: [], next_after: null });
    }
    if (path === base || path.startsWith(base + '?')) {
      const archive = new URL(path, 'https://example.test').searchParams.get('archived') === 'true';
      return json({ available: true, model: 'zai-glm-5-2', conversations: conversation && conversation.archived === archive ? [conversation] : [], next_offset: null });
    }
    throw new Error('Unexpected request ' + path);
  }));
  render(<Chat organizationId="company-a" licensed language="fr" t={copy.fr} />);
  await userEvent.click(screen.getByRole('button', { name: 'Créer un projet' }));
  await userEvent.type(screen.getByLabelText('Nom du projet'), 'Client Exemple');
  await userEvent.type(screen.getByLabelText('Contexte et consignes'), 'Des synthèses courtes pour la direction.');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le projet' }));
  await screen.findByRole('button', { name: 'Modifier le projet' });
  await userEvent.click(screen.getByRole('button', { name: 'Nouvelle conversation' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Organiser' }));
  await userEvent.clear(screen.getByLabelText('Titre de la discussion'));
  await userEvent.type(screen.getByLabelText('Titre de la discussion'), 'Séance de septembre');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
  await screen.findByRole('heading', { name: 'Séance de septembre' });
  await userEvent.click(screen.getByRole('button', { name: 'Archiver la discussion' }));
  await waitFor(() => expect(screen.queryByRole('heading', { name: 'Séance de septembre' })).toBeNull());
  await userEvent.click(screen.getByLabelText('Discussions archivées'));
  await screen.findByRole('heading', { name: 'Séance de septembre' });
  expect(projects[0].instructions).toBe('Des synthèses courtes pour la direction.');
});

test('business ideas personalize a task without submitting or connecting anything automatically', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  render(<FirstTasks organizationId="company-a" language="fr" sector="coaching" onOpen={() => {}} />);
  await userEvent.click(screen.getByRole('button', { name: /Concevoir un atelier/ }));
  expect((screen.getByLabelText('Par quoi aimeriez-vous commencer ?') as HTMLTextAreaElement).value).toContain('PowerPoint');
  await userEvent.click(screen.getByRole('button', { name: 'Explorer les 6 pistes PME' }));
  await screen.findByRole('button', { name: /Accueillir un collaborateur/ });
  expect(fetcher).not.toHaveBeenCalled();
});
