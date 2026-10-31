import { inject } from '@angular/core';
import { type CanActivateFn, Router, Routes } from '@angular/router';

import { EvaluationStore } from './services/evaluation-store';

/**
 * Sem sessão válida no estudo aberto, o avaliador volta ao início para aceitar o termo.
 * TODO: proteger as rotas `/admin` com o login previsto; nesta fase ficam abertas por decisão.
 */
const exigeSessao: CanActivateFn = async () => {
  const valida = await inject(EvaluationStore).sessaoValida();
  return valida || inject(Router).parseUrl('/');
};

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/welcome/welcome').then((m) => m.Welcome),
    title: 'Avaliação de Pipeline RAG',
  },
  {
    path: 'documentos',
    canActivate: [exigeSessao],
    loadComponent: () =>
      import('./pages/document-selection/document-selection').then((m) => m.DocumentSelection),
    title: 'Escolha um documento · Avaliação RAG',
  },
  {
    path: 'avaliacao/:docId',
    canActivate: [exigeSessao],
    loadComponent: () => import('./pages/evaluation/evaluation').then((m) => m.Evaluation),
    title: 'Avaliação · RAG',
  },
  {
    path: 'admin',
    loadComponent: () => import('./pages/admin/admin-shell').then((m) => m.AdminShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'estudos' },
      {
        path: 'estudos',
        loadComponent: () => import('./pages/admin/estudos').then((m) => m.AdminEstudos),
        title: 'Estudos · Gerenciamento',
      },
      {
        path: 'documentos',
        loadComponent: () => import('./pages/admin/documentos').then((m) => m.AdminDocumentos),
        title: 'Documentos · Gerenciamento',
      },
      {
        path: 'pipelines',
        loadComponent: () => import('./pages/admin/pipelines').then((m) => m.AdminPipelines),
        title: 'Pipelines · Gerenciamento',
      },
      {
        path: 'estudos/:studyId/avaliacoes',
        loadComponent: () => import('./pages/admin/avaliacoes').then((m) => m.AdminAvaliacoes),
        title: 'Avaliações · Gerenciamento',
      },
      {
        path: 'avaliacoes/:sessionId/:documentId',
        loadComponent: () =>
          import('./pages/admin/avaliacao-detalhe').then((m) => m.AdminAvaliacaoDetalhe),
        title: 'Avaliação · Gerenciamento',
      },
      {
        path: 'estudos/:studyId/resultados',
        loadComponent: () => import('./pages/admin/resultados').then((m) => m.AdminResultados),
        title: 'Resultados · Gerenciamento',
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
