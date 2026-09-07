import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import type { Language } from './locale';

export function ProjectDialog({ children, close, language, disabled, title }: { title?: string; children: ReactNode; close: () => void; language: Language; disabled: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute('open', '');
    return () => { dialog?.close?.(); };
  }, []);
  return createPortal(<dialog className="project-dialog" onSubmit={event => event.stopPropagation()} aria-label={title || (language === 'fr' ? 'Configurer mon projet' : 'Configure my project')} ref={ref} onCancel={event => { event.preventDefault(); if (!disabled) close(); }}>
    <header><h2>{title || (language === 'fr' ? 'Un contexte pour vos discussions' : 'Context for your conversations')}</h2><button type="button" className="icon-button" disabled={disabled} onClick={close} aria-label={language === 'fr' ? 'Fermer le projet' : 'Close project'}><X size={18} /></button></header>{children}
  </dialog>, document.body);
}
