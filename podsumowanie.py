# Import bibliotek
import streamlit as st
import io
import os
import tempfile
import shutil
from pydub import AudioSegment
from dotenv import dotenv_values
from openai import OpenAI
from yt_dlp import YoutubeDL

# Konfiguracja strony
st.set_page_config(page_title="Podsumowanie Audio lub Wideo", layout="centered")

# Pomocnicze zmienne w session_state
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# Tytuł
st.markdown("<h1 style='text-align:center;'>Podsumowanie Audio lub Wideo</h1>", unsafe_allow_html=True)

# Opis programu
with st.expander("📖 **Opis programu** *(kliknij aby rozwinąć)*"):
    st.markdown("""
    Program umożliwia użytkownikowi przetwarzanie materiałów audio i wideo w celu automatycznego wygenerowania transkrypcji oraz krótkiego podsumowania treści. Dodatkowo użytkownik może odsłuchać podsumowanie w formie pliku audio lub pobrać je jako tekst lub plik mp3.
    """)

# Instrukcja
with st.expander("📖 **Instrukcja obsługi** *(kliknij aby rozwinąć)*"):
    st.markdown("""
    ***Wymagane wprowadzenie klucza OpenAI przez użytkownika!***
    1. Wybierz plik lub wklej link YouTube.  
    2. Odsłuchaj audio i obejrzyj wideo.  
    3. Wygeneruj transkrypcję (Whisper AI) i podsumowanie (GPT).  
    4. Pobierz tekst lub odsłuchaj podsumowanie za pomocą modelu TTS.
    """)

# ----------------------------------------
# Inicjalizacja klienta OpenAI bez klucza
openai_client = st.text_input("🔑 Wpisz swój klucz OpenAI", type="password")

if not openai_client:
    st.warning("Podaj swój własny klucz OpenAI, aby uruchomić aplikację.")
    st.stop()

# Tworzenie klienta OpenAI
openai_client = OpenAI(api_key=openai_client)

# Testowanie klucza OpenAI
try:
    openai_client.models.list()  # test połączenia
    st.success("✅ Klucz zaakceptowany! Możesz korzystać z aplikacji.")
except Exception as e:
    st.error(f"❌ Błąd: nieprawidłowy klucz OpenAI ({e})")
    st.stop()
# ----------------------------------------

st.divider()

# Pole wyboru: plik z dysku albo link YouTube
st.markdown("### 📂 Wybierz źródło wideo/audio")
source = st.radio("Źródło:", ["Plik z dysku", "Link YouTube"])

video_file = None

# Opcja 1 – upload z dysku
if source == "Plik z dysku":
    video_file = st.file_uploader(
        "🎥 **Wybierz plik wideo lub audio:**",
        type=["mp4", "mov", "avi", "mkv", "mp3", "wav"],
        key=f"uploader_{st.session_state.uploader_key}",
    )

# Opcja 2 – link YouTube
elif source == "Link YouTube":
    youtube_url = st.text_input("🔗 Wklej link do filmu z YouTube:")
    if youtube_url:
        try:
            # utwórz tymczasowy katalog do pobrania
            temp_dir = tempfile.mkdtemp(prefix="yt_")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)

            # spróbuj znaleźć wynikowy plik .mp3 w temp_dir
            mp3_path = None
            for fname in os.listdir(temp_dir):
                if fname.lower().endswith(".mp3"):
                    mp3_path = os.path.join(temp_dir, fname)
                    break

            if mp3_path is None:
                raise RuntimeError("Nie znaleziono pliku MP3 w katalogu tymczasowym po pobraniu.")

            # wczytaj do pamięci
            with open(mp3_path, "rb") as f:
                buffer = io.BytesIO(f.read())
            buffer.name = "youtube_audio.mp3"
            buffer.seek(0)
            video_file = buffer

            st.success("✅ Pobrano i skonwertowano audio z YouTube")
            # wyświetl podgląd wideo (embed)
            st.video(youtube_url)

        except Exception as e:
            st.error(f"❌ Błąd pobierania z YouTube: {e}")
            # dodatkowa wskazówka jeśli to najczęstszy problem (ffmpeg)
            if "ffmpeg" in str(e).lower() or "ffprobe" in str(e).lower():
                st.info("Wygląda na problem z ffmpeg. Upewnij się, że ffmpeg jest zainstalowany i w PATH.")
        finally:
            # sprzątanie (usuń temp_dir jeśli istnieje)
            try:
                if os.path.isdir(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception:
                pass

# --------------------------------
# Obsługa wybranego pliku
if video_file is not None:
    video_file.seek(0)

    # Wyodrębnienie audio
    audio = AudioSegment.from_file(video_file)
    audio_buffer = io.BytesIO()
    audio.export(audio_buffer, format="mp3")
    audio_buffer.seek(0)
    audio_buffer.name = "audio.mp3"

    st.markdown("<h3 style='color:orange;'>🔊 Odtwarzanie audio</h3>", unsafe_allow_html=True)
    st.audio(audio_buffer, format="audio/mp3")

    # Generowanie napisów model whisper-1
    if "last_file" not in st.session_state or st.session_state.last_file != video_file.name:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer,
            response_format="text",
        )
        st.session_state.edited_text = transcript
        st.session_state.last_file = video_file.name

        # Generowanie podsumowania
        summary_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś asystentem, który tworzy krótkie i zwięzłe podsumowania tekstu."},
                {"role": "user", "content": f"Streść poniższy tekst:\n\n{transcript}"}
            ],
            max_tokens=300,
        )
        st.session_state.summary_text = summary_response.choices[0].message.content
        st.session_state.summary_audio = None  # reset audio za każdym nowym plikiem

    # Wyświetlanie testu
    st.markdown("<h3 style='color:purple;'>💬 Pobrany tekst z Audio</h3>", unsafe_allow_html=True)
    st.markdown(st.session_state.edited_text)

    # Wyświetlanie podsumowania
    if "summary_text" in st.session_state:
        st.markdown("<h3 style='color:blue;'>📌 Podsumowanie</h3>", unsafe_allow_html=True)
        st.text_area("Podsumowanie", value=st.session_state.summary_text, height=200)

        # Przyciski w jednej linii
        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                label="📥 Pobierz tekst podsumowania",
                data=st.session_state.summary_text,
                file_name="podsumowanie.txt",
                mime="text/plain"
            )

        with col2:
            if st.button("🎵 Przeczytaj podsumowanie"):
                response = openai_client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    response_format="mp3",
                    input=st.session_state.summary_text,
                )
                audio_summary = io.BytesIO(response.read())
                audio_summary.name = "summary.mp3"
                st.session_state.summary_audio = audio_summary
                st.audio(audio_summary, format="audio/mp3")

        with col3:
            if st.session_state.get("summary_audio") is not None:
                st.download_button(
                    label="⬇️ Pobierz plik audio z podsumowaniem",
                    data=st.session_state.summary_audio,
                    file_name="podsumowanie.mp3",
                    mime="audio/mpeg"
                )
st.divider()
# Przycisk: Wczytaj kolejne wideo
if st.button("➕ Wczytaj kolejne wideo", type="primary", use_container_width=True):
    for key in ["last_file", "edited_text", "summary_text", "summary_audio"]:
        st.session_state.pop(key, None)
    st.session_state.uploader_key += 1
    st.rerun()