import React, { useEffect, useState } from 'react';
import type { ContentItem } from '../../types';
import { SpotEngine } from '../../logic/engines/spot';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, cols, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';

export function SpotView({ api }: { api: ShellApi }) {
  const { props, t, label } = api;
  const [engine, bump] = useEngine(() => new SpotEngine(api.content, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const [hl, setHl] = useState<number | null>(null);
  const enter = () => {
    const r = engine.round; if (!r) return;
    const first = r.b[Array.from(r.diff)[0]];
    api.setPrompt('games.prompt.spot');
    api.publish({ round_index: engine.index, rounds_total: engine.total, prompt_key: 'games.prompt.spot', focus_item_id: first.id, answer_item_id: first.id, answer_label: label(first), last_correct: null, solved: engine.solved, hints_used: engine.hints });
  };
  useEffect(() => { engine.start(); enter(); bump(); }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const r = engine.round;
  if (!r) return null;
  const onTap = (i: number) => {
    const res = engine.tap(i);
    if (res.ignored) return;
    setHl(null);
    if (res.solved) setMsg(api.praise()); else if (res.correct) setMsg(null);
    else { setMsg(api.gentle()); if (engine.hintSuggested) setHl(engine.hint() ?? null); }
    bump();
  };
  const onNext = () => { if (engine.next()) api.finish(); else { setMsg(null); setHl(null); bump(); enter(); } };
  const board = (items: ContentItem[]) => (
    <div className="sm-grid" style={cols(r.cols)}>
      {items.map((it, i) => (
        <button key={i} type="button" aria-label={`${label(it)} ${i + 1}`} disabled={engine.solved}
          className={`sm-card ${engine.found.has(i) ? 'sm-done' : ''} ${engine.missed.has(i) ? 'sm-dim' : ''} ${hl === i ? 'sm-glow' : ''}`} onClick={() => onTap(i)}>
          <ItemPic item={it} size={56} />
        </button>
      ))}
    </div>
  );
  return (
    <main className="sm-stack">
      <p className="sm-prompt">{t('games.prompt.spot')}</p>
      <CueBanner cue={r.cue} t={t} />
      {msg && <Banner text={msg} />}
      <div className="sm-two">{board(r.a)}{board(r.b)}</div>
      {engine.solved ? <BigButton tone="primary" onClick={onNext}>{t('games.btn.next')}</BigButton> : <BigButton onClick={() => { setHl(engine.hint() ?? null); bump(); }}>{t('games.btn.hint')}</BigButton>}
    </main>
  );
}
