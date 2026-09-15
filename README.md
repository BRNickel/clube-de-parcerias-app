# Clube de Parcerias (saída pública)

Este repositório é a **saída** do Clube de Parcerias da Brazilian Nickel: a página em
`docs/index.html` é **gerada automaticamente** a partir das parcerias que o RH publicou no
painel interno, e servida por GitHub Pages em
<https://brnickel.github.io/clube-de-parcerias-app/>.

## Como funciona

1. O RH aprova e publica uma parceria no **Painel de Parcerias** (no brnapps, atrás do login).
2. A função pública `cards_publicos` devolve **só os cards ativos, só com os campos do card**
   (estabelecimento, categoria, condição, cidade, endereço, horário, WhatsApp do estabelecimento).
   Nada sobre quem indicou, contatos pessoais, motivos ou evidências sai dali: a própria função
   varre a resposta e se recusa a responder se aparecer e-mail ou campo proibido.
3. A rotina `.github/workflows/gerar.yml` roda **a cada 15 minutos**: chama a função, preenche
   `gerador/template.html` com `gerador/gerar.py` e, se o resultado mudou, faz commit de
   `docs/index.html`. O Pages publica o commit. Publicar no painel aparece aqui em até ~15 min.
4. Sem segredo nenhum no caminho: a função é pública e o commit usa o token automático do Actions.

## O que NÃO fazer

- Não editar `docs/index.html` à mão: a próxima geração sobrescreve.
- Não editar `gerador/template.html` à mão: ele é derivado do desenho do app
  (`App/clube-de-parceiros.html`, no projeto interno) por `comum/preparar_template.py`. Mudou o
  desenho? Roda o script lá e sobe o template aqui.
- Não colocar aqui nada que não seja campo do card. Este repositório é **público**.

## Regras do gerador

- Zero cards ativos **não** gera página vazia: mantém a atual (a provisória ou a última boa).
- Dado com chave proibida ou e-mail em qualquer lugar **aborta** a geração (código 2).
- Só grava se o resultado mudou: a rotina não faz commit à toa.
- `gerador/cidades.json` é a mesma lista de cidades do painel (códigos e nomes iguais); um
  código desconhecido (região digitada no painel) vira cidade própria, no fim da lista.
  "Vale para todas" (`TODAS`) põe o card em todas as cidades.

## Testar à mão

```
python3 gerador/gerar.py --entrada gerador/exemplo.json --saida /tmp/teste.html
```

`exemplo.json` tem três parceiros inventados, só para ver o desenho.

## Atenção

O GitHub desliga rotinas agendadas em repositório sem atividade por 60 dias. Se o app parar de
atualizar, abra Actions → "Gerar app" → Run workflow; qualquer commit também religa.
