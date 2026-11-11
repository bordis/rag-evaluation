import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import Keycloak from 'keycloak-js';

/** Login feito, mas sem a role do estudo no cliente: quem libera é o pesquisador. */
@Component({
  selector: 'app-sem-acesso',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="sem-acesso">
      <h1 class="sem-acesso__titulo font-display">Sem acesso a esta área</h1>
      <p class="sem-acesso__texto">
        Sua conta entrou, mas não tem permissão para esta área. Se você foi convidado a avaliar
        as respostas do SmartGen, peça à equipe responsável para liberar o seu usuário.
      </p>
      <button type="button" class="sem-acesso__sair" (click)="sair()">
        Entrar com outra conta
      </button>
    </section>
  `,
  styles: `
    .sem-acesso {
      max-width: 560px;
      margin: var(--space-xxl) auto;
      padding: 0 var(--space-lg);
    }
    .sem-acesso__titulo {
      font-size: 36px;
      color: var(--color-heading);
    }
    .sem-acesso__texto {
      margin: var(--space-md) 0 var(--space-lg);
      color: var(--color-body);
    }
    .sem-acesso__sair {
      padding: 10px 18px;
      border: 0;
      border-radius: var(--radius-sm);
      background-color: var(--color-primary);
      color: var(--color-on-primary);
      font-weight: 500;
      cursor: pointer;
    }
  `,
})
export class SemAcesso {
  private readonly keycloak = inject(Keycloak);

  protected sair(): void {
    void this.keycloak.logout({ redirectUri: window.location.origin });
  }
}
