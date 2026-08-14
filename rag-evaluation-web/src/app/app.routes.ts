import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/welcome/welcome').then((m) => m.Welcome),
    title: 'Avaliação de Pipeline RAG',
  },
  {
    path: 'perfil',
    loadComponent: () => import('./pages/profile/profile').then((m) => m.Profile),
    title: 'Seu perfil · Avaliação RAG',
  },
  {
    path: 'documentos',
    loadComponent: () =>
      import('./pages/document-selection/document-selection').then((m) => m.DocumentSelection),
    title: 'Escolha um documento · Avaliação RAG',
  },
  {
    path: 'avaliacao/:docId',
    loadComponent: () => import('./pages/evaluation/evaluation').then((m) => m.Evaluation),
    title: 'Avaliação · RAG',
  },
  { path: '**', redirectTo: '' },
];
