import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import { connect } from './lib/agui';

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
connect();
