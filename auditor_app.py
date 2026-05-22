import streamlit as st
import json, csv, time, io, base64
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import urllib.parse

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
  .rec-item   { font-size: 13px; padding: 4px 0 4px 12px; border-left: 2px solid #EF9F27; margin-bottom: 4px; }
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
  .stt-event { font-size: 11px; color: #9e9e9a; font-style: italic; }
</style>
""", unsafe_allow_html=True)

BASE_AUDIT_SYSTEM = """Eres un auditor experto de agentes de voz para call centers LATAM. Analiza la transcripción y devuelve SOLO JSON válido, sin markdown, sin texto extra.

Formato exacto:
{{"clasificacion":"resuelta|no_resuelta|escalada|error_tecnico|abandonada","score":8,"template_errors":false,"name_errors":false,"issues":["issue 1"],"resumen":"Resumen en 1-2 frases.","recomendaciones":[{{"texto":"Recomendación 1","prioridad":"alta|media|baja"}}],"sentimiento":{{"estado":"satisfecho|neutro|frustrado|confuso|molesto","intensidad":"leve|moderado|intenso","detalle":"1 frase explicando el tono emocional del usuario."}}}}

Prioridades: alta=impacta directamente el objetivo o genera mala experiencia, media=mejora la calidad pero no es crítico, baja=optimización opcional.

Criterios base: resuelta=objetivo cumplido, no_resuelta=no se logró, escalada=transferido a humano, error_tecnico=falla del sistema, abandonada=usuario colgó. Score 0-10. template_errors=true si hay {{{{variable}}}} sin reemplazar. name_errors=true si hay problemas con nombres.

{context_block}"""

VOICE_AUDIT_SYSTEM = """Eres un auditor experto de calidad de voz para agentes de IA en call centers LATAM. Recibirás una transcripción enriquecida con timestamps, diarización de speakers y eventos de audio no verbales (ruido, silencio, etc.) generada por el modelo Scribe v2 de ElevenLabs.

Analiza esta transcripción enriquecida y devuelve SOLO JSON válido, sin markdown, sin texto extra.

Formato exacto:
{{"generative_voice_score":8,"conversational_flow_score":7,"interruption_score":9,"background_noise_level":"limpio|leve|moderado|alto","noise_confused_with_voice":false,"premature_termination":false,"user_sentiment":"satisfecho|neutro|frustrado|confuso|molesto","voice_qa_reasoning":"2-3 frases justificando los scores."}}

- user_sentiment: estado emocional del usuario durante la llamada basado en el tono, velocidad del habla, pausas y palabras usadas.

Criterios:
- generative_voice_score (1-10): Penaliza artefactos artificiales, velocidad robótica, slips al español castillano.
- conversational_flow_score (1-10): Evalúa si hubo latencias o delays que rompieron la naturalidad. Analiza los gaps de tiempo entre speakers.
- interruption_score (1-10): Penaliza al agente por cortar al usuario. Perdona interrupciones por ruido de fondo. Analiza solapamientos de timestamps.
- background_noise_level: basado en eventos de audio detectados (ruido, música, etc.)
- noise_confused_with_voice: true si el agente respondió a ruido de fondo confundiéndolo con voz del usuario.
- premature_termination: true si el agente terminó antes de que el usuario completara su intención."""

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
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=60) as r:
            return r.read(), dict(r.headers)
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

def fetch_conversation_full(el_key, conv_id):
    """Fetch full conversation data including transcript with timestamps."""
    return api_req(f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}", {"xi-api-key": el_key})

def calculate_latency(transcript):
    """Calculate agent response latency from transcript timestamps.
    Returns: avg_latency_ms, max_latency_ms, latency_list"""
    latencies = []
    user_end = None
    for turn in transcript:
        role = turn.get("role","")
        # ElevenLabs provides time_in_call_secs per message
        t = turn.get("time_in_call_secs")
        if t is None:
            continue
        if role == "user":
            user_end = t
        elif role == "agent" and user_end is not None:
            delta = t - user_end
            if 0 < delta < 30:  # ignore implausible values
                latencies.append(round(delta, 2))
            user_end = None
    if not latencies:
        return None, None, []
    avg = round(sum(latencies)/len(latencies), 2)
    mx  = round(max(latencies), 2)
    return avg, mx, latencies

def check_has_audio(el_key, conv_id):
    """Check if conversation has audio available."""
    try:
        data = api_req(f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}", {"xi-api-key": el_key})
        return data.get("has_audio", False)
    except:
        return False

def fetch_audio_bytes(el_key, conv_id):
    """Fetch raw audio bytes from ElevenLabs."""
    try:
        raw, headers = api_req_raw(
            f"https://api.elevenlabs.io/v1/convai/conversations/{conv_id}/audio",
            {"xi-api-key": el_key}
        )
        return raw
    except:
        return None

def transcribe_with_scribe(el_key, audio_bytes):
    """Send audio to ElevenLabs Scribe v2 for detailed transcription with diarization."""
    if not audio_bytes:
        return None
    try:
        import urllib.request, uuid
        boundary = uuid.uuid4().hex
        CRLF = b"\r\n"

        def field(name, value):
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}").encode() + CRLF

        body = b""
        body += field("model_id", "scribe_v2")
        body += field("diarize", "true")
        body += field("detect_speaker_roles", "true")
        body += field("timestamps_granularity", "word")
        body += field("tag_audio_events", "true")
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode()
        body += audio_bytes + CRLF
        body += f"--{boundary}--\r\n".encode()

        url = f"https://api.elevenlabs.io/v1/speech-to-text"
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": el_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

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

def audit_voice_claude(ant_key, scribe_result):
    """Send Scribe enriched transcription to Claude for voice quality analysis."""
    if not scribe_result or scribe_result.get("error"):
        return None
    try:
        # Build enriched transcript with timestamps and events
        words = scribe_result.get("words", [])
        enriched_lines = []
        current_speaker = None
        current_line = []
        current_start = None

        for w in words:
            wtype = w.get("type", "word")
            speaker = w.get("speaker_id", "unknown")
            text = w.get("text", "")
            start = w.get("start", 0)
            end = w.get("end", 0)

            if wtype == "audio_event":
                if current_line:
                    enriched_lines.append(f"[{current_speaker or 'Speaker'} @{current_start:.1f}s]: {' '.join(current_line)}")
                    current_line = []
                enriched_lines.append(f"[AUDIO_EVENT @{start:.1f}s]: {text}")
                current_speaker = None
                current_start = None
            else:
                if speaker != current_speaker:
                    if current_line:
                        enriched_lines.append(f"[{current_speaker or 'Speaker'} @{current_start:.1f}s]: {' '.join(current_line)}")
                        current_line = []
                    current_speaker = speaker
                    current_start = start
                current_line.append(text)

        if current_line:
            enriched_lines.append(f"[{current_speaker or 'Speaker'} @{current_start:.1f}s]: {' '.join(current_line)}")

        enriched_tx = "\n".join(enriched_lines)

        data = api_req("https://api.anthropic.com/v1/messages",
            {"Content-Type":"application/json","x-api-key":ant_key,"anthropic-version":"2023-06-01"},
            {"model":"claude-sonnet-4-5","max_tokens":800,"system":VOICE_AUDIT_SYSTEM,
             "messages":[{"role":"user","content":f"Analiza la calidad de voz de esta llamada:\n\n{enriched_tx}"}]})
        text = "".join(b["text"] for b in data.get("content",[]) if b["type"]=="text")
        result = json.loads(text.replace("```json","").replace("```","").strip())
        result["enriched_transcript"] = enriched_lines
        return result
    except Exception as e:
        return {"error": str(e)}

def fmt_dur(s): return f"{int(s)//60}m {int(s)%60}s" if s else "—"

def content_alert_emoji(score, clf, r):
    """🔴🟡🟢 based on content quality: score, classification, template errors."""
    if r.get("template_errors") or r.get("name_errors") or clf == "error_tecnico":
        return "🔴"
    if score <= 4 or clf == "no_resuelta":
        return "🔴"
    if score <= 6:
        return "🟡"
    return "🟢"

def audio_alert_emoji(voice):
    """🎙️ badge for audio/voice quality issues — separate from content."""
    if not voice or voice.get("error"):
        return ""
    critical = (
        voice.get("noise_confused_with_voice") or
        voice.get("premature_termination") or
        (isinstance(voice.get("generative_voice_score"), int) and voice["generative_voice_score"] <= 4) or
        voice.get("background_noise_level") == "alto"
    )
    warning = (
        (isinstance(voice.get("generative_voice_score"), int) and voice["generative_voice_score"] <= 6) or
        (isinstance(voice.get("conversational_flow_score"), int) and voice["conversational_flow_score"] <= 5) or
        (isinstance(voice.get("interruption_score"), int) and voice["interruption_score"] <= 5) or
        voice.get("background_noise_level") == "moderado"
    )
    if critical: return "🎙️🔴"
    if warning:  return "🎙️🟡"
    return "🎙️🟢"

def sentiment_emoji(sentiment):
    return {
        "satisfecho": "😊",
        "neutro": "😐",
        "frustrado": "😤",
        "confuso": "😕",
        "molesto": "😠"
    }.get(sentiment, "")

def noise_badge(level):
    return {
        "limpio": "🔇 limpio",
        "leve":   "🔉 leve",
        "moderado": "🔊 moderado",
        "alto":   "📢 alto"
    }.get(level, level)
def fmt_dt(ts): return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "—"
def score_cls(s): return "score-high" if s>=7 else "score-mid" if s>=5 else "score-low"

def to_csv(rows):
    buf = io.StringIO(); buf.write("\ufeff")
    fields = ["id","agente","fecha","duracion","clasificacion","score",
              "error_template","error_nombre","resumen","issues","recomendaciones",
              "latencia_avg_s","latencia_max_s","voz_generativa","flujo_conversacional","interrupciones","ruido_fondo",
              "ruido_confundido_voz","terminacion_prematura","qa_voz","sentimiento"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows: w.writerow(r)
    return buf.getvalue()

# ── Session state ─────────────────────────────────────────────
for k,v in {"agents":[],"conversations":[],"selected_ids":set(),"audit_results":{},
            "transcripts":{},"loaded":False,"agent_id":"","agent_name":"Todos",
            "has_more":False,"cursor":None,"agent_context":{},"analyze_audio":True,
            "audio_cache":{}}.items():
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

    analyze_audio = st.toggle("🎵 Analizar audio (Scribe v2)", value=st.session_state.analyze_audio,
                               help="Usa ElevenLabs Scribe v2 para analizar calidad de voz, ruido, interrupciones y flujo. Tarda un poco más.")
    st.session_state.analyze_audio = analyze_audio
    if analyze_audio:
        st.caption("Diarización + timestamps + eventos de audio → Claude evalúa calidad de voz.")

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
                    st.session_state.audio_cache = {}
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
            st.markdown("<div style='font-size:11px;color:#9e9e9a;margin-bottom:6px;'>Cargado automáticamente desde ElevenLabs.</div>", unsafe_allow_html=True)
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
    st.markdown("**Lo que se evalúa:**\n- 🤖 Clasificación\n- ⭐ Score 0–10\n- `{{` Errores de template\n- 👤 Errores de nombre\n- 🔍 Issues y recomendaciones\n- 🎵 Voz generativa (Scribe)\n- 🌊 Flujo conversacional\n- 🔇 Ruido de fondo\n- ✂️ Interrupciones")

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

    # ── Filtros ──────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=False):
        fc1, fc2 = st.columns(2)
        with fc1:
            status_filter = st.selectbox("Status", ["todos","done","failed"], 
                format_func=lambda x: "Todos" if x=="todos" else x)
        with fc2:
            min_dur = st.slider("Duración mínima (seg)", 0, 300, 0, 10)
    convs_filtered = [c for c in convs if
        (status_filter == "todos" or c.get("status") == status_filter) and
        ((c.get("call_duration_secs") or 0) >= min_dur)
    ]
    if len(convs_filtered) != len(convs):
        st.caption(f"Mostrando {len(convs_filtered)} de {len(convs)} llamadas")

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

    for conv in convs_filtered:
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
            secs = conv.get("call_duration_secs") or 0
            msg_count = conv.get("message_count") or 0
            pre_flags = []
            if msg_count == 0:
                pre_flags.append(("⚠️", "sin mensajes", "#5c3a00", "#FAEEDA"))
            elif msg_count <= 2:
                pre_flags.append(("💬", "muy corta", "#5c3a00", "#FAEEDA"))
            if secs > 0 and secs < 20:
                pre_flags.append(("⏱️", "<20s", "#5c3a00", "#FAEEDA"))
            elif secs > 300:
                pre_flags.append(("⏱️", "+5min", "#5c3a00", "#FAEEDA"))

            audit = st.session_state.audit_results.get(cid)
            if audit and audit.get("status") == "done":
                sc = audit.get("score", 0)
                cl = audit.get("clasificacion", "")
                voice_r = audit.get("voice") or {}
                ca = content_alert_emoji(sc, cl, audit)
                aa = audio_alert_emoji(voice_r) if voice_r and not voice_r.get("error") else ""
                result_badge = f'<span style="font-size:12px;font-weight:700;margin-right:6px;">{ca} {sc}/10 {aa}</span>'
            else:
                result_badge = ""

            flags_html = " ".join(
                f'<span style="font-size:10px;background:{bg};color:{fc};padding:2px 7px;border-radius:10px;font-weight:600;">{icon} {label}</span>'
                for icon, label, fc, bg in pre_flags
            )
            left_badges = (result_badge + " " + flags_html).strip()

            st.markdown(
                f"{left_badges}&nbsp; `{cid}` &nbsp; {agent_tag}🕐 {dur} &nbsp; 📅 {dt} &nbsp; 💬 {msgs} msgs",
                unsafe_allow_html=True
            )

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
            audio_label = " + análisis de voz 🎵" if st.session_state.analyze_audio else ""
            st.markdown(f"*{n} llamadas seleccionadas{audio_label}*")

    if go and n > 0:
        ids = list(st.session_state.selected_ids)
        agent_ctx = st.session_state.agent_context.get(st.session_state.agent_id, "")
        prog = st.progress(0, text="Iniciando auditoría...")
        st.session_state.audit_results = {}

        for i, cid in enumerate(ids):
            prog.progress(i/len(ids), text=f"Evaluando {i+1}/{len(ids)}: `{cid[:35]}...`")
            try:
                # 1. Transcripción básica
                # Fetch full conversation data
                tx = fetch_transcript(el_key, cid)
                st.session_state.transcripts[cid] = tx

                # Calculate latency from timestamps
                avg_lat, max_lat, lat_list = calculate_latency(tx)

                # 2. Auditoría de contenido
                r = audit_claude(ant_key, tx, agent_ctx)
                r["latency_avg_s"] = avg_lat
                r["latency_max_s"] = max_lat
                r["agent_id"] = next((c for c in convs if c["conversation_id"]==cid), {}).get("agent_id","")

                # 3. Análisis de voz con Scribe si activado
                if st.session_state.analyze_audio:
                    prog.progress(i/len(ids), text=f"Verificando audio {i+1}/{len(ids)}: `{cid[:30]}...`")
                    has_audio = check_has_audio(el_key, cid)
                    audio_bytes = fetch_audio_bytes(el_key, cid) if has_audio else None
                    if audio_bytes:
                        # Cache audio for player
                        st.session_state.audio_cache[cid] = base64.b64encode(audio_bytes).decode()
                        prog.progress(i/len(ids), text=f"Transcribiendo con Scribe {i+1}/{len(ids)}...")
                        scribe = transcribe_with_scribe(el_key, audio_bytes)
                        if scribe and not scribe.get("error"):
                            prog.progress(i/len(ids), text=f"Analizando voz {i+1}/{len(ids)}...")
                            voice = audit_voice_claude(ant_key, scribe)
                            r["voice"] = voice
                        else:
                            r["voice"] = scribe  # will show error
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

    voice_results = [r["voice"] for r in done if r.get("voice") and not r["voice"].get("error")]
    avg_voz   = sum(v.get("generative_voice_score",0) for v in voice_results)/len(voice_results) if voice_results else None
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

    # ── Reset button ────────────────────────────────────────────
    if st.button("← Nueva evaluación", type="secondary"):
        for key in ["conversations","selected_ids","audit_results","transcripts",
                    "audio_cache","loaded","agent_id","agent_name","agents",
                    "has_more","cursor","agent_context"]:
            if key in st.session_state:
                if isinstance(st.session_state[key], set):
                    st.session_state[key] = set()
                elif isinstance(st.session_state[key], dict):
                    st.session_state[key] = {}
                elif isinstance(st.session_state[key], list):
                    st.session_state[key] = []
                elif isinstance(st.session_state[key], bool):
                    st.session_state[key] = False
                else:
                    st.session_state[key] = ""
        st.rerun()

    # ── Tabla agregada ──────────────────────────────────────────
    if not st.session_state.get("is_auditing", False) and len(res) > 1:
        with st.expander("📋 Tabla resumen de todas las llamadas", expanded=False):
            import pandas as pd
            PILL_SHORT = {"resuelta":"✅","no_resuelta":"❌","escalada":"↗","error_tecnico":"⚠️","abandonada":"📵"}
            rows = []
            for cid2, r2 in res.items():
                conv2 = next((c for c in convs if c["conversation_id"]==cid2), {})
                voice2 = r2.get("voice") or {}
                has_v2 = bool(voice2 and not voice2.get("error"))
                rows.append({
                    "Llamada": cid2[:20]+"...",
                    "Fecha": fmt_dt(conv2.get("start_time_unix_secs")),
                    "Duración": fmt_dur(conv2.get("call_duration_secs")),
                    "Estado": PILL_SHORT.get(r2.get("clasificacion",""),"?") + " " + PILL.get(r2.get("clasificacion",""),""),
                    "Score": r2.get("score","—"),
                    "Latencia avg": f"{r2.get('latency_avg_s','—')}s" if r2.get('latency_avg_s') else "—",
                    "Sentimiento": (r2.get("sentimiento",{}) or {}).get("estado","—"),
                    "Voz": voice2.get("generative_voice_score","—") if has_v2 else "—",
                    "Flujo": voice2.get("conversational_flow_score","—") if has_v2 else "—",
                    "Ruido": voice2.get("background_noise_level","—") if has_v2 else "—",
                    "Template ⚠": "sí" if r2.get("template_errors") else "no",
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

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
        has_voice = bool(voice and not voice.get("error"))
        audio_b64 = st.session_state.audio_cache.get(cid)

        warn = "".join([
            '<span class="pill pill-warn">⚠ template</span> ' if r.get("template_errors") else "",
            '<span class="pill pill-warn">⚠ nombre</span>'    if r.get("name_errors")     else "",
            '<span class="audio-badge">🎵 Scribe</span>'      if has_voice else ""
        ])

        content_alert = content_alert_emoji(score, clf, r)
        audio_alert = audio_alert_emoji(voice) if has_voice else ""
        sentiment = voice.get("user_sentiment","") if has_voice else ""
        sent_icon = sentiment_emoji(sentiment)
        noise_lvl = voice.get("background_noise_level","") if has_voice else ""
        noise_info = f"  {noise_badge(noise_lvl)}" if noise_lvl and noise_lvl != "limpio" else ""
        audio_section = f"  |  {audio_alert}{noise_info}{' ' + sent_icon if sent_icon else ''}" if has_voice else ""
        title = f"{content_alert} Score {score}/10 — {PILL.get(clf,clf)}  •  {cid[:28]}  •  {dur}{audio_section}"
        with st.expander(title.strip()):
            st.write(r.get("resumen",""))
            lat_avg = r.get("latency_avg_s")
            lat_badge = f"&nbsp; ⚡ {lat_avg}s latencia" if lat_avg is not None else ""
            lat_html = f'<span style="font-size:11px;font-weight:700;color:#ffffff;">{lat_badge}</span>' if lat_avg else ""
            st.markdown(f"""<div><span class="pill pill-{clf}">{PILL.get(clf,clf)}</span> &nbsp;
<span class="{score_cls(score)}">{score}/10</span> &nbsp; {warn} &nbsp; 🕐 {dur} &nbsp; 📅 {dt} {lat_html}</div>
""", unsafe_allow_html=True)

            # 🎵 Audio player
            if audio_b64:
                st.markdown("**🎵 Audio de la llamada:**")
                audio_bytes = base64.b64decode(audio_b64)
                st.audio(audio_bytes, format="audio/mp3")

            # Sentimiento
            sent = r.get("sentimiento") or {}
            if sent and isinstance(sent, dict):
                SENT_EMOJI = {"satisfecho":"😊","neutro":"😐","frustrado":"😤","confuso":"😕","molesto":"😠"}
                SENT_COLOR = {"satisfecho":"#EAF3DE","neutro":"#f5f5f3","frustrado":"#FAEEDA","confuso":"#E6F1FB","molesto":"#FCEBEB"}
                SENT_TEXT  = {"satisfecho":"#27500A","neutro":"#444441","frustrado":"#633806","confuso":"#0C447C","molesto":"#791F1F"}
                INT_LABEL  = {"leve":"leve","moderado":"moderado","intenso":"intenso"}
                estado = sent.get("estado","neutro")
                intensidad = sent.get("intensidad","leve")
                detalle = sent.get("detalle","")
                emoji = SENT_EMOJI.get(estado,"😐")
                bg = SENT_COLOR.get(estado,"#f5f5f3")
                tc = SENT_TEXT.get(estado,"#444441")
                st.markdown(f'''<div style="background:{bg};border-radius:8px;padding:10px 14px;margin:8px 0;">
  <span style="font-size:13px;font-weight:700;color:{tc};">{emoji} {estado.upper()}</span>
  <span style="font-size:11px;color:{tc};margin-left:8px;opacity:0.8;">· {INT_LABEL.get(intensidad,intensidad)}</span>
  <div style="font-size:12px;color:{tc};margin-top:4px;opacity:0.9;">{detalle}</div>
</div>''', unsafe_allow_html=True)

            issues = r.get("issues", [])
            if issues and isinstance(issues, list):
                st.markdown("**Issues:**")
                issues_html = " ".join(f'<span class="issue-tag">⚠ {str(i)}</span>' for i in issues if isinstance(i, str))
                st.markdown(issues_html, unsafe_allow_html=True)

            recs = r.get("recomendaciones", [])
            if recs and isinstance(recs, list):
                st.markdown("**Recomendaciones:**")
                PRIO_ICON = {"alta": "🔴", "media": "🟡", "baja": "🟢"}
                PRIO_LABEL = {"alta": "ALTA", "media": "MEDIA", "baja": "BAJA"}
                for rc in recs:
                    if isinstance(rc, dict):
                        texto = rc.get("texto", "")
                        prio  = rc.get("prioridad", "media").lower()
                    else:
                        texto = str(rc)
                        prio  = "media"
                    icon = PRIO_ICON.get(prio, "🟡")
                    label = PRIO_LABEL.get(prio, "MEDIA")
                    st.markdown(f"{icon} **{label}** — {texto}")

            # 🎵 Análisis de voz con Scribe
            if has_voice:
                vg  = voice.get("generative_voice_score", "—")
                vf  = voice.get("conversational_flow_score", "—")
                vi  = voice.get("interruption_score", "—")
                vn  = voice.get("background_noise_level", "—")
                vnc = "✅ No" if not voice.get("noise_confused_with_voice") else "⚠️ Sí"
                vpt = "✅ No" if not voice.get("premature_termination") else "⚠️ Sí"
                vqa = voice.get("voice_qa_reasoning", "")

                def vc(v): return "vm-high" if isinstance(v,int) and v>=7 else "vm-mid" if isinstance(v,int) and v>=5 else "vm-low"

                st.markdown(f"""<div class="voice-section">
  <div class="voice-section-title">🎵 Análisis de voz (Scribe v2)</div>
  <div class="voice-metric"><span class="vm-label">Voz generativa</span><span class="vm-val {vc(vg)}">{vg}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Flujo conversacional</span><span class="vm-val {vc(vf)}">{vf}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Interrupciones</span><span class="vm-val {vc(vi)}">{vi}/10</span></div>
  <div class="voice-metric"><span class="vm-label">Ruido de fondo</span><span class="vm-val">{vn}</span></div>
  <div class="voice-metric"><span class="vm-label">Ruido confundido con voz</span><span class="vm-val">{vnc}</span></div>
  <div class="voice-metric"><span class="vm-label">Terminación prematura</span><span class="vm-val">{vpt}</span></div>
  <div class="voice-metric"><span class="vm-label">Sentimiento del usuario</span><span class="vm-val">{sent_icon} {sentiment}</span></div>
  {"<div style='font-size:12px;color:#6b6b67;margin-top:8px;'>" + vqa + "</div>" if vqa else ""}
</div>""", unsafe_allow_html=True)

                # Transcripción enriquecida con timestamps
                enriched = voice.get("enriched_transcript", [])
                if enriched:
                    with st.expander("🕐 Transcripción con timestamps (Scribe)"):
                        for line in enriched:
                            if "AUDIO_EVENT" in line:
                                st.markdown(f"<span class='stt-event'>{line}</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(line)

            elif voice.get("error"):
                st.caption(f"⚠️ No se pudo analizar el audio: {voice['error']}")

            # Transcripción básica
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
            "latencia_avg_s": r.get("latency_avg_s",""),
            "latencia_max_s": r.get("latency_max_s",""),
            "recomendaciones":" | ".join(
                (rc.get("texto","") + " [" + rc.get("prioridad","") + "]") if isinstance(rc, dict) else str(rc)
                for rc in r.get("recomendaciones",[])
            ),
            "voz_generativa": voice.get("generative_voice_score","") if has_voice else "",
            "flujo_conversacional": voice.get("conversational_flow_score","") if has_voice else "",
            "interrupciones": voice.get("interruption_score","") if has_voice else "",
            "ruido_fondo": voice.get("background_noise_level","") if has_voice else "",
            "ruido_confundido_voz": "sí" if has_voice and voice.get("noise_confused_with_voice") else "no" if has_voice else "",
            "terminacion_prematura": "sí" if has_voice and voice.get("premature_termination") else "no" if has_voice else "",
            "qa_voz": voice.get("voice_qa_reasoning","") if has_voice else "",
            "sentimiento": voice.get("user_sentiment","") if has_voice else ""
        })

    if csv_rows:
        st.divider()
        st.download_button("⬇️ Exportar CSV", to_csv(csv_rows),
            f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", type="primary")
