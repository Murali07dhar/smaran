import React, { useEffect, useState } from 'react';
import { ChoiceEngine, type ChoiceKind, type ChoiceOption } from '../../logic/engines/choice';
import type { ShellApi } from '../GameShell';
import { Banner, BigButton, ItemPic, cols, useEngine } from '../Kit';
import { CueBanner } from '../CueBanner';

export function ChoiceView({ api, kind }: { api: ShellApi; kind: ChoiceKind }) {
  const { props, t, label } = api;
  const [engine, bump] = useEngine(() => new ChoiceEngine(kind, api.content, props.difficulty, api.ctx, props.cues));
  const [msg, setMsg] = useState<string | null>(null);
  const optLabel = (o: ChoiceOption) => (o.item ? label(o.item) : t(`games.cat.${o.id}`));
  const pub = (last: boolean | null) => {
    const r = engine.round; if (!r) return;
    const correct = r.options.find((o) => o.id === r.correct_id)!;
    api.publish({ round_index: engine.index, rounds_total: engine.total, prompt_key: r.prompt_key, prompt_params: r.context ? { prev: label(r.context) } : undefined, focus_item_id: r.item.id, answer_item_id: r.correct_id, answer_label: optLabel(correct), last_correct: last, solved: engine.solved, hints_used: engine.hints });
  };
  const enter = () => { const r = engine.round; if (!r) return; api.setPrompt(r.prompt_key, r.context ? { prev: label(r.context) } : undefined); pub(null); };
  useEffect(() => {
    engine.start();
    api.onFamilyHint.current = (id) => { engine.externalHint(id); bump(); };
    enter(); bump();
    return () => { api.onFamilyHint.current = null; };
  }, []);
  if (!engine.ready) return <div className="sm-stack"><Banner text={t('games.not_enough_content')} /></div>;
  const r = engine.round;
  if (!r) return null;
  const onPick = (o: ChoiceOption) => {
    const res = engine.answer(o.id);
    if (res.correct) setMsg(api.praise()); else if (!res.solved) setMsg(api.gentle());
    bump(); pub(res.correct);
  };
  const onNext = () => { if (engine.next()) api.finish(); else { setMsg(null); bump(); enter(); } };
  const ctxItem = kind === 'odd' ? null : kind === 'next' ? r.context! : r.item;
  const asPictures = kind === 'odd';
  const promptText = t(r.prompt_key, r.context ? { prev: label(r.context) } : undefined);
  return (
    <main className="sm-stack">
      <p className="sm-prompt">{promptText}</p>
      {ctxItem && <div className="sm-row"><ItemPic item={ctxItem} size={kind === 'next' ? 72 : 120} />{kind === 'next' && <strong>{label(ctxItem)}</strong>}</div>}
      <CueBanner cue={r.cue} t={t} />
      {msg && <Banner text={msg} />}
      <div className="sm-grid" style={asPictures ? cols(r.options.length <= 4 ? 2 : 3) : { gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
        {r.options.map((o) => {
          const dim = engine.wrong.has(o.id), good = engine.solved && o.id === r.correct_id;
          return (
            <button key={o.id} type="button" aria-label={optLabel(o)} disabled={dim || engine.solved}
              className={`sm-card ${dim ? 'sm-dim' : ''} ${good ? 'sm-done' : ''} ${api.hintItemId === o.id ? 'sm-glow' : ''}`} onClick={() => onPick(o)}>
              {o.item && (asPictures || kind === 'next') && <ItemPic item={o.item} size={asPictures ? 80 : 48} />}
              {(!asPictures || engine.showLabels) && <span>{optLabel(o)}</span>}
            </button>
          );
        })}
      </div>
      {engine.solved ? <BigButton tone="primary" onClick={onNext}>{t('games.btn.next')}</BigButton> : <BigButton onClick={() => { engine.hint(); bump(); }}>{t('games.btn.hint')}</BigButton>}
    </main>
  );
}
