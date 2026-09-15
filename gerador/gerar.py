# -*- coding: utf-8 -*-
"""Gera docs/index.html (o app público do Clube de Parcerias) a partir dos
cards ATIVOS que a função pública devolve.

Roda na rotina do GitHub Actions (.github/workflows/gerar.yml) a cada 15 min e
também à mão:
    python3 gerador/gerar.py                       # busca na função, grava docs/index.html
    python3 gerador/gerar.py --entrada x.json --saida /tmp/teste.html

Regras que não podem cair:
- A ÚNICA fonte é a função pública `cards_publicos`, que já devolve só campos
  do card. Mesmo assim tudo é VARRIDO aqui de novo: chave proibida ou e-mail
  em qualquer lugar do dado aborta a geração (código 2) e a página atual fica.
- Zero cards ativos NÃO gera página vazia: mantém a atual (página provisória
  ou a última geração boa). Só `--permitir-vazio` muda isso.
- Só grava se o resultado mudou: a rotina não faz commit à toa.
- Sem segredo nenhum: a função é pública e o commit usa o token do próprio
  Actions.
"""
import argparse, io, json, os, re, sys, unicodedata, urllib.request
from html import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
ENDPOINT = "https://taicyccelmjjsiwzwltc.supabase.co/functions/v1/clube_de_parcerias_api_cards_publicos"

# 🔴 MESMA lista do painel e do formulário (CATEGORIAS / TIPOS), nos mesmos códigos
CATN = {"alimentacao": "Alimentação", "beleza": "Beleza", "saude": "Saúde e bem-estar", "automotivo": "Automotivo",
        "construcao": "Construção", "compras": "Compras", "servico": "Serviço", "outros": "Outros"}
PROIBIDOS = {"colaborador", "colaboradorEmail", "preenchidoPor", "contatoNome", "contatoEmail", "contatoTelefone",
             "contatoFone", "historico", "evidencia", "pacote", "area", "filial", "genero", "nota", "motivo"}
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HORARIO_PADRAO = "Consultar horário de funcionamento"   # o mesmo texto do painel (HORARIO_PADRAO)


def slug(txt):
    t = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def plural(n, um, muitos):
    return ("%d %s" % (n, um)) if n == 1 else ("%d %s" % (n, muitos))


