import { useEffect, useRef, useState } from 'react';
import type { Language } from './locale';

export interface EditorConfig { id: string; base_version: number; automation_enabled: boolean; script_url: string; config: Record<string, unknown> }
interface Connector { disconnect: () => void; executeMethod: (method: string, args: unknown[], callback: (result: unknown) => void) => void }
interface OfficeEditor { destroyEditor: () => void; createConnector?: () => Connector }
declare global { interface Window { DocsAPI?: { DocEditor: new (id: string, config: Record<string, unknown>) => OfficeEditor } } }

export function Office({ configuration, file, language, choose, failed }: {
  configuration: EditorConfig; file: { id: string; filename: string }; language: Language;
  choose: (prompt: string) => void; failed: () => void;
}) {
  const elementId = 'office-' + configuration.id, fr = language === 'fr';
  const connector = useRef<Connector | null>(null), timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0), [ready, setReady] = useState(false), [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    let active = true, editor: OfficeEditor | undefined, script: HTMLScriptElement | undefined;
    setReady(false); setSelection(''); setError(''); setBusy(false);
    const start = () => {
      if (!active || !window.DocsAPI) return;
      try {
        editor = new window.DocsAPI.DocEditor(elementId, { ...configuration.config, events: {
          onError: () => { if (active) failed(); },
          onDocumentReady: () => {
            if (!active || !configuration.automation_enabled) return;
            try { connector.current = editor?.createConnector?.() || null; setReady(Boolean(connector.current)); }
            catch { setError(fr ? 'La sélection assistée est indisponible.' : 'Assisted selection is unavailable.'); }
          },
        } });
      } catch { failed(); }
    };
    if (window.DocsAPI) start();
    else {
      script = document.createElement('script'); script.src = configuration.script_url; script.async = true;
      script.onload = start; script.onerror = () => { if (active) failed(); }; document.head.append(script);
    }
    return () => { active = false; generation.current++; clearTimeout(timeout.current); connector.current?.disconnect(); connector.current = null; editor?.destroyEditor(); script?.remove(); };
  }, [configuration.id]);

  function capture() {
    if (!connector.current || busy) return;
    const request = ++generation.current;
    setBusy(true); setError(''); setSelection('');
    const unavailable = () => { setBusy(false); setError(fr ? 'Impossible de lire cette sélection. Sélectionnez du texte puis réessayez.' : 'Cannot read this selection. Select text and try again.'); };
    timeout.current = setTimeout(() => { if (generation.current === request) { generation.current++; unavailable(); } }, 10000);
    try {
      connector.current.executeMethod('GetSelectedText', [{ Numbering: false, Math: true, TableCellSeparator: '\t', ParaSeparator: '\n' }], value => {
        if (generation.current !== request) return;
        clearTimeout(timeout.current); setBusy(false);
        if (typeof value !== 'string' || !value.trim()) { unavailable(); return; }
        if (value.length > 12000) { setError(fr ? 'Sélection trop longue. Choisissez un passage de moins de 12 000 caractères.' : 'Selection too long. Choose fewer than 12,000 characters.'); return; }
        setSelection(value);
      });
    } catch { clearTimeout(timeout.current); unavailable(); }
  }
  return <section>
    {configuration.automation_enabled && <div className="office-selection">
      <button type="button" className="secondary" disabled={!ready || busy} onClick={capture}>{fr ? 'Reprendre la sélection avec l’assistant' : 'Work on the selection with the assistant'}</button>
      {error && <p role="alert">{error}</p>}
      {selection && <><blockquote>{selection}</blockquote><p className="subtle">{fr ? 'Ce passage vient de l’éditeur ouvert et peut contenir des modifications non encore enregistrées. Il sera ajouté au brouillon de la discussion.' : 'This passage comes from the open editor and may include unsaved changes. It will be added to your conversation draft.'}</p>
        <button type="button" className="primary" onClick={() => choose(`${fr ? 'Aide-moi à retravailler cette sélection de' : 'Help me revise this selection from'} « ${file.filename} » (${file.id}, ${fr ? 'session ouverte depuis' : 'session opened from'} v${configuration.base_version}). ${fr ? 'Le texte peut inclure des modifications non enregistrées. Propose une révision sans écraser le fichier.' : 'Text may include unsaved changes. Propose a revision without overwriting the file.'}\n\n${JSON.stringify({ selected_text: selection })}\n\n`)}>{fr ? 'Ajouter au brouillon' : 'Add to draft'}</button></>}
    </div>}
    <div className="office-frame"><div id={elementId} /></div>
  </section>;
}
