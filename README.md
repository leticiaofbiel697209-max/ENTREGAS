# Gestao de Entregas Novaprint

Sistema em Python + Streamlit para controlar rotas de entrega, registrar resultados pelo entregador e atualizar vendas no ERP GestaoClick.

## Como rodar

1. Instale as dependencias:

```bash
pip install -r requirements.txt
```

2. Copie o arquivo de ambiente:

```bash
copy .env.example .env
```

3. Preencha no `.env`:

```env
GESTAOCLICK_URL=https://api.gestaoclick.com
GESTAOCLICK_TOKEN=seu_token
GESTAOCLICK_SECRET_TOKEN=seu_secret_access_token
GESTAOCLICK_LOJA_ID=id_da_loja_novaprint_opcional
ADMIN_USER=admin
ADMIN_PASSWORD=sua_senha
```

4. Execute:

```bash
streamlit run app.py
```

O banco SQLite fica em `database/entregas.db` e e criado automaticamente se ainda nao existir.

## Como acessar

### Rodando no seu computador

Se voce copiou `.env.example` para `.env`, entre como ADMIN usando os valores definidos nele:

```text
Usuario: admin
Senha: 123456
```

No arquivo de exemplo, a senha vem como `123456`. Troque antes de usar de verdade.

### Rodando no Streamlit Cloud

Abra **Settings > Secrets** e cadastre:

```toml
ADMIN_USER = "admin"
ADMIN_PASSWORD = "sua_senha"
GESTAOCLICK_URL = "https://api.gestaoclick.com"
GESTAOCLICK_TOKEN = "seu_token"
GESTAOCLICK_SECRET_TOKEN = "seu_secret_access_token"
GESTAOCLICK_LOJA_ID = "id_da_loja_novaprint"
GESTAOCLICK_TIMEOUT = "30"
```

Depois salve e reinicie o app. Na tela inicial, use o usuario e a senha que voce colocou nesses Secrets.

## Perfis de acesso

- **ADMIN**: acessa dashboard, rotas, historico, configuracoes e painel do entregador.
- **ENTREGADOR**: acessa somente as entregas atribuidas ao proprio nome.

O primeiro acesso ADMIN usa as variaveis `ADMIN_USER` e `ADMIN_PASSWORD` do `.env`.
Cadastre entregadores em **Configuracoes** e defina um codigo de acesso para cada um.

## Integracao GestaoClick

O arquivo `services/gestaoclick_api.py` centraliza a comunicacao:

- `buscar_venda(venda_id)`
- `buscar_cliente(cliente_id)`
- `buscar_endereco_venda(venda_id)`
- `buscar_endereco_cliente(cliente_id)`
- `atualizar_status_venda(venda_id, status)`

As chamadas usam:

- `GESTAOCLICK_URL`
- `GESTAOCLICK_TOKEN`
- `GESTAOCLICK_SECRET_TOKEN`
- `GESTAOCLICK_LOJA_ID`, opcional quando o app nao conseguir identificar a loja NOVAPRINT pelo nome.

## Supabase

Para persistir rotas e entregadores em nuvem, crie um projeto no Supabase e execute o arquivo `supabase_schema.sql` no SQL Editor.

Depois configure:

```toml
SUPABASE_URL = "https://seu-projeto.supabase.co"
SUPABASE_SERVICE_KEY = "sua_service_role_key"
```

A versao atual ainda usa SQLite por padrao; essas chaves deixam o projeto preparado para migrar a persistencia sem mudar a estrutura de tabelas.

Como APIs de ERP podem variar por conta ou versao, as funcoes aceitam formatos comuns de resposta e registram o retorno completo da atualizacao no historico da entrega.

## Fluxo recomendado

1. ADMIN configura entregadores.
2. ADMIN cria uma rota com data, veiculo e observacao.
3. ADMIN adiciona entregas manualmente ou buscando dados no GestaoClick.
4. ENTREGADOR acessa pelo celular, ve apenas as proprias entregas e registra:
   - entregue;
   - falha;
   - ocorrencia.
5. Ao marcar **ENTREGUE**, o sistema chama o GestaoClick para atualizar o status da venda.

## Estrutura

```text
app.py
requirements.txt
README.md
.env.example
database/
  entregas.db
services/
  db.py
  gestaoclick_api.py
  rotas_service.py
modules/
  dashboard.py
  rotas.py
  entregador.py
  historico.py
  configuracoes.py
```
