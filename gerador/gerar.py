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
# 🔴 TODO CARD TEM "COMO USAR" (pedido dele, 17/09): sem etapas escritas, vale o
# padrão. Card sem a seção fazia o colaborador achar que não havia regra, e a
# regra existe: confirmar no balcão. O MESMO texto do painel (ETAPAS_PADRAO).
ETAPAS_PADRAO = ["Apresente o crachá funcional e informe o convênio com a Brazilian Nickel.",
                 "Confirme a condição vigente com o responsável do estabelecimento antes de usufruir do benefício."]
# 🔴 endereço é OPCIONAL desde 16/09 (parceria com rede de unidades não tem um
# endereço para listar): vazio, o card diz isto, e não tem botão de mapa.
ENDERECO_PADRAO = "Consultar endereço na internet"    # o mesmo texto do painel (ENDERECO_PADRAO)
# 🔴 no card, o atendimento fala a língua de quem usa (16/09): o MESMO mapa do painel
ATENDIMENTO_NO_CARD = {"Dos dois jeitos": "Online ou presencial"}


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


def telefone_bonito(v):
    """o número do jeito que se lê em voz alta, e não colado: quem vai DIGITAR
       num telefone precisa conseguir ler em pedaços. A MESMA regra do painel."""
    n = re.sub(r"\D", "", str(v or ""))
    if len(n) in (12, 13) and n.startswith("55"):
        n = n[2:]
    if len(n) == 11:
        return "(%s) %s-%s" % (n[:2], n[2:7], n[7:])
    if len(n) == 10:
        return "(%s) %s-%s" % (n[:2], n[2:6], n[6:])
    return str(v or "").strip()


def lista_de_enderecos(card):
    """a lista de endereços do card, [{endereco, rotulo}]; card antigo só tem
       `endereco` (texto) e vira lista de um. A MESMA regra de `limparEnderecos`
       do painel: só entra quem tem endereço, com os espaços aparados."""
    ends = card.get("enderecos")
    if not isinstance(ends, list):
        e = (card.get("endereco") or "").strip()
        ends = [{"endereco": e, "rotulo": "", "cidade": ""}] if e else []
    out = []
    for e in ends:
        if isinstance(e, str): e = {"endereco": e, "rotulo": "", "cidade": ""}
        if not isinstance(e, dict): continue
        end = re.sub(r"\s+", " ", str(e.get("endereco") or "")).strip()
        rot = re.sub(r"\s+", " ", str(e.get("rotulo") or "")).strip()
        cid = re.sub(r"\s+", " ", str(e.get("cidade") or "")).strip()
        if end: out.append({"endereco": end, "rotulo": rot, "cidade": cid})
    return out


def lista_de_etapas(card):
    """🔴 as etapas do "como utilizar" (17/09), limpas pela MESMA regra do
    formulário e do painel: oito no máximo, 140 letras cada, sem vazias."""
    et = card.get("comoUsar")
    if isinstance(et, str): et = [et] if et.strip() else []
    if not isinstance(et, list): return []
    out = []
    for x in et:
        v = re.sub(r"\s+", " ", str(x or "")).strip()[:140]
        if v: out.append(v)
    return out[:8]


def d(pt, en):
    """🔴 O PAR DE TEXTOS (17/09): os dois vivem na página e o idioma escolhido
    esconde um deles por CSS. Assim a página continua funcionando sem script, e
    em português, que é o idioma do documento."""
    return '<span class="i18 lg-pt">%s</span><span class="i18 lg-en">%s</span>' % (pt, en)


def nome_bi(cidade):
    """🔴 só as ABRANGÊNCIAS têm nome em inglês (17/09): "Belo Horizonte" não se
    traduz, "Brasil (todo o país)" sim, porque ali o nome é um rótulo nosso."""
    pt = escape(cidade["nome"])
    en = cidade.get("nome_en")
    return d(pt, escape(en)) if en else pt


