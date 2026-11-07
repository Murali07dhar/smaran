import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ContentItem, GameId } from '../types';
import type { GameProps } from '../sdk';
import { createGameContext, type GameContext } from '../logic/context';
import { GENTLE_KEYS, PRAISE_KEYS, labelOf, t as tr } from '../i18n/strings';
import type { Progress } from '../coop/protocol';
import { useCoop } from './useCoop';
import { FamilyView } from './FamilyView';
import { Banner, BigButton } from './Kit';

type Params = Record<string, string | number>;
export interface ShellApi {
  props: GameProps; gameId: GameId; ctx: GameContext; content: ContentItem[];
  t(k: string, p?: Params): string; label(i: ContentItem): string;
  say(k: string, p?: Params): void; setPrompt(k: string, p?: Params): void;
  praise(): string; gentle(): string; publish(p: Progress): void; finish(): void;
  hintItemId: string | null;
  onFamilyHint: React.MutableRefObject<((item_id: string) => void) | null>;
}
type Build = (api: ShellApi) => React.ReactNode;

/** Wraps every game: session context + events, voice prompts, co-op wiring. role='family' renders the family UI instead of the game. */
export function GameShell({ props, gameId, children }: { props: GameProps; gameId: GameId; children: Build }) {
  return props.role === 'family' ? <FamilyShell props={props} gameId={gameId} /> : <PatientShell props={props} gameId={gameId}>{children}</PatientShell>;
}

function FamilyShell({ props, gameId }: { props: GameProps; gameId: GameId }) {
  const coop = useCoop(props.coop, 'family', props.session_id);
  return <FamilyView gameId={gameId} locale={props.locale} content={props.content} coop={coop} />;
}

function PatientShell({ props, gameId, children }: { props: GameProps; gameId: GameId; children: Build }) {
  const onEvt = useRef(props.onEvent); onEvt.current = props.onEvent;
  const onDone = useRef(props.onComplete); onDone.current = props.onComplete;
  const [ctx] = useState(() => createGameContext({ session_id: props.session_id, seed: props.session_id, onEvent: (e) => onEvt.current(e) }));
  const coop = useCoop(props.coop, 'patient', props.session_id);
  const [done, setDone] = useState(false);
  const doneRef = useRef(false);
  const [engineKey, setEngineKey] = useState(0);
  const [encSeen, setEncSeen] = useState(0);
  const [hintSeen, setHintSeen] = useState(0);
  const famHint = useRef<((id: string) => void) | null>(null);
  const prompt = useRef<{ k: string; p?: Params } | null>(null);
  const hint = coop.state.hint, enc = coop.state.encourage;
  const encN = useRef(0); encN.current = enc?.n ?? 0;
  const hintN = useRef(0); hintN.current = hint?.n ?? 0;

  const t = useCallback((k: string, p?: Params) => tr(props.locale, k, p), [props.locale]);
  const label = useCallback((i: ContentItem) => labelOf(i, props.locale), [props.locale]);
  const say = useCallback((k: string, p?: Params) => { void props.voice.speak(p ? tr(props.locale, k, p) : k, props.locale); }, [props.voice, props.locale]);
  const setPrompt = useCallback((k: string, p?: Params) => { prompt.current = { k, p }; say(k, p); setEncSeen(encN.current); setHintSeen(hintN.current); }, [say]);
  const praise = useCallback(() => { const k = PRAISE_KEYS[ctx.events.length % PRAISE_KEYS.length]; say(k); return t(k); }, [ctx, say, t]);
  const gentle = useCallback(() => { const k = GENTLE_KEYS[ctx.events.length % GENTLE_KEYS.length]; say(k); return t(k); }, [ctx, say, t]);
  const finish = useCallback(() => {
    if (doneRef.current) return;
    doneRef.current = true; setDone(true); say('games.done');
    onDone.current(ctx.summary(gameId, props.difficulty));
  }, [ctx, gameId, props.difficulty, say]);

  const picks = coop.state.picked_item_ids;
  const content = useMemo(() => {
    if (!picks || !picks.length) return props.content;
    const f = props.content.filter((i) => i.kind === 'step' || picks.includes(i.id));
    return f.filter((i) => i.kind !== 'step').length >= 2 ? f : props.content;
  }, [props.content, picks]);
  // Family photo picks rebuild the game only before the first answer; later picks apply to the next session (host passes them in `content`).
  useEffect(() => { if (picks && picks.length && !ctx.events.some((e) => e.type === 'answer')) setEngineKey((k) => k + 1); }, [picks]);
  useEffect(() => { if (hint) { famHint.current?.(hint.item_id); say('games.hint_given'); } }, [hint?.n]);
  useEffect(() => { if (enc) say(enc.text_key); }, [enc?.n]);

  const api: ShellApi = {
    props, gameId, ctx, content, t, label, say, setPrompt, praise, gentle, publish: coop.publish, finish,
    hintItemId: hint && hint.n !== hintSeen ? hint.item_id : null, onFamilyHint: famHint,
  };
  return (
    <div className="sm-root" lang={props.locale}>
      <header className="sm-head">
        <h1>{t(`games.title.${gameId}`)}</h1>
        <BigButton onClick={() => prompt.current && say(prompt.current.k, prompt.current.p)}>🔊 {t('games.btn.again')}</BigButton>
      </header>
      {props.coop && !coop.state.peers.family && <p className="sm-muted">{t('games.coop.waiting')}</p>}
      {props.coop && coop.state.peers.family && <p className="sm-muted">{t('games.coop.connected')}</p>}
      {enc && enc.n !== encSeen && <div className="sm-stack"><Banner text={t(enc.text_key)} /></div>}
      {done ? <div className="sm-stack"><Banner text={t('games.done')} tone="calm" /></div> : <React.Fragment key={engineKey}>{children(api)}</React.Fragment>}
    </div>
  );
}
