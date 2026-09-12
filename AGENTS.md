# Instrucoes do agente — Crypto Research

## Missao

Transformar este laboratorio em um sistema de pesquisa quantitativa reproduzivel e, somente depois de validacao fora da amostra, em um bot de cripto seguro. O objetivo do agente nao e maximizar um backtest isolado; e encontrar evidencias robustas que sobrevivam a custos, ativos, periodos e dados nunca usados no desenvolvimento.

## Regra de seguranca inegociavel

- Nunca execute `main.py`, envie ordens, altere `DRY_RUN` para `False` ou use a conta real sem autorizacao explicita do usuario para aquela execucao.
- Considere `main.py` codigo de producao legado e potencialmente perigoso: atualmente ele aponta para ambiente real.
- Nunca leia, mostre, versione ou copie valores de `.env`, chaves da Binance, chaves OpenAI ou outros segredos.
- Pesquisa historica deve usar endpoints publicos e nao precisa de credenciais de trading.
- Antes de paper trading: testes automatizados, simulacao de falhas, reconciliacao de ordens e protecao de posicao sao obrigatorios.

## Ambiente padrao

- Windows: `.venv\Scripts\python.exe`
- Dependencias: `requirements.txt`
- Verificacao rapida sem rede:
  - `.venv\Scripts\python.exe -m pip check`
  - `.venv\Scripts\python.exe -m compileall -q research .`
- Teste publico com rede: `.venv\Scripts\python.exe -m experiments.legacy.test_indicators`

## Protocolo de pesquisa

1. Registre a hipotese e os criterios de aprovacao antes de olhar o resultado.
2. Use somente informacao disponivel ate o candle `t`; entradas devem ocorrer em `t+1` ou depois.
3. Inclua taxas, slippage e funding quando aplicaveis. O custo-base historico usado no projeto e 0,06% por round trip; teste custos piores.
4. Separe desenvolvimento, validacao e holdout. Nunca ajuste parametros usando um holdout ja aberto.
5. Compare com baselines simples e reporte amostra, retorno medio/mediano, profit factor, drawdown, estabilidade temporal e por ativo.
6. Altere uma familia de hipotese por vez. Resultados negativos sao conclusoes validas; nao faca tuning ate passar por acaso.
7. Salve resultados pequenos e auditaveis em `results/`. Arquivos brutos `*_events.csv` e dados em `data/` nao entram no Git.
8. Uma estrategia so pode avancar para paper trading depois de passar criterios predefinidos em dados verdadeiramente fora da amostra.

## Fluxo de desenvolvimento

- Comece conferindo `git status` e preserve mudancas existentes.
- Antes de editar, rode o baseline relevante e registre o resultado.
- Implemente a menor mudanca coerente, execute verificacoes proporcionais ao risco e compare com o baseline.
- Mantenha codigo reutilizavel em `research/`; evite criar novos scripts monoliticos quando a logica puder virar modulo e configuracao.
- Atualize README e documentos quando comandos, arquitetura ou conclusoes mudarem.
- Crie commits pequenos e descritivos apenas depois das verificacoes passarem.
- Nunca envie para o GitHub segredos, ambientes virtuais, dados brutos ou arquivos acima do limite do provedor.

## Estado cientifico atual

- A estrategia C2 teve desempenho positivo no conjunto de desenvolvimento, mas falhou no holdout de agosto de 2026 (PF aproximado de 0,71 com custo de 0,06%).
- Ela nao esta aprovada para producao nem paper trading como estrategia vencedora.
- Experimentos posteriores devem ser tratados como descoberta exploratoria ate passarem por um novo protocolo de validacao sem contaminacao.
