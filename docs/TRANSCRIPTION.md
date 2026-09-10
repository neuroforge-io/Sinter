# Local transcription and review

[Back to Sinter](../README.md)

Sinter uses the optional **faster-whisper** engine to recognise speech locally. It then gives you a reviewable transcript, not automatically approved minutes. Audio is never sent to the Fracture API by the transcription workflow.

## First-time setup

Run `python3 setup_speech.py` from the Sinter source folder, or `py setup_speech.py` on Windows. Answer the installation prompt. The helper creates or uses `.venv`, installs the speech extra there and checks the engine import. Restart Sinter with its usual launcher so it uses that environment.

For manual installation into an existing virtual environment:

```sh
python -m pip install '.[speech]'
python start.py
```

Do not install into system Python with administrator privileges just to run Sinter. Packages and models can be sizeable. Allow for the download, free disk space and the memory required by your chosen model.

## Recording to reviewed minutes

1. Open **Meeting minutes** and expand **Start with an audio recording**. Use **Check transcription setup** to see whether the package is available in the running environment.
2. Choose the file, language and model. Confirm you have permission to process the recording. Separately authorise a model download on first use; cached models work offline.
3. Leave isolated-channel mode **off** for a room microphone or ordinary stereo mix. Enable it only when left and right really are separate microphone tracks. Sinter rejects mono input in this mode rather than inventing a second speaker.
4. Transcribe, then use the passage playback controls. The review-only filter highlights flagged passages; unflagged passages may also be wrong. Word probabilities are model confidence, not calibrated accuracy.
5. Assign labels to individual passages only after listening. Original labels are retained in the JSON. Use the speaker confirmation section to map those labels to names. A single unidentified recording is never automatically assigned to one person.
6. Prepare draft minutes. Use **Make a traceable transcript correction** for text changes; supply a reason. Confirm actual commitments, votes and decisions with the chair before issuing anything official.

Changing the selected audio file or leaving the page releases the local playback URL. The app does not retain the recording. Save your original audio separately; reconnect it yourself for later review. Temporary upload files are removed when processing finishes. Cancelling takes effect at the next processing checkpoint; model loading or a native decoding/inference call may finish first.

## Models and limits

`tiny` is a quick preview; `base` is a balanced starting point; `small` uses more resources. `.en` variants are English-only and cannot be combined with another language. Known-language selection helps avoid an unnecessary language guess. No model choice guarantees correct names, amounts or negation.

Browser uploads accept WAV, MP3, M4A, OGG, WebM, FLAC and MP4 up to **25 MB**. The CLI accepts a local file up to **500 MB**. Recordings longer than four hours or transcripts exceeding 3,000 passages / 200,000 text characters must be split. For practical memory use, split long recordings into shorter sessions before processing.

Browser playback support varies with codec and browser; a file may transcribe even when that browser cannot play it. Export WAV or FLAC with your audio editor when needed. PyAV handles decoding for faster-whisper; the package normally supplies its FFmpeg libraries without a separate system installation.

## Command-line use

Use the virtual environment's interpreter. On Linux/macOS:

```sh
.venv/bin/python -m sinter transcribe meeting.wav --consent --allow-download --language en --model base.en -o transcript.json
.venv/bin/python -m sinter transcribe meeting.wav --consent --language en --format srt -o transcript.srt
.venv/bin/python -m sinter transcribe separate-microphones.wav --consent --split-channels -o channels.json
```

On Windows, substitute `.venv\Scripts\python.exe`. Omit `--allow-download` once the model is cached. The CLI processes the recording for each invocation; use the browser's export buttons to obtain several formats from one run.

JSON is the lossless master: recognised text, model/engine version, word timings, flags, track labels and the audio SHA-256 are retained. TXT, SRT and VTT are convenient interchange formats, not complete evidence archives. Subtitle exports require real time ranges; Sinter does not invent them for untimed notes.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Package unavailable after installing | Restart using the project launcher. Installation and execution must use the same `.venv`. |
| Model will not load | Explicitly allow the first download; check connection and free disk space. Try `tiny`. |
| Native-library error | Check the installation output and platform support of faster-whisper/CTranslate2/PyAV. Python 3.11 is a useful separate environment to test with. Do not disable security controls. |
| No speech detected | Listen to the input, check microphone levels and track selection. Existing transcript text is not replaced by an empty result. |
| Wrong language | Select the known language. Do not use an English-only model for another language. |
| Repeated or implausible words | Review the audio. Try a clearer recording or another model. Do not let a language model silently repair the transcript. |
| Two channel labels for the same voice | Ordinary stereo does not imply isolated speakers. Repeat with channel separation off. |

## Scope and upstream references

The integration checks use short public upstream speech fixtures, two-channel audio, silence and malformed input. They do not establish accuracy on noisy rooms, overlapping speakers, accents or long meetings. Automatic mixed-room diarization and voice-based identity verification are absent.

Implementation references: [faster-whisper usage and requirements](https://github.com/SYSTRAN/faster-whisper), [transcription options](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py), and [stereo decoding](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/audio.py). The optional package is MIT-licensed; downloaded model and transitive dependency terms remain separate. Nothing in Sinter's Apache-2.0 licence relicenses those components.
