import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

const theme = localStorage.getItem('h2a-theme') || 'dark';
document.documentElement.setAttribute('data-theme', theme);

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
