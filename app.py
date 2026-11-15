import streamlit as st
import os, subprocess, tempfile

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos.")

url = st.text_input("Link del video de Kick o YouTube")
idioma = st.selectbox("Idioma del video", ["Español", "English"])
lang_code = "es" if idioma == "Español" else "en"

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()

    st.info("⏳ Trabajando... No cierres esta pestaña, tarda 3-4 minutos.")

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")
        audio_path = os.path.join(tmp, "audio.mp3")

        # 1. Bajar solo 5 min en 480p - esto ya sabemos que anda
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

        # 2. Transcribir con faster-whisper (el que vos tenés)
        st.write("2/4 Transcribiendo audio para subtítulos...")
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", audio_path], capture_output=True)
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_path, language=lang_code)
            texto = " ".join([s.text for s in segments])
            st.write(f"Transcripción lista: {texto[:150]}...")
        except Exception as e:
            st.write(f"Sigo sin subtítulos, pero hago los clips igual: {e}")

        # 3. Hacer 5 clips de 30 seg, vertical 9:16
        st.write("3/4 Cortando 5 clips verticales...")
        clips = []
        for i in range(5):
            start = i * 30
            out = os.path.join(tmp, f"clip_{i+1}.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(start), "-i", video_path, "-t", "30",
                "-vf", "crop=ih*9/16:ih,scale=720:1280",
                "-c:a", "aac", out
            ], capture_output=True)
            if os.path.exists(out):
                clips.append(out)
                st.write(f"Clip {i+1} listo ✅")

        st.write("4/4 ¡Listo! Bajalos acá abajo 👇")
        for i, c in enumerate(clips):
            with open(c, "rb") as f:
                st.download_button(f"⬇️ Bajar Clip {i+1} (30 seg)", f, file_name=f"clip_{i+1}.mp4", mime="video/mp4")
