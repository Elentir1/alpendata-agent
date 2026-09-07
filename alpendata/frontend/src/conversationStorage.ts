import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

const prefix = 'alpendata.chat.';
export function readChatValue(key: string) {
  try { return localStorage.getItem(prefix + key) || ''; }
  catch { return ''; }
}
export function writeChatValue(key: string, value: string) {
  try { if (value) localStorage.setItem(prefix + key, value); else localStorage.removeItem(prefix + key); }
  catch { /* Private browsing/storage quota: editing remains available in this page. */ }
}
export function clearChatStorage() {
  try { for (const key of Object.keys(localStorage)) if (key.startsWith(prefix)) localStorage.removeItem(key); }
  catch { /* Storage may be disabled. */ }
}
export type PendingMessage = { request_id: string; message: string };
export function readPendingMessage(scope: string, conversation: string): PendingMessage | null {
  try {
    const value = JSON.parse(readChatValue(`${scope}.pending.${conversation}`));
    return value && typeof value.request_id === 'string' && typeof value.message === 'string' ? value : null;
  } catch { return null; }
}
export function savePendingMessage(scope: string, conversation: string, value: PendingMessage | null) {
  writeChatValue(`${scope}.pending.${conversation}`, value ? JSON.stringify(value) : '');
}
export function useConversationDraft(scope: string, conversation: string): [string, Dispatch<SetStateAction<string>>] {
  const key = `${scope}.draft.${conversation}`;
  const [entry, setEntry] = useState({ key, value: readChatValue(key) });
  const value = entry.key === key ? entry.value : readChatValue(key);
  const change: Dispatch<SetStateAction<string>> = next => {
    setEntry(previous => {
      const current = previous.key === key ? previous.value : readChatValue(key);
      const result = typeof next === 'function' ? next(current) : next;
      if (conversation) writeChatValue(key, result);
      return { key, value: result };
    });
  };
  return [value, change];
}

export function linkedConversation(organizationId: string) {
  const query = new URLSearchParams(location.search);
  return query.get('organization') === organizationId ? query.get('conversation') || '' : '';
}
export function rememberConversation(scope: string, organizationId: string, conversationId: string) {
  writeChatValue(`${scope}.selected`, conversationId);
  const url = new URL(location.href);
  url.searchParams.set('organization', organizationId);
  if (conversationId) url.searchParams.set('conversation', conversationId);
  else url.searchParams.delete('conversation');
  history.replaceState(null, '', url.pathname + url.search + url.hash);
}
