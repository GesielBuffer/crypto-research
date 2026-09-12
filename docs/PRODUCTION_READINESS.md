# Prontidao para producao

## Estado executivo

O runtime de execucao foi separado do laboratorio, mas trading real esta
tecnicamente bloqueado. Isso e intencional: a unica candidata congelada, C2,
falhou no holdout de agosto de 2026 com profit factor aproximado de 0,714.

O termo "producao" neste repositorio passa a significar um processo observavel,
reproduzivel e protegido. Nao significa colocar uma hipotese reprovada em uma
conta real.

## Componentes implementados

- `execution/models.py`: contratos imutaveis de intencao e fill;
- `execution/risk.py`: estrategia aprovada, notional, alavancagem, posicoes,
  perda diaria, freshness dos dados e kill switch;
- `execution/paper.py`: exchange local sem credenciais e com IDs idempotentes;
- `execution/service.py`: unica porta para validacao e envio ao adaptador;
- `execution/journal.py`: journal append-only e deteccao de ordens interrompidas;
- `execution/readiness.py`: gates objetivos de promocao;
- `deployment/readiness.toml`: estado versionado da promocao.

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
8. revisao humana da promocao e das credenciais de menor privilegio.

Verifique o estado atual sem acessar exchange:

```powershell
.\.venv\Scripts\python.exe -m execution.app
```

Enquanto houver blockers, nenhum adaptador de conta real deve ser conectado ao
`TradingService`.
