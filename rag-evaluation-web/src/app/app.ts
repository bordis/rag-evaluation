import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  inject,
  signal,
} from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import Keycloak from 'keycloak-js';

import { ROLE_ADMIN, temRole } from './auth/autenticacao';

type Painel = 'pesquisador' | 'conta';

/** Itens da área do pesquisador, com uma linha que diz para que serve cada tela. */
const ITENS_PESQUISADOR = [
  { rota: '/admin/estudos', titulo: 'Estudos', descricao: 'Abrir, encerrar e ver resultados' },
  {
    rota: '/admin/documentos',
    titulo: 'Documentos',
    descricao: 'Enviar PDFs e acompanhar a ingestão',
  },
  {
    rota: '/admin/pipelines',
    titulo: 'Pipelines',
    descricao: 'Configurar os quatro braços do estudo',
  },
] as const;

function iniciaisDe(nome: string): string {
  const partes = nome.split(/[\s._-]+/).filter(Boolean);
  const letras = partes.length > 1 ? partes[0][0] + partes[partes.length - 1][0] : nome.slice(0, 2);
  return letras.toUpperCase();
}

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.css',
  host: {
    '(document:click)': 'fecharSeFora($event)',
    '(document:keydown.escape)': 'fechar()',
  },
})
export class App {
  private readonly keycloak = inject(Keycloak);
  private readonly elemento = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly router = inject(Router);

  /** O menu do pesquisador revela que há pipelines: o avaliador não o vê. */
  protected readonly admin = temRole(this.keycloak, ROLE_ADMIN);
  protected readonly itensPesquisador = ITENS_PESQUISADOR;

  /** Só na tela, para a pessoa saber com que conta entrou; nunca vai para a API. */
  protected readonly usuario =
    (this.keycloak.tokenParsed?.['preferred_username'] as string | undefined) ?? '';
  protected readonly nome =
    (this.keycloak.tokenParsed?.['name'] as string | undefined) ?? this.usuario;
  protected readonly iniciais = iniciaisDe(this.nome || '?');

  protected readonly aberto = signal<Painel | null>(null);
  protected readonly naAreaPesquisador = signal(false);

  constructor() {
    const inscricao = this.router.events.subscribe((evento) => {
      if (evento instanceof NavigationEnd) {
        this.naAreaPesquisador.set(evento.urlAfterRedirects.startsWith('/admin'));
        this.fechar();
      }
    });
    inject(DestroyRef).onDestroy(() => inscricao.unsubscribe());
  }

  protected alternar(painel: Painel): void {
    this.aberto.update((atual) => (atual === painel ? null : painel));
  }

  protected fechar(): void {
    this.aberto.set(null);
  }

  protected fecharSeFora(evento: MouseEvent): void {
    const alvo = evento.target as Element | null;
    const dentro = [...this.elemento.nativeElement.querySelectorAll('.suspenso')].some((caixa) =>
      caixa.contains(alvo),
    );
    if (this.aberto() && !dentro) {
      this.fechar();
    }
  }

  protected sair(): void {
    void this.keycloak.logout({ redirectUri: document.baseURI });
  }
}
