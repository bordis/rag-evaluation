"""Backend do estudo.

Usa os certificados do sistema operacional em vez dos do `certifi`: um antivirus que inspeciona
HTTPS instala a propria raiz no sistema, e sem isso as chamadas a OpenAI falham de forma
intermitente. Precisa rodar antes de qualquer cliente HTTP ser criado, por isso fica no pacote raiz.
"""

import truststore

truststore.inject_into_ssl()
