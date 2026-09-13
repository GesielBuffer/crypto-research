# Plano acelerado de 28 dias

## Objetivo e limite

Inicio: **2026-09-13**. Decisao GO/NO-GO: **2026-10-10**. Um eventual piloto
minimo pode ser considerado a partir de **2026-10-11**, mas somente se todos os
gates versionados estiverem aprovados. A data nao transforma um NO-GO em GO.

O objetivo das quatro semanas e obter uma decisao auditavel, nao prometer lucro.
O candidato C2 permanece reprovado e nao pode ser reutilizado como candidato
novo.

## Trilha paralela

| Prazo | Pesquisa | Execucao e operacao |
|---|---|---|
| 13-15 set | definir familias e criterios sem usar dados futuros | protecao, fechamento emergencial e falhas |
| 13-18 set | desenvolvimento, custos e walk-forward em dados antigos | preflight e ensaios locais/Testnet |
| 18 set | congelar no maximo uma candidata ou declarar NO-GO antecipado | registrar commit, parametros e hashes |
| 19 set-10 out | holdout futuro sem tuning | shadow, paper e Testnet em paralelo |
| 10 out | relatorio final imutavel | reconciliacao e decisao GO/NO-GO |
| 11 out | nenhuma alteracao se houver falha | piloto minimo somente com todos os gates |

## Regras para comprimir sem contaminar

1. Pesquisa e engenharia rodam em paralelo, mas o candidato e congelado antes
   do primeiro candle do holdout.
2. Durante o holdout, resultados podem ser monitorados para seguranca, mas nao
   podem orientar parametros, filtros ou selecao de ativos.
3. Paper e Testnet validam o encanamento; nao substituem a evidencia estatistica
   do holdout.
4. Replay e injecao de falhas comprimem testes de engenharia, nao o tempo de
   mercado.
5. Qualquer mudanca da estrategia apos 18 de setembro cria uma nova candidata e
   reinicia o holdout.

## Gates para o dia 28

- candidata identificada por commit e configuracao imutavel;
- criterios de PASS registrados antes do holdout;
- holdout realmente novo com decisao PASS;
- custos, slippage e funding incluidos quando aplicaveis;
- paper e Testnet sem posicoes orfas ou ordens duplicadas;
- toda entrada com stop e take-profit confirmados;
- fechamento emergencial, reconciliacao e kill switch comprovados;
- relatorios de paper e Testnet identificados por SHA-256;
- adaptador real revisado separadamente;
- autorizacao humana explicita para uma execucao especifica.

## Estado inicial

Em 2026-09-13, protecao obrigatoria e fechamento emergencial foram implementados
e cobertos por testes locais e testes unitarios do adaptador Testnet. Continuam
fechados os gates de estrategia, holdout, paper, Testnet e adaptador real.
