import { inject } from '@angular/core';
import { type CanActivateFn, Router, Routes } from '@angular/router';

import { exigeRole, ROLE_ADMIN, ROLES_DO_ESTUDO } from './auth/autenticacao';
import { EvaluationStore } from './services/evaluation-store';

/**
 * Sem sessão válida no estudo aberto (termo não aceito), o avaliador não navega: volta ao início,
 * que rola até o termo e o destaca. Vale para o menu "Documentos" e para a URL digitada.
 * O login vem antes de tudo (`login-required`); `exigeRole` confere a role do cliente.
 */
const exigeSessao: CanActivateFn = async () => {
  const store = inject(EvaluationStore);
  const router = inject(Router);
  if (await store.sessaoValida()) {
    return true;
  }
  store.pedirAceite();
  return router.parseUrl('/');
};

export const routes: Routes = [
  {
    path: '',
    canActivate: [exigeRole],
    data: { roles: ROLES_DO_ESTUDO },
    loadComponent: () => import('./pages/welcome/welcome').then((m) => m.Welcome),
    title: 'Avaliação de respostas · SmartGen',
  },
  {
    path: 'documentos',
    canActivate: [exigeRole, exigeSessao],
    data: { roles: ROLES_DO_ESTUDO },
    loadComponent: () =>
      import('./pages/document-selection/document-selection').then((m) => m.DocumentSelection),
    title: 'Escolha um documento · SmartGen',
  },
  {
    path: 'avaliacao/:docId',
    canActivate: [exigeRole, exigeSessao],
    data: { roles: ROLES_DO_ESTUDO },
    loadComponent: () => import('./pages/evaluation/evaluation').then((m) => m.Evaluation),
    title: 'Avaliação de respostas · SmartGen',
  },
  {
    path: 'admin',
    canActivate: [exigeRole],
    data: { roles: [ROLE_ADMIN] },
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
  {
    path: 'sem-acesso',
    loadComponent: () => import('./pages/sem-acesso/sem-acesso').then((m) => m.SemAcesso),
    title: 'Sem acesso · SmartGen',
  },
  { path: '**', redirectTo: '' },
];
