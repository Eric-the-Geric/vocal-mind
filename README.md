# Vocal Mind

# Overview

Vocal Mind is a real-time transcription and text-to-speech orchestration tool that leverages the OpenAI API and local audio hardware. It streams microphone input for live transcription, applies prompt-based transcript cleanup, and converts text responses back into speech.

## Installation steps

TLDR;

 __on linux__
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your_openai_api_key"
cd eric/testing_sockets/ # assuming your in ./vocal-mind
python main.py
```
__on mac__
```bash
python3 -m venv env
source env/bin/activate
brew install portaudio # required by pyaudio to work on mac
pip install -r requirements.txt
export OPENAI_API_KEY="your_openai_api_key"
python eric/testing_sockets/main.py
```

Prerequisites:

- Python 3.13
- Homebrew (MacOS)

1. Create a virtual environment:
   ```bash
   python3 -m venv env
   ```
2. Activate the virtual environment:
   ```bash
   source env/bin/activate
   ```
3. Install dependencies (mac only):
    ```bash
    brew install portaudio
    ```
4. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
5. Provide the OpenAI API key:
   ```bash
   export OPENAI_API_KEY="your_openai_api_key"
   ```
# Roadmap & Improvements

| Area                     | Suggestions                                                                                      |
|--------------------------|--------------------------------------------------------------------------------------------------|
| **Docs & onboarding**    | Add a project-purpose section to this README; show end-to-end usage examples                      |
| **.gitignore hygiene**   | Don’t ignore `*.txt`/`*.wav` globally—only ignore generated outputs (e.g. `/outputs/*.wav`)      |
| **Module cleanup**       | Remove or implement `src/voice.py`; break `main.py` into smaller modules (e.g. `transcribe.py`) |
| **Configuration**        | Use a `.env` or config file for API key, model names, file paths; leverage `python-dotenv`      |
| **CLI & UX**             | Add `argparse` flags for modes (`--transcribe`, `--clean`, `--tts`); expose rate/chunk size      |
| **Prompt management**    | Version prompts; validate templates at startup                                                   |
| **Error handling & logs**| Standardize on one logging framework (`logging` or `loguru`); handle network or hardware errors  |
| **Testing & CI**         | Add unit tests for core logic; include CI for tests and linters                                  |
| **Packaging**            | Provide a `pyproject.toml` or `setup.py` for `pip install`; pin dependency versions               |
| **Repo hygiene**         | Move `outputs/` off-repo or trim it; add `/outputs/*` to `.gitignore`; remove large commits      |
| **Pre-commit & linting** | Add pre-commit with Black/isort/flake8/mypy; hook spellcheck for prompts                         |

In brief:
- Document the project purpose in this README (not just installation).
- Fix `.gitignore` to only ignore generated outputs, not all `.txt`/`.wav`.
- Modularize the code: split `main.py`, remove unused files, add CLI.
- Add tests and CI coverage for core functions and linting.

6. Run the application:
   ```bash
   python main.py
   ```

#TODO
Explore the openai AgentSDK, as it might be a faster pipeline to do the text-to-speech.
This will also allow me to explore the sdk more and potentially use it more of my applications



