import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { ChatResponse } from './ChatResponse';

afterEach(cleanup);
test('renders markdown tables while keeping raw HTML, remote images and unsafe links inert', () => {
  render(<ChatResponse language="fr" text={'## Synthèse\n\n| Client | État |\n| --- | --- |\n| Exemple | Prêt |\n\n<img src=x onerror=alert(1)>\n\n![privé](https://example.com/track)\n\n[piège](javascript:alert%281%29)\n\n[source](https://example.com/source)'} />);
  expect(screen.getByRole('heading', { name: 'Synthèse' })).toBeTruthy();
  expect(screen.getByRole('table')).toBeTruthy();
  expect(document.querySelector('img')).toBeNull();
  expect(screen.queryByRole('link', { name: 'piège' })).toBeNull();
  expect(screen.getByRole('link', { name: 'source' }).getAttribute('rel')).toContain('noreferrer');
});
