import React, { useEffect, useState } from 'react';
import type { Cue } from '../../types';
import { PairsEngine } from '../../logic/engines/pairs';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, cols, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';

export function PairsView({ api }: { api: ShellApi }) {
  const { props, t, label } = api;
  const [engine, bump] = useEngine(() => new PairsEngine(api.content, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const [hl, setHl] = useState<string[]>([]);
  const [cue, setCue] = useState<Cue | null>(null);
  const pub = (last: boolean | null) => {
    const up = engine.faceUp.length ? engine.cards.find((c) => c.card_id === engine.faceUp[0])?.item : undefined;
    api.publish({ round_index: engine.matched.size, rounds_total: engine.total, prompt_key: 'games.prompt.pairs', focus_item_id: up?.id ?? null, answer_item_id: up?.id ?? null, answer_label: up ? label(up) : null, last_correct: last, solved: engine.finished, hints_used: engine.hints });
  };
  useEffect(() => {
    api.onFamilyHint.current = (id) => { engine.externalHint(id); setHl(engine.cards.filter((c) => c.item.id === id && !engine.isMatched(id)).map((c) => c.card_id)); bump(); };
    api.setPrompt('games.prompt.pairs'); pub(null);
    return () => { api.onFamilyHint.current = null; };
  }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const onFlip = (id: string) => {
    const r = engine.flip(id);
    if (r.kind === 'ignored') return;
    const card = engine.cards.find((c) => c.card_id === id)!;
    setCue(engine.cueFor(card.item.id)); setHl([]);
    if (r.kind === 'match') setMsg(api.praise());
    else if (r.kind === 'mismatch') { setMsg(api.gentle()); if (engine.hintSuggested) setHl(engine.hint()); }
    else setMsg(null);
    bump(); pub(r.kind === 'match' ? true : r.kind === 'mismatch' ? false : null);
    if (r.complete) api.finish();
  };
  const n = engine.cards.length;
  return (
    <main className="sm-stack">
      <p className="sm-prompt">{t('games.prompt.pairs')}</p>
      <CueBanner cue={cue} t={t} />
      {msg && <Banner text={msg} />}
      <div className="sm-grid" style={cols(n <= 4 ? 2 : n === 6 || n === 9 ? 3 : 4)}>
        {engine.cards.map((c) => {
          const matched = engine.isMatched(c.item.id), up = matched || engine.isUp(c.card_id);
          const glow = hl.includes(c.card_id) || api.hintItemId === c.item.id;
          return (
            <button key={c.card_id} type="button" className={`sm-card ${up ? 'sm-up' : 'sm-down'} ${matched ? 'sm-done' : ''} ${glow && !matched ? 'sm-glow' : ''}`} aria-label={up ? label(c.item) : t('games.prompt.pairs')} onClick={() => onFlip(c.card_id)}>
              {up ? <><ItemPic item={c.item} size={72} />{engine.showLabels && <span>{label(c.item)}</span>}</> : <span aria-hidden="true">✦</span>}
            </button>
          );
        })}
      </div>
      <BigButton onClick={() => { setHl(engine.hint()); bump(); pub(null); }}>{t('games.btn.hint')}</BigButton>
    </main>
  );
}
