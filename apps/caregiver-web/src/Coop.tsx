import React,{useState} from 'react';import QRCode from 'qrcode';import {useTranslation} from 'react-i18next';import {createRoom} from './core/api';
// Room comes from POST /coop/rooms (server-issued join_code). game_id is a placeholder until @smaran/games lists real ids.
export default function Coop({sel}:{sel:string}){
 const {t}=useTranslation();const [qr,setQr]=useState('');const [code,setCode]=useState('');const [err,setErr]=useState('');
 const room=async()=>{try{const r=await createRoom(sel,'memory-match');setCode(r.join_code);setQr(await QRCode.toDataURL(`smaran://coop/${r.room_id}?code=${r.join_code}`));setErr('')}catch(e:any){setErr(e.message)}};
 return <div><h3>{t('coop')}</h3><button onClick={room}>{t('createRoom')}</button>{err&&<p className="att">{err}</p>}{code&&<p data-testid="join">Join code: <b>{code}</b></p>}{qr&&<img src={qr} alt="QR" width={160}/>}</div>;
}