def card_html(c, cidade):
    tipo = c.get("tipo") if c.get("tipo") in CATN else "outros"
    card = c.get("card") or {}
    estab = (c.get("estab") or "").strip()
    titulo = (card.get("titulo") or "").strip()
    pendente = "" if titulo else " pendente"
    cond = escape(titulo) if titulo else d("Condições a confirmar", "Terms to be confirmed")
    cls_logo, ico = icone_html(card, tipo)
    linhas = []
    def linha(simbolo, txt, href=None, bruto=None):
        """`bruto` já vem com marcação (o par de idiomas); `txt` é texto puro"""
        if bruto:
            linhas.append('          <div class="d-row"><svg class="ic"><use href="#i-%s"/></svg><span class="d-txt">%s</span></div>' % (simbolo, bruto))
            return
        if not txt: return
        if href:
            # 🔴 ENDEREÇO É LINK (16/09): a própria linha abre o mapa; saiu o botão
            linhas.append('          <div class="d-row"><svg class="ic"><use href="#i-%s"/></svg><a class="d-txt" href="%s" target="_blank" rel="noopener" title="Abrir no Google Maps">%s</a></div>'
                          % (simbolo, escape(href, quote=True), escape(txt)))
        else:
            linhas.append('          <div class="d-row"><svg class="ic"><use href="#i-%s"/></svg><span class="d-txt">%s</span></div>' % (simbolo, escape(txt)))
    linha("tag", (card.get("detalhe") or "").strip())
    at = (c.get("atendimento") or "").strip()
    linha("shop", ATENDIMENTO_NO_CARD.get(at, at))
    # 🔴 VÁRIOS ENDEREÇOS (16/09): uma linha por endereço, com o nome curto na
    # frente para casar com o botão; sem nenhum, o texto padrão (o MESMO do painel)
    # 🔴 ENDEREÇO DENTRO DA CIDADE (16/09): esta seção é UMA cidade, então só os
    # endereços dela entram; endereço sem cidade (dado antigo) entra em todas.
    ends = [e for e in lista_de_enderecos(card) if not e["cidade"] or e["cidade"] == cidade["cod"]]
    if not ends: linha("pin", None, None, d("Consultar endereço na internet", "Check the address online"))
    for e in ends:
        end = e["endereco"]
        q = end if slug(cidade["nome"]) in slug(end) else end + ", " + cidade["nome"]
        linha("pin", end, "https://www.google.com/maps/search/?api=1&query=" + urllib.request.quote(q))
    # sem horário no formulário nem no card, o texto padrão (o MESMO do painel)
    hora = (card.get("horario") or "").strip()
    if hora: linha("clock", hora)
    else: linha("clock", None, None, d("Consultar horário de funcionamento", "Check the opening hours"))
    # 🔴 O NÚMERO APARECE SEMPRE (16/09), como o endereço e o horário. Antes ele
    # só existia dentro do botão de WhatsApp, então quem não usa WhatsApp, ou
    # está no computador, não tinha o número: o card guardava e não mostrava.
    # 🔴 WHATSAPP AO LADO DO NÚMERO (16/09): o link é só o ícone, na mesma linha;
    # saiu o botão de baixo. Continua só quando o painel marcou que é WhatsApp:
    # telefone fixo virava uma conversa que não existe.
    fone_txt = telefone_bonito(card.get("telefone"))
    fone = digitos_fone(card.get("telefone"))
    if fone_txt:
        wa = ('<a class="d-wa" target="_blank" rel="noopener" title="Abrir conversa no WhatsApp" aria-label="WhatsApp" href="https://wa.me/55%s"><svg class="ic"><use href="#i-wa"/></svg></a>' % fone) if (fone and card.get("whatsapp")) else ""
        linhas.append('          <div class="d-row"><svg class="ic"><use href="#i-phone"/></svg><span class="d-txt">%s%s</span></div>' % (escape(fone_txt), wa))
    # 🔴 COMO USAR O BENEFÍCIO (17/09): bloco próprio, numerado, e SEMPRE O ÚLTIMO
    # do card (pedido dele). Ele responde a outra pergunta ("o que eu faço no
    # balcão?") e fecha o card; o telefone é informação do lugar e fica junto do
    # endereço e do horário, logo acima.
    etapas = lista_de_etapas(card) or ETAPAS_PADRAO
    if etapas:
        linhas.append('          <div class="p-como"><div class="p-como-t">%s</div><ol class="p-como-l">%s</ol></div>'
                      % (d("Como usar o benefício", "How to use it"),
                         "".join("<li>%s</li>" % escape(e) for e in etapas)))
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
       "cls_logo": cls_logo, "ico": ico, "catn": escape(CATN[tipo]), "pend": pendente, "cond": cond,
       "linhas": "\n".join(linhas)}


