import './index.css';
import React from 'react';import {createRoot} from 'react-dom/client';import './locales';import App from './App';import {setStorage} from './core/api';import {storage} from './adapters/web';setStorage(storage);
const go=()=>createRoot(document.getElementById('root')!).render(<App/>);
if((import.meta as any).env.VITE_USE_MOCKS==='true'){import('./mocks/browser').then(m=>m.worker.start({onUnhandledRequest:'bypass'})).then(go)}else go();
