// Locale keys for every game string. as + en provided; other locales fall back to en (see HANDOFF: translations unverified).
export type StringTable = Record<string, string>;
const en: StringTable = {
  'games.title.memory_pairs': 'Match the pictures', 'games.title.image_grid': 'Put the picture together',
  'games.title.target_tap': 'Find and tap', 'games.title.spot_diff': 'Spot the difference',
  'games.title.routine_order': 'Morning routine', 'games.title.odd_one_out': 'Which one is different?',
  'games.title.naming': 'What is this called?', 'games.title.sorting': 'Sort into groups', 'games.title.arrange_steps': 'Making tea', 'games.title.routine_next': 'What comes next?', 'games.prompt.next': 'After "{prev}", what comes next?',
  'games.prompt.pairs': 'Tap a picture to turn it over. Find its partner.',
  'games.prompt.grid': 'Put the picture back together. Tap one piece, then another to swap them.',
  'games.prompt.tap': 'Tap every {name}.', 'games.prompt.spot': 'Find what is different. Tap the changes.',
  'games.prompt.order_morning': 'What comes next in your morning?', 'games.prompt.order_tea': 'What comes next when making tea?',
  'games.prompt.odd': 'Which one is different from the others?', 'games.prompt.name': 'What is this called?', 'games.prompt.sort': 'Where does this belong?',
  'games.praise.1': 'Lovely!', 'games.praise.2': 'Well done.', 'games.praise.3': 'That is right!', 'games.praise.4': 'Beautiful.',
  'games.gentle.1': 'Almost. Take your time.', 'games.gentle.2': 'Let us look again together.', 'games.gentle.3': 'No hurry. Try another one.',
  'games.hint_given': 'Here is a little help.',
  'games.btn.next': 'Next', 'games.btn.hint': 'Help me', 'games.btn.again': 'Listen again', 'games.btn.done': 'All done',
  'games.cue.look': 'Remember this', 'games.cue.listen': 'Listen',
  'games.done': 'Wonderful. You did lovely today.',
  'games.disclaimer': 'SMARAN is a support tool, not a medical diagnosis.',
  'games.not_enough_content': 'Ask your family to add a few more pictures.',
  'games.cat.instruments': 'Instruments', 'games.cat.textiles': 'Cloth and weaving', 'games.cat.food': 'Food and drink', 'games.cat.festivals': 'Festivals',
  'games.coop.waiting': 'Waiting for your family to join.', 'games.coop.connected': 'Family is with you.',
  'games.coop.family.title': 'Family view', 'games.coop.family.round': 'Round {n} of {total}',
  'games.coop.family.answer': 'The answer is {label}', 'games.coop.family.send_hint': 'Send a hint',
  'games.coop.family.encourage': 'Send encouragement', 'games.coop.family.pick': 'Choose pictures for the next game',
  'games.coop.family.use_picks': 'Use these pictures', 'games.coop.family.waiting': 'Waiting for the patient to start.',
  'games.coop.family.not_connected': 'Not connected to a shared game.', 'games.coop.family.last_ok': 'Last answer: correct', 'games.coop.family.last_retry': 'Last answer: trying again',
  'games.coop.enc.1': 'We are proud of you!', 'games.coop.enc.2': 'You are doing wonderfully.', 'games.coop.enc.3': 'Take your time. We are with you.', 'games.coop.enc.4': 'Lovely choice!',
};
const as: StringTable = {
  'games.title.memory_pairs': 'ছবি মিলোৱা', 'games.title.image_grid': 'ছবি জোৰা লগোৱা',
  'games.title.target_tap': 'বিচাৰি টিপক', 'games.title.spot_diff': 'পাৰ্থক্য বিচাৰক',
  'games.title.routine_order': 'ৰাতিপুৱাৰ কাম', 'games.title.odd_one_out': 'কোনটো পৃথক?',
  'games.title.naming': 'ইয়াৰ নাম কি?', 'games.title.sorting': 'ভাগ কৰক', 'games.title.arrange_steps': 'চাহ বনোৱা', 'games.title.routine_next': 'তাৰ পিছত কি?', 'games.prompt.next': '"{prev}"ৰ পিছত কি কৰিব?',
  'games.prompt.pairs': 'এখন ছবি টিপক। ইয়াৰ লগৰখন বিচাৰক।',
  'games.prompt.grid': 'ছবিখন আকৌ সম্পূৰ্ণ কৰক। এটা টুকুৰা টিপক, তাৰ পিছত আন এটা টিপক।',
  'games.prompt.tap': 'প্ৰতিটো {name} টিপক।', 'games.prompt.spot': 'পাৰ্থক্য বিচাৰক। সলনি হোৱা ঠাইবোৰ টিপক।',
  'games.prompt.order_morning': 'ৰাতিপুৱা তাৰ পিছত কি কৰিব?', 'games.prompt.order_tea': 'চাহ বনাওঁতে তাৰ পিছত কি কৰিব?',
  'games.prompt.odd': 'কোনটো আনবোৰতকৈ পৃথক?', 'games.prompt.name': 'ইয়াৰ নাম কি?', 'games.prompt.sort': 'এইটো কোন ভাগত যাব?',
  'games.praise.1': 'বঢ়িয়া!', 'games.praise.2': 'বহুত ভাল।', 'games.praise.3': 'ঠিক আছে!', 'games.praise.4': 'অতি সুন্দৰ।',
  'games.gentle.1': 'প্ৰায় হৈ গৈছিল। লাহে লাহে।', 'games.gentle.2': 'আহক, আকৌ এবাৰ একেলগে চাওঁ।', 'games.gentle.3': 'চিন্তা নাই। আন এটা চেষ্টা কৰক।',
  'games.hint_given': 'এইখিনি অলপ সহায়।',
  'games.btn.next': 'পিছলৈ', 'games.btn.hint': 'সহায় লওক', 'games.btn.again': 'আকৌ শুনক', 'games.btn.done': 'হৈ গ’ল',
  'games.cue.look': 'মনত পেলাওক', 'games.cue.listen': 'শুনক',
  'games.done': 'অতি সুন্দৰ! আজি আপুনি বহুত ভাল কৰিলে।',
  'games.disclaimer': 'SMARAN এটা সহায়ক সঁজুলি, ই চিকিৎসকীয় ৰোগ নিৰ্ণয় নহয়।',
  'games.not_enough_content': 'পৰিয়ালক আৰু কিছু ছবি যোগ কৰিবলৈ কওক।',
  'games.cat.instruments': 'বাদ্যযন্ত্ৰ', 'games.cat.textiles': 'বস্ত্ৰ আৰু তাঁত', 'games.cat.food': 'খাদ্য আৰু পানীয়', 'games.cat.festivals': 'উৎসৱ',
  'games.coop.waiting': 'পৰিয়ালৰ বাবে অপেক্ষা কৰি আছোঁ।', 'games.coop.connected': 'পৰিয়াল আপোনাৰ লগত আছে।',
  'games.coop.family.title': 'পৰিয়ালৰ দৃশ্য', 'games.coop.family.round': '{total}ৰ ভিতৰত {n} নং পৰ্যায়',
  'games.coop.family.answer': 'উত্তৰ হ’ল {label}', 'games.coop.family.send_hint': 'ইংগিত পঠাওক',
  'games.coop.family.encourage': 'উৎসাহ পঠাওক', 'games.coop.family.pick': 'পৰৱৰ্তী খেলৰ বাবে ছবি বাছনি কৰক',
  'games.coop.family.use_picks': 'এই ছবিবোৰ ব্যৱহাৰ কৰক', 'games.coop.family.waiting': 'ৰোগীয়ে আৰম্ভ কৰালৈ অপেক্ষা কৰক।',
  'games.coop.family.not_connected': 'ভাগ-বতৰা খেলৰ লগত সংযোগ হোৱা নাই।', 'games.coop.family.last_ok': 'শেহতীয়া উত্তৰ: শুদ্ধ', 'games.coop.family.last_retry': 'শেহতীয়া উত্তৰ: আকৌ চেষ্টা কৰি আছে',
  'games.coop.enc.1': 'আমি আপোনাক লৈ গৌৰৱ কৰোঁ!', 'games.coop.enc.2': 'আপুনি অতি ভাল কৰি আছে।', 'games.coop.enc.3': 'লাহে লাহে কৰক, আমি আপোনাৰ লগত আছোঁ।', 'games.coop.enc.4': 'বঢ়িয়া বাছনি!',
};
export const strings: Record<string, StringTable> = { en, as };
export const PRAISE_KEYS = ['games.praise.1', 'games.praise.2', 'games.praise.3', 'games.praise.4'];
export const GENTLE_KEYS = ['games.gentle.1', 'games.gentle.2', 'games.gentle.3'];
export const ENCOURAGE_KEYS = ['games.coop.enc.1', 'games.coop.enc.2', 'games.coop.enc.3', 'games.coop.enc.4'];
export function t(locale: string, key: string, params?: Record<string, string | number>): string {
  const raw = strings[locale]?.[key] ?? strings.en[key] ?? key;
  return params ? raw.replace(/\{(\w+)\}/g, (_, k) => (k in params ? String(params[k]) : `{${k}}`)) : raw;
}
/** Label of a content item for a locale, falling back to en then any label. */
export function labelOf(item: { id: string; labels: Partial<Record<string, string>> }, locale: string): string {
  return item.labels[locale] ?? item.labels.en ?? Object.values(item.labels)[0] ?? item.id;
}
