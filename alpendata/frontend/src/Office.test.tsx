import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Office, type EditorConfig } from './Office';

const configuration: EditorConfig = { id: 'session', base_version: 3, provider: 'collabora', action_url: 'https://office.example.test/browser/build/cool.html?WOPISrc=https%3A%2F%2Fapp.example.test%2Fwopi%2Fsession', access_token: 'synthetic-document-token', access_token_ttl: 1800000000000 };
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function message(frame: HTMLIFrameElement, MessageId: string, Values = {}, origin = 'https://office.example.test', source = frame.contentWindow) {
  act(() => { window.dispatchEvent(new MessageEvent('message', { origin, source, data: JSON.stringify({ MessageId, Values }) })); });
}

test('Collabora credentials are posted to its frame, and only its requested selection can enter the draft', async () => {
  const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
  const choose = vi.fn(), failed = vi.fn();
  const view = render(<Office configuration={configuration} file={{ id: 'private-file', filename: 'Client.docx' }} language="en" choose={choose} failed={failed} />);
  const frame = screen.getByTitle('Client.docx') as HTMLIFrameElement;
  const post = vi.spyOn(frame.contentWindow!, 'postMessage');
  expect(submit).toHaveBeenCalledOnce();
  expect(frame.src).not.toContain(configuration.access_token);
  const form = view.container.querySelector('form')!;
  expect(form.method).toBe('post'); expect(form.target).toBe(frame.name);
  expect(new FormData(form).get('access_token')).toBe(configuration.access_token);
  const capture = screen.getByRole('button', { name: 'Work on the selection with the assistant' });
  message(frame, 'App_LoadingStatus', { Status: 'Document_Loaded' }, 'https://evil.example');
  expect(capture).toHaveProperty('disabled', true);
  message(frame, 'App_LoadingStatus', { Status: 'Document_Loaded' });
  message(frame, 'Action_Copy_Resp', { content: 'Unrequested secret' });
  expect(screen.queryByText('Unrequested secret')).toBeNull();
  await userEvent.click(capture);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('Action_Copy'), 'https://office.example.test');
  message(frame, 'Action_Copy_Resp', { content: 'Wrong frame' }, 'https://office.example.test', window);
  expect(screen.queryByText('Wrong frame')).toBeNull();
  message(frame, 'Action_Copy_Resp', { content: 'Confidential selected passage' });
  expect(choose).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Add to draft' }));
  expect(choose).toHaveBeenCalledWith(expect.stringContaining('session opened from v3'));
  expect(choose).toHaveBeenCalledWith(expect.stringContaining('Confidential selected passage'));
  view.unmount();
  message(frame, 'App_LoadingStatus', { Status: 'Failed' });
  expect(failed).not.toHaveBeenCalled();
});

test('Collabora save failures remain visible and never announce a successful save', async () => {
  vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
  render(<Office configuration={configuration} file={{ id: 'file', filename: 'Budget.xlsx' }} language="fr" choose={vi.fn()} failed={vi.fn()} />);
  const frame = screen.getByTitle('Budget.xlsx') as HTMLIFrameElement;
  const post = vi.spyOn(frame.contentWindow!, 'postMessage');
  message(frame, 'App_LoadingStatus', { Status: 'Document_Loaded' });
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le document' }));
  expect(post).toHaveBeenCalledWith(expect.stringContaining('Action_Save'), 'https://office.example.test');
  message(frame, 'Action_Save_Resp', { success: false });
  expect(screen.getByRole('alert').textContent).toContain('Gardez l’éditeur ouvert');
});
