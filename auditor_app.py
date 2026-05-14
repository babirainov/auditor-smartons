import streamlit as st
import json, csv, time, io
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError

st.set_page_config(page_title="Auditor de Smartons", page_icon="🎙️", layout="wide")

st.markdown("""
<style>
  [data-testid="stSidebar"] { background: #1a1a18; }
  .metric-row { display: flex; gap: 12px; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .metric-box { background: #f5f5f3; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 130px; }
  .metric-box .label { font-size: 11px; font-weight: 600; color: #6b6b67; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
  .metric-box .value { font-size: 28px; font-weight: 700; color: #1a1a18; line-height: 1; }
  .metric-box .sub   { font-size: 12px; color: #9e9e9a; margin-top: 2px; }
  .pill { display: inline-block; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 20px; }
  .pill-resuelta      { background: #EAF3DE; color: #27500A; }
  .pill-no_resuelta   { background: #FCEBEB; color: #791F1F; }
  .pill-escalada      { background: #FAEEDA; color: #633806; }
  .pill-error_tecnico { background: #FBEAF0; color: #72243E; }
  .pill-abandonada    { background: #F1EFE8; color: #444441; }
  .pill-warn          { background: #FAEEDA; color: #633806; border: 1px solid #EF9F27; }
  .score-high { color: #27500A; font-weight: 700; }
  .score-mid  { color: #633806; font-weight: 700; }
  .score-low  { color: #791F1F; font-weight: 700; }
  .issue-tag  { display: inline-block; background: #f5f5f3; border: 1px solid #d3d1c7; color: #6b6b67; font-size: 11px; padding: 2px 8px; border-radius: 20px; margin: 2px; }
  .rec-item   { font-size: 13px; color: #6b6b67; padding: 4px 0 4px 12px; border-left: 2px solid #EF9F27; margin-bottom: 4px; }
  .resumo     { font-size: 14px; color: #1a1a18; line-height: 1.6; margin-bottom: 12px; }
  h1 { font-size: 24px !important; }
</style>
""", unsafe_allow_html=True)

AUDIT_SYSTEM = """Eres un auditor experto de agentes de voz para call centers. Analiza la transcripción y devuelve SOLO JSON válido, sin markdown, sin texto extra.

Formato exacto:
{"clasificacion":"resuelta|no_resuelta|escalada|error_tecnico|abandonada","score":8,"template_errors":false,"name_errors":false,"issues":["issue 1"],"resumen":"Resumen en 1-2 frases.","recomendaciones":["Recomendación 1"]}

Criterios: resuelta=objetivo cumplido, no_resuelta=no se logró, escalada=transferido a humano, error_tecnico=falla del sistema, abandonada=usuario colgó. Score 0-10. template_errors=true si hay {{variable}} sin reemplazar. name_errors=true si hay problemas con nombres."""

def api_req(url, headers, body=None):
    req = Request(url, headers=headers)
    if body:
        req.data = json.dumps(body).encode()
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        err = json.loads(e.read())
        raise Exception(f"HTTP {e.code}: {err.get('detail') or err.get('error', {}).get('message', '')}")

def fetch_agents(el_key):
    data = api_req("https://api.elevenlabs.io/v1/convai/agents?page_size=50", {"xi-api-key": el_key})
    return data.get("agents", [])

def fetch_conversations(el_key, agent_id, page_size, cursor=None):
    url = f"https://api.elevenlabs.io/v1/convai/conversations?page_size={page_size}"
    if agent_id: url += f"&agent_id={agent_id}"
    if cursor:   url += f"&cursor={cursor}"
    data = api_req(url, {"xi-api-key": el_key})
    return data.get("conversations", []), data.get("next_cursor"), data.get("has_more", False)

def fetch_transcript(el_key, conv_id):
    data = api_req(f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}", {"xi-api-key": el_key})
    return data.get("transcript", [])

