import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Bolha de pergunta do avaliador, alinhada estilo chat. */
@Component({
  selector: 'app-chat-message',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat-message.html',
  styleUrl: './chat-message.css',
})
export class ChatMessage {
  readonly pergunta = input.required<string>();
}
