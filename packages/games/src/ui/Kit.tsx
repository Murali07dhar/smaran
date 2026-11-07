import React, { useReducer, useState } from 'react';
import type { ContentItem } from '../types';
import { assetUrl } from './assets';

/** Holds a framework-agnostic engine instance and gives a bump() to re-render after mutating it. */
export function useEngine<T>(make: () => T): [T, () => void] {
  const [engine] = useState(make);
  const [, bump] = useReducer((x: number) => x + 1, 0);
  return [engine, bump as () => void];
}
export function BigButton(p: { children: React.ReactNode; onClick?: () => void; tone?: 'primary' | 'ghost' | 'warm'; disabled?: boolean; label?: string; className?: string }) {
  const tone = p.tone ?? 'ghost';
  return <button type="button" className={`sm-btn sm-btn-${tone} ${p.className ?? ''}`} onClick={p.onClick} disabled={p.disabled} aria-label={p.label}>{p.children}</button>;
}
export function ItemPic({ item, size = 96 }: { item: ContentItem; size?: number }) {
  if (item.image) return <img className="sm-pic" src={assetUrl(item.image)} alt="" width={size} height={size} style={{ objectFit: 'cover' }} draggable={false} />;
  return <span className="sm-emoji" style={{ fontSize: size * 0.7 }} aria-hidden="true">{item.icon ?? '•'}</span>;
}
export function Banner({ text, tone = 'warm' }: { text: string; tone?: 'warm' | 'calm' }) {
  return <div className={`sm-banner ${tone === 'warm' ? 'sm-banner-warm' : ''}`} role="status">{text}</div>;
}
export const cols = (n: number) => ({ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` });
