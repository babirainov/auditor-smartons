import streamlit as st
import json, csv, time, io, base64
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
  .resumo { font-size: 14px; line-height: 1.6; margin-bottom: 12px; }
  h1 { font-size: 24px !important; }
  .context-box { background: #FAEEDA; border-left: 3px solid #EF9F27; border-radius: 6px; padding: 10px 14px; font-size: 12px; color: #633806; margin-bottom: 8px; }
  .voice-section { background: #f0f4ff; border-left: 3px solid #5b7fff; border-radius: 6px; padding: 12px 14px; margin-top: 12px; }
  .voice-section-title { font-size: 12px; font-weight: 700; color: #2a3d8f; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
  .voice-metric { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; border-bottom: 0.5px solid #dde4ff; }
  .voice-metric:last-child { border: none; }
  .voice-metric .vm-label { color: #6b6b67; }
  .voice-metric .vm-val { font-weight: 600; color: #1a1a18; }
  .vm-high { color: #27500A !important; }
  .vm-mid  { color: #633806 !important; }
  .vm-low  { color: #791F1F !important; }
  .audio-badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; background: #e6f0ff; color: #2a3d8f; margin-left: 6px; }
</style>
""", unsafe_allow_html=True)

BASE_AUDIT_SYSTEM = """Eres un auditor experto de agentes de voz para call centers LATAM. Analiza la transcripción y devuelve SOLO JSON válido, sin markdown, sin texto extra.

Formato exacto:
{{"clasificacion":"resuelta|no_resuelta|escalada|error_tecnico|abandonada","score":8,"template_errors":false,"name_errors":false,"issues":["issue 1"],"resumen":"Resumen en 1-2 frases.","recomendaciones":["Recomendación 1"]}}

Criterios base: resuelta=objetivo cumplido, no_resuelta=no se logró, escalada=transferido a humano, error_tecnico=falla del sistema, abandonada=usuario colgó. Score 0-10. template_errors=true si hay {{{{variable}}}} sin reemplazar. name_errors=true si hay problemas con nombres.

{context_block}"""

AUDIO_AUDIT_SYSTEM = """Eres un auditor experto de calidad de voz para agentes de IA en call centers LATAM. Analiza el audio de la llamada y devuelve SOLO JSON válido, sin markdown, sin texto extra.

Evalúa estas métricas de voz:
1. generative_voice_score (1-10): Penaliza artefactos de voz artificial, aceleraciones robóticas, cambios bruscos de velocidad, o slips al español castillano/Spain Spanish en lugar de español LATAM.
2. conversational_flow_score (1-10): Evalúa si la latencia o delays en el procesamiento afectaron la naturalidad de la conversación.
3. interruption_score (1-10): Penaliza al agente por cortar al usuario en medio de una frase. Perdona interrupciones causadas por ruido de fondo.
4. background_noise_level: "limpio", "leve", "moderado" o "alto"
5. noise_confused_with_voice (boolean): true si el agente respondió a ruido de fondo confundiéndolo con la voz del usuario.
6. premature_termination (boolean): true si el agente desconectó antes de que el usuario terminara su intención.
7. voice_qa_reasoning: String de 2-3 frases justificando los scores de voz.

Formato exacto:
{{"generative_voice_score":8,"conversational_flow_score":7,"interruption_score":9,"background_noise_level":"limpio","noise_confused_with_voice":false,"premature_termination":false,"voice_qa_reasoning":"El agente mantuvo una voz natural durante toda la llamada..."}}"""

def build_system_prompt(agent_context):
    if agent_context and agent_context.strip():
        context_block = f"OBJETIVO ESPECÍFICO DE ESTE AGENTE (úsalo como criterio principal para el score y clasificación):\n{agent_context.strip()}"
    else:
        context_block = ""
    return BASE_AUDIT_SYSTEM.format(context_block=context_block)

def get_secret(key):
    try:
        return st.secrets[key]
    except:
        return ""

EL_KEY_DEFAULT  = get_secret("EL_KEY")
ANT_KEY_DEFAULT = get_secret("ANT_KEY")

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

def api_req_raw(url, headers):
    """Fetch raw bytes (for audio)."""
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=60) as r:
            return r.read()
    except HTTPError as e:
        raise Exception(f"HTTP {e.code} fetching audio")

def fetch_agents(el_key):
    data = api_req("https://api.elevenlabs.io/v1/convai/agents?page_size=50", {"xi-api-key": el_key})
    return data.get("agents", [])

def fetch_agent_prompt(el_key, agent_id):
    try:
        data = api_req(f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}", {"xi-api-key": el_key})
        return data.get("conversation_config", {}).get("agent", {}).get("prompt", {}).get("prompt", "")
    except:
        return ""

def fetch_conversations(el_key, agent_id, page_size, cursor=None):
    url = f"https://api.elevenlabs.io/v1/convai/conversations?page_size={page_size}"
    if agent_id: url += f"&agent_id={agent_id}"
    if cursor:   url += f"&cursor={cursor}"
    data = api_req(url, {"xi-api-key": el_key})
    return data.get("conversations", []), data.get("next_cursor"), data.get("has_more", False)

def fetch_transcript(el_key, conv_id):
    data = api_req(f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}", {"xi-api-key": el_key})
    return data.get("transcript", [])

def fetch_audio(el_key, conv_id):
    """Fetch conversation audio as base64 MP3."""
    try:
        raw = api_req_raw(
            f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}/audio",
            {"xi-api-key": el_key}
        )
        return base64.standard_b64encode(raw).decode("utf-8")
    except:
        return None

def audit_claude(ant_key, transcript, agent_context=""):
    if not transcript:
        return {"clasificacion":"abandonada","score":0,"template_errors":False,"name_errors":False,
                "issues":["Transcripción vacía"],"resumen":"Sin contenido.","recomendaciones":[]}
    tx = "\n".join(f"{'Agente' if t['role']=='agent' else 'Usuario'}: {t['message']}" for t in transcript)
    system = build_system_prompt(agent_context)
    data = api_req("https://api.anthropic.com/v1/messages",
        {"Content-Type":"application/json","x-api-key":ant_key,"anthropic-version":"2023-06-01"},
        {"model":"claude-sonnet-4-5","max_tokens":1000,"system":system,
         "messages":[{"role":"user","content":f"Audita esta llamada:\n\n{tx}"}]})
    text = "".join(b["text"] for b in data.get("content",[]) if b["type"]=="text")
    return json.loads(text.replace("```json","").replace("```","").strip())

def audit_audio_claude(ant_key, audio_b64):
    """Send audio to Claude for voice quality analysis."""
    if not audio_b64:
        return None
    try:
        data = api_req("https://api.anthropic.com/v1/messages",
            {"Content-Type":"application/json","x-api-key":ant_key,"anthropic-version":"2023-06-01"},
            {"model":"claude-sonnet-4-5","max_tokens":800,"system":AUDIO_AUDIT_SYSTEM,
             "messages":[{"role":"user","content":[
                 {"type":"text","text":"Analiza la calidad de voz de esta llamada:"},
                 {"type":"document","source":{"type":"base64","media_type":"audio/mpeg","data":audio_b64}}
             ]}]})
        text = "".join(b["text"] for b in data.get("content",[]) if b["type"]=="text")
        return json.loads(text.replace("```json","").replace("```","").strip())
    except Exception as e:
        return {"error": str(e)}

def fmt_dur(s): return f"{int(s)//60}m {int(s)%60}s" if s else "—"
def fmt_dt(ts): return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "—"
def score_cls(s): return "score-high" if s>=7 else "score-mid" if s>=5 else "score-low"

def to_csv(rows):
    buf = io.StringIO(); buf.write("\ufeff")
    fields = ["id","agente","fecha","duracion","clasificacion","score",
              "error_template","error_nombre","resumen","issues","recomendaciones",
              "voz_generativa","flujo_conversacional","interrupciones","ruido_fondo",
              "ruido_confundido_voz","terminacion_prematura","qa_voz"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows: w.writerow(r)
    return buf.getvalue()

# ── Session state ─────────────────────────────────────────────
for k,v in {"agents":[],"conversations":[],"selected_ids":set(),"audit_results":{},
            "transcripts":{},"loaded":False,"agent_id":"","agent_name":"Todos",
            "has_more":False,"cursor":None,"agent_context":{},"analyze_audio":True}.items():
    if k not in st.session_state: st.session_state[k] = v

PILL = {"resuelta":"resuelta","no_resuelta":"no resuelta","escalada":"escalada",
        "error_tecnico":"error técnico","abandonada":"abandonada"}

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎙️ Auditor de Smartons")
    st.markdown("*ElevenLabs × Claude AI*")
    st.divider()

    if EL_KEY_DEFAULT and ANT_KEY_DEFAULT:
        el_key  = EL_KEY_DEFAULT
        ant_key = ANT_KEY_DEFAULT
        st.success("🔐 API Keys configuradas")
    else:
        el_key  = st.text_input("API Key de ElevenLabs", type="password", placeholder="xi-...")
        ant_key = st.text_input("API Key de Anthropic",  type="password", placeholder="sk-ant-...")

    st.divider()
    page_size = st.slider("Llamadas por carga", 10, 100, 30, 10)

    # Toggle análisis de audio
    analyze_audio = st.toggle("🎵 Analizar audio (voz)", value=st.session_state.analyze_audio,
                               help="Analiza calidad de voz, ruido de fondo e interrupciones. Tarda un poco más.")
    st.session_state.analyze_audio = analyze_audio
    if analyze_audio:
        st.caption("Se evaluará: voz generativa, flujo, interrupciones, ruido de fondo.")

    c1, c2 = st.columns(2)
    with c1:
        load = st.button("🔄 Cargar", use_container_width=True, type="primary")
    with c2:
        more_btn = st.button("+ Más", use_container_width=True, disabled=not st.session_state.has_more)

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
            if sel and sel not in st.session_state.agent_context:
                with st.spinner("Leyendo prompt del agente..."):
                    prompt = fetch_agent_prompt(el_key, sel)
                    if prompt:
                        st.session_state.agent_context[sel] = prompt
            st.rerun()

        if sel:
            st.divider()
            st.markdown("**🎯 Prompt del agente:**")
            st.markdown("<div style='font-size:11px;color:#9e9e9a;margin-bottom:6px;'>Cargado automáticamente desde ElevenLabs. Puedes editarlo para ajustar el criterio de evaluación.</div>", unsafe_allow_html=True)
            current_ctx = st.session_state.agent_context.get(sel, "")
            new_ctx = st.text_area("Prompt", value=current_ctx,
                placeholder="Se cargará automáticamente al seleccionar el agente.",
                height=150, label_visibility="collapsed", key=f"ctx_{sel}")
            if new_ctx != current_ctx:
                st.session_state.agent_context[sel] = new_ctx
            if st.button("🔄 Recargar prompt", use_container_width=True):
                with st.spinner("Leyendo prompt..."):
                    prompt = fetch_agent_prompt(el_key, sel)
                    if prompt:
                        st.session_state.agent_context[sel] = prompt
                        st.success("✓ Prompt actualizado")
                        st.rerun()
                    else:
                        st.warning("No se encontró prompt para este agente.")

    st.divider()
    st.markdown("**Lo que se evalúa:**\n- 🤖 Clasificación\n- ⭐ Score 0–10\n- `{{` Errores de template `}}`\n- 👤 Errores de nombre\n- 🔍 Issues y recomendaciones\n- 🎵 Voz generativa\n- 🌊 Flujo conversacional\n- 🔇 Ruido de fondo\n- ✂️ Interrupciones")

# ── Main ──────────────────────────────────────────────────────
st.title("Auditor de Smartons")

if not st.session_state.loaded:
    st.info("👈 Haz clic en **Cargar** para comenzar.")
    st.stop()

convs = st.session_state.conversations
tab1, tab2 = st.tabs([f"📋 Llamadas ({len(convs)})", "📊 Resultados"])

# ── TAB 1 ─────────────────────────────────────────────────────
with tab1:
    st.markdown(f"**Agente:** {st.session_state.agent_name} &nbsp;·&nbsp; **{len(convs)} conversaciones**")

    ctx = st.session_state.agent_context.get(st.session_state.agent_id, "")
    if ctx:
        st.markdown(f'<div class="context-box">🎯 <strong>Objetivo activo:</strong> {ctx[:200]}{"..." if len(ctx)>200 else ""}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([2, 2])
    with c1:
        if st.button("✅ Seleccionar todas", use_container_width=True):
            for c in convs:
                cid = c["conversation_id"]
                st.session_state.selected_ids.add(cid)
                st.session_state[f"chk_{cid}"] = True
            st.rerun()
    with c2:
        if st.button("☐ Deseleccionar", use_container_width=True):
            for c in convs:
                st.session_state[f"chk_{c['conversation_id']}"] = False
            st.session_state.selected_ids.clear()
            st.rerun()

    st.divider()

    for conv in convs:
        cid = conv["conversation_id"]
        agent_tag = f"🤖 `{conv.get('agent_id','')[:20]}`&nbsp;" if not st.session_state.agent_id else ""
        dur = fmt_dur(conv.get("call_duration_secs"))
        dt  = fmt_dt(conv.get("start_time_unix_secs"))
        msgs = conv.get("message_count", "?")

        col_chk, col_info = st.columns([0.5, 9.5])
        with col_chk:
            checked = cid in st.session_state.selected_ids
            if st.checkbox("", value=checked, key=f"chk_{cid}"):
                st.session_state.selected_ids.add(cid)
            else:
                st.session_state.selected_ids.discard(cid)
        with col_info:
            st.markdown(f"`{cid}` &nbsp; {agent_tag}🕐 {dur} &nbsp; 📅 {dt} &nbsp; 💬 {msgs} msgs", unsafe_allow_html=True)

    if st.session_state.has_more:
        st.info("Hay más llamadas. Usa **+ Más** en la barra lateral.")

    st.divider()
    n = len(st.session_state.selected_ids)
    ca, cb = st.columns([2, 8])
    with ca:
        go = st.button(f"▶ Auditar {n} llamada{'s' if n!=1 else ''}",
                       disabled=n==0, type="primary", use_container_width=True)
    with cb:
        if n > 0:
            audio_label = " + audio 🎵" if st.session_state.analyze_audio else ""
            st.markdown(f"*{n} llamadas seleccionadas{audio_label}*")

    if go and n > 0:
        ids = list(st.session_state.selected_ids)
        agent_ctx = st.session_state.agent_context.get(st.session_state.agent_id, "")
        prog = st.progress(0, text="Iniciando auditoría...")
        st.session_state.audit_results = {}

        for i, cid in enumerate(ids):
            prog.progress(i/len(ids), text=f"Evaluando {i+1}/{len(ids)}: `{cid[:35]}...`")
            try:
                tx = fetch_transcript(el_key, cid)
                st.session_state.transcripts[cid] = tx
                r = audit_claude(ant_key, tx, agent_ctx)
                r["agent_id"] = next((c for c in convs if c["conversation_id"]==cid), {}).get("agent_id","")

                # Análisis de audio si está activado
                if st.session_state.analyze_audio:
                    prog.progress(i/len(ids), text=f"Analizando audio {i+1}/{len(ids)}: `{cid[:30]}...`")
                    audio_b64 = fetch_audio(el_key, cid)
                    if audio_b64:
                        voice_result = audit_audio_claude(ant_key, audio_b64)
                        r["voice"] = voice_result
                    else:
                        r["voice"] = None

                st.session_state.audit_results[cid] = {"status":"done", **r}
            except Exception as e:
                st.session_state.audit_results[cid] = {"status":"error","error":str(e)}
            if i < len(ids)-1: time.sleep(0.5)

        prog.progress(1.0, text=f"✅ {len(ids)} llamadas evaluadas!")
        st.balloons()
        st.info("👉 Revisa los resultados en la pestaña **Resultados**.")

# ── TAB 2 ─────────────────────────────────────────────────────
with tab2:
    res = {k:v for k,v in st.session_state.audit_results.items() if v.get("status")=="done"}
    if not res:
        st.info("Ninguna auditoría realizada aún."); st.stop()

    done = list(res.values())
    avg  = sum(r.get("score",0) for r in done)/len(done)
    resueltas    = sum(1 for r in done if r.get("clasificacion")=="resuelta")
    issues_count = sum(1 for r in done if r.get("issues"))
    tpl          = sum(1 for r in done if r.get("template_errors"))

    # Métricas de voz si existen
    voice_results = [r["voice"] for r in done if r.get("voice") and not r["voice"].get("error")]
    avg_voz = sum(v.get("generative_voice_score",0) for v in voice_results)/len(voice_results) if voice_results else None
    avg_flujo = sum(v.get("conversational_flow_score",0) for v in voice_results)/len(voice_results) if voice_results else None
    noise_issues = sum(1 for v in voice_results if v.get("noise_confused_with_voice")) if voice_results else 0

    metrics_html = f"""<div class="metric-row">
      <div class="metric-box"><div class="label">Score promedio</div><div class="value">{avg:.1f}</div><div class="sub">de 10</div></div>
      <div class="metric-box"><div class="label">Resueltas</div><div class="value">{resueltas}</div><div class="sub">de {len(done)}</div></div>
      <div class="metric-box"><div class="label">Con issues</div><div class="value">{issues_count}</div><div class="sub">llamadas</div></div>
      <div class="metric-box"><div class="label">Error template</div><div class="value">{tpl}</div><div class="sub">detectados</div></div>"""
    if avg_voz is not None:
        metrics_html += f"""
      <div class="metric-box"><div class="label">🎵 Voz generativa</div><div class="value">{avg_voz:.1f}</div><div class="sub">promedio</div></div>
      <div class="metric-box"><div class="label">🌊 Flujo conv.</div><div class="value">{avg_flujo:.1f}</div><div class="sub">promedio</div></div>
      <div class="metric-box"><div class="label">🔇 Ruido→voz</div><div class="value">{noise_issues}</div><div class="sub">llamadas</div></div>"""
    metrics_html += "</div>"
    st.markdown(metrics_html, unsafe_allow_html=True)

    FL = {"todas":"Todas","resuelta":"✅ Resueltas","no_resuelta":"❌ No resueltas",
          "escalada":"↗ Escaladas","error_tecnico":"⚠️ Error técnico","abandonada":"📵 Abandonadas"}
    ca, cb = st.columns(2)
    with ca: filt = st.selectbox("Filtrar:", list(FL.keys()), format_func=lambda x: FL[x])
    with cb:
        agents_in = list(set(r.get("agent_id","") for r in done if r.get("agent_id")))
        af = st.selectbox("Agente:", ["todos"]+agents_in,
             format_func=lambda x: "— Todos —" if x=="todos" else x) if len(agents_in)>1 else "todos"

    csv_rows = []
    for cid, r in res.items():
        clf = r.get("clasificacion","")
        if filt!="todas" and clf!=filt: continue
        if af!="todos" and r.get("agent_id","")!=af: continue

        conv  = next((c for c in convs if c["conversation_id"]==cid), {})
        dur   = fmt_dur(conv.get("call_duration_secs"))
        dt    = fmt_dt(conv.get("start_time_unix_secs"))
        score = r.get("score",0)
        voice = r.get("voice") or {}
        has_voice = voice and not voice.get("error")

        warn = "".join([
            '<span class="pill pill-warn">⚠ template</span> ' if r.get("template_errors") else "",
            '<span class="pill pill-warn">⚠ nombre</span>'    if r.get("name_errors")     else "",
            '<span class="audio-badge">🎵 audio</span>'       if has_voice else ""
        ])

        with st.expander(f"Score {score}/10 — {PILL.get(clf,clf)}  •  {cid[:38]}  •  {dur}"):
            st.write(r.get("resumen",""))
            st.markdown(f"""<div><span class="pill pill-{clf}">{PILL.get(clf,clf)}</span> &nbsp;
<span class="{score_cls(score)}">{score}/10</span> &nbsp; {warn} &nbsp; 🕐 {dur} &nbsp; 📅 {dt}</div>
""", unsafe_allow_html=True)

            issues = r.get("issues", [])
            if issues and isinstance(issues, list):
                st.markdown("**Issues:**")
                issues_html = " ".join(f'<span class="issue-tag">⚠ {str(i)}</span>' for i in issues if isinstance(i, str))
                st.markdown(issues_html, unsafe_allow_html=True)

            recs = r.get("recomendaciones", [])
            if recs and isinstance(recs, list):
                st.markdown("**Recomendaciones:**")
                for rc in recs:
                    if isinstance(rc, str):
                        st.markdown(f'<div class="rec-item">{rc}</div>', unsafe_allow_html=True)

            # Sección de análisis de voz
            if has_voice:
                vg  = voice.get("generative_voice_score", "—")
                vf  = voice.get("conversational_flow_score", "—")
                vi  = voice.get("interruption_score", "—")
                vn  = voice.get("background_noise_level", "—")
                vnc = "✅ No" if not voice.get("noise_confused_with_voice") else "⚠️ Sí"
                vpt = "✅ No" if not voice.get("premature_termination") else "⚠️ Sí"
                vqa = voice.get("voice_qa_reasoning", "")

                def vc(v): return f"vm-high" if isinstance(v,int) and v>=7 else "vm-mid" if isinstance(v,int) and v>=5 else "vm-low"

                st.markdown(f"""<div class="voice-section">
  <div class="voice-section-title">🎵 Análisis de voz</div>
  <div class="voice-metric"><span class="vm-label">Voz generativa</span><span class="vm-val {vc(vg)}">{vg}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Flujo conversacional</span><span class="vm-val {vc(vf)}">{vf}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Interrupciones</span><span class="vm-val {vc(vi)}">{vi}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Ruido de fondo</span><span class="vm-val">{vn}</span></div>
  <div class="voice-metric"><span class="vm-label">Ruido confundido con voz</span><span class="vm-val">{vnc}</span></div>
  <div class="voice-metric"><span class="vm-label">Terminación prematura</span><span class="vm-val">{vpt}</span></div>
  {"<div style='font-size:12px;color:#6b6b67;margin-top:8px;'>" + vqa + "</div>" if vqa else ""}
</div>""", unsafe_allow_html=True)

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
            "issues":" | ".join(str(i) for i in r.get("issues",[]) if isinstance(i,str)),
            "recomendaciones":" | ".join(str(i) for i in r.get("recomendaciones",[]) if isinstance(i,str)),
            "voz_generativa": voice.get("generative_voice_score","") if has_voice else "",
            "flujo_conversacional": voice.get("conversational_flow_score","") if has_voice else "",
            "interrupciones": voice.get("interruption_score","") if has_voice else "",
            "ruido_fondo": voice.get("background_noise_level","") if has_voice else "",
            "ruido_confundido_voz": "sí" if has_voice and voice.get("noise_confused_with_voice") else "no" if has_voice else "",
            "terminacion_prematura": "sí" if has_voice and voice.get("premature_termination") else "no" if has_voice else "",
            "qa_voz": voice.get("voice_qa_reasoning","") if has_voice else ""
        })

    if csv_rows:
        st.divider()
        st.download_button("⬇️ Exportar CSV", to_csv(csv_rows),
            f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", type="primary")
