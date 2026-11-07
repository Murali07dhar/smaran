import React from 'react';
import type { Domain, GameId } from './types';
import type { GameModule, GameProps } from './sdk';
import { GameShell, type ShellApi } from './ui/GameShell';
import { PairsView } from './ui/views/PairsView';
import { GridView } from './ui/views/GridView';
import { TapView } from './ui/views/TapView';
import { SpotView } from './ui/views/SpotView';
import { OrderView } from './ui/views/OrderView';
import { ChoiceView } from './ui/views/ChoiceView';
export { difficultyMap, paramsFor } from './logic/difficulty';

const mk = (id: GameId, domain: Domain, supports_coop: boolean, build: (api: ShellApi) => React.ReactNode): GameModule => {
  const Component: React.FC<GameProps> = (props) => <GameShell props={props} gameId={id}>{build}</GameShell>;
  Component.displayName = `Game(${id})`;
  return { id, domain, supports_coop, Component };
};
/** Game registry: two games per domain. Attention games are solo-only (spatial/timing-sensitive, little for family to add). */
export const games: GameModule[] = [
  mk('memory_pairs', 'memory', true, (a) => <PairsView api={a} />),
  mk('image_grid', 'memory', true, (a) => <GridView api={a} />),
  mk('target_tap', 'attention', false, (a) => <TapView api={a} />),
  mk('spot_diff', 'attention', false, (a) => <SpotView api={a} />),
  mk('routine_order', 'routine', true, (a) => <OrderView api={a} routine_id="morning" gameId="routine_order" />),
  mk('routine_next', 'routine', true, (a) => <ChoiceView api={a} kind="next" />),
  mk('odd_one_out', 'pattern_object', true, (a) => <ChoiceView api={a} kind="odd" />),
  mk('naming', 'pattern_object', true, (a) => <ChoiceView api={a} kind="name" />),
  mk('sorting', 'executive', true, (a) => <ChoiceView api={a} kind="sort" />),
  mk('arrange_steps', 'executive', true, (a) => <OrderView api={a} routine_id="make_tea" gameId="arrange_steps" />),
];
export const gameById = (id: GameId) => games.find((g) => g.id === id);
