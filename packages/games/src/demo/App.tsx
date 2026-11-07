import React, { useMemo, useState } from 'react';
import assam from '../../../content/packs/assam.json';
import photos from '../../../content/packs/demo_photos.json';
import routines from '../../../content/packs/routines.json';
import { games } from '../registry';
import type { ContentItem, GameEvent, GameId, SessionSummary } from '../types';
import { createMockVoice, mockCues, createCoopBus } from '../mocks';
import { validateGameEvent } from '../logic/events';
import { toObservations } from '../logic/observations';
import { uuidv7 } from '../logic/uuid7';
import { t } from '../i18n/strings';

const content = [...assam.items, ...photos.items, ...routines.items] as unknown as ContentItem[];
const patient = { id: 'demo-patient', display_name: 'Demo', age: 74, language: 'as' };

export function App() {
  const [gameId, setGameId] = useState<GameId>('memory_pairs');
  const [difficulty, setDifficulty] = useState(1);
  const [mode, setMode] = useState<'solo' | 'coop'>('solo');
  const [locale, setLocale] = useState<'as' | 'en'>('en');
  const [useCues, setUseCues] = useState(true);
  const [aloud, setAloud] = useState(false);
  const [run, setRun] = useState(0);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [caption, setCaption] = useState('');
  const mod = games.find((g) => g.id === gameId)!;
  const coop = mode === 'coop' && mod.supports_coop;
  const session_id = useMemo(() => uuidv7(), [run, gameId, difficulty, mode]);
  const bus = useMemo(() => createCoopBus(), [run, gameId, difficulty, mode]);
  const voice = useMemo(() => createMockVoice({ onSpeak: (text, loc) => { setCaption(text); if (aloud && 'speechSynthesis' in window) { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = loc === 'as' ? 'as-IN' : 'en-IN'; speechSynthesis.speak(u); } } }), [aloud]);
  const patientT = useMemo(() => bus.transport(), [bus]);
  const familyT = useMemo(() => bus.transport(), [bus]);
  const reset = () => { setEvents([]); setSummary(null); setRun((r) => r + 1); };
  const common = { session_id, patient, content, cues: useCues ? mockCues : [], difficulty, locale, voice, onEvent: (e: GameEvent) => setEvents((xs) => [...xs, e]), onComplete: setSummary };
  const Comp = mod.Component;
  const bad = events.filter((e) => validateGameEvent(e).length).length;
  const key = `${run}-${gameId}-${difficulty}-${mode}-${locale}`;
  return (
    <>
      <div className="demo-bar">
        <label>Game<select value={gameId} onChange={(e) => { setGameId(e.target.value as GameId); reset(); }}>{games.map((g) => <option key={g.id} value={g.id}>{g.domain}: {g.id}</option>)}</select></label>
        <fieldset><legend>Difficulty</legend>{[1, 5, 9].map((d) => <label key={d}><input type="radio" checked={difficulty === d} onChange={() => { setDifficulty(d); reset(); }} /> {d}</label>)}</fieldset>
        <fieldset><legend>Mode</legend>{(['solo', 'coop'] as const).map((m) => <label key={m}><input type="radio" disabled={m === 'coop' && !mod.supports_coop} checked={mode === m} onChange={() => { setMode(m); reset(); }} /> {m}</label>)}</fieldset>
        <label>Language<select value={locale} onChange={(e) => { setLocale(e.target.value as 'as' | 'en'); reset(); }}><option value="en">English</option><option value="as">অসমীয়া</option></select></label>
        <label><span><input type="checkbox" checked={useCues} onChange={(e) => { setUseCues(e.target.checked); reset(); }} /> cues</span></label>
        <label><span><input type="checkbox" checked={aloud} onChange={(e) => setAloud(e.target.checked)} /> speak aloud</span></label>
        <button onClick={reset}>Restart</button>
      </div>
      {caption && <div className="demo-caption" aria-live="polite">🔊 {caption}</div>}
      <div className={`demo-panes ${coop ? 'coop' : ''}`}>
        <Comp key={`p-${key}`} {...common} role="patient" coop={coop ? patientT : undefined} />
        {coop && <Comp key={`f-${key}`} {...common} role="family" coop={familyT} />}
      </div>
      <div className="demo-log" aria-label="event log">
        <div>{events.length} events, <span className={bad ? 'bad' : 'ok'}>{bad ? `${bad} INVALID` : 'all valid GameEvents'}</span></div>
        {events.slice(-30).map((e) => { const errs = validateGameEvent(e); return <div key={e.event_id} className={errs.length ? 'bad' : ''}>{e.type} item={e.item_id} with_cue={String(e.with_cue)} correct={String(e.correct)} {errs.join('; ')}</div>; })}
      </div>
      {summary && (
        <div className="demo-summary">
          <strong>Session summary</strong> (cue effect = with vs without cue): <code>{JSON.stringify({ with_cue: summary.with_cue, without_cue: summary.without_cue, hints: summary.hints_used })}</code>
          <div>Observations for AI: <code>{JSON.stringify(toObservations(events, mockCues).slice(0, 4))}</code></div>
          <em>{t(locale, summary.disclaimer_key)}</em>
        </div>
      )}
    </>
  );
}
