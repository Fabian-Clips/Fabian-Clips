import streamlit as st
import os, subprocess, tempfile

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos con subtítulos.")

url = st.text_input("Link del video de Kick o YouTube")
idioma = st.selectbox("Idioma del video", ["Español", "English"])

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()

    st.info("⏳ Trabajando... No cierres esta pestaña.")

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")

        # CLAVE: solo 5 minutos, calidad 480p, max 250 MB
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--user-agent", "Mozilla/5.0",
            "--extractor-args", "youtube:player_client=android,web",
            "-f", "best[height<=480]",
            "--download-sections", "*00:00-00:05:00",
            "--max-filesize", "250M",
            "-o", video_path,
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
            st.error("No pude descargar. Probá con otro link.")
            st.code(res.stderr[-600:])
            st.stop()

        tamano_mb = os.path.getsize(video_path)//1024//1024
        st.success(f"¡Video descargado! Tamaño: {tamano_mb} MB - Ya puedo hacer los clips.")
        # NO mostramos el video entero acá, eso era lo que rompía todo
        st.write("Listo, ya bajó solo los primeros 5 minutos. Ahora sigue la parte de los clips.")
