import React,{useEffect,useRef,useState} from 'react';import {useTranslation} from 'react-i18next';import {consents,setConsent as postConsent,uploadMedia,listRoutines,createRoutine,reportCsv,Consent,ConsentKind,Routine} from './core/api';import {mic,files} from './adapters/web';
const KINDS:ConsentKind[]=['camera','mic','data_sharing'];
export default function Content({sel,canEdit}:{sel:string;canEdit:boolean}){const {t}=useTranslation();
 const [cons,setCons]=useState<Consent[]>([]);const [routines,setRoutines]=useState<Routine[]>([]);
 const [rec,setRec]=useState(false);const [clips,setClips]=useState<string[]>([]);const [rn,setRn]=useState('');const [steps,setSteps]=useState('');const [err,setErr]=useState('');
 const load=()=>{consents(sel).then(setCons).catch(()=>{});listRoutines(sel).then(setRoutines).catch(()=>{})};
 useEffect(load,[sel]);
 const cp=(k:ConsentKind)=>{const r=cons.filter(c=>c.kind===k).sort((a,b)=>b.ts.localeCompare(a.ts))[0];return r?.granted===true}; // latest record wins; default off
 const setConsent=async(k:ConsentKind,v:boolean)=>{try{await postConsent(sel,k,v);load()}catch(e:any){setErr(e.message)}};
 const h=useRef<any>(null);
 const start=async()=>{h.current=await mic.record();setRec(true)};
 const stop=async()=>{const {blob}=await h.current.stop();setRec(false);const name=`voice-${Date.now()}.webm`;await uploadMedia(sel,'audio',blob,name,[name]);setClips(c=>[...c,name])};
 const addRoutine=async()=>{await createRoutine(sel,rn,steps.split('\n').filter(Boolean));setRn('');setSteps('');load()};
 const csv=async()=>files.download('smaran-progress.csv',new Blob([await reportCsv(sel)],{type:'text/csv'}));
 return <div>
 <h3>{t('consent')}</h3>{KINDS.map(k=><label key={k} style={{marginRight:12}}><input type="checkbox" data-testid={'consent-'+k} disabled={!canEdit} checked={cp(k)} onChange={e=>setConsent(k,e.target.checked)}/> {k}</label>)}{!canEdit&&<small> (view only)</small>}{err&&<p className="att">{err}</p>}
 <h3>{t('voice')}</h3>{!cp('mic')&&<p className="att">Mic consent required.</p>}
 {rec?<button onClick={stop}>{t('stop')}</button>:<button disabled={!cp('mic')} onClick={start}>{t('record')}</button>}{clips.map(c=><p key={c}>{c}</p>)}
 <h3>{t('routines')}</h3>{routines.map(r=><p key={r.id} data-testid="routine"><b>{r.title}</b>: {Array.isArray(r.steps)?r.steps.map(s=>typeof s==='string'?s:s.title).join(' → '):''}</p>)}
 <input placeholder="Routine name" value={rn} onChange={e=>setRn(e.target.value)}/> <textarea placeholder="One step per line" value={steps} onChange={e=>setSteps(e.target.value)}/> <button disabled={!rn} onClick={addRoutine}>Add routine</button>
 <h3>{t('report')}</h3><button onClick={csv}>Export CSV</button> <button className="alt" onClick={()=>window.print()}>Export PDF</button><p><small>Support tool only, not a diagnosis.</small></p>
 </div>;
}
