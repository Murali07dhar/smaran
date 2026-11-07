import React,{useState} from 'react';import {useTranslation} from 'react-i18next';import {login} from './core/api';
export default function Login({onLogin}:{onLogin:(role:string)=>void}){
 const {t}=useTranslation();const [u,setU]=useState('');const [pw,setPw]=useState('');const [err,setErr]=useState('');
 return <main className="card" style={{maxWidth:360,margin:'40px auto'}}><h1>SMARAN</h1><p>Understanding Memory Through Emotion</p>
  <input data-testid="user" aria-label={t('user')} placeholder={t('user')} value={u} onChange={e=>setU(e.target.value)}/><br/><br/>
  <input aria-label={t('pass')} type="password" placeholder={t('pass')} value={pw} onChange={e=>setPw(e.target.value)}/><br/><br/>
  <button data-testid="login" onClick={()=>login(u,pw).then(d=>onLogin(d.role)).catch(()=>setErr('Login failed'))}>{t('login')}</button><p className="att">{err}</p></main>;
}
