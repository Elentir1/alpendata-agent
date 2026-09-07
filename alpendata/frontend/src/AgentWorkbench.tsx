import { useEffect, useRef } from 'react';
import { ArrowUpRight, Brain, CalendarClock, FileText, ListChecks, Mail, NotebookPen, PlugZap, ShieldCheck, X } from 'lucide-react';
import { PersonalMemory } from './PersonalMemory';
import { PersonalAutonomy } from './PersonalAutonomy';
import { Tools } from './Tools';
import { FirstTasks } from './FirstTasks';
import { Documents } from './Documents';
import type { DocumentReceipt } from './Documents';
import type { Language } from './locale';

export type WorkbenchTab = 'actions' | 'documents' | 'memory' | 'connections' | 'autonomy' | 'routines';
export const workActions = [
  { id: 'document', icon: FileText, fr: 'Créer un livrable', en: 'Create a deliverable', detailFr: 'Word, Excel, PowerPoint ou PDF', detailEn: 'Word, Excel, PowerPoint or PDF', promptFr: 'Aide-moi à créer un document professionnel. Commence par me demander son objectif, son public et le format souhaité (Word, Excel, PowerPoint ou PDF), puis crée un fichier téléchargeable.', promptEn: 'Help me create a professional document. First ask me about its goal, audience and preferred format (Word, Excel, PowerPoint or PDF), then create a downloadable file.' },
  { id: 'analysis', icon: ListChecks, fr: 'Analyser et décider', en: 'Analyze and decide', detailFr: 'Calculs, comparaisons et plan d’action', detailEn: 'Calculations, comparisons and action plan', promptFr: 'Aide-moi à analyser une situation et à prendre une décision. Demande-moi les données nécessaires, vérifie les calculs avec tes outils et présente les options dans un tableau avec un plan d’action.', promptEn: 'Help me analyze a situation and make a decision. Ask for the necessary data, verify calculations using your tools, and present the options in a table with an action plan.' },
  { id: 'method', icon: NotebookPen, fr: 'Apprendre ma méthode', en: 'Learn my workflow', detailFr: 'Une procédure que votre agent peut réutiliser', detailEn: 'A procedure your agent can reuse', promptFr: 'Je veux t’apprendre une méthode de travail réutilisable. Demande-moi les étapes et les critères de qualité, puis enregistre une méthode personnelle réutilisable. Ne conserve aucun secret et montre-moi ce qui est enregistré.', promptEn: 'I want to teach you a reusable workflow. Ask about the steps and quality criteria, then save a reusable personal workflow. Do not store secrets and show me what is saved.' },
  { id: 'mail', icon: Mail, fr: 'Préparer un échange', en: 'Prepare a conversation', detailFr: 'Briefing client et brouillon de mail', detailEn: 'Client briefing and email draft', promptFr: 'Aide-moi à préparer mon prochain échange client et un brouillon de mail. Demande-moi le contexte manquant. Si ma messagerie est connectée dans cette discussion, consulte les échanges pertinents ; sinon, propose-moi de coller leur contenu. Ne l’envoie pas.', promptEn: 'Help me prepare my next client conversation and an email draft. Ask for missing context. If my mailbox is connected in this conversation, consult relevant messages; otherwise ask me to paste their content. Do not send it.' },
];

export function ActionCards({ language, disabled, choose, compact = false }: { language: Language; disabled: boolean; choose: (prompt: string) => void; compact?: boolean }) {
  return <div className={compact ? 'starter-actions' : 'workbench-actions'}>{workActions.map(item => <button key={item.id} type="button" disabled={disabled} onClick={() => choose(language === 'fr' ? item.promptFr : item.promptEn)}>
    <item.icon size={20} /><span><strong>{language === 'fr' ? item.fr : item.en}</strong><small>{language === 'fr' ? item.detailFr : item.detailEn}</small></span><ArrowUpRight size={15} />
  </button>)}</div>;
}

