import streamlit as st
import os, subprocess, requests, tempfile, re

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos con subtítulos.")

url = st.text_input("Link del video de Kick o YouTube")
idioma = st.selectbox("Idioma del video", ["Español", "English"])

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()

    st.info("⏳ Trabajando... No cierres esta pestaña, tarda 2-3 minutos.")

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")

        # Comando que sí anda en 2026 para YouTube y Kick
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-check-certificates",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "--add-header", "Referer: https://www.youtube.com/",
            # Esto es la clave: usa el cliente de Android, no necesita JavaScript
            "--extractor-args", "youtube:player_client=android,web",
            "--js-runtimes", "node:deno",
            "-f", "best",
            "-o", video_path,
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
            st.error("No pude descargar el video. Probá con otro link más corto.")
            st.code(res.stderr[-800:] if res.stderr else "archivo vacío")
            st.stop()

        st.success("¡Video descargado! Ya puedo hacer los clips.")
        st.write(f"Tamaño: {os.path.getsize(video_path)//1024} KB")
        st.video(video_path)
