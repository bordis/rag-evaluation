import type { Ajuda } from '../../components/analise-cartao/analise-cartao';

/** Texto dos botões "?". Cada entrada diz como ler a análise e cita de onde ela vem. */
export const AJUDA = {
  perguntas: {
    oQueE:
      'A resposta curta a cada pergunta do estudo, calculada com os dados atuais. Serve para se orientar; o detalhe está na aba indicada em cada linha.',
    comoLer: [
      '"Evidência a favor": o p ajustado ficou abaixo de 0,05 e os intervalos por avaliador e por documento não incluem 50%.',
      '"Inconclusivo": o teste simples deu significativo, mas o intervalo que respeita avaliadores ou documentos inclui 50%. O resultado pode depender de poucas pessoas ou de poucos documentos.',
      '"Sem evidência": não dá para distinguir de 50%. Isso não prova que não há efeito: veja o poder na aba Validade.',
    ],
    cuidado:
      'O resultado confirmatório é o do modelo misto (aba Preferência). Esta tela não substitui esse modelo.',
    fontes:
      'van der Lee et al. (2021), p. 14–15, sobre testes, efeitos mistos e pesquisa confirmatória; Card et al. (2020), p. 2, sobre resultado nulo e poder.',
  },
  amostra: {
    oQueE:
      'Quantas pessoas, rodadas e documentos entraram na análise, comparados com a faixa prevista no protocolo. Rodada é a unidade de análise; ciclo é o conjunto de até 10 rodadas de um avaliador em um documento.',
    comoLer: [
      'Abaixo da faixa prevista, trate todo resultado como provisório.',
      'Compare a mediana de rodadas por avaliador com o máximo: uma diferença grande indica que poucas pessoas pesam muito no resultado.',
    ],
    cuidado:
      'Avaliadores são sessões anônimas nesta fase: fechar a aba e voltar cria outra sessão, o que pode inflar a contagem.',
    fontes:
      'van der Lee et al. (2021), p. 5 e 12 (a mediana da área é de 3 avaliadores; menos de 50 costuma ter pouco poder, número que diminui com várias observações por participante); Card et al. (2020), p. 7, sobre o que costuma faltar nos relatos.',
  },
  vitoria: {
    oQueE:
      'A proporção de rodadas, entre as que tiveram um vencedor, em que cada pipeline foi escolhido. É uma contagem simples, que em desenhos comparativos costuma dar resultados parecidos com os de modelos de escolha mais elaborados.',
    comoLer: [
      'Sem nenhuma diferença, cada pipeline ficaria perto de 25% (a linha vertical).',
      'O traço é o intervalo de confiança de 95%. Se ele cruza 25%, o dado é compatível com o acaso.',
      '"Faixa de posição": 1–2 significa que os dados não separam esse pipeline do que está ao lado. Só há ordem quando os intervalos, corrigidos para quatro comparações, não se sobrepõem.',
    ],
    cuidado:
      'O intervalo de Wilson trata as rodadas como independentes, e as do mesmo avaliador não são. Para concluir, use os efeitos abaixo. Rodadas "nenhuma" ficam fora dessa conta.',
    fontes:
      'Chiang et al. (2024), p. 4–5 (taxa de vitória e faixas de posição); Zheng et al. (2023), p. 7–8; Kiritchenko e Mohammad (2017), p. 4, citando Louviere et al. (2015), sobre a contagem.',
  },
  efeitos: {
    oQueE:
      'Testa as três hipóteses como perguntas de sim ou não sobre a resposta vencedora. Ingestão: veio de pipeline com Docling (2 ou 4)? Recuperação: veio de recuperação avançada (3 ou 4)? Interação: veio da diagonal 1 e 4, e não de 2 e 3?',
    comoLer: [
      'A linha de referência é 50%. Acima dela, o Docling ou a recuperação avançada foram preferidos; abaixo, o contrário.',
      'Na interação, uma taxa diferente de 50% indica que o ganho de um fator depende do outro. Use as comparações simples para ver em que sentido.',
      'Só afirme um efeito quando o p de Holm for menor que 0,05 e os dois intervalos por bootstrap não incluírem 50%.',
      'Pontos acima de 50 e razão de chances são o tamanho do efeito: dizem quanto, e não só se existe.',
    ],
    cuidado:
      'As rodadas "nenhuma" ficam de fora: esses testes valem só para as rodadas com vencedor. O bootstrap reamostra um agrupamento de cada vez; o modelo misto trata os dois ao mesmo tempo.',
    fontes:
      'van der Lee et al. (2021), p. 14–15 (comparações múltiplas, tamanho de efeito, efeitos mistos); Card et al. (2020), p. 8–9 (ignorar a variação entre avaliadores superestima a certeza).',
  },
  simples: {
    oQueE:
      'As quatro comparações em que só um fator muda: 2 contra 1 e 4 contra 3 isolam a ingestão; 3 contra 1 e 4 contra 2 isolam a recuperação. Olha só as rodadas vencidas por um dos dois pipelines do par.',
    comoLer: [
      'Taxa acima de 50% favorece o primeiro pipeline do par.',
      'Compare as duas linhas de um mesmo fator. Se a recuperação avançada ganha com Docling e não com texto bruto, é assim que a interação se mostra.',
      'O p foi multiplicado por 4 (Bonferroni) porque são quatro perguntas sobre os mesmos dados.',
    ],
    cuidado:
      'Cada par usa só parte das rodadas, então os intervalos são mais largos. Detectar interação pede mais rodadas do que detectar um efeito principal.',
    fontes:
      'van der Lee et al. (2021), p. 8 e 14–15 (lógica de ablação e Bonferroni); Chiang et al. (2024), Fig. 2 (matriz de vitórias entre pares); Kiritchenko e Mohammad (2017), p. 2 (uma escolha revela comparações par a par).',
  },
  modelo: {
    oQueE:
      'A regressão logística com efeitos aleatórios de avaliador e documento, prevista na análise confirmatória. Ela roda fora desta tela, em R, sobre o CSV exportado.',
    comoLer: [
      'Em cada efeito, o script imprime a taxa estimada e o IC de 95%; o teste do intercepto contra 0 equivale ao teste contra 50%.',
      'Se o modelo e o bootstrap discordarem, relate os dois e discuta. Avisos de convergência ou variância próxima de zero costumam indicar poucos avaliadores ou documentos.',
    ],
    fontes: 'van der Lee et al. (2021), p. 15; Card et al. (2020), p. 8–9.',
  },
  nenhuma: {
    oQueE:
      'Com que frequência o avaliador recusou as quatro respostas. Ela não entra na taxa de vitória e é um resultado próprio: mede quantas perguntas nenhum pipeline respondeu bem.',
    comoLer: [
      'Taxa alta significa que comparar os pipelines importa menos do que corrigir um problema comum a todos.',
      'Compare por documento: um documento com taxa muito acima dos outros pode ter conversão ruim ou estar fora do que os avaliadores perguntam.',
      'Veja o que causou cada caso na aba Erros.',
    ],
    cuidado:
      'A opção vale para "nenhuma está correta", e não para "nenhuma é boa o bastante"; o avaliador pode entender de um jeito ou de outro.',
    fontes:
      'Chiang et al. (2024), p. 3 (botões "tie" e "both are bad"); Zheng et al. (2023), p. 29.',
  },
  documento: {
    oQueE:
      'As vitórias de cada pipeline em cada documento, com as taxas de Docling e de recuperação avançada. Mostra se o resultado global é geral ou vem de poucos documentos.',
    comoLer: [
      'Quanto mais escuro o quadro, mais vitórias naquele documento.',
      'Um documento com muitas tabelas é onde a ingestão tem mais chance de aparecer.',
      'Um padrão que vira de um documento para outro pede cautela ao generalizar.',
    ],
    cuidado:
      'Com 10 a 20 rodadas por documento, as taxas oscilam muito. Isto é descritivo e não tem teste. Por documento o resultado também depende de quem o escolheu, pois cada avaliador pega o que conhece melhor.',
    fontes:
      'Medeiros e Oliveira (2025), em que o melhor modelo mudou de uma base para outra; Chiang et al. (2024), Tab. 2 (alguns tópicos distinguem modelos e outros não).',
  },
  poder: {
    oQueE:
      'Se a taxa real fosse 55%, 60%, 65% ou 70%, qual a chance de o teste atual detectar? O cálculo usa o número de rodadas, e nunca o efeito observado.',
    comoLer: [
      'Poder abaixo de 80% é pouco, por convenção. Um resultado "sem evidência" com pouco poder não significa ausência de efeito.',
      '"Exagero" é quanto um resultado significativo tende a superestimar o efeito real (erro Type-M). 2× significa que um efeito real de 5 pontos apareceria, em média, como 10.',
      'Taxa mínima detectável: a menor taxa real que chega a 80% de poder com as rodadas atuais.',
    ],
    cuidado:
      'A conta trata as rodadas como independentes, então é um teto otimista: com variação entre avaliadores, o poder real é menor. Calcular o poder com o efeito medido é a armadilha do poder post hoc e não está aqui de propósito.',
    fontes: 'Card et al. (2020), p. 1–3 e 8–9.',
  },
  posicao: {
    oQueE:
      'Com que frequência cada posição exibida foi escolhida. Como os rótulos são sorteados a cada pergunta, a posição não deveria importar.',
    comoLer: [
      'Sem viés, cada posição fica perto de 25%.',
      'p menor que 0,05 no teste qui-quadrado indica preferência por alguma posição, em geral a primeira.',
      'O sorteio protege a comparação entre pipelines: um viés de posição aumenta o ruído, mas não favorece um pipeline, se a tabela de sorteio estiver equilibrada.',
    ],
    cuidado:
      'A medição do viés de posição em Zheng et al. é em juízes LLM; para pessoas, os autores só citam outros trabalhos. Por isso não há um valor esperado para comparar.',
    fontes:
      'Zheng et al. (2023), p. 4 e 6; van der Lee et al. (2021), p. 13 (aleatorizar a ordem costuma bastar); Es et al. (2024), p. 2.',
  },
  sorteio: {
    oQueE:
      'Quantas vezes cada pipeline apareceu em cada posição. Confere se o sorteio simples ficou equilibrado.',
    comoLer: [
      'Em cada linha, os quatro números devem ser parecidos.',
      'p baixo em um pipeline indica desequilíbrio. Junto com um viés de posição, isso poderia favorecer esse pipeline.',
    ],
    cuidado: 'Com poucas rodadas, um desequilíbrio é esperado e não indica defeito no sorteio.',
    fontes: 'van der Lee et al. (2021), p. 13.',
  },
  fadiga: {
    oQueE:
      'Como o comportamento muda ao longo do ciclo de 10 perguntas: tempo gasto, recusa das respostas e escolhas. O tempo mostrado é o de leitura e decisão: sem a escrita da pergunta, a espera pela geração e o tempo com a aba oculta. Inclui a consulta ao PDF, que abre na mesma tela.',
    comoLer: [
      'Tempo caindo muito pode indicar aprendizado com a interface ou leitura mais superficial (satisficing). Por isso olhe junto com as outras medidas.',
      'Sinal mais forte de fadiga: tempo caindo e posição 1 subindo, ao mesmo tempo. A escolha passa a seguir a tela, e não o conteúdo.',
      'A escolha de recuperação avançada convergindo para 50% ao final sugere escolhas cada vez mais ao acaso.',
      '"ms por mil caracteres" corrige o tempo pelo tamanho das respostas, que confunde a leitura.',
    ],
    cuidado:
      'Nas ordens altas há menos rodadas, porque nem todos chegam ao fim, e quem chega não é uma amostra aleatória. O teste de início contra fim não considera o avaliador; o modelo de fadiga está no script em R.',
    fontes:
      'van der Lee et al. (2021), p. 13 (satisficing e efeitos de ordem); Kiritchenko e Mohammad (2017), p. 3 (carga cognitiva de comparar quatro itens não medida na literatura).',
  },
  coleta: {
    oQueE:
      'Fatos registrados durante a coleta que podem afetar uma escolha sem ter relação com os pipelines.',
    comoLer: [
      '"Viram as quatro": menos de 100% significa escolhas feitas sem as quatro respostas terem aparecido na tela, o caso mais direto de leitura superficial (satisficing). Compare início e fim do ciclo.',
      'Respostas cortadas perdem por um motivo alheio aos fatores. Se um pipeline concentra os cortes, a comparação com ele fica comprometida.',
      'Perguntas com falha somem da análise. Se forem muitas ou parecidas entre si, a amostra deixa de representar o que foi perguntado.',
      'Recargas interrompem a leitura e podem distorcer o tempo daquela rodada.',
    ],
    cuidado:
      'Aparecer na tela não prova que a resposta foi lida. A medida marca o mínimo: quem não viu a resposta certamente não a leu.',
    fontes:
      'van der Lee et al. (2021), p. 13 (satisficing) e p. 15 (critérios de exclusão definidos antes da coleta).',
  },
  ambiente: {
    oQueE:
      'Modelos, temperatura, prompts, preços e configuração dos pipelines no momento em que o estudo foi aberto.',
    comoLer: [
      'É a fonte para a tabela de configuração do apêndice da dissertação.',
      'Os modelos ainda vão mudar até a coleta: cite daqui o que este estudo de fato usou.',
    ],
    cuidado:
      'Um pipeline editado com o estudo aberto não muda este retrato. O que cada resposta usou fica guardado na própria resposta, e o modelo exato de cada etapa, na telemetria.',
    fontes:
      'Es et al. (2024), p. 6–7, e Card et al. (2020), p. 9, sobre reprodutibilidade e dados compartilhados.',
  },
  tamanho: {
    oQueE:
      'Verifica se a resposta mais longa ganha mais do que o acaso (25%) e se algum pipeline escreve mais que os outros.',
    comoLer: [
      'Taxa muito acima de 25% indica preferência por respostas longas.',
      'Se um pipeline também escreve mais e vence mais, parte da vitória pode ser tamanho, e não qualidade.',
      'Respostas mais longas podem ser de fato mais completas. Aqui não há como separar as duas coisas: leia algumas rodadas para decidir.',
    ],
    cuidado:
      'O viés de verbosidade foi medido em juízes LLM. Aplicá-lo a pessoas é uma hipótese deste estudo, e não um achado da literatura.',
    fontes: 'Zheng et al. (2023), p. 5 (viés de verbosidade).',
  },
  avaliadores: {
    oQueE:
      'O comportamento de cada avaliador, para achar quem pesa demais ou responde em padrão. A linha fica marcada para revisão quando uma posição é escolhida muito acima do acaso, com correção para muitas comparações.',
    comoLer: [
      '"Revisar" é um convite para ler as rodadas da pessoa, não um veredito.',
      'Tempo muito baixo, junto de uma posição dominante, é o caso mais preocupante.',
    ],
    cuidado:
      'Não exclua avaliadores olhando o resultado. Qualquer critério de exclusão deve estar definido antes da coleta e ser relatado.',
    fontes:
      'Chiang et al. (2024), p. 5 e 8 (detecção de usuários anômalos); van der Lee et al. (2021), p. 15 (pré-registro de critérios de exclusão).',
  },
  confiabilidade: {
    oQueE:
      'Divide os avaliadores ao acaso em duas metades, 100 vezes, e vê se as duas ordenam os pipelines da mesma forma. Como cada pessoa faz perguntas próprias, não há como calcular a concordância direta entre avaliadores.',
    comoLer: [
      'Spearman perto de 1: as duas metades chegam à mesma ordem. Perto de 0: a ordem depende de quem avaliou.',
      '"Mesmo primeiro lugar" é a fração de divisões em que as duas metades apontam o mesmo pipeline vencedor. O acaso daria cerca de 25%.',
    ],
    cuidado:
      'Com quatro pipelines, a correlação de postos é só descritiva. Não há valor de corte aplicável: os valores altos de Kiritchenko e Mohammad (ρ = 0,95) foram medidos em milhares de itens.',
    fontes:
      'Kiritchenko e Mohammad (2017), p. 2 e 4–5 (reprodutibilidade e split-half); van der Lee et al. (2021), p. 5.',
  },
  concordancia: {
    oQueE:
      'Em quantas rodadas o pipeline de maior nota no RAGAS é o mesmo que a pessoa escolheu. É a comparação rodada a rodada, com muito mais poder do que comparar só a ordem final dos quatro.',
    comoLer: [
      'O acaso daria 25%. Bem acima disso, o RAGAS aponta na direção das pessoas; perto disso, ele mede outra coisa.',
      'Discordância também é resultado: pode indicar que as métricas não captam o que as pessoas valorizam.',
      'Compare entre métricas: fidelidade e precisão do contexto avaliam partes diferentes do pipeline.',
    ],
    cuidado:
      'Os 95%, 78% e 70% do artigo do RAGAS são de pares fáceis e construídos artificialmente em inglês, e os "mais de 80%" de Zheng são entre duas respostas; nenhum serve de meta para uma escolha entre quatro. Empates repartem o acerto.',
    fontes:
      'Es et al. (2024), Tab. 4 e p. 7; Zheng et al. (2023), p. 7–8; Paranhos et al. (2024), p. 9 (pedem métricas alinhadas à satisfação do usuário).',
  },
  vitoriasJuiz: {
    oQueE:
      'A taxa de vitória de cada pipeline segundo as pessoas e segundo o RAGAS, nas mesmas rodadas, com o tau de Kendall da ordem agregada.',
    comoLer: [
      'Barras parecidas indicam que os dois juízes preferem os mesmos pipelines no agregado, ainda que discordem rodada a rodada.',
      'Tau de 1 é a mesma ordem; 0, sem relação; −1, a ordem invertida.',
    ],
    cuidado:
      'Com quatro itens, o tau tem pouquíssimo poder: só o use como descrição, nunca como teste.',
    fontes: 'Zheng et al. (2023), Fig. 3–4; Friel et al. (2024), Tab. 5; Card et al. (2020), p. 2.',
  },
  margem: {
    oQueE:
      'A concordância separada pela vantagem da melhor nota sobre a segunda. Rodadas em que o RAGAS "tem certeza" concordam mais com as pessoas?',
    comoLer: [
      'Concordância subindo da margem pequena para a grande reproduz o padrão de Zheng et al.: juiz e pessoas concordam mais quando os sistemas são distantes.',
      'Se ela não sobe, a nota do RAGAS não informa nem quando parece decidida.',
    ],
    cuidado:
      'Os pipelines daqui compartilham modelo e prompt e tendem a ser parecidos, a situação em que qualquer juiz acompanha mal as pessoas.',
    fontes: 'Zheng et al. (2023), Fig. 2 e p. 25.',
  },
  efeitosRagas: {
    oQueE:
      'O efeito dos dois fatores sobre cada métrica, calculado dentro de cada rodada: a média dos pipelines com o fator menos a média dos sem ele.',
    comoLer: [
      'Valor positivo: o fator aumenta a nota. A escala vai de −1 a 1.',
      'Marcado com "≠ 0": o intervalo por bootstrap não inclui zero.',
      'Compare com a aba Preferência: o RAGAS e as pessoas enxergam o mesmo efeito?',
    ],
    cuidado:
      'As métricas só veem o efeito da ingestão pelos trechos que chegam ao modelo. E a resposta longa pode ser punida ou premiada por métricas diferentes.',
    fontes: 'Es et al. (2024), p. 3–4; Friel et al. (2024), p. 5.',
  },
  notas: {
    oQueE:
      'A média de cada métrica por pipeline. Fidelidade: a resposta se apoia no contexto? Relevância: responde ao que foi perguntado? Precisão do contexto: os trechos servem?',
    comoLer: [
      'Fidelidade e precisão dizem de onde vem o problema: precisão baixa aponta para a recuperação; fidelidade baixa com precisão boa aponta para a geração.',
      'As notas situam os pipelines, mas não definem qual é melhor: esse é o papel do julgamento humano.',
    ],
    cuidado:
      'Relevância não mede se a resposta está certa. Se a comparar com outros trabalhos, confira a versão da biblioteca e o modelo juiz: as notas dependem de ambos.',
    fontes: 'Es et al. (2024), p. 3–7; Friel et al. (2024), p. 5 e 9; Paranhos et al. (2024).',
  },
  rejeitadas: {
    oQueE:
      'Compara a melhor nota do RAGAS nas rodadas recusadas pelas pessoas e nas rodadas com vencedor.',
    comoLer: [
      'Se a nota for bem menor nas recusadas, o RAGAS percebe quando tudo está errado.',
      'Se forem parecidas, ele dá nota boa a respostas que as pessoas dizem estar erradas, uma divergência a discutir.',
    ],
    fontes: 'Es et al. (2024); van der Lee et al. (2021), p. 3.',
  },
  custoBeneficio: {
    oQueE:
      'Junta a preferência humana e o custo por resposta. Responde se o ganho compensa o gasto adicional.',
    comoLer: [
      'O canto superior esquerdo do gráfico é o melhor negócio: mais vitórias e menos custo.',
      '"Dominado por": existe outro pipeline melhor ou igual em vitórias, custo e latência ao mesmo tempo.',
      'Compare o ganho em pontos com o múltiplo de custo. +10 pontos por 2× o custo é uma decisão; +1 ponto por 2× é outra.',
    ],
    cuidado:
      'Dominância olha só as médias e ignora os intervalos: diferenças pequenas de vitória podem ser ruído. O custo em US$ usa os preços configurados e não inclui a descrição de imagens na ingestão. A reordenação local tem US$ zero, mas custa tempo.',
    fontes:
      'Wang et al. (2024), sobre o custo das técnicas avançadas; Arslan et al. (2024), sobre o custo de API em produção.',
  },
  custoEtapas: {
    oQueE: 'Para onde vai o tempo de cada resposta, etapa por etapa.',
    comoLer: [
      'Em geral a geração domina. Nos pipelines 3 e 4, veja o que HyDE e reordenação acrescentam.',
      'Se a geração é quase tudo, trocar de busca muda pouco a latência percebida.',
    ],
    cuidado:
      'Em CPU, o tempo de reordenação inclui a fila e cresce com a concorrência, porque as quatro respostas rodam em paralelo. Para citar esse custo, use o "p50 sem concorrência", de rodadas sem outra em andamento. p95 pode ser dominado por poucos casos no início da coleta.',
    fontes:
      'Li et al. (2026), p. 8 (geração de 75% a 91% da latência, em outro hardware); Wang et al. (2024), sobre HyDE e reordenação.',
  },
  ingestao: {
    oQueE:
      'Quanto custa preparar o acervo em cada pipeline. O custo é pago uma vez por documento, e não por pergunta. Os números são do acervo inteiro e não só deste estudo.',
    comoLer: [
      'Compare o tempo de conversão de 2 e 4 com o de 1 e 3: esse é o custo do Docling.',
      '"Parte da conversão" mostra quanto do tempo total vai para a leitura do documento.',
    ],
    cuidado:
      'Os 98,2% de Li et al. são de OCR (EasyOCR e RapidOCR). Aqui o OCR está desligado, então a comparação direta não vale.',
    fontes: 'Li et al. (2026), p. 5 e 9; Livathinos et al. (2025).',
  },
  erros: {
    oQueE:
      'Para cada rodada recusada, uma primeira hipótese da causa em cada resposta, feita com as notas do RAGAS. Precisão do contexto baixa sugere recuperação. Precisão boa e fidelidade baixa sugerem geração.',
    comoLer: [
      '"Recuperação": os trechos entregues pouco serviam. Abra a rodada e veja se o trecho certo apareceu em alguma etapa.',
      '"Geração": os trechos serviam, mas a resposta não se apoia neles.',
      '"Divergência": o RAGAS não viu problema e a pessoa recusou. Pode ser erro factual fora do alcance das métricas.',
      'Recuperação muito menor nos pipelines 3 e 4 indica ganho da recuperação avançada, e o mesmo vale para 2 e 4 com a ingestão.',
    ],
    cuidado:
      'É uma triagem automática, com limiar de 0,5 definido por convenção neste projeto, e não um diagnóstico. A classificação final é a sua: abra a rodada, leia os trechos e registre a causa no seletor de cada pipeline. Procure também os casos de tabela grande ocupando o contexto e de título da tabela em outro chunk.',
    fontes:
      'Friel et al. (2024), p. 5 (leitura diagnóstica); Li et al. (2026), p. 6 e 10 (recuperação alta não garante resposta certa); Lin (2024) sobre os casos de tabela.',
  },
  contexto: {
    oQueE:
      'Verifica se os pipelines receberam a mesma quantidade de contexto e se as recuperações de fato diferem. É uma checagem do experimento, e não um resultado.',
    comoLer: [
      'Chunks e caracteres devem ficar parecidos nos quatro; senão, uma vitória pode ser só "mais contexto".',
      'Sobreposição (Jaccard): 1 são os mesmos trechos, 0 trechos totalmente diferentes. Perto de 1, a recuperação avançada quase não mudou o que chega ao modelo.',
    ],
    cuidado:
      'Só faz sentido comparar pipelines do mesmo parser, pois os chunks de texto bruto e os de Docling são diferentes. Os caracteres mudam um pouco entre parsers, e isso é esperado.',
    fontes: 'Friel et al. (2024), p. 3; Es et al. (2024), p. 3; Li et al. (2026), p. 6.',
  },
} satisfies Record<string, Ajuda>;
