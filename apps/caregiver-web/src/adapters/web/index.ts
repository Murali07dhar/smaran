import type {StorageAdapter,FileAdapter,MicAdapter} from '../types';
export const storage:StorageAdapter={get:k=>localStorage.getItem(k),set:(k,v)=>localStorage.setItem(k,v)};
export const files:FileAdapter={download(name,data){const a=document.createElement('a');a.href=URL.createObjectURL(data);a.download=name;a.click()}};
export const mic:MicAdapter={async record(){const s=await navigator.mediaDevices.getUserMedia({audio:true});const r=new MediaRecorder(s),p:Blob[]=[];r.ondataavailable=e=>p.push(e.data);r.start();
 return{stop:()=>new Promise(res=>{r.onstop=()=>{s.getTracks().forEach(t=>t.stop());res({blob:new Blob(p,{type:r.mimeType}),mime:r.mimeType})};r.stop()})}}};
