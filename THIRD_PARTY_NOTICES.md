# Third-party notices

No third-party model weights or source trees are committed to the Git source history. The complete offline Windows release bundles pinned speech-model weights and runtime packages obtained from their upstream distributions. Their source identifiers, revisions, package versions, and applicable notices are included with that release.

## Default speech stack

- [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — Apache License 2.0. Provides the offline TTS runtime used by the default adapter.
- [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — Apache License 2.0 model distribution. The default installer obtains the `kokoro-multi-lang-v1_0` conversion from the official k2-fsa release and requires its bundled `LICENSE` before installation. The selected default voice is `zf_xiaoxiao` (speaker ID 47).
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) — MIT License. Used for optional local speech recognition and backed by CTranslate2 and other transitive dependencies with their own notices.
- [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small) — MIT-labelled converted Whisper model bundled by the complete offline release at the pinned revision recorded in `WHISPER-MODEL-MANIFEST.json`. Its MIT notice is included as `WHISPER-MODEL-LICENSE.txt`.

The license of a model implementation does not automatically settle rights in every dataset, checkpoint, speaker likeness, or generated output. Review the exact archive and intended distribution mode before bundling any weights.

## Optional speech components

- [myshell-ai/MeloTTS](https://github.com/myshell-ai/MeloTTS) — MIT-licensed upstream implementation retained only as a compatibility model option.
- [hexgrad/kokoro](https://github.com/hexgrad/kokoro) — optional Python pipeline; the default sherpa-onnx Kokoro path does not require this package.
- [hexgrad/misaki](https://github.com/hexgrad/misaki) — optional language front end used by Kokoro; its installed version retains its own license.
- [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) — optional external high-quality TTS service. It is not installed, copied, or started by this project.

## Application components

- [pywebview](https://github.com/r0x0r/pywebview) — optional desktop window.
- [keyring](https://github.com/jaraco/keyring) — operating-system credential store access.
- [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) — Microsoft's signed Evergreen Standalone Installer is included in the complete offline Windows release under `Prerequisites`.
- A separately installed [llama.cpp](https://github.com/ggml-org/llama.cpp) server may provide local OpenAI-compatible inference. It is not included here.

Before shipping an installer, generate a locked dependency inventory and include every applicable source and model license text. Also review the license of the selected GGUF model separately.