def audit_claude(ant_key, transcript):
    if not transcript:
        return {"clasificacion":"abandonada","score":0,"template_errors":False,"name_errors":False,
                "issues":["Transcripción vacía"],"resumen":"Sin contenido.","recomendaciones":[]}
    tx = "\n".join(f"{'Agente' if t['role']=='agent' else 'Usuario'}: {t['message']}" for t in transcript)
    data = api_req("https://api.anthropic.com/v1/messages",
        {"Content-Type":"application/json","x-api-key":ant_key,"anthropic-version":"2023-06-01"},
        {"model":"claude-sonnet-4-5","max_tokens":1000,"system":AUDIT_SYSTEM,
         "messages":[{"role":"user","content":f"Audita esta llamada:\n\n{tx}"}]})
    text = "".join(b["text"] for b in data.get("content",[]) if b["type"]=="text")
    return json.loads(text.replace("```json","").replace("```","").strip())

def fmt_dur(s): return f"{int(s)//60}m {int(s)%60}s" if s else "—"
def fmt_dt(ts): return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "—"
def score_cls(s): return "score-high" if s>=7 else "score-mid" if s>=5 else "score-low"

def to_csv(rows):
    buf = io.StringIO(); buf.write("\ufeff")
    w = csv.DictWriter(buf, fieldnames=["id","agente","fecha","duracion","clasificacion","score","error_template","error_nombre","resumen","issues","recomendaciones"])
    w.writeheader(); [w.writerow(r) for r in rows]
    return buf.getvalue()

# Session state
for k,v in {"agents":[],"conversations":[],"selected_ids":set(),"audit_results":{},
            "transcripts":{},"loaded":False,"agent_id":"","agent_name":"Todos",
            "has_more":False,"cursor":None}.items():
    if k not in st.session_state: st.session_state[k] = v

PILL = {"resuelta":"resuelta","no_resuelta":"no resuelta","escalada":"escalada",
        "error_tecnico":"error técnico","abandonada":"abandonada"}

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎙️ Auditor de Smartons")
    st.markdown("*ElevenLabs × Claude AI*")
    st.divider()
    el_key  = st.text_input("API Key de ElevenLabs",  type="password", placeholder="xi-...")
    ant_key = st.text_input("API Key de Anthropic",   type="password", placeholder="sk-ant-...")
    st.divider()
    page_size = st.slider("Llamadas por carga", 10, 100, 30, 10)

    c1, c2 = st.columns(2)
    with c1:
        load = st.button("🔄 Cargar", use_container_width=True, type="primary")
    with c2:
        more_btn = st.button("+ Más", use_container_width=True,
                             disabled=not st.session_state.has_more)

    if load:
        if not el_key or not ant_key:
            st.error("Completa las dos API Keys.")
        else:
            with st.spinner("Conectando..."):
                try:
                    st.session_state.agents = fetch_agents(el_key)
                    convs, cur, has = fetch_conversations(el_key, st.session_state.agent_id, page_size)
                    st.session_state.conversations = convs
                    st.session_state.cursor = cur
                    st.session_state.has_more = has
                    st.session_state.selected_ids = set()
                    st.session_state.audit_results = {}
                    st.session_state.loaded = True
                    st.success(f"✓ {len(convs)} llamadas cargadas")
                except Exception as e:
                    st.error(f"Error: {e}")

    if more_btn and st.session_state.has_more:
        with st.spinner("Cargando más..."):
            try:
                more, cur, has = fetch_conversations(el_key, st.session_state.agent_id, page_size, st.session_state.cursor)
                st.session_state.conversations += more
                st.session_state.cursor = cur
                st.session_state.has_more = has
                st.rerun()
            except Exception as e:
                st.error(str(e))

    if st.session_state.agents:
        st.divider()
        st.markdown("**Filtrar por agente:**")
        opts = {"": "— Todos —"} | {a["agent_id"]: a.get("name", a["agent_id"]) for a in st.session_state.agents}
        sel = st.selectbox("Agente", list(opts.keys()), format_func=lambda x: opts[x], label_visibility="collapsed")
        if sel != st.session_state.agent_id:
            st.session_state.agent_id = sel
            st.session_state.agent_name = opts[sel]
            st.session_state.conversations = []
            st.session_state.loaded = False
            st.rerun()

    st.divider()
    st.markdown("**Lo que se evalúa:**\n- 🤖 Clasificación\n- ⭐ Score 0–10\n- `{{` Errores de template `}}`\n- 👤 Errores de nombre\n- 🔍 Issues\n- 💡 Recomendaciones")

