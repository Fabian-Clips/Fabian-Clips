import streamlit as st
import os, subprocess, tempfile, zipfile, io

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips estilo RDjavi.")

url = st.text_input("Link del video de Kick o YouTube")
nombre = st.text_input("Nombre para el cartel rojo del medio", value="RDjavi")
idioma = st.selectbox("Idioma del video", ["Español", "English"])
lang_code = "es" if idioma == "Español" else "en"

if "clips_guardados" not in st.session_state:
    st.session_state.clips_guardados = None

def crear_subtitulos_ass(segments, path):
    # Estilo NOXEN: letras grandes, blancas y amarillas, borde negro grueso
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,30,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,10,10,350,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(t):
        h = int(t//3600); m = int((t%3600)//60); s = int(t%60); cs = int((t%1)*100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    lines = [header]
    for seg in segments:
        # Pintamos algunas palabras en amarillo como en el ejemplo
        texto = seg.text.strip().upper()
        lines.append(f"Dialogue: 0,{fmt(seg.start)},{fmt(seg.end)},Default,,0,0,0,,{texto}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()
    st.info("⏳ Trabajando... No cierres esta pestaña, tarda 4-5 minutos.")
    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")
        audio_path = os.path.join(tmp, "audio.mp3")
        cara_path = os.path.join(tmp, "cara.mp4")
        ass_path = os.path.join(tmp, "subs.ass")

        st.write("1/4 Bajando video (solo 5 min)...")
        cmd = ["yt-dlp", "--no-playlist", "--user-agent", "Mozilla/5.0",
               "--extractor-args", "youtube:player_client=android,web",
               "-f", "best[height<=480]",
               "--download-sections", "*00:00-00:05:00",
               "--max-filesize", "250M",
               "-o", video_path, url]
        subprocess.run(cmd, capture_output=True)
        if not os.path.exists(video_path):
            st.error("No pude descargar.")
            st.stop()
        st.success(f"Video bajado: {os.path.getsize(video_path)//1024//1024} MB")

        st.write("2/4 Transcribiendo para los subtítulos...")
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", audio_path], capture_output=True)
        segments_list = []
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_path, language=lang_code)
            segments_list = list(segments)
            st.write(f"Transcripción lista: {len(segments_list)} frases")
        except Exception as e:
            st.write("Sigo sin subtítulos, pero hago los clips igual.")

        # Carita del streamer de los primeros segundos, bien centrada
        st.write("2.5/4 Guardando la carita del streamer...")
        subprocess.run([
            "ffmpeg", "-y", "-ss", "2", "-i", video_path, "-t", "8",
            "-vf", "crop=ih*9/16:ih,scale=720:540",
            "-c:a", "aac", cara_path
        ], capture_output=True)

        st.write("3/4 Cortando 5 clips estilo RDjavi...")
        clips_bytes = []
        for i in range(5):
            start = i * 30
            out = os.path.join(tmp, f"clip_{i+1}.mp4")
            # Subtítulos solo para este clip de 30 seg
            clip_segs = [s for s in segments_list if s.start >= start and s.start < start+30]
            # Ajustamos tiempos para que empiecen en 0 en este clip
            for s in clip_segs:
                s.start -= start; s.end -= start
            crear_subtitulos_ass(clip_segs, ass_path)

            # Filtro: ARRIBA streamer 720x540 + ABAJO juego 720x740 = 720x1280
            # + cartel rojo en el medio + subtítulos
            filtro = (
                "[0:v]scale=720:540:force_original_aspect_ratio=increase,crop=720:540[top];"
                "[1:v]scale=720:740:force_original_aspect_ratio=increase,crop=720:740[bottom];"
                "[top][bottom]vstack=inputs=2[base];"
                f"[base]drawbox=x=270:y=500:w=180:h=50:color=red@0.95:t=fill,"
                f"drawtext=text='{nombre}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=28:fontcolor=white:x=360-text_w/2:y=512,"
                f"subtitles='{ass_path}'[v]"
            )
            subprocess.run([
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", cara_path,
                "-ss", str(start), "-i", video_path, "-t", "30",
                "-filter_complex", filtro,
                "-map", "[v]", "-map", "1:a", "-c:a", "aac", "-shortest", out
            ], capture_output=True)
            if os.path.exists(out):
                with open(out, "rb") as f:
                    clips_bytes.append((f"clip_{i+1}.mp4", f.read()))
                st.write(f"Clip {i+1} listo ✅")

        st.session_state.clips_guardados = clips_bytes
        st.success("¡Listo! Ya quedaron guardados, bajalos abajo.")

if st.session_state.clips_guardados:
    st.write("4/4 Bajalos acá 👇 - Ya no se van a borrar")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        for nombre_f, datos in st.session_state.clips_guardados:
            z.writestr(nombre_f, datos)
    st.download_button("⬇️ BAJAR LOS 5 CLIPS JUNTOS (ZIP)", zip_buffer.getvalue(), file_name="mis_5_clips.zip", mime="application/zip", type="primary")
    st.write("O uno por uno:")
    for nombre_f, datos in st.session_state.clips_guardados:
        st.download_button(f"⬇️ Bajar {nombre_f}", datos, file_name=nombre_f, mime="video/mp4")
