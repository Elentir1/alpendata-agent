import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { WorkOptions, defaultWorkSettings } from './WorkOptions';

afterEach(cleanup);

test('submitting work settings never submits the surrounding message composer', async () => {
  const send = vi.fn(), apply = vi.fn(async () => {});
  render(<form onSubmit={event => { event.preventDefault(); send(); }}><textarea defaultValue="Unsent client message" />
    <WorkOptions language="en" current={{ work_settings: defaultWorkSettings }} connections={[]} disabled={false} existing apply={apply} />
  </form>);
  await userEvent.click(screen.getByRole('button', { name: 'Work settings' }));
  await userEvent.selectOptions(screen.getByLabelText('Depth'), 'deep');
  await userEvent.click(screen.getByRole('button', { name: 'Continue with these settings' }));
  expect(apply).toHaveBeenCalledWith(expect.objectContaining({ work_settings: expect.objectContaining({ depth: 'deep' }) }));
  expect(send).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('textbox')).toHaveProperty('value', 'Unsent client message');
});

test('failed settings remain editable for a retry', async () => {
  const apply = vi.fn().mockRejectedValueOnce(new Error('Lost connection')).mockResolvedValueOnce(undefined);
  render(<WorkOptions language="en" current={{ work_settings: defaultWorkSettings }} connections={[]} disabled={false} existing apply={apply} />);
  await userEvent.click(screen.getByRole('button', { name: 'Work settings' }));
  await userEvent.selectOptions(screen.getByLabelText('Depth'), 'deep');
  await userEvent.click(screen.getByRole('button', { name: 'Continue with these settings' }));
  expect(await screen.findByText(/These settings could not be applied/)).toBeTruthy();
  expect(screen.getByLabelText('Depth')).toHaveProperty('value', 'deep');
  await userEvent.click(screen.getByRole('button', { name: 'Continue with these settings' }));
  expect(apply).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole('dialog')).toBeNull();
});