# ── Main ──────────────────────────────────────────────────────
st.title("Auditor de Smartons")

if not st.session_state.loaded:
    st.info("👈 Ingresa las API Keys y haz clic en **Cargar** para comenzar.")
    st.stop()

convs = st.session_state.conversations
tab1, tab2 = st.tabs([f"📋 Llamadas ({len(convs)})", "📊 Resultados"])

with tab1:
    st.markdown(f"**Agente:** {st.session_state.agent_name} &nbsp;·&nbsp; **{len(convs)} conversaciones**")
    c1, c2 = st.columns([2,2])
    with c1:
        if st.button("✅ Seleccionar todas"):
            st.session_state.selected_ids = {c["conversation_id"] for c in convs}; st.rerun()
    with c2:
        if st.button("☐ Deseleccionar"):
            st.session_state.selected_ids = set(); st.rerun()
    st.divider()

    for conv in convs:
        cid = conv["conversation_id"]
        checked = cid in st.session_state.selected_ids
        ca, cb = st.columns([0.5, 9.5])
        with ca:
            v = st.checkbox("", value=checked, key=f"c_{cid}")
            if v != checked:
                if v: st.session_state.selected_ids.add(cid)
                else: st.session_state.selected_ids.discard(cid)
        with cb:
            agent_tag = f"🤖 `{conv.get('agent_id','')[:20]}`&nbsp;" if not st.session_state.agent_id else ""
            st.markdown(f"`{cid}` &nbsp; {agent_tag}🕐 {fmt_dur(conv.get('call_duration_secs'))} &nbsp; 📅 {fmt_dt(conv.get('start_time_unix_secs'))} &nbsp; 💬 {conv.get('message_count','?')} msgs", unsafe_allow_html=True)

    if st.session_state.has_more:
        st.info("Hay más llamadas. Usa **+ Más** en la barra lateral.")

    st.divider()
    n = len(st.session_state.selected_ids)
    ca, cb = st.columns([2,8])
    with ca:
        go = st.button(f"▶ Auditar {n} llamada{'s' if n!=1 else ''}", disabled=n==0, type="primary", use_container_width=True)
    with cb:
        if n > 0: st.markdown(f"*{n} llamadas seleccionadas*")

    if go and n > 0:
        ids = list(st.session_state.selected_ids)
        prog = st.progress(0, text="Iniciando...")
        st.session_state.audit_results = {}
        for i, cid in enumerate(ids):
            prog.progress(i/len(ids), text=f"Evaluando {i+1}/{len(ids)}: `{cid[:35]}...`")
            try:
                tx = fetch_transcript(el_key, cid)
                st.session_state.transcripts[cid] = tx
                r = audit_claude(ant_key, tx)
                r["agent_id"] = next((c for c in convs if c["conversation_id"]==cid), {}).get("agent_id","")
                st.session_state.audit_results[cid] = {"status":"done", **r}
            except Exception as e:
                st.session_state.audit_results[cid] = {"status":"error","error":str(e)}
            if i < len(ids)-1: time.sleep(0.4)
        prog.progress(1.0, text=f"✅ {len(ids)} llamadas evaluadas!")
        st.balloons()
        st.info("👉 Revisa los resultados en la pestaña **Resultados**.")

