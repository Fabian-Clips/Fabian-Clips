import glob
import json
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
import streamlit as st
from faster_whisper import WhisperModel

CLIP_SECONDS = 30
NUM_CLIPS = 5

st.set_page_config(page_title="Clips para TikTok", page_icon="🎬")


# ---------- Utilidades ----------

def run(cmd, cwd=None):
    """Ejecuta un programa (ffmpeg, yt-dlp) y avisa si falla."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])
    return r.stdout


@st.cache_resource
def load_model():
    # "small" anda bien en cualquier compu. Si querés más precisión: "medium"
    return WhisperModel("small", device="cpu", compute_type="int8")


def download_video(url, folder):
    run([
        "yt-dlp", "-f", "mp4/best", "--merge-output-format", "mp4",
        "--no-playlist", "-o", os.path.join(folder, "original.%(ext)s"), url,
    ])
    files = glob.glob(os.path.join(folder, "original.*"))
    if not files:
        raise RuntimeError("No pude descargar el video.")
    return files[0]


def probe(path):
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", path,
    ])
    data = json.loads(out)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"]), float(data["format"]["duration"])


def extract_audio(video, folder):
    wav = os.path.join(folder, "audio.wav")
    run(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav])
    return wav


def loudness_per_second(wav_path):
    with wave.open(wav_path, "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = len(data) // rate
    if n == 0:
        return np.zeros(1)
    data = data[: n * rate].reshape(n, rate)
    return np.sqrt((data ** 2).mean(axis=1))


def transcribe(model, wav_path, language):
    segments, _ = model.transcribe(
        wav_path, word_timestamps=True, language=language, vad_filter=True
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append((w.start, w.end, w.word.strip()))
    return words


# ---------- Elegir los mejores momentos ----------

def pick_moments(duration, words, loudness):
    """Puntúa cada ventana de 30s por cantidad de habla + volumen y elige las mejores."""
    clip_len = min(CLIP_SECONDS, duration)
    if duration <= CLIP_SECONDS:
        return [0.0], clip_len

    n = int(np.ceil(duration))

    def fit(a):
        a = np.asarray(a, dtype=np.float32)[:n]
        return np.pad(a, (0, n - len(a)))

    speech = np.zeros(n, dtype=np.float32)
    for start, _, _ in words:
        speech[min(int(start), n - 1)] += 1
    loud = fit(loudness)

    def norm(a):
        m = a.max()
        return a / m if m > 0 else a

    per_second = 0.6 * norm(speech) + 0.4 * norm(loud)
    cum = np.concatenate([[0], np.cumsum(per_second)])

    last_start = int(duration - clip_len)
    candidates = [(cum[s + int(clip_len)] - cum[s], s) for s in range(last_start + 1)]
    candidates.sort(reverse=True)

    # Separación mínima entre clips (si el video es corto, se permite algo de solapamiento)
    if duration >= clip_len * NUM_CLIPS:
        gap = clip_len
    else:
        gap = max(5.0, (duration - clip_len) / (NUM_CLIPS - 1))

    chosen = []
    for _, s in candidates:
        if all(abs(s - c) >= gap for c in chosen):
            chosen.append(s)
        if len(chosen) == NUM_CLIPS:
            break
    return [float(c) for c in chosen], clip_len


# ---------- Subtítulos estilo TikTok ----------

def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(words, start, length, width, height, path):
    font_size = int(width * 0.09)
    outline = max(4, int(width * 0.008))
    margin_v = int(height * 0.22)
    margin_x = int(width * 0.06)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},0,2,{margin_x},{margin_x},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    clip_words = [
        (s - start, e - start, w)
        for s, e, w in words
        if s >= start and s < start + length and w
    ]
    lines = []
    for i in range(0, len(clip_words), 3):  # 3 palabras por pantalla
        group = clip_words[i:i + 3]
        g_start = group[0][0]
        g_end = group[-1][1]
        if i + 3 < len(clip_words):
            g_end = max(g_end, min(clip_words[i + 3][0], g_end + 0.4))
        text = " ".join(w for _, _, w in group).upper().replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{ass_time(g_start)},{ass_time(g_end)},Default,,0,0,0,,{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")


def render_clip(video, folder, idx, start, length, words, width, height):
    ass_name = f"sub{idx}.ass"
    out_name = f"clip{idx}.mp4"
    build_ass(words, start, length, width, height, os.path.join(folder, ass_name))
    run([
        "ffmpeg", "-y", "-ss", str(start), "-i", os.path.basename(video),
        "-t", str(length), "-vf", f"ass={ass_name}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart", out_name,
    ], cwd=folder)
    return os.path.join(folder, out_name)


# ---------- Pantalla ----------

st.title("🎬 Generador de clips para TikTok")
st.write("Pegá el link, y te armo 5 clips de 30 segundos con subtítulos.")

url = st.text_input("Link del video de TikTok")
idioma = st.selectbox("Idioma del video", ["Automático", "Español", "Inglés"])
codigo_idioma = {"Automático": None, "Español": "es", "Inglés": "en"}[idioma]

if st.button("Generar clips", type="primary"):
    if not url.strip():
        st.warning("Primero pegá un link.")
    else:
        if st.session_state.get("workdir"):
            shutil.rmtree(st.session_state["workdir"], ignore_errors=True)
        folder = tempfile.mkdtemp(prefix="clips_")
        st.session_state["workdir"] = folder
        st.session_state["clips"] = []
        try:
            with st.status("Trabajando...", expanded=True) as status:
                st.write("⬇️ Descargando el video...")
                video = download_video(url.strip(), folder)
                width, height, duration = probe(video)

                st.write("🔊 Analizando el audio...")
                wav = extract_audio(video, folder)
                loud = loudness_per_second(wav)

                st.write("📝 Transcribiendo con Whisper (la primera vez tarda más)...")
                words = transcribe(load_model(), wav, codigo_idioma)

                st.write("⭐ Buscando los mejores momentos...")
                starts, length = pick_moments(duration, words, loud)

                clips = []
                for i, s in enumerate(starts, start=1):
                    st.write(f"✂️ Armando clip {i} de {len(starts)}...")
                    path = render_clip(video, folder, i, s, length, words, width, height)
                    clips.append({"path": path, "start": s, "length": length})
                st.session_state["clips"] = clips
                status.update(label="¡Listo!", state="complete")
        except Exception as e:
            st.error(f"Algo falló: {e}")

for i, clip in enumerate(st.session_state.get("clips", []), start=1):
    minutos, segundos = divmod(int(clip["start"]), 60)
    st.subheader(f"Clip {i}  (desde {minutos}:{segundos:02d})")
    st.video(clip["path"])
    with open(clip["path"], "rb") as f:
        st.download_button(
            f"⬇️ Descargar clip {i}", f.read(),
            file_name=f"clip_{i}.mp4", mime="video/mp4", key=f"dl{i}",
      )
