"""Run in a separate CUDA/Python 3.12 DeepSeek-OCR-2 environment."""

import json
from pathlib import Path
import re
import sys


def main() -> None:
    """Write one scanned page's OCR result for review before extraction can use it."""
    # Keep CUDA dependencies outside the normal HTML/native-PDF path.
    import torch
    from transformers import AutoModel, AutoTokenizer

    image, destination = map(Path, sys.argv[1:3])
    model_name = "deepseek-ai/DeepSeek-OCR-2"
    if not torch.cuda.is_available():
        raise RuntimeError("DeepSeek-OCR-2 requires its separate CUDA environment.")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name, trust_remote_code=True, use_safetensors=True,
        _attn_implementation="flash_attention_2",
    )
    model = model.eval().cuda().to(torch.bfloat16)
    result = model.infer(
        tokenizer, prompt="<image>\n<|grounding|>Convert the document to markdown. ",
        image_file=str(image), output_path=str(destination.parent), base_size=1024,
        image_size=768, crop_mode=True, save_results=True,
    )
    markdown = destination.parent / "result.mmd"
    text = markdown.read_text() if markdown.exists() else result if isinstance(result, str) else ""
    text = re.sub(r"<\|(?:ref|det)\|>.*?<\|/(?:ref|det)\|>", "", text, flags=re.S)
    if not text.strip():
        raise ValueError("DeepSeek returned no text.")
    # The extractor requires explicit approval after this text is checked against the page.
    record = {
        "model": model_name, "revision": getattr(model.config, "_commit_hash", None),
        "approved": False, "image": image.name, "text": text,
    }
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    temporary.replace(destination)


if __name__ == "__main__":
    main()