def carregar(entrada):
    if entrada and not entrada.startswith("http"):
        return json.load(io.open(entrada, encoding="utf-8"))
    req = urllib.request.Request(entrada or ENDPOINT, headers={"Accept": "application/json", "User-Agent": "clube-de-parcerias-gerador"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def varrer(dado):
    """chave proibida em QUALQUER nível, ou e-mail em qualquer valor: aborta"""
    achados = []
    def anda(o, caminho):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in PROIBIDOS: achados.append("chave proibida: %s.%s" % (caminho, k))
                anda(v, caminho + "." + k)
        elif isinstance(o, list):
            for i, v in enumerate(o): anda(v, "%s[%d]" % (caminho, i))
        elif isinstance(o, str):
            if RE_EMAIL.search(o) and not o.startswith("data:"): achados.append("e-mail em %s" % caminho)
    anda(dado, "cards")
    return achados


def icone_html(card, tipo):
    ic = (card.get("icone") or "").strip()
    if ic.startswith("data:image/"):
        return ' logo', '<img src="%s" alt="">' % escape(ic, quote=True)
    if ic not in CATN: ic = tipo
    return '', '<svg class="ic"><use href="#i-%s"/></svg>' % ic


def digitos_fone(t):
    d = re.sub(r"\D", "", t or "")
    if len(d) in (12, 13) and d.startswith("55"): d = d[2:]
    return d if len(d) in (10, 11) else ""


def card_html(c, cidade):
    tipo = c.get("tipo") if c.get("tipo") in CATN else "outros"
    card = c.get("card") or {}
    estab = (c.get("estab") or "").strip()
    titulo = (card.get("titulo") or "").strip()
    pendente = "" if titulo else " pendente"
    cond = titulo or "Condições a confirmar"
    cls_logo, ico = icone_html(card, tipo)
    linhas = []
    def linha(simbolo, txt):
        if txt: linhas.append('          <div class="d-row"><svg class="ic"><use href="#i-%s"/></svg><span class="d-txt">%s</span></div>' % (simbolo, escape(txt)))
    linha("tag", (card.get("detalhe") or "").strip())
    linha("shop", (c.get("atendimento") or "").strip())
    linha("pin", (card.get("endereco") or "").strip())
    # sem horário no formulário nem no card, o texto padrão (o MESMO do painel)
    linha("clock", (card.get("horario") or "").strip() or HORARIO_PADRAO)
    acoes = []
    end = (card.get("endereco") or "").strip()
    if end:
        q = end if slug(cidade["nome"]) in slug(end) else end + ", " + cidade["nome"]
        acoes.append('        <a class="act-btn act-map" target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&amp;query=%s"><svg class="ic"><use href="#i-map"/></svg>Ver no mapa</a>'
                     % escape(urllib.request.quote(q), quote=True))
    fone = digitos_fone(card.get("telefone"))
    if fone:
        acoes.append('        <a class="act-btn act-wa" target="_blank" rel="noopener" href="https://wa.me/55%s"><svg class="ic"><use href="#i-wa"/></svg>WhatsApp</a>' % fone)
    if acoes:
        linhas.append('          <div class="p-actions">\n%s\n      </div>' % "\n".join(acoes))
    return '''    <article class="p-card" data-nome="%(nome)s" data-ramo="%(ramo)s" data-cat="%(tipo)s" data-cidade="%(cidade)s" data-uf="%(uf)s">
      <div class="p-agua" aria-hidden="true"><svg class="ic"><use href="#i-%(tipo)s"/></svg></div>
      <details class="p-det">
        <summary class="p-sum">
          <div class="p-ico%(cls_logo)s">%(ico)s</div>
          <div class="p-sum-txt"><div class="p-name">%(nome)s</div><div class="p-cat">%(catn)s <svg class="ic p-cat-ico"><use href="#i-%(tipo)s"/></svg></div></div>
          <div class="p-cond-box%(pend)s"><div class="p-cond%(pend)s">%(cond)s</div></div>
          <svg class="ic p-chev"><use href="#i-chev"/></svg>
        </summary>
        <div class="p-mais">
%(linhas)s
        </div>
      </details>
    </article>
''' % {"nome": escape(estab, quote=True), "ramo": escape((CATN[tipo] + " " + (c.get("atendimento") or "")).strip(), quote=True),
       "tipo": tipo, "cidade": escape(cidade["nome"], quote=True), "uf": escape(cidade["uf"], quote=True),
       "cls_logo": cls_logo, "ico": ico, "catn": escape(CATN[tipo]), "pend": pendente, "cond": escape(cond),
       "linhas": "\n".join(linhas)}


def montar(cards, cidades_base):
    """cidades na ordem do painel; 'TODAS' entra em todas; código desconhecido
    (região digitada no painel) vira cidade própria, no fim"""
    por_cod = {c["cod"]: dict(c) for c in cidades_base}
    ordem = [c["cod"] for c in cidades_base if c["cod"] != "TODAS"]
    extras = []
    for c in cards:
        for cod in c.get("cidades") or []:
            if cod not in por_cod and cod not in extras: extras.append(cod)
    extras.sort(key=lambda x: slug(x))
    for cod in extras: por_cod[cod] = {"cod": cod, "nome": cod, "uf": ""}
    ordem += extras
    grupos = []
    for cod in ordem:
        lista = [c for c in cards if cod in (c.get("cidades") or []) or "TODAS" in (c.get("cidades") or [])]
        if lista: grupos.append((por_cod[cod], lista))
    return grupos


def gerar(template, grupos):
    home, secoes = [], []
    for cidade, lista in grupos:
        sid = "c-" + slug(cidade["nome"])
        uf = (' <span class="uf-pill">%s</span>' % escape(cidade["uf"])) if cidade["uf"] else ""
        home.append('''      <a class="city-card" href="#%s">
        <div class="city-ico"><svg class="ic"><use href="#i-city"/></svg></div>
        <div class="city-info">
          <div class="city-name">%s%s</div>
          <div class="city-sub">%s</div>
        </div><svg class="ic chev"><use href="#i-chev"/></svg>
      </a>''' % (sid, escape(cidade["nome"]), uf, plural(len(lista), "parceiro", "parceiros")))
        secoes.append('''<!-- ==================== %s ==================== -->
<section class="view" id="%s">
  <a class="back-btn" href="#home"><svg class="ic"><use href="#i-back"/></svg>Todas as cidades</a>
  <div class="city-head">
    <h2>%s%s</h2>
    <div class="city-sub">%s</div>
  </div>
  <div class="chips"></div>
  <div class="partners">

%s
  </div>
  <div class="footnote"><b>Lembrete:</b> apresente o crachá funcional e informe o convênio com a Brazilian Nickel antes de fechar a compra. Descontos não são cumulativos com outras promoções, salvo indicação em contrário. As parcerias podem ser alteradas ou encerradas sem aviso prévio.</div>
</section>
''' % (escape(cidade["nome"].upper()), sid, escape(cidade["nome"]), uf,
       plural(len(lista), "parceiro disponível nesta cidade", "parceiros disponíveis nesta cidade"),
       "\n".join(card_html(c, cidade) for c in lista)))
    s = template
    s = re.sub(r"<!-- GERADO:CIDADES -->.*?<!-- /GERADO:CIDADES -->", lambda _: "<!-- GERADO:CIDADES -->\n" + "\n".join(home) + "\n<!-- /GERADO:CIDADES -->", s, flags=re.S)
    s = re.sub(r"<!-- GERADO:SECOES -->.*?<!-- /GERADO:SECOES -->", lambda _: "<!-- GERADO:SECOES -->\n" + "\n".join(secoes) + "<!-- /GERADO:SECOES -->", s, flags=re.S)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default=ENDPOINT, help="URL da função ou arquivo JSON")
    ap.add_argument("--template", default=os.path.join(AQUI, "template.html"))
    ap.add_argument("--cidades", default=os.path.join(AQUI, "cidades.json"))
    ap.add_argument("--saida", default=os.path.join(RAIZ, "docs", "index.html"))
    ap.add_argument("--permitir-vazio", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dado = carregar(a.entrada)
    if not dado.get("ok"):
        print("função respondeu erro:", dado.get("erro")); return 3
    cards = dado.get("cards") or []
    achados = varrer(cards)
    if achados:
        print("VARREDURA BARROU (nada gravado):"); [print("  ", x) for x in achados]; return 2
    if not cards and not a.permitir_vazio:
        print("sem cards ativos: mantive a saída atual"); return 0

    template = io.open(a.template, encoding="utf-8").read()
    cidades = json.load(io.open(a.cidades, encoding="utf-8"))
    grupos = montar(cards, cidades)
    s = gerar(template, grupos)

    # conferências da saída
    esperado = sum(len(l) for _, l in grupos)
    assert s.count('<article class="p-card"') == esperado, "contagem de cards divergiu"
    assert "GERADO:" in s and s.count("<!-- GERADO:CIDADES -->") == 1 and s.count("<!-- GERADO:SECOES -->") == 1
    injetado = s[s.find("<!-- GERADO:CIDADES -->"):s.find("<!-- /GERADO:CIDADES -->")] + s[s.find("<!-- GERADO:SECOES -->"):s.find("<!-- /GERADO:SECOES -->")]
    assert not RE_EMAIL.search(re.sub(r'src="data:[^"]*"', "", injetado)), "e-mail na saída"

    atual = io.open(a.saida, encoding="utf-8").read() if os.path.exists(a.saida) else ""
    if atual == s:
        print("sem mudança: %d cards em %d cidades" % (esperado, len(grupos))); return 0
    os.makedirs(os.path.dirname(a.saida), exist_ok=True)
    io.open(a.saida, "wb").write(s.encode("utf-8"))
    print("gerado: %s | %d cards em %d cidades | %d bytes" % (a.saida, esperado, len(grupos), len(s.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
