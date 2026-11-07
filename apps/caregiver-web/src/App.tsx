import React,{useEffect,useState} from 'react';import {useTranslation} from 'react-i18next';
import Login from './Login';import {listPatients,listReminders,listMedia,createReminder,uploadMedia,createPatient,issuePin,lastStale,Patient,Reminder,Media,Role} from './core/api';import Panels from './Panels';import Content from './Content';import {buildRRule} from './core/rrule';
const order:any={alert:0,watch:1,stable:2};
export default function App(){
 const {t,i18n}=useTranslation();const [role,setRole]=useState<Role|''>('');
 const [pats,setPats]=useState<Patient[]>([]);const [stale,setStale]=useState(false);const [sel,setSel]=useState('');const [err,setErr]=useState('');
 const [rems,setRems]=useState<Reminder[]>([]);const [media,setMedia]=useState<Media[]>([]);
 const [title,setTitle]=useState('');const [cat,setCat]=useState('medicine');const [loc,setLoc]=useState('en');const [time,setTime]=useState('08:00');
 const [np,setNp]=useState({name:'',age:'',language:'as'});const [pin,setPin]=useState('');
 const load=()=>listPatients().then(d=>{setPats([...d].sort((a,b)=>(order[a.severity_band||'stable']??3)-(order[b.severity_band||'stable']??3)));setStale(lastStale)}).catch(e=>setErr(String(e.message)));
 const loadPatient=()=>{if(!sel)return;listReminders(sel).then(setRems).catch(()=>{});listMedia(sel).then(setMedia).catch(()=>{})};
 useEffect(()=>{if(role)load()},[role]);useEffect(loadPatient,[sel]);
 if(!role)return <Login onLogin={(r:string)=>setRole(r as Role)}/>;
 const p=pats.find(x=>x.id===sel);
 const addRem=async()=>{await createReminder(sel,{category:cat,title,schedule:buildRRule({freq:'DAILY',days:[],times:[time]}),locale:loc,escalate_after_misses:2,active:true});setTitle('');loadPatient()};
 const upload=async(f?:File)=>{if(!f)return;await uploadMedia(sel,'photo',f,f.name,[f.name]);loadPatient()};
 const addPatient=async()=>{const c=await createPatient({name:np.name,age:+np.age,language:np.language});setNp({...np,name:'',age:''});setPin((await issuePin(c.id)).pin);load()};
 const canEdit=role==='caregiver'; // health_worker is read-only for consent (DPDP: the guardian grants it)
 return <div><header className="card"><b>SMARAN</b> · {role} <select aria-label={t('lang')} value={i18n.language} onChange={e=>i18n.changeLanguage(e.target.value)}><option value="en">English</option><option value="as">অসমীয়া</option></select>{stale&&<span className="att"> {t('stale')}</span>}{err&&<span className="att"> {err}</span>}</header>
 <section className="card"><h2>{t('patients')}</h2>{pats.map(x=><button key={x.id} className="alt" style={{margin:4}} data-testid={'pat-'+x.id} onClick={()=>setSel(x.id)}>{x.name} · {x.severity_band||'–'}{x.open_alerts>0&&` · ${x.open_alerts} ${t('alerts')}`}</button>)}
  {role!=='admin'&&<p><input aria-label="Name" placeholder="Name" value={np.name} onChange={e=>setNp({...np,name:e.target.value})}/> <input aria-label="Age" type="number" placeholder="Age" value={np.age} onChange={e=>setNp({...np,age:e.target.value})}/> <select aria-label={t('lang')} value={np.language} onChange={e=>setNp({...np,language:e.target.value})}>{['as','bn','ne','brx','mni','en'].map(c=><option key={c}>{c}</option>)}</select> <button data-testid="addpat" disabled={!np.name||!np.age} onClick={addPatient}>Add patient</button>{pin&&<span data-testid="pin"> Patient PIN: <b>{pin}</b></span>}</p>}</section>
 {p&&<section className="card"><h2>{p.name}</h2>
  <small>{t('disc')}</small><h3>{t('photo')}</h3><input data-testid="photo" type="file" accept="image/*" onChange={e=>upload(e.target.files?.[0])}/>{media.map(m=><p key={m.id} data-testid="media">{m.kind}: {Array.isArray(m.tags)?m.tags.join(', '):m.mime}</p>)}
  <h3>{t('reminders')}</h3>{rems.map(r=><p key={r.id} data-testid="rem">{r.category}: {r.title}</p>)}
  <input data-testid="rtitle" placeholder={t('title')} value={title} onChange={e=>setTitle(e.target.value)}/> <select value={cat} onChange={e=>setCat(e.target.value)}>{['medicine','hydration','activity','appointment'].map(c=><option key={c}>{c}</option>)}</select>
  <input type="time" value={time} onChange={e=>setTime(e.target.value)}/> <select value={loc} onChange={e=>setLoc(e.target.value)}>{['as','bn','ne','brx','mni','en'].map(c=><option key={c}>{c}</option>)}</select> <button data-testid="addrem" disabled={!title} onClick={addRem}>{t('add')}</button><Panels sel={sel}/><Content sel={sel} canEdit={canEdit}/></section>}</div>;
}
