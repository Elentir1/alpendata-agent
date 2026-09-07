import { useEffect, useState } from 'react';
import { api } from './api';
import type { Language } from './locale';

interface Result { id: string; kind: string; title: string; text: string; project_id: string; project_name: string; version?: number }
interface Page { results: Result[]; next_offset: number | null }

export function SearchResources({ base, query, project, language, disabled, choose }: { base: string; query: string; project: string; language: Language; disabled: boolean; choose: (projectId: string, prompt: string) => void }) {
  const fr = language === 'fr', [page, setPage] = useState<Page | null>(null), [failed, setFailed] = useState(false);
  const url = `${base}/search-resources?q=${encodeURIComponent(query.trim())}${project ? '&project=' + encodeURIComponent(project) : ''}`;
  useEffect(() => { let active = true; setPage(null); setFailed(false);
    const timer = setTimeout(() => { api<Page>(url).then(value => { if (active) setPage(value); }).catch(() => { if (active) setFailed(true); }); }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [url]);
  return <section className="search-resources" aria-label={fr ? 'Résultats dans les projets' : 'Project search results'}>
    <h4>{fr ? 'Documents et connaissances' : 'Documents and knowledge'}</h4>
    {failed && <p role="status">{fr ? 'La recherche dans les projets est indisponible.' : 'Project search is unavailable.'}</p>}
    {page?.results.map(result => <details key={result.id}><summary>{result.title}<small>{result.project_name}</small></summary><p>{result.text}</p>
      {result.kind === 'document' && <a href={`${base.replace(/\/chat$/, '')}/files/${result.id}/versions/${result.version}/content`} download>{fr ? 'Télécharger cette version' : 'Download this version'} · v{result.version}</a>}
      <button className="text-button" disabled={disabled} onClick={() => choose(result.project_id, result.kind === 'document'
        ? `${fr ? 'Retrouve et lis ce fichier du projet' : 'Find and read this project file'} : ${result.title}, ID ${result.id}, version ${result.version}. ${fr ? 'Demande-moi le travail souhaité.' : 'Ask me what I want to do with it.'}`
        : `${fr ? 'Retrouve cette ressource dans le projet' : 'Find this resource in the project'} : ${result.title}, ID ${result.id}. ${fr ? 'Demande-moi le travail souhaité.' : 'Ask me what I want to do with it.'}`)}>{fr ? 'Ouvrir une discussion dans ce projet' : 'Open a conversation in this project'}</button>
    </details>)}
    {page && !page.results.length && <p className="subtle">{fr ? 'Aucune ressource correspondante.' : 'No matching resources.'}</p>}
    {page?.next_offset != null && <button className="text-button" onClick={async () => { try { const more = await api<Page>(url + '&before=' + page.next_offset); setPage({ ...more, results: [...page.results, ...more.results] }); } catch { setFailed(true); } }}>{fr ? 'Voir la suite' : 'Show more'}</button>}
  </section>;
}