def montar(cards, cidades_base):
    """cidades na ordem do painel; 'TODAS' entra em todas; código desconhecido
    (região digitada no painel) vira cidade própria, no fim"""
    por_cod = {c["cod"]: dict(c) for c in cidades_base}
    # 🔴 ABRANGÊNCIAS AMPLAS (17/09) vão para o FIM da lista: "Brasil" não é uma
    # cidade onde alguém mora, é o recorte de quem vale em qualquer lugar. Quem
    # abre o app procura a própria cidade primeiro.
    comuns = [c["cod"] for c in cidades_base if c["cod"] != "TODAS" and not c.get("ampla")]
    # as que existem no cadastro: cidade digitada no painel não entra aqui, e
    # não deve mesmo, porque ela só existe por causa de um card
    fixas = set(comuns)
    amplas = [c["cod"] for c in cidades_base if c.get("ampla")]
    ordem = comuns
    extras = []
    for c in cards:
        for cod in c.get("cidades") or []:
            if cod not in por_cod and cod not in extras: extras.append(cod)
    extras.sort(key=lambda x: slug(x))
    # 🔴 A CIDADE DIGITADA TEM PAÍS (17/09): ele vem no card, em `paisesCidades`,
    # e é o que decide se um benefício "válido em todo o Brasil" entra nela. Sem
    # país a cidade ficava de fora dessas contas, em silêncio.
    pais_de = {}
    for c in cards:
        for cod, pais in ((c.get("card") or {}).get("paisesCidades") or {}).items():
            p = str(pais or "").strip().upper()
            if len(p) == 2 and cod not in pais_de: pais_de[cod] = p
    for cod in extras:
        por_cod[cod] = {"cod": cod, "nome": cod, "uf": "", "pais": pais_de.get(cod, "")}
    ordem += extras + amplas
    grupos = []

    def vale_na_cidade(c, cidade):
        """🔴 ABRANGÊNCIA AMPLA ENTRA NAS CIDADES DO ESCOPO (17/09): quem marca
        "Brasil" quer o card à vista de quem abre Belo Horizonte, e não escondido
        numa seção que ninguém procura. "Global" entra em todas; "Canadá" só nas
        cidades canadenses, que hoje não existem, então fica só na seção dele."""
        cods = c.get("cidades") or []
        if cidade["cod"] in cods: return True
        if "TODAS" in cods: return True                      # dado anterior a 16/09
        if cidade.get("ampla"): return False                 # a seção da abrangência é exata
        for cod in cods:
            amp = por_cod.get(cod)
            if not amp or not amp.get("ampla"): continue
            if not amp.get("pais"): return True              # Global: qualquer lugar
            if amp.get("pais") == cidade.get("pais"): return True
        return False

    for cod in ordem:
        cidade = por_cod[cod]
        lista = [c for c in cards if vale_na_cidade(c, cidade)]
        # 🔴 CIDADE FIXA ENTRA MESMO VAZIA (19/09, pedido dele por causa de
        # Toronto): quem é de lá precisa achar a própria cidade e LER que ainda
        # não há parceria, em vez de não achar nada e concluir que o Clube não é
        # para ele. Abrangência vazia continua fora: ela não é lugar de ninguém.
        if lista or (cod in por_cod and not cidade.get("ampla") and cod in fixas):
            grupos.append((cidade, lista))
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
      </a>''' % (sid, nome_bi(cidade), uf, d(plural(len(lista), "parceiro", "parceiros"),
                     plural(len(lista), "partner", "partners"))))
        secoes.append('''<!-- ==================== %s ==================== -->
<section class="view" id="%s">
  <a class="back-btn" href="#home"><svg class="ic"><use href="#i-back"/></svg>%s</a>
  <div class="city-head">
    <h2>%s%s</h2>
    <div class="city-sub">%s</div>
  </div>
  <div class="chips"></div>
  <div class="partners">

%s
  </div>
  %s
  <div class="footnote">%s</div>
</section>
''' % (escape(cidade["nome"].upper()), sid,
       d("Todas as localidades", "All locations"),
       nome_bi(cidade), uf,
       d(plural(len(lista), "parceiro disponível nesta localidade", "parceiros disponíveis nesta localidade"),
         plural(len(lista), "partner available in this location", "partners available in this location")),
       "\n".join(card_html(c, cidade) for c in lista),
       ("" if lista else '<div class="vazio-cidade">%s</div>' % d(
           "Ainda não há parceria cadastrada aqui. Conhece um lugar que valha a pena? Indique pelo formulário do Clube.",
           "There are no partners here yet. Know a place worth adding? Send it through the Club form.")),
       d("<b>Lembrete:</b> apresente o crachá funcional e informe o convênio com a Brazilian Nickel antes de concluir a compra. As condições não são cumulativas com outras promoções, salvo indicação em contrário, e podem ser alteradas ou encerradas sem aviso prévio.",
         "<b>Reminder:</b> present your employee badge and mention the Brazilian Nickel agreement before completing the purchase. Terms are not cumulative with other promotions unless stated otherwise, and may change or end without prior notice.")))
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
