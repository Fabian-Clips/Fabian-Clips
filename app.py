import streamlit as st
import os, subprocess, json, requests, tempfile, re

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos con subtítulos.")

url = st.text_input("Link del video de Kick o YouTube")
idioma = st.selectbox("Idioma del video", ["Español", "English"])

def get_kick_source(video_url):
    # Saca el ID del video de Kick: /videos/XXXX
    m = re.search(r"/videos/([a-f0-9\-]+)", video_url)
    if not m:
        return None
    vid_id = m.group(1)
    # Kick API v2 te da el link real mp4/m3u8
    try:
        r = requests.get(f"https://kick.com/api/v2/videos/{vid_id}", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        # puede venir en data['data']['source'] o data['source']
        d = data.get("data", data)
        src = d.get("source") or d.get("livestream", {}).get("playback_url")
        if src:
            return src
    except Exception as e:
        st.write(f"No pude usar API de Kick, pruebo con yt-dlp: {e}")
    return None

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()

    st.info("⏳ Trabajando... No cierres esta pestaña, tarda 2-3 minutos.")
    progress = st.progress(0, text="Descargando video...")

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")

        # 1. Si es Kick, intento por API primero
        kick_src = get_kick_source(url) if "kick.com" in url else None
        descargado = False

        if kick_src:
            progress.progress(20, text="Bajando desde Kick...")
            res = subprocess.run(["ffmpeg", "-y", "-i", kick_src, "-t", "600", "-c", "copy", video_path], capture_output=True, text=True)
            if os.path.exists(video_path) and os.path.getsize(video_path) > 1000:
                descargado = True

        # 2. Si no anduvo, uso yt-dlp con headers de navegador
        if not descargado:
            progress.progress(30, text="Probando con yt-dlp...")
            cmd = [
                "yt-dlp", "--no-playlist",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "--add-header", "Referer: https://kick.com/",
                "-f", "best[height<=720]/best",
                "--max-filesize", "800M",
                "-o", video_path,
                url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
                st.error(f"No pude descargar el video: {res.stderr[-500:] if res.stderr else 'archivo vacío'}")
                st.stop()

        progress.progress(50, text="Transcribiendo audio...")
        st.success("¡Video descargado! Ya puedo hacer los clips.")
        st.write(f"Tamaño: {os.path.getsize(video_path)//1024} KB")
        st.video(video_path)
        # Acá sigue tu código viejo de transcribir + cortar en 5 clips de 30 seg
        # Si querés, pegame el resto de tu app.py y te lo dejo completo con subtítulos
