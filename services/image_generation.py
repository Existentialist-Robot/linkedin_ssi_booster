from typing import Any
import os

# ---------------------------------------------------------------------------
# Backend dispatcher
# ---------------------------------------------------------------------------
# IMAGE_BACKEND env var selects the engine. Default: "flux".
# Both Claude Code and Codex CLI run scripts directly — no image API key needed.
# Add new backends here as the toolchain grows.

def generate_image(
    prompt: str,
    output_path: str = "data/output.png",
    width: int = 1024,
    height: int = 1024,
    backend: str | None = None,
    **kwargs,
) -> str:
    """
    Backend-agnostic dispatcher. Extra kwargs forwarded to the backend.
    backend: "flux" (default via IMAGE_BACKEND env var)
    """
    backend = (backend or os.environ.get("IMAGE_BACKEND", "flux")).lower()
    if backend == "flux":
        return generate_flux_image(prompt=prompt, output_path=output_path,
                                   width=width, height=height, **kwargs)
    raise ValueError(f"Unknown IMAGE_BACKEND: '{backend}'. Supported: flux")


# ---------------------------------------------------------------------------
# FLUX.1-schnell (local GGUF — runs on RTX 4070 8GB, no runtime API key)
# ---------------------------------------------------------------------------

_HF_BASE_MODEL = os.environ.get("FLUX_HF_BASE_MODEL", "black-forest-labs/FLUX.1-schnell")


def generate_flux_image(
    prompt: str,
    output_path: str = "data/output.png",
    model_dir: str | None = None,
    width: int = 1024,
    height: int = 1024,
    num_inference_steps: int = 4,
    step_pause_ms: int = 0,
) -> str:
    """
    Generate via FLUX.1-schnell GGUF (local GPU).

    model_dir: folder containing flux1-schnell-Q4_K_S.gguf.
               Defaults to FLUX_MODEL_DIR env var → 'models/flux' → '/app/models/flux'.
    step_pause_ms: sleep ms between diffusion steps to yield to the WDDM display
                   driver. 0 = no throttle. Use 200 when Chrome or other GPU-sharing
                   apps are open. Also caps VRAM at 85% when non-zero.

    HF_TOKEN is only needed on the first run to download pipeline components
    (~15 GB cached to ~/.cache/huggingface). Subsequent runs are fully offline.
    """
    import torch
    from diffusers import FluxPipeline, FluxTransformer2DModel, GGUFQuantizationConfig

    if model_dir is None:
        model_dir = os.environ.get(
            "FLUX_MODEL_DIR",
            "models/flux" if os.path.isdir("models/flux") else "/app/models/flux",
        )

    if step_pause_ms > 0 and torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(0.85)

    transformer_path = os.path.join(model_dir, "flux1-schnell-Q4_K_S.gguf")
    local_config = os.path.join(model_dir, "transformer_config.json")
    hf_token = os.environ.get("HF_TOKEN") or None

    print(f"--- Loading FLUX from {transformer_path} ---")

    transformer_kwargs: dict = {
        "quantization_config": GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        "torch_dtype": torch.bfloat16,
    }
    if os.path.isfile(local_config):
        transformer_kwargs["config"] = local_config
    elif hf_token:
        transformer_kwargs["token"] = hf_token

    transformer = FluxTransformer2DModel.from_single_file(transformer_path, **transformer_kwargs)

    pipe = FluxPipeline.from_pretrained(
        _HF_BASE_MODEL,
        transformer=transformer,
        torch_dtype=torch.bfloat16,
        token=hf_token,
    )
    pipe.enable_model_cpu_offload()

    print(f"--- Generating: {prompt[:50]}... ---")

    with torch.inference_mode():
        result: Any = pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=0.0,
            max_sequence_length=256,
        )
        image = result.images[0]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    image.save(output_path)
    print(f"--- Saved: {output_path} ---")

    del pipe, transformer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()

    return output_path
