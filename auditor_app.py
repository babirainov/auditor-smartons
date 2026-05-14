import streamlit as st
import json, csv, time, io
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ── Página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Auditor de Smartons",
    page_icon="🎙️",
    layout="wide"
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background: #1a1a18; }
  .metric-row { display: flex; gap: 12px; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .metric-box { background: #f5f5f3; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 130px; }
  .metric-box .label { font-size: 11px; font-weight: 600; color: #6b6b67; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
  .metric-box .value { font-size: 28px; font-weight: 700; color: #1a1a18; line-height: 1; }
  .metric-box .sub   { font-size: 12px; color: #9e9e9a; margin-top: 2px; }
  .pill { display: inline-block; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 20px; }
  .pill-resolvida     { background: #EAF3DE; color: #27500A; }
  .pill-nao_resolvida { background: #FCEBEB; color: #791F1F; }
  .pill-escalada      { background: #FAEEDA; color: #633806; }
  .pill-erro_tecnico  { background: #FBEAF0; color: #72243E; }
  .pill-abandonada    { background: #F1EFE8; color: #444441; }
  .pill-warn          { background: #FAEEDA; color: #633806; border: 1px solid #EF9F27; }
  .score-high { color: #27500A; font-weight: 700; }
  .score-mid  { color: #633806; font-weight: 700; }
  .score-low  { color: #791F1F; font-weight: 700; }
  .issue-tag { display: inline-block; background: #f5f5f3; border: 1px solid #d3d1c7; color: #6b6b67; font-size: 11px; padding: 2px 8px; border-radius: 20px; margin: 2px; }
  .rec-item { font-size: 13px; color: #6b6b67; padding: 4px 0 4px 12px; border-left: 2px solid #EF9F27; margin-bottom: 4px; }
  .resumo { font-size: 14px; color: #1a1a18; line-height: 1.6; margin-bottom: 12px; }
  div[data-testid="stCheckbox"] label { font-size: 13px; }
  .stButton > button { border-radius: 8px; }
  .stButton > button[kind="primary"] { background: #BA7517; border: none; }
  .stButton > button[kind="primary"]:hover { background: #854F0B; border: none; }
  h1 { font-size: 24px !important; }
</style>
""", unsafe_allow_html=True)

# ── Sistema de auditoria ──────────────────────────────────────
AUDIT_SYSTEM = """Você é um auditor especialista em agentes de voz. Analise a transcrição e retorne SOMENTE JSON válido, sem markdown, sem texto extra.

Formato exato:
{"classificacao":"resolvida|nao_resolvida|escalada|erro_tecnico|abandonada","score":8,"template_errors":false,"name_errors":false,"issues":["issue 1"],"resumo":"Resumo em 1-2 frases.","recomendacoes":["Recomendação 1"]}

Critérios: resolvida=objetivo cumprido, nao_resolvida=não resolvido, escalada=transferido para humano, erro_tecnico=falha do sistema, abandonada=usuário desligou. Score 0-10. template_errors=true se houver {{variavel}} não substituída. name_errors=true se nome incorreto/duplo/estranho."""

def api_request(url, headers, body=None):
    req = Request(url, headers=headers)
    if body:
        req.data = json.dumps(body).encode()
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        err = json.loads(e.read())
        raise Exception(f"HTTP {e.code}: {err.get('detail') or err.get('error', {}).get('message', '')}")

def fetch_conversations(el_key, agent_id, max_calls):
    url = f"https://api.elevenlabs.io/v1/convai/conversations?page_size={max_calls}"
    if agent_id:
        url += f"&agent_id={agent_id}"
    data = api_request(url, {"xi-api-key": el_key})
    return data.get("conversations", [])

def fetch_transcript(el_key, conv_id):
    url = f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}"
    data = api_request(url, {"xi-api-key": el_key})
    return data.get("transcript", [])

def audit_with_claude(ant_key, transcript):
    if not transcript:
        return {"classificacao": "abandonada", "score": 0, "template_errors": False,
                "name_errors": False, "issues": ["Transcrição vazia"],
                "resumo": "Sem conteúdo.", "recomendacoes": []}
    tx_text = "\n".join(
        f"{'Agente' if t['role'] == 'agent' else 'Usuário'}: {t['message']}"
        for t in transcript
    )
    body = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1000,
        "system": AUDIT_SYSTEM,
        "messages": [{"role": "user", "content": f"Audite esta ligação:\n\n{tx_text}"}]
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ant_key,
        "anthropic-version": "2023-06-01"
    }
    data = api_request("https://api.anthropic.com/v1/messages", headers, body)
    text = "".join(b["text"] for b in data.get("content", []) if b["type"] == "text")
    clean = text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

def fmt_dur(secs):
    if not secs:
        return "—"
    return f"{int(secs)//60}m {int(secs)%60}s"

def fmt_date(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")

def score_color(s):
    if s >= 7: return "score-high"
    if s >= 5: return "score-mid"
    return "score-low"

def results_to_csv(results):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel
    fieldnames = ["id", "data", "duracao", "classificacao", "score",
                  "erro_template", "erro_nome", "resumo", "issues", "recomendacoes"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    return buf.getvalue()

# ── Session state ─────────────────────────────────────────────
for key, default in {
    "conversations": [],
    "selected_ids": set(),
    "audit_results": {},
    "transcripts": {},
    "loaded": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎙️ Auditor de Smartons")
    st.markdown("*ElevenLabs × Claude AI*")
    st.divider()

    el_key = st.text_input("API Key do ElevenLabs", type="password", placeholder="xi-...")
    ant_key = st.text_input("API Key da Anthropic", type="password", placeholder="sk-ant-...")
    agent_id = st.text_input("Agent ID (opcional)", placeholder="Deixe vazio para todos")
    max_calls = st.slider("Máximo de ligações", 5, 100, 30, 5)

    st.divider()
    if st.button("🔄 Carregar ligações", use_container_width=True, type="primary"):
        if not el_key or not ant_key:
            st.error("Preencha as duas API Keys.")
        else:
            with st.spinner("Conectando ao ElevenLabs..."):
                try:
                    convs = fetch_conversations(el_key, agent_id, max_calls)
                    st.session_state.conversations = convs
                    st.session_state.selected_ids = set()
                    st.session_state.audit_results = {}
                    st.session_state.loaded = True
                    st.success(f"✓ {len(convs)} conversas carregadas!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    st.divider()
    st.markdown("""
**O que é avaliado:**
- 🤖 Classificação do resultado
- ⭐ Score 0–10
- `{{` Erros de template `}}`
- 👤 Erros de nome
- 🔍 Issues detectados
- 💡 Recomendações
    """)

# ── Main ──────────────────────────────────────────────────────
st.title("Auditor de Smartons")

if not st.session_state.loaded:
    st.info("👈 Configure as API Keys na barra lateral e clique em **Carregar ligações** para começar.")
    st.stop()

convs = st.session_state.conversations
if not convs:
    st.warning("Nenhuma conversa encontrada.")
    st.stop()

# ── Abas ──────────────────────────────────────────────────────
tab1, tab2 = st.tabs([f"📋 Ligações ({len(convs)})", "📊 Resultados"])

# ── TAB 1: Lista de ligações ──────────────────────────────────
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**{len(convs)} conversas disponíveis** — selecione as que deseja auditar:")
    with col2:
        if st.button("Selecionar todas"):
            st.session_state.selected_ids = {c["conversation_id"] for c in convs}
            st.rerun()

    for conv in convs:
        cid = conv["conversation_id"]
        dur = fmt_dur(conv.get("call_duration_secs"))
        dt = fmt_date(conv.get("start_time_unix_secs"))
        msgs = conv.get("message_count", "?")
        checked = cid in st.session_state.selected_ids

        col_chk, col_info = st.columns([0.5, 9.5])
        with col_chk:
            val = st.checkbox("", value=checked, key=f"chk_{cid}")
            if val != checked:
                if val:
                    st.session_state.selected_ids.add(cid)
                else:
                    st.session_state.selected_ids.discard(cid)
        with col_info:
            st.markdown(
                f"`{cid}` &nbsp; 🕐 {dur} &nbsp; 📅 {dt} &nbsp; 💬 {msgs} msgs",
                unsafe_allow_html=True
            )

    st.divider()
    n_sel = len(st.session_state.selected_ids)
    col_btn, col_info = st.columns([2, 8])
    with col_btn:
        audit_clicked = st.button(
            f"▶ Auditar {n_sel} ligaç{'ões' if n_sel != 1 else 'ão'}",
            disabled=n_sel == 0,
            type="primary",
            use_container_width=True
        )
    with col_info:
        if n_sel > 0:
            st.markdown(f"*{n_sel} ligações selecionadas*")

    if audit_clicked and n_sel > 0:
        ids = list(st.session_state.selected_ids)
        progress_bar = st.progress(0, text="Iniciando auditoria...")
        st.session_state.audit_results = {}

        for i, cid in enumerate(ids):
            conv = next((c for c in convs if c["conversation_id"] == cid), {})
            pct = i / len(ids)
            progress_bar.progress(pct, text=f"Auditando {i+1}/{len(ids)}: `{cid[:30]}...`")
            try:
                tx = fetch_transcript(el_key, cid)
                st.session_state.transcripts[cid] = tx
                result = audit_with_claude(ant_key, tx)
                st.session_state.audit_results[cid] = {"status": "done", **result}
            except Exception as e:
                st.session_state.audit_results[cid] = {"status": "error", "error": str(e)}
            if i < len(ids) - 1:
                time.sleep(0.4)

        progress_bar.progress(1.0, text=f"✅ {len(ids)} ligações avaliadas!")
        st.balloons()
        st.info("👉 Veja os resultados na aba **Resultados**.")

# ── TAB 2: Resultados ─────────────────────────────────────────
with tab2:
    results = {k: v for k, v in st.session_state.audit_results.items() if v.get("status") == "done"}

    if not results:
        st.info("Nenhuma auditoria realizada ainda. Selecione ligações e clique em **Auditar**.")
        st.stop()

    # Métricas
    done = list(results.values())
    avg_score = sum(r.get("score", 0) for r in done) / len(done)
    resolvidas = sum(1 for r in done if r.get("classificacao") == "resolvida")
    with_issues = sum(1 for r in done if r.get("issues"))
    tpl_errors = sum(1 for r in done if r.get("template_errors"))

    st.markdown(f"""
<div class="metric-row">
  <div class="metric-box"><div class="label">Score médio</div><div class="value">{avg_score:.1f}</div><div class="sub">de 10</div></div>
  <div class="metric-box"><div class="label">Resolvidas</div><div class="value">{resolvidas}</div><div class="sub">de {len(done)}</div></div>
  <div class="metric-box"><div class="label">Com issues</div><div class="value">{with_issues}</div><div class="sub">ligações</div></div>
  <div class="metric-box"><div class="label">Erro template</div><div class="value">{tpl_errors}</div><div class="sub">detectados</div></div>
</div>
""", unsafe_allow_html=True)

    # Filtro
    LABELS = {
        "todas": "Todas",
        "resolvida": "✅ Resolvidas",
        "nao_resolvida": "❌ Não resolvidas",
        "escalada": "↗ Escaladas",
        "erro_tecnico": "⚠️ Erro técnico",
        "abandonada": "📵 Abandonadas"
    }
    filter_opt = st.selectbox("Filtrar por:", list(LABELS.keys()), format_func=lambda x: LABELS[x])

    # Cards de resultado
    PILL_LABELS = {
        "resolvida": "resolvida", "nao_resolvida": "não resolvida",
        "escalada": "escalada", "erro_tecnico": "erro técnico", "abandonada": "abandonada"
    }

    csv_rows = []
    shown = 0
    for cid, result in results.items():
        clf = result.get("classificacao", "")
        if filter_opt != "todas" and clf != filter_opt:
            continue
        shown += 1

        conv = next((c for c in convs if c["conversation_id"] == cid), {})
        dur = fmt_dur(conv.get("call_duration_secs"))
        dt = fmt_date(conv.get("start_time_unix_secs"))
        score = result.get("score", 0)
        sc = score_color(score)

        warn_html = ""
        if result.get("template_errors"):
            warn_html += '<span class="pill pill-warn">⚠ template</span> '
        if result.get("name_errors"):
            warn_html += '<span class="pill pill-warn">⚠ nome</span>'

        with st.expander(
            f"Score {score}/10 — {PILL_LABELS.get(clf, clf)}  •  {cid[:40]}  •  {dur}",
            expanded=False
        ):
            st.markdown(f"""
<p class="resumo">{result.get('resumo', '')}</p>
<div>
  <span class="pill pill-{clf}">{PILL_LABELS.get(clf, clf)}</span> &nbsp;
  <span class="{sc}">{score}/10</span> &nbsp; {warn_html}
  &nbsp; 🕐 {dur} &nbsp; 📅 {dt}
</div>
""", unsafe_allow_html=True)

            issues = result.get("issues", [])
            if issues:
                st.markdown("**Issues detectados:**")
                st.markdown(" ".join(f'<span class="issue-tag">⚠ {i}</span>' for i in issues), unsafe_allow_html=True)

            recs = result.get("recomendacoes", [])
            if recs:
                st.markdown("**Recomendações:**")
                for rec in recs:
                    st.markdown(f'<div class="rec-item">{rec}</div>', unsafe_allow_html=True)

            tx = st.session_state.transcripts.get(cid, [])
            if tx:
                with st.expander("Ver transcrição"):
                    for line in tx:
                        role = "**Agente:**" if line["role"] == "agent" else "*Usuário:*"
                        st.markdown(f"{role} {line['message']}")

        csv_rows.append({
            "id": cid,
            "data": dt,
            "duracao": dur,
            "classificacao": clf,
            "score": score,
            "erro_template": "sim" if result.get("template_errors") else "não",
            "erro_nome": "sim" if result.get("name_errors") else "não",
            "resumo": result.get("resumo", ""),
            "issues": " | ".join(result.get("issues", [])),
            "recomendacoes": " | ".join(result.get("recomendacoes", []))
        })

    if shown == 0:
        st.info("Nenhuma ligação com esse filtro.")

    # Export
    if csv_rows:
        st.divider()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="⬇️ Exportar CSV",
            data=results_to_csv(csv_rows),
            file_name=f"auditoria_smartons_{ts}.csv",
            mime="text/csv",
            type="primary"
        )