with tab2:
    res = {k:v for k,v in st.session_state.audit_results.items() if v.get("status")=="done"}
    if not res:
        st.info("Ninguna auditoría realizada aún."); st.stop()

    done = list(res.values())
    avg = sum(r.get("score",0) for r in done)/len(done)
    resueltas = sum(1 for r in done if r.get("clasificacion")=="resuelta")
    issues_count = sum(1 for r in done if r.get("issues"))
    tpl = sum(1 for r in done if r.get("template_errors"))

    st.markdown(f"""<div class="metric-row">
      <div class="metric-box"><div class="label">Score promedio</div><div class="value">{avg:.1f}</div><div class="sub">de 10</div></div>
      <div class="metric-box"><div class="label">Resueltas</div><div class="value">{resueltas}</div><div class="sub">de {len(done)}</div></div>
      <div class="metric-box"><div class="label">Con issues</div><div class="value">{issues_count}</div><div class="sub">llamadas</div></div>
      <div class="metric-box"><div class="label">Error template</div><div class="value">{tpl}</div><div class="sub">detectados</div></div>
    </div>""", unsafe_allow_html=True)

    FL = {"todas":"Todas","resuelta":"✅ Resueltas","no_resuelta":"❌ No resueltas",
          "escalada":"↗ Escaladas","error_tecnico":"⚠️ Error técnico","abandonada":"📵 Abandonadas"}
    ca, cb = st.columns(2)
    with ca: filt = st.selectbox("Filtrar:", list(FL.keys()), format_func=lambda x: FL[x])
    with cb:
        agents_in = list(set(r.get("agent_id","") for r in done if r.get("agent_id")))
        af = st.selectbox("Agente:", ["todos"]+agents_in, format_func=lambda x: "— Todos —" if x=="todos" else x) if len(agents_in)>1 else "todos"

    csv_rows = []
    for cid, r in res.items():
        clf = r.get("clasificacion","")
        if filt!="todas" and clf!=filt: continue
        if af!="todos" and r.get("agent_id","")!=af: continue

        conv = next((c for c in convs if c["conversation_id"]==cid), {})
        dur = fmt_dur(conv.get("call_duration_secs"))
        dt  = fmt_dt(conv.get("start_time_unix_secs"))
        score = r.get("score",0)
        warn = (''.join(['<span class="pill pill-warn">⚠ template</span> ' if r.get("template_errors") else "",
                         '<span class="pill pill-warn">⚠ nombre</span>' if r.get("name_errors") else ""]))

        with st.expander(f"Score {score}/10 — {PILL.get(clf,clf)}  •  {cid[:38]}  •  {dur}"):
            st.markdown(f"""<p class="resumo">{r.get('resumen','')}</p>
<div><span class="pill pill-{clf}">{PILL.get(clf,clf)}</span> &nbsp;
<span class="{score_cls(score)}">{score}/10</span> &nbsp; {warn} &nbsp; 🕐 {dur} &nbsp; 📅 {dt}</div>
""", unsafe_allow_html=True)
            if r.get("issues"):
                st.markdown("**Issues:**")
                st.markdown(" ".join(f'<span class="issue-tag">⚠ {i}</span>' for i in r["issues"]), unsafe_allow_html=True)
            if r.get("recomendaciones"):
                st.markdown("**Recomendaciones:**")
                [st.markdown(f'<div class="rec-item">{rc}</div>', unsafe_allow_html=True) for rc in r["recomendaciones"]]
            tx = st.session_state.transcripts.get(cid,[])
            if tx:
                with st.expander("Ver transcripción"):
                    for l in tx:
                        st.markdown(f"{'**Agente:**' if l['role']=='agent' else '*Usuario:*'} {l['message']}")

        csv_rows.append({"id":cid,"agente":r.get("agent_id",""),"fecha":dt,"duracion":dur,
            "clasificacion":clf,"score":score,
            "error_template":"sí" if r.get("template_errors") else "no",
            "error_nombre":"sí" if r.get("name_errors") else "no",
            "resumen":r.get("resumen",""),
            "issues":" | ".join(r.get("issues",[])),
            "recomendaciones":" | ".join(r.get("recomendaciones",[]))})

    if csv_rows:
        st.divider()
        st.download_button("⬇️ Exportar CSV", to_csv(csv_rows),
            f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", type="primary")
