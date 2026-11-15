import os
import subprocess
import streamlit as st
import yt_dlp

st.set_page_config(page_title="Generador de clips para TikTok")
st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos con subtítulos.")

url = st.text_input("Link del video de Kick")
idioma = st.selectbox("Idioma del video", ["Español", "Automático"])
idioma_code = "es" if idioma == "Español" else None

if st.button("Generar clips"):
    if not url:
        st.warning("Pegá un link primero")
        st.stop()

    st.info("⏳ Trabajando... No cierres esta pestaña, tarda 2-3 minutos.")
    st.write("1/4 Descargando el video...")

    os.makedirs("work", exist_ok=True)
    video_path = "work/video.mp4"
    if os.path.exists(video_path):
        os.remove(video_path)

    ydl_opts = {
        "format": "best[height<=720]/best",
        "outtmpl": video_path,
        "quiet": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        st.error(f"No pude descargar el video: {e}")
        st.stop()

    st.write("2/4 Analizando el audio...")

    # Extraer audio para Whisper
    audio_path = "work/audio.wav"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", audio_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    st.write("3/4 Transcribiendo con Whisper (la primera vez tarda más)...")

    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language=idioma_code, word_timestamps=True)

    # Guardar subtítulos y juntar texto por segundos
    srt_path = "work/subs.srt"
    all_words = []
    with open(srt_path, "w", encoding="utf-8") as f:
        idx = 1
        for seg in segments:
            for w in getattr(seg, "words", []) or []:
                all_words.append((w.start, w.end, w.word.strip()))
            start = seg.start
            end = seg.end
            text = seg.text.strip()
            def fmt(t):
                h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int((t % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{idx}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")
            idx += 1

    if not all_words:
        st.error("No detecté voz en este video. Probá con otro link.")
        st.stop()

    st.write("4/4 Cortando los 5 clips verticales...")

    # Duración total
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                         capture_output=True, text=True)
    try:
        total = float(dur.stdout.strip())
    except:
        total = 150

    clips = []
    for i in range(5):
        start = i * 30
        if start >= total:
            break
        out = f"work/clip_{i+1}.mp4"
        # Vertical 1080x1920, recorta centro, quema subtítulos
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", "30", "-i", video_path,
               "-vf", f"crop=ih*9/16:ih,scale=1080:1920,subtitles={srt_path}:force_style='Fontsize=28,PrimaryColour=&HFFFFFF&,Outline=2,Shadow=1,Alignment=2,MarginV=150'",
               "-c:a", "aac", out]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(out):
            clips.append(out)

    st.success(f"¡Listo! Te generé {len(clips)} clips.")
    for i, c in enumerate(clips, 1):
        st.write(f"### Clip {i} - {i*30}s a {(i*30)+30}s")
        st.video(c)
        with open(c, "rb") as f:
            st.download_button(f"⬇️ Descargar Clip {i}", f, file_name=f"clip_{i}.mp4", mime="video/mp4", key=f"dl{i}")
