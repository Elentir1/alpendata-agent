import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { Language } from './locale';

export function FilePassages({ root, file, language, choose }: { root: string; file: { id: string; filename: string; version: number }; language: Language; choose: (prompt: string) => void }) {
  const fr = language === 'fr', container = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<{ reference: string; text: string }[]>([]), [error, setError] = useState(false);
  const [status, setStatus] = useState(''), [selection, setSelection] = useState('');
  useEffect(() => { let active = true; setPages([]); setSelection(''); setError(false);
    api<{ passages: typeof pages; status: string }>(`${root}/files/${file.id}/versions/${file.version}/passages`).then(result => { if (active) { setPages(result.passages); setStatus(result.status); } }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [root, file.id, file.version]);
  return <details className="file-passages"><summary>{fr ? 'Consulter le texte et ses références' : 'Read text and source references'} · v{file.version}</summary>
    {error && <p role="alert">{fr ? 'Lecture indisponible.' : 'Reading unavailable.'}</p>}
    {!pages.length && <p>{['queued', 'running'].includes(status) ? fr ? 'Analyse en cours. Rouvrez ce fichier après quelques instants.' : 'Analysis in progress. Reopen this file shortly.' : fr ? 'Aucun texte disponible pour cette version.' : 'No text available for this version.'}</p>}
    {status === 'partial' && <p>{fr ? 'Analyse partielle : certains passages ne sont pas inclus.' : 'Partial analysis: some passages are not included.'}</p>}
    <div ref={container} onMouseUp={() => { const selected = window.getSelection(); if (selected && container.current?.contains(selected.anchorNode) && container.current?.contains(selected.focusNode)) setSelection(selected.toString().slice(0, 8000)); }} onTouchEnd={() => { const selected = window.getSelection(); if (selected && container.current?.contains(selected.anchorNode) && container.current?.contains(selected.focusNode)) setSelection(selected.toString().slice(0, 8000)); }}>
      {pages.map((page, index) => <section key={index}><h4>{page.reference}</h4><p>{page.text}</p><button className="text-button" onClick={() => choose(`${fr ? 'Examine ce passage' : 'Review this passage'} (${file.filename}, ID ${file.id}, version ${file.version}, ${page.reference}) :\n\n${page.text.slice(0, 8000)}\n\n${fr ? 'Demande-moi les modifications souhaitées.' : 'Ask me for the desired changes.'}`)}>{fr ? 'Citer ce passage' : 'Quote this passage'}</button></section>)}
    </div>
    {!!selection && <button className="secondary" onClick={() => choose(`${fr ? 'Travaille sur cette sélection' : 'Work on this selection'} (${file.filename}, ID ${file.id}, version ${file.version}) :\n\n${selection}\n\n${fr ? 'Demande-moi les modifications souhaitées.' : 'Ask me for the desired changes.'}`)}>{fr ? 'Travailler sur ma sélection' : 'Work on my selection'}</button>}
  </details>;
}
