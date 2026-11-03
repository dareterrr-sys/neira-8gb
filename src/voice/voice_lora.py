"""The sounds version of Neira's voice as a LoRA on top of the main voice, switched on and off instantly.

The sounds version was trained FROM the main one (train_lora.py --init_weights), so it is the main weights plus a rank-32
update per layer; extract_lora.py recovers that update (A, B). Here every such layer becomes base(x) + on * B(A(x)),
where `on` is ONE GPU number shared by all layers. The CUDA graphs of faster-qwen3-tts read it on every replay, so
switching voices is writing 1 or 0 into it: no weight copies (~75 MB of extra VRAM, a few % slower generation).
Attach BEFORE model.warmup() (that is when the graphs are captured).
"""
import time

import torch
from safetensors.torch import load_file


class LoraToggle(torch.nn.Module):
    def __init__(self, base, A, B, on):
        super().__init__()
        self.base, self.on = base, on
        self.A = torch.nn.Parameter(A, requires_grad=False)
        self.B = torch.nn.Parameter(B, requires_grad=False)

    def forward(self, x):
        return self.base(x) + self.on * torch.nn.functional.linear(torch.nn.functional.linear(x, self.A), self.B)


class LoraVoices:
    def __init__(self, root, lora_path):
        p = next(root.parameters())
        self.on = torch.zeros((), device=p.device, dtype=p.dtype)
        f = load_file(lora_path, device=str(p.device))
        names = sorted({k[: -len(".weight.lora_A")] for k in f if k.endswith(".lora_A")})
        for name in names:
            parent, child = name.rsplit(".", 1)
            mod = root.get_submodule(parent)
            setattr(mod, child, LoraToggle(getattr(mod, child), f[name + ".weight.lora_A"].to(p.dtype),
                                           f[name + ".weight.lora_B"].to(p.dtype), self.on))
        self.active, self.layers = "main", len(names)

    def use(self, which):
        """"sounds" or "main"; returns the seconds spent (0: nothing to copy)."""
        if which != self.active:
            self.on.fill_(1.0 if which == "sounds" else 0.0)
            self.active = which
        return 0.0


class MergeVoices:
    """Same LoRA, but switched by adding B@A INTO the layer weights in place (and subtracting it to go back), so the
    graphs run the plain weights: no slowdown (LoraToggle's ~2900 tiny extra kernels per audio frame cost +36%), a switch
    takes ~0.25 s on the GPU instead of 2.4-3.5 s of copying from the checkpoint file. In bf16, round(round(W+D)-D)
    is W except for ~1% of the weights (those next to a power of two), always the same ones: their exact main values
    are found once at start and put back after every return, so the main voice stays bit-exact."""

    def __init__(self, root, lora_path):
        p0 = next(root.parameters())
        f = load_file(lora_path, device=str(p0.device))
        params = dict(root.named_parameters())
        self.items, fixed = [], 0
        with torch.inference_mode():
            for key in sorted(k[: -len(".lora_A")] for k in f if k.endswith(".lora_A")):
                p, A, B = params[key], f[key + ".lora_A"], f[key + ".lora_B"]
                back = p.clone()   # the very same steps as a real switch there and back
                self._shift(back, A, B, 1.0)
                self._shift(back, A, B, -1.0)
                idx = (back != p).flatten().nonzero().flatten()
                vals = p.flatten()[idx]
                self.items.append((p, A, B, idx.to(torch.int32).cpu().pin_memory(), vals.cpu().pin_memory()))
                fixed += len(idx)
                del back
        torch.cuda.empty_cache()
        self.layers, self.fixed, self.active = len(self.items), fixed, "main"

    @classmethod
    def _shift(cls, p, A, B, sign):
        """p := round_bf16(p ± B@A), with one fp32 buffer of p's size (the GPU is nearly full while the brain runs)."""
        d = cls._delta(A, B)
        if sign < 0:
            d.neg_()
        d.add_(p)
        p.copy_(d)

    @staticmethod
    def _delta(A, B):
        """B@A in full fp32 every time (the exact return to the main voice needs the very same numbers; TF32 would
        change them if something switched it on in between)."""
        prev = torch.backends.cuda.matmul.allow_tf32
        torch.backends.cuda.matmul.allow_tf32 = False
        try:
            return B.float() @ A.float()
        finally:
            torch.backends.cuda.matmul.allow_tf32 = prev

    @torch.inference_mode()
    def use(self, which):
        """"sounds" or "main"; returns the seconds spent."""
        if which == self.active:
            return 0.0
        t0, sign = time.time(), (1.0 if which == "sounds" else -1.0)
        for p, A, B, idx, vals in self.items:
            self._shift(p, A, B, sign)
            if which == "main" and len(idx):
                p.view(-1)[idx.to(p.device, non_blocking=True).long()] = vals.to(p.device, non_blocking=True)
        torch.cuda.synchronize()
        self.active = which
        return time.time() - t0
