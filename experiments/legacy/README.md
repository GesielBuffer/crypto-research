# Experimentos legados

Este diretorio preserva os scripts monoliticos anteriores a consolidacao. Eles
nao fazem parte do runtime operacional, nao sao testes automatizados e nao
podem promover estrategias.

Os resultados pequenos permanecem em `results/` e o codigo original permanece
tambem no historico Git. Quando uma familia voltar a ser relevante, sua regra
de sinal deve ser extraida para `research/`, registrada em
`experiments/registry.toml`, ligada a um manifesto de dados e reproduzida por
teste de regressao antes de qualquer novo desenvolvimento.

Para executar deliberadamente um estudo arquivado a partir da raiz:

```powershell
.\.venv\Scripts\python.exe -m experiments.legacy.test_nome_do_experimento
```

Alguns estudos baixam dados publicos ou geram arquivos grandes. Inspecione a
configuracao antes da execucao.
