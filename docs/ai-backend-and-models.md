# AI Backend and Models

All generation in the project uses Ollama as a locally running LLM server, which means no cloud AI keys are required for the main writing workflow. The README presents Ollama as the foundation for local post generation and recommends tuning model choice and context window based on quality and available memory.

## Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gemma4:26b
```

The documented setup also mentions macOS and Windows installers from `https://ollama.com/download`, followed by `.env` configuration through `OLLAMA_MODEL` and `OLLAMA_NUM_CTX`.

## Recommended models

The README recommends `gemma4:26b` for best post quality, and lists `qwen2.5:14b`, `llama3.2`, and `mistral-nemo` as smaller or faster alternatives. It also characterizes `qwen2.5:14b` as a strong fallback when VRAM is constrained and `llama3.2` as the fastest but lower-quality option.

| Model          | Positioning                                                     |
| -------------- | --------------------------------------------------------------- |
| `gemma4:26b`   | Recommended for best quality and stronger long-prompt behavior. |
| `qwen2.5:14b`  | Strong fallback with lower memory requirements.                 |
| `llama3.2`     | Fastest option with lower output quality.                       |
| `mistral-nemo` | Additional supported alternative.                               |

## Context sizing

The README recommends `OLLAMA_NUM_CTX=16384` as the baseline for persona-heavy grounded prompts, with `8192` suggested when memory or latency is tight and `32768` suggested only when logs show truncation or degraded long-context behavior. This guidance is tied directly to the large prompt footprint created by persona, grounding, and curation context.

## One-off override

The active model can also be overridden for a single run by prefixing the command with an `OLLAMA_MODEL` environment override. This is useful when comparing speed or quality without editing `.env`.

```bash
OLLAMA_MODEL=llama3.2 python main.py --curate --dry-run
```
