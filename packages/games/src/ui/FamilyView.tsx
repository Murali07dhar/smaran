import React, { useState } from 'react';
import type { ContentItem, GameId } from '../types';
import { ENCOURAGE_KEYS, labelOf, t as tr } from '../i18n/strings';
import type { CoopApi } from './useCoop';
import { Banner, BigButton, ItemPic } from './Kit';

/** Rich family-side UI of the asymmetric co-op: mirrors the patient's round, sends hints/encouragement, picks photos. Never plays. */
export function FamilyView({ gameId, locale, content, coop }: { gameId: GameId; locale: string; content: ContentItem[]; coop: CoopApi }) {
  const t = (k: string, p?: Record<string, string | number>) => tr(locale, k, p);
  const { state } = coop;
  const pr = state.progress;
  const [sel, setSel] = useState<string[]>([]);
  const focus = pr?.focus_item_id ? content.find((i) => i.id === pr.focus_item_id) : undefined;
  const pickable = content.filter((i) => i.kind !== 'step');
  const toggle = (id: string) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  return (
    <div className="sm-root sm-family" lang={locale}>
      <header className="sm-head"><h1>{t('games.coop.family.title')}: {t(`games.title.${gameId}`)}</h1></header>
      {!coop.connected && <Banner text={t('games.coop.family.not_connected')} />}
      <div className="sm-stack">
        <section className="sm-section" aria-live="polite">
          {!pr ? <p className="sm-prompt">{t('games.coop.family.waiting')}</p> : (
            <>
              <p className="sm-prompt">{t('games.coop.family.round', { n: Math.min(pr.round_index + 1, pr.rounds_total), total: pr.rounds_total })}</p>
              <p>{t(pr.prompt_key, pr.prompt_params)}</p>
              <div className="sm-row">
                {focus && <ItemPic item={focus} size={72} />}
                {pr.answer_label && <strong>{t('games.coop.family.answer', { label: pr.answer_label })}</strong>}
              </div>
              <div className="sm-chips">
                {pr.last_correct != null && <span className={`sm-chip ${pr.last_correct ? 'sm-chip-ok' : ''}`}>{t(pr.last_correct ? 'games.coop.family.last_ok' : 'games.coop.family.last_retry')}</span>}
                <span className="sm-chip">{pr.hints_used} {t('games.btn.hint')}</span>
              </div>
              <BigButton tone="primary" disabled={!pr.answer_item_id} onClick={() => pr.answer_item_id && coop.sendHint(pr.answer_item_id)}>{t('games.coop.family.send_hint')}</BigButton>
            </>
          )}
        </section>
        <section className="sm-section">
          <h2>{t('games.coop.family.encourage')}</h2>
          <div className="sm-row">{ENCOURAGE_KEYS.map((k) => <BigButton key={k} tone="warm" onClick={() => coop.sendEncourage(k)}>{t(k)}</BigButton>)}</div>
        </section>
        <section className="sm-section">
          <h2>{t('games.coop.family.pick')}</h2>
          <div className="sm-row">
            {pickable.map((i) => (
              <button key={i.id} type="button" className={`sm-card ${sel.includes(i.id) ? 'sm-sel' : ''}`} aria-pressed={sel.includes(i.id)} onClick={() => toggle(i.id)} style={{ width: 110 }}>
                <ItemPic item={i} size={56} /><span>{labelOf(i, locale)}</span>
              </button>
            ))}
          </div>
          <p><BigButton tone="primary" disabled={sel.length < 2} onClick={() => coop.sendPicks(sel)}>{t('games.coop.family.use_picks')}</BigButton></p>
        </section>
      </div>
    </div>
  );
}
