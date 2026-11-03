"""Less VRAM for the voice (28.10), so the brain gets room for its hot experts while Neira speaks.

1. The talker's text embedding table (151936 x 2048, 593 MiB) moves to the CPU: it is read only while a sentence is
   being prepared (its tokens, a fraction of a millisecond), never inside the CUDA graphs of the audio frames.
2. The talker's layer matrices (q/k/v/o/gate/up/down, the same ones the LoRAs train) become int8 with one bf16 scale
   per output row (symmetric, absmax): ~1460 MiB less. The matrix is turned back to bf16 for each product, inside the
   graphs, one layer at a time.
LoRA voices (sounds, colleague) are merged into the int8 weights like MergeVoices does it in bf16: q := round((q*s +
B@A) / s) with the row scales kept, and the exact main int8 values are copied back from a pinned CPU copy on return.
Apply right after FasterQwen3TTS.from_pretrained and before the first generation (the graphs are captured then)."""
import re
import time

import torch
from safetensors.torch import load_file

import int8_gemv

import os
DEQUANT = os.environ.get("INT8_KERNEL") == "dequant"
LAYERS = re.compile(r"(q|k|v|o|gate|up|down)_proj$")


class CpuEmbedding(torch.nn.Module):
    def __init__(self, emb, device):
        super().__init__()
        self.cpu_weight = emb.weight.detach().to("cpu").clone()   # plain RAM (not pinned: Windows may page it out when RAM is short); a plain attribute: .to() leaves it here
        self.device, self.embedding_dim = device, emb.embedding_dim

    @property
    def weight(self):
        return self.cpu_weight

    def forward(self, ids):
        return torch.nn.functional.embedding(ids.to("cpu"), self.cpu_weight).to(self.device, non_blocking=True)


# 29.10: one scale per GROUP weights of a row, like llama.cpp's Q8_0 (blocks of 32, fp16 scale) - one scale per
# whole row (2048 weights) rounded the small weights away and the author heard her melody go flat. 0 = per row.
GROUP = int(os.environ.get("INT8_GROUP", "32"))


class Int8Linear(torch.nn.Module):
    def __init__(self, lin):
        super().__init__()
        w = lin.weight.detach().float()
        n, k = w.shape
        g = GROUP if GROUP and k % GROUP == 0 else k
        wg = w.view(n, k // g, g)
        scale = (wg.abs().amax(2, keepdim=True) / 127).clamp_min(1e-8)
        self.register_buffer("q", torch.round(wg / scale).clamp(-127, 127).to(torch.int8).view(n, k))
        self.register_buffer("s", scale.view(n, k // g).to(torch.float16))
        self.group = g
        self.bias = lin.bias
        self.in_features, self.out_features = lin.in_features, lin.out_features

    def scales(self, rows=slice(None)):
        """The scales spread over every weight of the given rows: [rows, K] float32."""
        return self.s[rows].float().repeat_interleave(self.group, dim=1)

    def weight_bf16(self, dtype):
        return (self.q.float() * self.scales()).to(dtype)

    def forward(self, x):
        x2 = x.reshape(-1, x.shape[-1])
        if x2.shape[0] <= 4 and not DEQUANT:   # the one-frame steps: our fused Triton kernel (int8_gemv.py)
            big_k = x2.shape[1] > 2048
            y = int8_gemv.gemv(x2.contiguous(), self.q, self.s, 8 if big_k else 16, 512 if big_k else 256)
            y = y.view(*x.shape[:-1], -1)
            return y if self.bias is None else y + self.bias
        return torch.nn.functional.linear(x, self.weight_bf16(x.dtype), self.bias)   # prefill: a whole sentence


def shrink(root, int8=True):
    """root = model.model.model (the Qwen3-TTS model with .talker) -> MiB freed."""
    dev = next(root.parameters()).device
    before = torch.cuda.memory_allocated()
    talker = root.talker
    inner = talker.model
    inner.text_embedding = CpuEmbedding(inner.text_embedding, dev)
    if int8:
        for name, mod in list(inner.layers.named_modules()):   # not the code predictor: it runs 15x per frame
            for child, sub in list(mod.named_children()):
                if isinstance(sub, torch.nn.Linear) and LAYERS.search(child):
                    setattr(mod, child, Int8Linear(sub))
    # the freed bf16 matrices sit in the same allocator segments as weights that stay, so the VRAM would not go back
    # to the system (reserved stayed ~5 GB): move everything out and back in, packed
    root.to("cpu")
    torch.cuda.empty_cache()
    root.to(dev)
    return (before - torch.cuda.memory_allocated()) / 2 ** 20


ROWS = 512   # rows per block when a LoRA voice is merged into the weights (small temporaries)
MAIN = {}   # id(tensor) -> its main-voice values in pinned RAM, ONE copy for every LoRA voice (sounds, colleague)


def main_copy(t):
    """The main voice's values of a layer, shared: each LoRA voice used to keep its own (2 x ~1.8 GB of pinned RAM,
    which Windows cannot page out - the brain's experts were paged out instead). Taken at start, main voice active."""
    if id(t) not in MAIN:
        MAIN[id(t)] = (t, t.detach().cpu().clone())   # plain RAM, not pinned (29.10: ~25 GB was unpageable with the locked brain)
    return MAIN[id(t)][1]


class Int8MergeVoices:
    """MergeVoices for int8 layers: same interface (use("sounds"/"main") -> seconds, .active, .layers)."""

    def __init__(self, root, lora_path):
        dev = next(root.parameters()).device
        f = load_file(lora_path, device=str(dev))
        self.items = []
        for key in sorted(k[: -len(".weight.lora_A")] for k in f if k.endswith(".weight.lora_A")):
            mod = root.get_submodule(key)   # int8 (main talker layers) or a plain bf16 Linear (code predictor)
            t = mod.q if isinstance(mod, Int8Linear) else mod.weight
            self.items.append((mod, t, f[key + ".weight.lora_A"], f[key + ".weight.lora_B"], main_copy(t)))
        self.layers, self.fixed, self.active = len(self.items), 0, "main"

    @torch.inference_mode()
    def use(self, which):
        if which == self.active:
            return 0.0
        t0 = time.time()
        for mod, t, A, B, orig in self.items:
            if which == "main":
                t.copy_(orig, non_blocking=True)
                continue
            # in row blocks of ROWS: one fp32 block of a whole layer is 50 MB, and with the GPU nearly full (game +
            # brain) those temporaries made Windows shuffle memory - the switch took 2.8 s instead of ~0.3 s. The
            # way back is a copy of the main values, so this side need not be bit-exact (TF32 is fine).
            Bf, Af = B.float(), A.float()
            for r in range(0, t.shape[0], ROWS):
                d = Bf[r:r + ROWS] @ Af
                if not isinstance(mod, Int8Linear):
                    t[r:r + ROWS].copy_(d.add_(t[r:r + ROWS]))
                else:
                    s = mod.scales(slice(r, r + ROWS))
                    t[r:r + ROWS].copy_(torch.round(d.addcmul_(t[r:r + ROWS].float(), s).div_(s)).clamp_(-127, 127)
                                        .to(torch.int8))
        torch.cuda.synchronize()
        self.active = which
        return time.time() - t0
