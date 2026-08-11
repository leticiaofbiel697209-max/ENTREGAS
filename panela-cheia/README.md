# Panela Cheia — V1

Snapshot técnico do novo app de receitas criado no Lovable.

## Branch

Esta versão está isolada na branch `panela-cheia-v1` para não alterar o projeto antigo de ENTREGAS em `main`.

## Erro corrigido nesta branch

O preview móvel apresentou o erro Safari/React `null is not an object (evaluating 'dispatcher.useContext')`.

A correção defensiva aplicada aqui evita múltiplas instâncias do runtime React/contexto:

- React e React DOM fixados em `19.2.0`;
- `overrides` impedindo dependências transitivas de instalar outra cópia de React;
- `resolve.dedupe` explícito no Vite para `react`, `react-dom`, `@tanstack/react-router` e `@tanstack/react-query`.

O React documenta que módulos/contextos duplicados no bundle podem quebrar `useContext`, e o erro observado é compatível com uma chamada de hook em um runtime React diferente do renderer.

## Próximo passo

Conectar o projeto Lovable existente a esta branch/repositório e trazer o restante do snapshot de código. Nenhuma alteração deve ser feita no `main` até a versão da branch ser validada no preview móvel.
