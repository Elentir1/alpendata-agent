import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Office } from './Office';

afterEach(() => { cleanup(); delete window.DocsAPI; });

test('Office selection requires an explicit preview-to-draft action and disconnects on close', async () => {
  const choose = vi.fn(), failed = vi.fn(), disconnect = vi.fn(), destroyEditor = vi.fn();
  let ready: () => void = () => {};
  const executeMethod = vi.fn((_method, _args, callback) => callback('Confidential selected passage'));
  window.DocsAPI = { DocEditor: class {
    constructor(_id: string, config: Record<string, unknown>) { ready = (config.events as { onDocumentReady: () => void }).onDocumentReady; }
    createConnector() { return { executeMethod, disconnect }; }
    destroyEditor = destroyEditor;
  } };
  const view = render(<Office configuration={{ id: 'session', base_version: 3, automation_enabled: true, script_url: '', config: {} }} file={{ id: 'private-file', filename: 'Client.docx' }} language="en" choose={choose} failed={failed} />);
  expect(screen.getByRole('button')).toHaveProperty('disabled', true);
  act(ready);
  await userEvent.click(screen.getByRole('button', { name: 'Work on the selection with the assistant' }));
  expect(screen.getByText('Confidential selected passage')).toBeTruthy();
  expect(choose).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Add to draft' }));
  expect(choose).toHaveBeenCalledWith(expect.stringContaining('session opened from v3'));
  expect(choose).toHaveBeenCalledWith(expect.stringContaining('Confidential selected passage'));
  expect(executeMethod).toHaveBeenCalledOnce();
  expect(executeMethod.mock.calls[0][0]).toBe('GetSelectedText');
  view.unmount();
  expect(disconnect).toHaveBeenCalledOnce(); expect(destroyEditor).toHaveBeenCalledOnce();
  expect(failed).not.toHaveBeenCalled();
});

test('no Automation API calls are made when its license option is disabled', () => {
  const createConnector = vi.fn(); let ready: () => void = () => {};
  window.DocsAPI = { DocEditor: class {
    constructor(_id: string, config: Record<string, unknown>) { ready = (config.events as { onDocumentReady: () => void }).onDocumentReady; }
    createConnector = createConnector;
    destroyEditor() {}
  } };
  render(<Office configuration={{ id: 'session', base_version: 1, automation_enabled: false, script_url: '', config: {} }} file={{ id: 'file', filename: 'Client.docx' }} language="en" choose={vi.fn()} failed={vi.fn()} />);
  act(ready);
  expect(screen.queryByRole('button')).toBeNull();
  expect(createConnector).not.toHaveBeenCalled();
});
