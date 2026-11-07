import React,{useEffect,useState} from 'react';import Plot from './Plot';import {useTranslation} from 'react-i18next';import Coop from './Coop';
import {trends,cueComparison,triggers,severity,listAlerts,ackAlert,TrendDay,CueComparison,Trigger,Severity,Alert} from './core/api';
export default function Panels({sel}:{sel:string}){const {t}=useTranslation();
 const [note,setNote]=useState<Record<string,string>>({});
 const [days,setDays]=useState<TrendDay[]>([]);const [cue,setCue]=useState<CueComparison|null>(null);const [trig,setTrig]=useState<Trigger[]>([]);const [sev,setSev]=useState<Severity|null>(null);const [alerts,setAlerts]=useState<Alert[]>([]);
 const reloadAlerts=()=>listAlerts(sel).then(setAlerts).catch(()=>{});
 useEffect(()=>{trends(sel).then(d=>setDays(d.days)).catch(()=>setDays([]));cueComparison(sel).then(setCue).catch(()=>setCue(null));triggers(sel).then(setTrig).catch(()=>setTrig([]));severity(sel).then(setSev).catch(()=>setSev(null));reloadAlerts()},[sel]);
 const ack=async(a:Alert)=>{await ackAlert(a.id,note[a.id]);reloadAlerts()};
 const L={autosize:true,height:240,margin:{l:40,r:10,t:36,b:30}};const W={width:'100%'};const x=days.map(d=>d.date);
 const drivers=Array.isArray(sev?.drivers)?(sev!.drivers as unknown[]).map(d=>typeof d==='string'?d:((d as any)?.detail??(d as any)?.feature??JSON.stringify(d))).join('; '):JSON.stringify(sev?.drivers??'');
 return <div>
 {sev&&<><h3>{t('support')}</h3><p data-testid="gds">Band: <b className={sev.band==='alert'?'att':''}>{sev.band}</b> · GDS-style {sev.gds_style_indicator}/7 · {drivers}<br/><small data-testid="disclaimer">{sev.disclaimer}</small></p></>}
 <Plot data={[{x,y:days.map(d=>d.avg_score),type:'scatter',line:{color:'#0F766E'}}]} layout={{...L,title:t('trend')}} useResizeHandler style={W}/><small>{t('disc')}</small>
 <Plot data={[{x,y:days.map(d=>d.avg_response_ms),type:'scatter',line:{color:'#F59E0B'}}]} layout={{...L,title:t('response')}} useResizeHandler style={W}/>
 {cue&&<Plot data={[{x:['Without cue','With cue'],y:[cue.without_cue.accuracy*100,cue.with_cue.accuracy*100],type:'bar',marker:{color:['#475569','#0F766E']}}]} layout={{...L,title:t('completion')}} useResizeHandler style={W}/>}
 <Plot data={[{x,y:days.map(d=>d.engagement_minutes),type:'bar',marker:{color:'#0F766E'}}]} layout={{...L,title:t('engagement')}} useResizeHandler style={W}/>
 <h3>{t('alerts')}</h3>{alerts.map(a=><div key={a.id} data-testid="alert">{a.message} {a.acknowledged_at?<b>✓ {a.note}</b>:<><input placeholder="Note" value={note[a.id]||''} onChange={e=>setNote({...note,[a.id]:e.target.value})}/> <button onClick={()=>ack(a)}>{t('ack')}</button></>}</div>)}
 <h3>{t('profile')}</h3>{trig.map(c=><div key={c.cue_id} data-testid="trigger"><b>{c.cue_type} {c.cue_id}</b> · {c.valence_label} · {Math.round(c.confidence*100)}% · validated {c.last_validated_at.slice(0,10)} · half-life {c.half_life_days}d</div>)}
 <Coop sel={sel}/>
 </div>;
}
