#!/usr/bin/env python3
"""Generates CC0 placeholder art (emoji-on-colour SVG), generated tones (WAV) and the JSON packs.
Everything produced here is original/generated output released under CC0-1.0. Run: python3 scripts/gen-content.py"""
import json, math, os, struct, wave
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLORS = {'instruments': '#FDE68A', 'textiles': '#FBCFE8', 'food': '#BBF7D0', 'festivals': '#BFDBFE', 'my_photos': '#E9D5FF', 'cue': '#CCFBF1'}

def svg(path, emoji, color, title):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='utf-8').write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" role="img"><title>{title}</title>'
        f'<rect width="240" height="240" rx="36" fill="{color}"/>'
        f'<text x="120" y="152" font-size="110" text-anchor="middle" font-family="Noto Color Emoji,Apple Color Emoji,Segoe UI Emoji,sans-serif">{emoji}</text></svg>')

# (id, category, emoji, en, as)
OBJECTS = [
 ('dhol','instruments','🥁','Dhol (drum)','ঢোল'), ('pepa','instruments','📯','Pepa (buffalo-horn pipe)','পেঁপা'),
 ('gogona','instruments','🎶','Gogona (reed instrument)','গগনা'), ('toka','instruments','🎋','Toka (bamboo clapper)','তকা'),
 ('bhortal','instruments','🔔','Bhortal (cymbals)','ভোৰতাল'),
 ('gamosa','textiles','🧣','Gamosa','গামোছা'), ('muga_silk','textiles','🧵','Muga silk','মুগা'),
 ('mekhela_chador','textiles','👘','Mekhela chador','মেখেলা চাদৰ'), ('japi','textiles','👒','Japi (bamboo hat)','জাপি'),
 ('handloom','textiles','🧶','Handloom yarn','তাঁত'),
 ('pitha','food','🥞','Pitha (rice cake)','পিঠা'), ('laru','food','🍡','Laru (sweet ball)','লাড়ু'),
 ('masor_tenga','food','🍲','Masor tenga (sour fish curry)','মাছৰ টেঙা'), ('tea','food','🍵','Tea','চাহ'),
 ('rice','food','🍚','Rice','ভাত'), ('jolpan','food','🥣','Jolpan (breakfast snack)','জলপান'), ('khar','food','🥬','Khar (alkaline dish)','খাৰ'),
 ('bohag_bihu','festivals','🌸','Bohag Bihu','বহাগ বিহু'), ('magh_bihu','festivals','🔥','Magh Bihu','মাঘ বিহু'),
 ('kati_bihu','festivals','🪔','Kati Bihu','কাতি বিহু'), ('durga_puja','festivals','🙏','Durga Puja','দুৰ্গা পূজা'),
 ('ali_ai_ligang','festivals','🌾','Ali-Ai-Ligang','আলি আই লিগাং'),
]
PHOTOS = [('home','🏡','Home','ঘৰ'),('garden','🌼','Garden','বাগান'),('temple','🛕','Temple','নামঘৰ'),
          ('riverside','🌅','Riverside','নদীৰ পাৰ'),('market','🧺','Market','বজাৰ'),('tea_garden','🍃','Tea garden','চাহ বাগিচা')]
ROUTINES = {
 'morning': [('wake','🌅','Wake up','শুই উঠা'),('wash_face','💧','Wash your face','মুখ ধোৱা'),('brush_teeth','🪥','Brush your teeth','দাঁত ঘহা'),
             ('bathe','🛁','Take a bath','গা-পা ধোৱা'),('pray','🙏','Say a prayer','প্ৰাৰ্থনা কৰা'),('breakfast','🥣','Have breakfast','জলপান খোৱা'),('medicine','💊','Take your medicine','দৰব খোৱা')],
 'make_tea': [('boil','🔥','Boil water','পানী উতলোৱা'),('leaves','🍃','Add tea leaves','চাহপাত দিয়া'),('milk','🥛','Add milk and sugar','গাখীৰ আৰু চেনি দিয়া'),
              ('simmer','♨️','Let it simmer','অলপ উতলিবলৈ দিয়া'),('strain','🥄','Strain the tea','চাহ ছেকা'),('pour','☕','Pour into a cup','কাপত ঢালা')],
}
def pack(pack_id, items): return {'pack_id': pack_id, 'version': '1.0.0', 'license': 'CC0-1.0', 'locales': ['as', 'en'], 'items': items}
def dump(name, obj): json.dump(obj, open(os.path.join(ROOT, 'packs', name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

items = []
for i, c, e, en, a in OBJECTS:
    svg(f'{ROOT}/assets/objects/{i}.svg', e, COLORS[c], en)
    items.append({'id': f'obj_{i}', 'kind': 'object', 'category': c, 'labels': {'en': en, 'as': a}, 'image': f'assets/objects/{i}.svg', 'icon': e, 'source': 'placeholder'})
dump('assam.json', pack('assam_culture', items))
ph = []
for i, e, en, a in PHOTOS:
    svg(f'{ROOT}/assets/photos/{i}.svg', e, COLORS['my_photos'], en)
    ph.append({'id': f'photo_{i}', 'kind': 'photo', 'category': 'my_photos', 'labels': {'en': en, 'as': a}, 'image': f'assets/photos/{i}.svg', 'icon': e, 'source': 'placeholder'})
dump('demo_photos.json', pack('demo_photos_stand_in_for_caregiver_uploads', ph))
steps = []
for rid, rows in ROUTINES.items():
    for n, (i, e, en, a) in enumerate(rows, 1):
        steps.append({'id': f'step_{rid}_{i}', 'kind': 'step', 'category': rid, 'routine_id': rid, 'step_order': n, 'labels': {'en': en, 'as': a}, 'icon': e, 'source': 'placeholder'})
dump('routines.json', pack('routines', steps))
svg(f'{ROOT}/assets/cues/tea_garden.svg', '🍃', COLORS['cue'], 'Tea garden')
svg(f'{ROOT}/assets/cues/family.svg', '👨‍👩‍👧', '#FEF3C7', 'Family together')

def wav(path, notes, dur, decay):
    sr = 22050; frames = []
    for f in notes:
        for k in range(int(sr * dur)):
            t = k / sr; env = math.exp(-decay * t)
            v = env * (math.sin(2*math.pi*f*t) * .6 + math.sin(2*math.pi*2*f*t) * .25 + math.sin(2*math.pi*3*f*t) * .1)
            frames.append(int(max(-1, min(1, v)) * 14000))
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(b''.join(struct.pack('<h', x) for x in frames)); w.close()
wav(f'{ROOT}/assets/cues/chime.wav', [880], 1.4, 3.0)
wav(f'{ROOT}/assets/cues/melody.wav', [392, 440, 523, 587, 523, 440, 392], 0.35, 2.5)
print('generated', len(items), 'objects,', len(ph), 'photos,', len(steps), 'steps')
