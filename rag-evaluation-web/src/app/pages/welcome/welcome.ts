import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Tela de boas-vindas: agradecimento + explicação do processo de avaliação. */
@Component({
  selector: 'app-welcome',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  templateUrl: './welcome.html',
  styleUrl: './welcome.css',
})
export class Welcome {
  protected readonly passos = [
    {
      numero: '1',
      titulo: 'Escolha um documento',
      texto:
        'Selecione, entre os documentos disponíveis, aquele sobre o qual você tem mais conhecimento.',
    },
    {
      numero: '2',
      titulo: 'Faça perguntas',
      texto:
        'Converse com o documento como em um chat. Você pode fazer até 10 perguntas por documento.',
    },
    {
      numero: '3',
      titulo: 'Escolha a melhor resposta',
      texto:
        'Para cada pergunta, apresentamos 4 respostas anônimas (A, B, C e D). Escolha a que mais lhe agradar.',
    },
  ];
}
