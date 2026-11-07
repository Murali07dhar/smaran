import React, { useEffect } from 'react';
import type { Cue } from '../types';
import { assetUrl } from './assets';
import { getAudio } from './runtime';
import { BigButton } from './Kit';

/** Shows a photo cue or plays an audio/music cue (never auto-fails; blocked autoplay degrades to the replay button). */
export function CueBanner({ cue, t }: { cue: Cue | null; t: (k: string) => string }) {
  useEffect(() => {
    if (cue && cue.cue_type !== 'photo') void getAudio().play(assetUrl(cue.uri));
    return () => { if (cue && cue.cue_type !== 'photo') getAudio().stop(); };
  }, [cue?.cue_id]);
  if (!cue) return null;
  return (
    <div className="sm-cue" role="note">
      {cue.cue_type === 'photo'
        ? <img className="sm-pic" src={assetUrl(cue.uri)} alt={cue.label ?? ''} width={72} height={72} />
        : <BigButton tone="warm" onClick={() => void getAudio().play(assetUrl(cue.uri))} label={t('games.cue.listen')}>🔊 {t('games.cue.listen')}</BigButton>}
      <span>{cue.cue_type === 'photo' ? t('games.cue.look') : cue.label}</span>
    </div>
  );
}
