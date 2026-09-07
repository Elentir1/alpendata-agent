import { useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';
import type { Language } from './locale';

export function ChatResponse({ text, language }: { text: string; language: Language }) {
  const [copied, setCopied] = useState(false), [failed, setFailed] = useState(false);
  return <>
    <div className="response-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{
      // Remote image requests could disclose private content to a model-generated URL.
      img: ({ alt }) => <span>{alt}</span>,
      a: ({ href, children }) => href && /^https?:\/\//i.test(href) ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
      table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
    }}>{text}</Markdown></div>
    <button className="response-copy" type="button" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setCopied(true); setFailed(false); }
      catch { setFailed(true); }
    }}>{copied ? <Check size={14} /> : <Copy size={14} />}{language === 'fr' ? copied ? 'Copié' : 'Copier la réponse' : copied ? 'Copied' : 'Copy response'}</button>
    {failed && <p role="status">{language === 'fr' ? 'La copie a échoué. Vous pouvez sélectionner le texte pour le copier.' : 'Copy failed. You can select and copy the text instead.'}</p>}
  </>;
}
