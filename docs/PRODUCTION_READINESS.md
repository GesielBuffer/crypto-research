# Prontidao para producao

## Estado executivo

O runtime de execucao foi separado do laboratorio, mas trading real esta
tecnicamente bloqueado. Isso e intencional: a unica candidata congelada, C2,
falhou no holdout de agosto de 2026 com profit factor aproximado de 0,714.

O termo "producao" neste repositorio passa a significar um processo observavel,
reproduzivel e protegido. Nao significa colocar uma hipotese reprovada em uma
conta real.

## Componentes implementados

- `execution/models.py`: contratos imutaveis de entrada, fill e protecao;
- `execution/risk.py`: estrategia aprovada, notional, alavancagem, posicoes,
  perda diaria, freshness dos dados e kill switch;
- `execution/paper.py`: exchange local sem credenciais e com IDs idempotentes;
- `execution/service.py`: unica porta para validacao e envio ao adaptador;
- toda entrada exige stop-loss e take-profit; falha de protecao aciona
  fechamento emergencial e impede reutilizacao da entrada encerrada;
- breakeven opcional por multiplo de R, com buffer economico explicito e
  comportamento simetrico para long e short;
- substituicao de stop sem janela desprotegida: cria e confirma o novo stop
  antes de cancelar o anterior, com retry idempotente e reconciliacao;
- supervisor de uma iteracao consulta mark price, exige timestamp recente e
  recusa simbolo divergente antes de avaliar o gatilho;
- filtros atuais do simbolo sao consultados no Testnet: quantidade invalida,
  stop ou alvo fora do `PRICE_FILTER` bloqueiam a entrada antes do POST;
- o stop de breakeven e arredondado conservadoramente pelo `tickSize`, para
  baixo em long e para cima em short;
- loop de supervisao com polling configuravel, backoff exponencial, limite de
  falhas transitorias, execucao limitada para testes e encerramento cooperativo;
- `execution/journal.py`: journal append-only e deteccao de ordens interrompidas;
- `execution/binance_testnet.py`: gateway USD-M assinado que rejeita qualquer host diferente do Testnet;
- `execution/config.py`: configuracao fail-closed; variaveis de ambiente nao conseguem habilitar conta real;
- `execution/readiness.py`: gates objetivos de promocao;
- `deployment/readiness.toml`: estado versionado da promocao.

As protecoes usam o servico Algo atual da Binance USD-M
(`/fapi/v1/algoOrder` e `/fapi/v1/openAlgoOrders`). Os tipos condicionais nao
sao enviados pelo endpoint legado de ordens comuns.

O legado `main.py` nao faz parte da nova arquitetura e nao deve ser executado.
Ele mistura selecao de ativos, sinal, cliente HTTP, sizing, protecao e loop, alem
de possuir configuracao historica de conta real e alavancagem elevada.

## Gates obrigatorios

Trading real somente pode ser considerado quando todos forem verdadeiros:

1. estrategia aprovada em desenvolvimento e robustez;
2. novo holdout, nunca usado em tuning, aprovado;
3. paper trading aprovado por periodo predefinido;
4. testnet aprovado;
5. recuperacao de falhas simulada;
6. reconciliacao de ordens e posicoes testada;
7. kill switch testado;
8. protecao de posicao e fechamento emergencial testados;
9. revisao humana da promocao e das credenciais de menor privilegio.

Verifique o estado atual sem acessar exchange:

```powershell
.\.venv\Scripts\python.exe -m execution.app
```

Enquanto houver blockers, nenhum adaptador de conta real deve ser conectado ao
`TradingService`.

## Correcoes fail-closed

- retries consultam primeiro o `client_order_id` na exchange;
- timeout depois do aceite e reconciliado sem uma segunda ordem;
- IDs reaproveitados para quantidade, ativo ou lado diferentes sao rejeitados;
- journal e exchange divergentes exigem reconciliacao, sem retry cego;
- fill antigo com posicao zerada e tratado como encerrado, nunca como motivo
  para recriar stop e alvo;
- ordens condicionais orfas sao identificadas pelos IDs daquela entrada,
  canceladas de forma restrita e verificadas; ordens alheias nao sao tocadas;
- quantidade parcial, invertida ou multiplas linhas de posicao bloqueiam a
  automacao e exigem reconciliacao;
- timestamps obsoletos ou no futuro sao recusados;
- IDs fora do formato aceito pela Binance sao recusados;
- o gateway implementado aceita somente `https://testnet.binancefuture.com`.
- falha ao confirmar o novo stop preserva o stop antigo; estado ambiguo exige
  reconciliacao, e ausencia confirmada de protecao aciona fechamento emergencial.

O gateway testnet possui testes unitarios com transporte simulado, mas o gate
`testnet_passed` permanece falso ate um ciclo real no ambiente de demonstracao,
com credenciais exclusivas e sem permissao de saque. Nenhuma credencial foi
lida ou usada durante esta implementacao.

O breakeven tambem nao e um gate universal nem deve ser habilitado por intuicao.
Cada estrategia deve pre-registrar `activation_r_multiple` e
`cost_buffer_rate`, comparar o resultado com e sem a regra em dados de
desenvolvimento e validar a escolha fora da amostra. Hospedagem do processo,
heartbeat externo, alertas operacionais e o ensaio completo no Testnet ainda
sao pendencias operacionais.
