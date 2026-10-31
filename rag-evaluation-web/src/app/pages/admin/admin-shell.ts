import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/**
 * Moldura da área de gerenciamento; a navegação fica no menu superior do app.
 * TODO: com o login, esconder do avaliador os links desta área, que revela os pipelines.
 */
@Component({
  selector: 'app-admin-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet],
  templateUrl: './admin-shell.html',
})
export class AdminShell {}
