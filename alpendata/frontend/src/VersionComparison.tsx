import { useEffect, useState } from 'react';
import { api, ApiError } from './api';
import { ProjectDialog } from './ProjectDialog';
import type { Language } from './locale';

interface Result { partial: boolean; identical_bytes: boolean; text_available: boolean; changed_sections: number; differences: { reference: string; before: string; after: string }[] }
export function VersionComparison({ root, fileId, before, after, otherFileId, language, close }: { root: string; fileId: string; before: number; after: number; otherFileId?: string; language: Language; close: () => void }) {
  const fr = language === 'fr', [result, setResult] = useState<Result | null>(null), [error, setError] = useState('');
  useEffect(() => { let active = true; api<Result>(`${root}/files/${fileId}/compare`, { before_version: before, after_version: after, ...(otherFileId ? { other_file_id: otherFileId } : {}) }).then(value => { if (active) setResult(value); }).catch(cause => { if (active) setError(cause instanceof ApiError && cause.code === 'document_analysis_pending' ? fr ? 'L’analyse des versions est encore en cours. Réessayez dans quelques instants.' : 'Version analysis is still running. Try again shortly.' : fr ? 'Comparaison indisponible.' : 'Comparison unavailable.'); }); return () => { active = false; }; }, [root, fileId, before, after, otherFileId]);
  return <ProjectDialog title={fr ? 'Comparer les versions' : 'Compare versions'} language={language} close={close} disabled={false}>
    <p>{fr ? 'Comparaison du texte extrait. La mise en page et les éléments graphiques peuvent différer ; les fichiers originaux restent disponibles.' : 'Comparison of extracted text. Layout and graphics may differ; original files remain available.'}</p>
    <div className="message-actions"><a href={`${root}/files/${fileId}/versions/${before}/content`} download>{fr ? 'Version de départ' : 'Starting version'} · v{before}</a><a href={`${root}/files/${otherFileId || fileId}/versions/${after}/content`} download>{fr ? 'Version comparée' : 'Compared version'} · v{after}</a></div>
    {error && <p role="alert">{error}</p>}{!result && !error && <p role="status">{fr ? 'Comparaison…' : 'Comparing…'}</p>}
    {result?.identical_bytes && <p>{fr ? 'Les fichiers sont identiques.' : 'The files are identical.'}</p>}
    {result && !result.identical_bytes && !result.changed_sections && <p>{result.text_available ? fr ? 'Aucune différence dans le texte extrait. Vérifiez la mise en page dans les fichiers.' : 'No differences in extracted text. Check layout in the files.' : fr ? 'Le texte de ces fichiers ne permet pas une comparaison. Téléchargez les versions pour les examiner.' : 'The files have no comparable extracted text. Download the versions to inspect them.'}</p>}
    {result?.partial && <p>{fr ? 'Aperçu partiel : téléchargez les versions pour une vérification complète.' : 'Partial preview: download the versions for a complete review.'}</p>}
    {result?.differences.map(change => <section className="version-comparison" key={change.reference}><h3>{change.reference}</h3><div><article><strong>{fr ? 'Avant' : 'Before'}</strong><pre>{change.before || '—'}</pre></article><article><strong>{fr ? 'Après' : 'After'}</strong><pre>{change.after || '—'}</pre></article></div></section>)}
  </ProjectDialog>;
}
