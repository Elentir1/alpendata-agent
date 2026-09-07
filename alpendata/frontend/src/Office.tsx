import { useEffect, useRef, useState } from 'react';
import type { Language } from './locale';

export interface EditorConfig { id: string; base_version: number; provider: 'collabora'; action_url: string; access_token: string; access_token_ttl: number }

export function Office({ configuration, file, language, choose, failed }: {
  configuration: EditorConfig; file: { id: string; filename: string }; language: Language;
  choose: (prompt: string) => void; failed: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null), form = useRef<HTMLFormElement>(null);
  const capturePending = useRef(false), timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [copyExpired, setCopyExpired] = useState(false);
  const [selection, setSelection] = useState(''), [error, setError] = useState('');
  const fr = language === 'fr', origin = new URL(configuration.action_url).origin;
  const target = 'office-' + configuration.id;
  const fail = useRef(failed); fail.current = failed;
  function send(MessageId: string, Values = {}) {
    frame.current?.contentWindow?.postMessage(JSON.stringify({ MessageId, Values, SendTime: Date.now() }), origin);
  }
  useEffect(() => {
    setReady(false); setSelection(''); setError(''); setBusy(false); setCopyExpired(false);
    capturePending.current = false;
    const loading = setTimeout(() => fail.current(), 60000);
    const receive = (event: MessageEvent) => {
      if (event.origin !== origin || event.source !== frame.current?.contentWindow) return;
      let message;
      try { message = typeof event.data === 'string' ? JSON.parse(event.data) : event.data; } catch { return; }
      if (!message || typeof message !== 'object') return;
      if (message.MessageId === 'App_LoadingStatus') {
        send('Host_PostmessageReady');
        if (message.Values?.Status === 'Document_Loaded') { clearTimeout(loading); setReady(true); }
        if (message.Values?.Status === 'Failed') { clearTimeout(loading); fail.current(); }
      }
      if (message.MessageId === 'Action_Copy_Resp' && capturePending.current) {
        capturePending.current = false; clearTimeout(timeout.current); setBusy(false);
        const value = message.Values?.content;
        if (typeof value !== 'string' || !value.trim()) { setError(fr ? 'Sélectionnez du texte dans le document puis réessayez.' : 'Select text in the document and try again.'); return; }
        if (value.length > 12000) { setError(fr ? 'Choisissez un passage de moins de 12 000 caractères.' : 'Choose a passage of fewer than 12,000 characters.'); return; }
        setSelection(value);
      }
      if (message.MessageId === 'Action_Save_Resp' && message.Values?.success === false) {
        setError(fr ? 'La sauvegarde a échoué. Gardez l’éditeur ouvert et réessayez.' : 'Saving failed. Keep the editor open and try again.');
      }
    };
    window.addEventListener('message', receive);
    // POST avoids putting the document credential in browser history or the frame URL.
    form.current?.submit();
    return () => { clearTimeout(loading); clearTimeout(timeout.current); capturePending.current = false; window.removeEventListener('message', receive); };
  }, [configuration.id]);

  function capture() {
    if (!ready || capturePending.current || copyExpired) return;
    capturePending.current = true; setBusy(true); setError(''); setSelection('');
    timeout.current = setTimeout(() => {
      capturePending.current = false; setBusy(false); setCopyExpired(true);
      setError(fr ? 'La sélection n’a pas répondu. Enregistrez puis rouvrez l’éditeur pour réessayer.' : 'Selection did not respond. Save and reopen the editor to try again.');
    }, 10000);
    send('Action_Copy', { Mimetype: 'text/plain;charset=utf-8' });
  }
  return <section>
    <div className="office-selection">
      <button type="button" className="secondary" disabled={!ready} onClick={() => { setError(''); send('Action_Save', { Notify: true, DontTerminateEdit: true }); }}>{fr ? 'Enregistrer le document' : 'Save document'}</button>
      <button type="button" className="secondary" disabled={!ready || busy || copyExpired} onClick={capture}>{fr ? 'Reprendre la sélection avec l’assistant' : 'Work on the selection with the assistant'}</button>
      {!ready && <p role="status">{fr ? 'Ouverture du document…' : 'Opening document…'}</p>}
      {error && <p role="alert">{error}</p>}
      {selection && <><blockquote>{selection}</blockquote><p className="subtle">{fr ? 'Ce passage vient de l’éditeur ouvert et peut contenir des modifications non encore enregistrées. Il sera ajouté au brouillon de la discussion.' : 'This passage comes from the open editor and may include unsaved changes. It will be added to your conversation draft.'}</p>
        <button type="button" className="primary" onClick={() => choose(`${fr ? 'Aide-moi à retravailler cette sélection de' : 'Help me revise this selection from'} « ${file.filename} » (${file.id}, ${fr ? 'session ouverte depuis' : 'session opened from'} v${configuration.base_version}). ${fr ? 'Le texte peut inclure des modifications non enregistrées. Propose une révision sans écraser le fichier.' : 'Text may include unsaved changes. Propose a revision without overwriting the file.'}\n\n${JSON.stringify({ selected_text: selection })}\n\n`)}>{fr ? 'Ajouter au brouillon' : 'Add to draft'}</button></>}
    </div>
    <form ref={form} action={configuration.action_url} method="post" target={target} hidden>
      <input type="hidden" name="access_token" value={configuration.access_token} />
      <input type="hidden" name="access_token_ttl" value={configuration.access_token_ttl} />
    </form>
    <div className="office-frame"><iframe ref={frame} name={target} title={file.filename} referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write; fullscreen" onLoad={() => send('Host_PostmessageReady')} /></div>
  </section>;
}
