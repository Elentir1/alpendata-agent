import { useState } from 'react';
import type { Language } from './locale';

const ideas = [
  { id: 'clients', fr: ['Relation client', 'Préparer un rendez-vous', 'Préparer une fiche de rendez-vous avec les objectifs du client, les questions à poser et les prochaines étapes, à partir des informations que je fournis.'], en: ['Client relationships', 'Prepare a meeting', 'Prepare a meeting brief with client goals, questions and next steps, using information I provide.'] },
  { id: 'sales', fr: ['Commercial', 'Structurer une offre', 'Créer une trame de proposition commerciale avec besoin, périmètre, livrables et points à confirmer. Me demander les informations manquantes sans inventer de prix.'], en: ['Sales', 'Structure a proposal', 'Create a proposal outline with needs, scope, deliverables and points to confirm. Ask for missing information without inventing prices.'] },
  { id: 'people', fr: ['RH et équipe', 'Accueillir un collaborateur', 'Préparer un parcours d’accueil pour un nouveau collaborateur : première semaine, documents à prévoir et responsabilités à attribuer.'], en: ['People and team', 'Welcome a teammate', 'Prepare a new teammate onboarding plan: first week, documents to prepare and responsibilities to assign.'] },
  { id: 'operations', fr: ['Organisation', 'Clarifier un processus', 'Transformer une tâche récurrente que je décris en procédure simple avec étapes, responsable de chaque étape et checklist de contrôle.'], en: ['Operations', 'Clarify a process', 'Turn a recurring task I describe into a simple procedure with steps, responsibilities and a quality checklist.'] },
  { id: 'management', fr: ['Gestion', 'Préparer un suivi d’activité', 'Créer un tableau Excel de suivi d’activité avec indicateurs à choisir, actions et échéances. Laisser les données inconnues vides et expliquer les calculs.'], en: ['Management', 'Set up activity tracking', 'Create an Excel activity tracker with indicators to choose, actions and deadlines. Leave unknown data blank and explain calculations.'] },
  { id: 'coaching', fr: ['Conseil et coaching', 'Concevoir un atelier', 'Préparer un atelier adapté à mon public avec objectifs, déroulement, exercices et un support PowerPoint réutilisable.'], en: ['Consulting and coaching', 'Design a workshop', 'Prepare a workshop for my audience with goals, agenda, exercises and a reusable PowerPoint deck.'] },
] as const;

export function BusinessIdeas({ language, sector = '', disabled = false, onChoose }: { language: Language; sector?: string; disabled?: boolean; onChoose: (text: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const fr = language === 'fr';
  const ordered = [...ideas].sort((a, b) => Number(b.id === sector) - Number(a.id === sector));
  return <section className="business-ideas" aria-label={fr ? 'Idées pour mon entreprise' : 'Ideas for my business'}>
    <h3>{fr ? 'Des idées pour votre quotidien' : 'Ideas for your working day'}</h3>
    <p className="subtle">{fr ? 'Choisissez une piste pour la personnaliser. Ces exemples peuvent commencer avec vos indications, sans connexion obligatoire.' : 'Choose a starting point to personalize. These examples can use your instructions without a required connection.'}</p>
    <div className="idea-grid">{(expanded ? ordered : ordered.slice(0, 3)).map(idea => <button type="button" className="idea-card" key={idea.id} disabled={disabled} onClick={() => onChoose(idea[language][2])}>
      <span className="eyebrow">{idea[language][0]}</span><strong>{idea[language][1]}</strong><span>{idea[language][2]}</span>
    </button>)}</div>
    <button type="button" className="text-button" onClick={() => setExpanded(!expanded)}>{fr ? expanded ? 'Voir moins d’idées' : 'Explorer les 6 pistes PME' : expanded ? 'Show fewer ideas' : 'Explore all 6 business ideas'}</button>
  </section>;
}

export function DiscoveryFields({ language, sector, success, output, onSector, onSuccess, onOutput }: { language: Language; sector: string; success: string; output: string; onSector: (value: string) => void; onSuccess: (value: string) => void; onOutput: (value: string) => void }) {
  const fr = language === 'fr';
  const questions: Record<string, [string, string]> = {
    clients: ['Quel rendez-vous souhaitez-vous mieux préparer ?', 'Which meeting would you like to prepare better?'],
    sales: ['Quel type de client ou d’offre souhaitez-vous développer ?', 'What kind of client or proposal would you like to develop?'],
    people: ['Quel moment de la vie de votre équipe souhaitez-vous simplifier ?', 'Which part of your team’s work would you like to simplify?'],
    operations: ['Quelle tâche vous oblige à répéter les mêmes étapes ?', 'Which task makes you repeat the same steps?'],
    management: ['Quel indicateur ou quelle décision voulez-vous mieux suivre ?', 'Which indicator or decision would you like to track better?'],
    coaching: ['Pour quel public et quel objectif préparez-vous vos séances ?', 'Who are your sessions for and what are their goals?'],
  };
  return <fieldset className="discovery-fields"><legend>{fr ? 'Construisons votre premier cas d’usage' : 'Let’s shape your first use case'}</legend>
    <label htmlFor="work-area">{fr ? 'Votre priorité du moment' : 'Your current priority'}</label>
    <select id="work-area" value={sector} onChange={event => onSector(event.target.value)}><option value="">{fr ? 'Je souhaite explorer' : 'I would like to explore'}</option>{ideas.map(idea => <option key={idea.id} value={idea.id}>{idea[language][0]}</option>)}</select>
    <label htmlFor="success">{questions[sector]?.[fr ? 0 : 1] || (fr ? 'À quoi ressemblerait un premier résultat utile ?' : 'What would a useful first result look like?')}</label>
    <textarea id="success" value={success} onChange={event => onSuccess(event.target.value)} maxLength={1000} rows={2} placeholder={fr ? 'Un cas concret, le public concerné, votre prochaine échéance…' : 'A concrete case, its audience, your next deadline…'} />
    <label htmlFor="preferred-output">{fr ? 'Le format qui vous serait le plus utile' : 'The most useful format for you'}</label>
    <select id="preferred-output" value={output} onChange={event => onOutput(event.target.value)}>{(fr ? [['', 'L’assistant me conseille'], ['document', 'Document Word ou PDF'], ['spreadsheet', 'Tableau Excel'], ['presentation', 'Présentation PowerPoint'], ['checklist', 'Checklist ou procédure']] : [['', 'Let the assistant suggest'], ['document', 'Word document or PDF'], ['spreadsheet', 'Excel spreadsheet'], ['presentation', 'PowerPoint presentation'], ['checklist', 'Checklist or procedure']]).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>
  </fieldset>;
}
