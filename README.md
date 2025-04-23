# Installation steps

TLDR;

```bash
python3 -m venv env
source env/bin/activate
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
3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Provide the OpenAI API key:
   ```bash
   export OPENAI_API_KEY="your_openai_api_key"
   ```
5. Run the application:
   ```bash
   python eric/testing_sockets/main.py
   ```
