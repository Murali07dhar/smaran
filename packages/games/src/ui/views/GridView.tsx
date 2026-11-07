import React, { useEffect, useState } from 'react';
import { GridEngine } from '../../logic/engines/grid';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, cols, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';
import { assetUrl } from '../assets';

export function GridView({ api }: { api: ShellApi }) {
  const { props, t, label } = api;
  const [engine, bump] = useEngine(() => new GridEngine(api.content, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const [hl, setHl] = useState<number[]>([]);
  const pub = (last: boolean | null) => {
    const it = engine.puzzle?.item;
    api.publish({ round_index: engine.index, rounds_total: engine.total, prompt_key: 'games.prompt.grid', focus_item_id: it?.id ?? null, answer_item_id: it?.id ?? null, answer_label: it ? label(it) : null, last_correct: last, solved: engine.solved, hints_used: engine.hints });
  };
  useEffect(() => {
    engine.start();
    api.onFamilyHint.current = (id) => {
      engine.externalHint(id);
      const p = engine.tiles.findIndex((tile, i) => tile !== i);
      if (p >= 0) setHl([p, engine.tiles.indexOf(p)]);
      bump();
    };
    api.setPrompt('games.prompt.grid'); pub(null); bump();
    return () => { api.onFamilyHint.current = null; };
  }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const pz = engine.puzzle;
  if (!pz) return null;
  const n = engine.n, pct = (i: number) => (n === 1 ? 0 : (i / (n - 1)) * 100);
  const onTile = (pos: number) => {
    const r = engine.select(pos);
    if (r.kind === 'ignored') return;
    setHl([]);
    if (r.kind === 'swap') {
      if (r.solved) setMsg(api.praise());
      else if (r.improved) setMsg(null);
      else { setMsg(api.gentle()); if (engine.hintSuggested) setHl(engine.hint()); }
      pub(!!r.improved);
    }
    bump();
  };
  const onNext = () => { if (engine.next()) api.finish(); else { setMsg(null); setHl([]); bump(); pub(null); } };
  return (
    <main className="sm-stack">
      <p className="sm-prompt">{t('games.prompt.grid')}</p>
      <CueBanner cue={pz.cue} t={t} />
      {msg && <Banner text={msg} />}
      {engine.preview && <div className={api.hintItemId === pz.item.id ? 'sm-glow' : ''} style={{ width: 96 }}><ItemPic item={pz.item} size={96} /></div>}
      <div className="sm-grid" style={{ ...cols(n), maxWidth: 420 }}>
        {engine.tiles.map((tile, pos) => (
          <button key={pos} type="button" aria-label={`${pos + 1}`} className={`sm-tile ${engine.isCorrect(pos) ? 'sm-done' : ''} ${engine.selected === pos ? 'sm-sel' : ''} ${hl.includes(pos) ? 'sm-glow' : ''}`}
            style={{ backgroundImage: `url(${assetUrl(pz.item.image)})`, backgroundSize: `${n * 100}% ${n * 100}%`, backgroundPosition: `${pct(tile % n)}% ${pct(Math.floor(tile / n))}%` }}
            onClick={() => onTile(pos)} />
        ))}
      </div>
      {engine.solved ? <BigButton tone="primary" onClick={onNext}>{t('games.btn.next')}</BigButton> : <BigButton onClick={() => { setHl(engine.hint()); bump(); pub(null); }}>{t('games.btn.hint')}</BigButton>}
    </main>
  );
}
