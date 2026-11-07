import React, { useEffect, useState } from 'react';
import { TapEngine } from '../../logic/engines/tap';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, cols, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';

export function TapView({ api }: { api: ShellApi }) {
  const { props, t, label } = api;
  const [engine, bump] = useEngine(() => new TapEngine(api.content, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const [hl, setHl] = useState<string | null>(null);
  const enter = (last: boolean | null) => {
    const r = engine.round; if (!r) return;
    api.setPrompt('games.prompt.tap', { name: label(r.target) });
    api.publish({ round_index: engine.index, rounds_total: engine.total, prompt_key: 'games.prompt.tap', prompt_params: { name: label(r.target) }, focus_item_id: r.target.id, answer_item_id: r.target.id, answer_label: label(r.target), last_correct: last, solved: engine.solved, hints_used: engine.hints });
  };
  useEffect(() => { engine.start(); enter(null); bump(); }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const r = engine.round;
  if (!r) return null;
  const onTap = (id: string) => {
    const res = engine.tap(id);
    if (res.ignored) return;
    setHl(null);
    if (res.solved) setMsg(api.praise());
    else if (res.correct) setMsg(null);
    else { setMsg(api.gentle()); if (engine.hintSuggested) setHl(engine.hint() ?? null); }
    bump();
  };
  const onNext = () => { if (engine.next()) api.finish(); else { setMsg(null); setHl(null); bump(); enter(null); } };
  const n = r.cells.length;
  return (
    <main className="sm-stack">
      <div className="sm-row"><ItemPic item={r.target} size={80} /><p className="sm-prompt">{t('games.prompt.tap', { name: label(r.target) })}</p></div>
      <CueBanner cue={r.cue} t={t} />
      {msg && <Banner text={msg} />}
      <div className="sm-grid" style={cols(n <= 4 ? 2 : n <= 9 ? 3 : 4)}>
        {r.cells.map((c) => (
          <button key={c.cell_id} type="button" aria-label={label(c.item)} disabled={engine.solved}
            className={`sm-card ${engine.found.has(c.cell_id) ? 'sm-done' : ''} ${engine.missed.has(c.cell_id) ? 'sm-dim' : ''} ${hl === c.cell_id ? 'sm-glow' : ''}`} onClick={() => onTap(c.cell_id)}>
            <ItemPic item={c.item} size={64} />
          </button>
        ))}
      </div>
      {engine.solved ? <BigButton tone="primary" onClick={onNext}>{t('games.btn.next')}</BigButton> : <BigButton onClick={() => { setHl(engine.hint() ?? null); bump(); }}>{t('games.btn.hint')}</BigButton>}
    </main>
  );
}
