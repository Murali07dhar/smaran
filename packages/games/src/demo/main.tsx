import React from 'react';
import { createRoot } from 'react-dom/client';
import '../styles.css';
import './demo.css';
import { setAssetBase } from '../ui/assets';
import { App } from './App';
setAssetBase('/');
createRoot(document.getElementById('root')!).render(<App />);
