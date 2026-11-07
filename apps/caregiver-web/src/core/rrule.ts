export type Rec = { freq: 'DAILY' | 'WEEKLY'; days: string[]; times: string[] };
export const buildRRule = (r: Rec) => {
  const hh = r.times.map(t => +t.split(':')[0]).join(','), mm = [...new Set(r.times.map(t => +t.split(':')[1]))].join(',');
  return `FREQ=${r.freq};${r.freq === 'WEEKLY' && r.days.length ? `BYDAY=${r.days.join(',')};` : ''}BYHOUR=${hh};BYMINUTE=${mm}`;
};