export function AgentWorkbench({ tab, setTab, close, organizationId, language, licensed, documents, choose, disabled, onOpen, onManage }: { tab: WorkbenchTab; setTab: (tab: WorkbenchTab) => void; close: () => void; organizationId: string; language: Language; licensed: boolean; documents: DocumentReceipt[]; choose: (prompt: string) => void; disabled: boolean; onOpen: (id: string) => void; onManage?: () => void }) {
  const fr = language === 'fr', panel = useRef<HTMLElement>(null);
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; panel.current?.focus(); return () => { if (previous?.isConnected) previous.focus(); }; }, []);
  const tabs: { id: WorkbenchTab; label: string; icon: typeof Brain }[] = [
    { id: 'actions', label: fr ? 'Savoir-faire' : 'Capabilities', icon: NotebookPen },
    { id: 'documents', label: fr ? 'Livrables' : 'Deliverables', icon: FileText },
    { id: 'memory', label: fr ? 'Mémoire' : 'Memory', icon: Brain },
    { id: 'connections', label: fr ? 'Connexions' : 'Connections', icon: PlugZap },
    { id: 'autonomy', label: fr ? 'Autonomie' : 'Autonomy', icon: ShieldCheck },
    { id: 'routines', label: fr ? 'Routines' : 'Routines', icon: CalendarClock },
  ];
  return <aside className="agent-workbench" aria-label={fr ? 'Espace de travail de l’agent' : 'Agent workspace'} ref={panel} tabIndex={-1} onKeyDown={event => { if (event.key === 'Escape') close(); }}>
    <header><div><span className="eyebrow">ALPENDATA</span><h2>{fr ? 'Votre agent, en action' : 'Your agent at work'}</h2></div><button className="icon-button" aria-label={fr ? 'Fermer le volet' : 'Close panel'} onClick={close}><X size={19} /></button></header>
    <nav className="workbench-tabs" aria-label={fr ? 'Fonctions de l’agent' : 'Agent features'}>{tabs.map(item => <button key={item.id} aria-pressed={tab === item.id} className={tab === item.id ? 'selected' : ''} onClick={() => setTab(item.id)}><item.icon size={15} />{item.label}{item.id === 'documents' && documents.length > 0 && <span>{documents.length}</span>}</button>)}</nav>
    <div className="workbench-content" key={tab}>
      {tab === 'actions' && <><p>{fr ? 'Décrivez le résultat attendu. Votre agent choisit ses outils et réalise le travail en plusieurs étapes.' : 'Describe the outcome. Your agent chooses its tools and works through the steps.'}</p><ActionCards language={language} disabled={disabled} choose={choose} /><p className="subtle">{fr ? 'Chaque suggestion prépare un message que vous pouvez modifier avant de l’envoyer.' : 'Each suggestion prepares a message you can edit before sending.'}</p><button className="secondary" disabled={disabled} onClick={() => choose(fr ? 'Liste mes méthodes personnelles enregistrées et explique quand les utiliser. N’en crée et n’en modifie aucune.' : 'List my saved personal workflows and explain when to use them. Do not create or modify any.')}>{fr ? 'Retrouver mes méthodes' : 'Find my workflows'}</button><div className="capability-note"><h3>{fr ? 'Des outils selon vos accès' : 'Tools matched to your access'}</h3><p>{fr ? 'Les connexions et l’autonomie se règlent ici. Les nouveaux accès et les nouvelles compétences sont pris en compte dans une nouvelle discussion.' : 'Manage connections and autonomy here. New access and new skills take effect in a new conversation.'}</p><p>{fr ? 'La navigation web, les agents délégués et l’installation libre de plugins ne sont pas encore disponibles dans cette version.' : 'Web browsing, delegated agents and unrestricted plugin installation are not yet available in this version.'}</p></div></>}
      {tab === 'documents' && (documents.length ? <Documents items={documents} organizationId={organizationId} language={language} /> : <div className="workbench-empty"><FileText size={30} /><h3>{fr ? 'Vos résultats, au même endroit' : 'Your results in one place'}</h3><p>{fr ? 'Les fichiers créés dans cette discussion apparaîtront ici, prêts à être téléchargés ou partagés.' : 'Files created in this conversation will appear here, ready to download or share.'}</p><button className="secondary" disabled={disabled} onClick={() => choose(fr ? workActions[0].promptFr : workActions[0].promptEn)}>{fr ? 'Créer un premier document' : 'Create a first document'}</button></div>)}
      {tab === 'memory' && <PersonalMemory organizationId={organizationId} language={language} expanded />}
      {tab === 'connections' && <Tools companyId={organizationId} language={language} />}
      {tab === 'autonomy' && <PersonalAutonomy organizationId={organizationId} language={language} licensed={licensed} expanded />}
      {tab === 'routines' && <><FirstTasks organizationId={organizationId} language={language} onOpen={onOpen} /><button className="secondary" onClick={onManage}>{fr ? 'Gérer mes automatisations' : 'Manage my automations'}</button></>}
    </div>
  </aside>;
}
