import React, { useEffect, useState } from 'react';
import type { GameId } from '../../types';
import { OrderEngine } from '../../logic/engines/order';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';

export function OrderView({ api, routine_id, gameId }: { api: ShellApi; routine_id: string; gameId: Extract<GameId, 'routine_order' | 'arrange_steps'> }) {
  const { props, t, label } = api;
  const key = routine_id === 'morning' ? 'games.prompt.order_morning' : 'games.prompt.order_tea';
  const [engine, bump] = useEngine(() => new OrderEngine(api.content, routine_id, gameId, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const [hl, setHl] = useState<string | null>(null);
  const pub = (last: boolean | null) => {
    const n = engine.next;
    api.publish({ round_index: engine.placed.length, rounds_total: engine.total, prompt_key: key, focus_item_id: n?.id ?? null, answer_item_id: n?.id ?? null, answer_label: n ? label(n) : null, last_correct: last, solved: engine.finished, hints_used: engine.hints });
  };
  useEffect(() => {
    engine.start();
    api.onFamilyHint.current = (id) => { engine.externalHint(id); setHl(id); bump(); };
    api.setPrompt(key); pub(null); bump();
    return () => { api.onFamilyHint.current = null; };
  }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const onTap = (id: string) => {
    const r = engine.tap(id);
    if (r.ignored) return;
    setHl(null);
    if (r.correct) setMsg(api.praise()); else { setMsg(api.gentle()); if (engine.hintSuggested) setHl(engine.hint() ?? null); }
    bump(); pub(r.correct);
    if (r.complete) api.finish();
  };
  const next = engine.next;
  return (
    <main className="sm-stack">
      <p className="sm-prompt">{t(key)}</p>
      {next && <CueBanner cue={engine.cueFor(next.id)} t={t} />}
      {msg && <Banner text={msg} />}
      <ol className="sm-chips" aria-label="done steps">
        {engine.placed.map((id) => { const s = engine.order.find((x) => x.id === id)!; return <li key={id} className="sm-chip sm-chip-ok">{s.icon} {label(s)}</li>; })}
      </ol>
      <div className="sm-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        {engine.presented.filter((s) => !engine.isPlaced(s.id)).map((s) => (
          <button key={s.id} type="button" aria-label={label(s)} disabled={engine.wrongTaps.has(s.id)}
            className={`sm-card ${engine.wrongTaps.has(s.id) ? 'sm-dim' : ''} ${hl === s.id || api.hintItemId === s.id ? 'sm-glow' : ''}`} onClick={() => onTap(s.id)}>
            <ItemPic item={s} size={56} /><span>{label(s)}</span>
          </button>
        ))}
      </div>
      <BigButton onClick={() => { setHl(engine.hint() ?? null); bump(); pub(null); }}>{t('games.btn.hint')}</BigButton>
    </main>
  );
}
