import { useEffect, useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';
import { api, ApiError } from './api';
import { readChatValue, writeChatValue } from './conversationStorage';
import type { Language } from './locale';

type Result = { id: string; text: string; status: string; model: string };
export function Dictation({ path, language, model, disabled, insert }: {
  path: string; language: Language; model: string; disabled: boolean; insert: (text: string) => void;
}) {
  const fr = language === 'fr', key = 'dictation.' + path;
  const recorder = useRef<MediaRecorder | null>(null), stream = useRef<MediaStream | null>(null), alive = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [recording, setRecording] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  const [result, setResult] = useState<Result | null>(null), [text, setText] = useState('');
  const [requestId, setRequestId] = useState(() => readChatValue(key));
  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(timer.current); if (recorder.current?.state === 'recording') recorder.current.stop(); stream.current?.getTracks().forEach(track => track.stop()); }; }, []);
  useEffect(() => {
    if (!requestId || (result && result.status !== 'running')) return;
    let active = true, missing = 0;
    const read = () => api<Result>(path + '/dictations/' + requestId).then(value => {
      if (!active) return; setResult(value); if (value.status === 'completed') { setText(value.text); setBusy(false); setError(false); }
      else if (value.status !== 'running') { setBusy(false); setError(true); }
    }).catch(cause => { if (!active) return; if (cause instanceof ApiError && cause.status === 404) { if (++missing < 5) return; setResult({ id: requestId, text: '', status: 'missing', model }); setBusy(false); } setError(true); });
    void read(); const interval = setInterval(() => void read(), 3000);
    return () => { active = false; clearInterval(interval); };
  }, [path, requestId, result?.status]);
  async function record() {
    setError(false);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error('Unsupported recorder');
      const active = new MediaRecorder(media, { mimeType, audioBitsPerSecond: 64000 }); recorder.current = active;
      const chunks: Blob[] = [];
      active.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      active.onstop = async () => {
        clearTimeout(timer.current); media.getTracks().forEach(track => track.stop());
        if (!alive.current) return;
        setRecording(false); setBusy(true);
        try {
          const blob = new Blob(chunks, { type: mimeType });
          if (!blob.size || blob.size > 2 * 1024 * 1024) throw new Error('Recording limit');
          const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(blob); });
          const id = crypto.randomUUID(); writeChatValue(key, id); setRequestId(id); setResult(null);
          const value = await api<Result>(path + '/dictations', { request_id: id, language, media_type: mimeType.split(';')[0], content_base64: content });
          if (alive.current) { setResult(value); setText(value.text); }
        } catch { if (alive.current) setError(true); }
        finally { if (alive.current) setBusy(false); }
      };
      active.start(); setRecording(true); timer.current = setTimeout(() => { if (active.state === 'recording') active.stop(); }, 120000);
    } catch { stream.current?.getTracks().forEach(track => track.stop()); setError(true); }
  }
  if (!model || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') return null;
  return <div className="dictation-control">
    <button type="button" className="composer-tools" disabled={disabled || busy} onClick={() => recording ? recorder.current?.stop() : void record()} aria-label={recording ? fr ? 'Terminer la dictée' : 'Finish dictation' : fr ? 'Dicter un brouillon' : 'Dictate a draft'}>{recording ? <Square size={16} /> : <Mic size={16} />}{recording ? fr ? 'Terminer' : 'Finish' : fr ? 'Dicter' : 'Dictate'}</button>
    {(recording || busy) && <small role="status">{recording ? fr ? 'Micro actif · 2 min maximum' : 'Microphone on · 2 min maximum' : fr ? 'Transcription…' : 'Transcribing…'}</small>}
    {error && <small role="alert">{fr ? 'La dictée n’a pas pu être confirmée. Aucun message n’a été envoyé.' : 'Dictation could not be confirmed. No message was sent.'}</small>}
    {result?.status === 'completed' && <div className="dictation-draft"><label>{fr ? 'Relire ma dictée' : 'Review my dictation'}<textarea rows={4} maxLength={32000} value={text} onChange={event => setText(event.target.value)} /></label><small>Mistral · {result.model}</small><button type="button" disabled={disabled || !text.trim()} onClick={() => { insert(text); writeChatValue(key, ''); setRequestId(''); setResult(null); }}>{fr ? 'Insérer dans mon brouillon' : 'Insert into my draft'}</button><button type="button" onClick={() => { writeChatValue(key, ''); setRequestId(''); setResult(null); }}>{fr ? 'Écarter' : 'Dismiss'}</button></div>}
  </div>;
}
