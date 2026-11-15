import streamlit as st
import os, subprocess, tempfile, io, zipfile, time

st.set_page_config(page_title="Clips en VIVO - RDjavi", layout="wide")

# --- ESTILO BOTÓN GRANDE PARA LA NETBOOK ---
st.markdown("""
<style>
.big-btn button { font-size: 28px !important; padding: 20px !important; background-color: red !important; color: white !important; font-weight: bold !important; height: 70px !important; width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔴 CLIPS EN VIVO - Estilo MR Vargas TV")
st.write("Netbook al lado de la tele. Pegá el link, apretá el botón rojo, y la app sola saca los clips completos.")

if "clips_vivo" not in st.session_state:
    st.session_state.clips_vivo = []
if "grabando" not in st.session_state:
    st.session_state.grabando = False

# --- ARRIBA: PEGAR LINK + BOTÓN GRANDE ---
url = st.text_input("🔗 Pegá acá el link del directo EN VIVO de Kick / YouTube", placeholder="Pegá el link acá...")
nombre = st.text_input("Nombre del streamer", value="RDjavi")

col_btn1, col_btn2 = st.columns([3, 1])
with col_btn1:
    st.markdown('<div class="big-btn">', unsafe_allow_html=True)
    if st.button("🔴 EMPEZAR A GRABAR EN VIVO"):
        if not url:
            st.warning("Pegá el link primero")
        else:
            st.session_state.grabando = True
            st.success("🔴 ¡GRABANDO! Dejá la netbook abierta. Yo solo saco los clips.")
    st.markdown('</div>', unsafe_allow_html=True)
with col_btn2:
    if st.button("⏹️ PARAR"):
        st.session_state.grabando = False
        st.info("Paraste la grabación.")

if st.session_state.grabando:
    st.warning("🔴 EN VIVO - Estoy escuchando el directo... Si se enoja, se ríe, hace un chiste o entra al juego, te saco el clip COMPLETO, de donde empieza hasta donde termina.")

    # --- PALABRAS QUE LA APP ESCUCHA ---
    # Enojo
    PALABRAS_ENOJO = ["boludo", "pelotudo", "idiota", "tonto", "mierda", "hijo de", "callate", "cállate", "no me rompas", "me tienen harto", "salí de acá", "forro", "gil", "chat de mierda", "no jodan", "déjense de joder"]
    # Risa / Chiste
    PALABRAS_RISA = ["jajaja", "jaja", "me muero", "no puedo", "que gracioso", "qué gracioso", "me cago de risa", "es un chiste", "mirá lo que hizo"]
    # Juego
    PALABRAS_JUEGO = ["gta", "vamos a jugar", "entro al juego", "cargando", "ya estoy en el juego", "partida", "vamos a robar", "policía", "me mataron", "ganamos"]
    # Importante
    PALABRAS_IMPORTANTE = ["apagón", "apagon", "17 de noviembre", "noticia", "urgente", "miren esto", "escuchen esto", "atención"]

    def que_paso_en(texto):
        t = texto.lower()
        for p in PALABRAS_ENOJO:
            if p in t:
                return f"{nombre} SE ENOJA CON EL CHAT"
        for p in PALABRAS_RISA:
            if p in t:
                return f"{nombre} SE RIE / HACE UN CHISTE"
        for p in PALABRAS_JUEGO:
            if p in t:
                return f"{nombre} ENTRA AL JUEGO - {p.upper()}"
        for p in PALABRAS_IMPORTANTE:
            if p in t:
                return f"{nombre} HABLA DE {p.upper()}"
        return None

    if st.button("🔄 REVISAR AHORA - Buscar momento importante en los últimos minutos", type="primary"):
        st.info("Escuchando los últimos minutos del directo...")
        with tempfile.TemporaryDirectory() as tmp:
            v = os.path.join(tmp, "vivo.mp4")
            a = os.path.join(tmp, "vivo.mp3")
            cara = os.path.join(tmp, "cara.jpg")
            # Bajamos 5 minutos para poder agarrar el momento COMPLETO, de donde empieza a donde termina
            cmd = ["yt-dlp", "--no-playlist", "--user-agent", "Mozilla/5.0",
                   "--extractor-args", "youtube:player_client=android,web",
                   "-f", "best[height<=480]", "--download-sections", "*00:00-00:05:00",
                   "--max-filesize", "400M", "-o", v, url]
            subprocess.run(cmd, capture_output=True)
            if not os.path.exists(v):
                st.error("No pude bajar el directo. ¿Está en vivo? ¿El link está bien?")
                st.stop()
            subprocess.run(["ffmpeg", "-y", "-i", v, "-vn", a], capture_output=True)
            try:
                from faster_whisper import WhisperModel
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segs, _ = model.transcribe(a, language="es")
                segs = list(segs)
            except Exception as e:
                st.write(f"No pude transcribir ahora, pruebo de nuevo: {e}")
                segs = []

            if not segs:
                st.write("No escuché nada claro, sigo grabando...")
                st.stop()

            # --- DETECTAR MOMENTO COMPLETO: DE DONDE EMPIEZA A DONDE TERMINA ---
            # Buscamos el primer segmento donde se enoja / ríe / etc.
            # Y seguimos hasta que pasen 3 frases seguidas sin que se enoje / ría, ahí termina el momento
            encontrado = None
            for idx, s in enumerate(segs):
                titulo = que_paso_en(s.text)
                if titulo:
                    inicio = max(0, s.start - 2)  # 2 seg antes para agarrar el principio
                    # Ahora buscamos dónde termina: seguimos mientras siga enojado / riéndose
                    fin = s.end
                    sin_nada = 0
                    for s2 in segs[idx+1:]:
                        if que_paso_en(s2.text):
                            fin = s2.end
                            sin_nada = 0
                        else:
                            sin_nada += 1
                            # Si pasaron 3 frases y ya no se enoja, ahí termina el momento
                            if sin_nada >= 3:
                                fin = s2.start
                                break
                            fin = s2.end
                    dur = int(fin - inicio)
                    # Si es muy cortito, lo dejamos en 25 seg mínimo para que se entienda
                    if dur < 25:
                        fin = inicio + 25
                        dur = 25
                    # Si es muy largo, lo cortamos en 2 minutos máximo para TikTok
                    if dur > 120:
                        fin = inicio + 120
                        dur = 120
                    encontrado = (inicio, fin, dur, titulo)
                    st.success(f"🎯 ¡ENCONTRÉ ALGO! {titulo}")
                    st.write(f"Empieza en el seg {int(inicio)} y termina en el seg {int(fin)} - Dura {dur} seg COMPLETO, sin cortar a la mitad.")
                    break

            if not encontrado:
                st.write("En estos minutos no se enojó, ni se rió, ni pasó nada. Sigo escuchando... Dejá la netbook abierta y apretá REVISAR de nuevo en 2 minutos.")
                st.stop()

            inicio, fin, dur, titulo = encontrado
            # Cortamos el clip COMPLETO
            subprocess.run(["ffmpeg", "-y", "-ss", str(inicio+2), "-i", v, "-vframes", "1", "-vf", "crop=iw*0.6:ih:iw*0.2:0", cara], capture_output=True)
            out = os.path.join(tmp, "clip_vivo.mp4")
            filtro = (
                "[0:v]scale=720:540:force_original_aspect_ratio=decrease,pad=720:540:(ow-iw)/2:(oh-ih)/2:black,setsar=1[top];"
                "[1:v]scale=720:740:force_original_aspect_ratio=decrease,pad=720:740:(ow-iw)/2:(oh-ih)/2:black,setsar=1[bottom];"
                "[top][bottom]vstack=inputs=2[base];"
                f"[base]drawbox=x=270:y=500:w=180:h=50:color=red@0.95:t=fill,"
                f"drawtext=text='{nombre}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=28:fontcolor=white:x=360-text_w/2:y=512[v]"
            )
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", cara, "-ss", str(inicio), "-i", v, "-t", str(dur),
                            "-filter_complex", filtro, "-map", "[v]", "-map", "1:a", "-c:a", "aac", "-shortest", out], capture_output=True)
            if os.path.exists(out):
                with open(out, "rb") as f:
                    datos = f.read()
                st.session_state.clips_vivo.append({"titulo": titulo, "video": datos, "dur": dur})
                st.success(f"✅ Clip guardado: {titulo} - {dur} seg completo")
                st.video(datos)

# --- ABAJO: LISTA DE CLIPS QUE YA SALIERON, COMO MR VARGAS ---
st.write("---")
st.write("### 📋 Clips que ya salieron solos - En espera para subir a TikTok")
if not st.session_state.clips_vivo:
    st.write("Todavía no salió ningún clip. Cuando él se enoje, se ría o entre al juego, acá te aparece solo.")
else:
    col_izq, col_medio, col_der = st.columns([1, 1, 1.2])
    # Izquierda: lista
    with col_izq:
        st.write("**Esperando la decisión**")
        for i, c in enumerate(st.session_state.clips_vivo):
            st.write(f"Clip #{84+i} - {c['titulo']} - {c['dur']} seg")
    # Medio: video
    with col_medio:
        ultimo = st.session_state.clips_vivo[-1]
        st.write(f"**{ultimo['titulo']}**")
        st.video(ultimo['video'])
    # Derecha: editor
    with col_der:
        st.write("**✏️ Editor**")
        nuevo_titulo = st.text_input("Título del clip", value=ultimo['titulo'])
        st.write(f"Duración completa: {ultimo['dur']} segundos - De donde empieza a donde termina")
        st.download_button("⬇️ Bajar este clip para TikTok", ultimo['video'], file_name=f"{nuevo_titulo}.mp4", mime="video/mp4", type="primary")
        if st.button("❌ Descartar este clip"):
            st.session_state.clips_vivo.pop()
            st.rerun()

    st.write("---")
    st.write("**Bajar todos juntos:**")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        for i, c in enumerate(st.session_state.clips_vivo):
            z.writestr(f"clip_{i+1}_{c['titulo']}.mp4", c['video'])
    st.download_button("⬇️ BAJAR TODOS LOS CLIPS (ZIP)", zip_buf.getvalue(), file_name="clips_en_vivo.zip", mime="application/zip")
