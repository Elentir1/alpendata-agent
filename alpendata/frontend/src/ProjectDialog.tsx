import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import type { Language } from './locale';

export function ProjectDialog({ children, close, language, disabled }: { children: ReactNode; close: () => void; language: Language; disabled: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute('open', '');
    return () => { dialog?.close?.(); };
  }, []);
  return <dialog className="project-dialog" aria-label={language === 'fr' ? 'Configurer mon projet' : 'Configure my project'} ref={ref} onCancel={event => { event.preventDefault(); if (!disabled) close(); }}>
    <header><h2>{language === 'fr' ? 'Un contexte pour vos discussions' : 'Context for your conversations'}</h2><button className="icon-button" disabled={disabled} onClick={close} aria-label={language === 'fr' ? 'Fermer le projet' : 'Close project'}><X size={18} /></button></header>{children}
  </dialog>;
}
