"""Park the voice in RAM instead of quitting (28.10): a hard turn gives the GPU to the brain, and the voice used to come
back by a full restart (~33 s: load, int8, LoRAs, warm-up). Parked, its weights wait in pinned RAM and come back over
PCIe in a fraction of a second; only the CUDA graphs are captured again (their pointers die with the old memory),
which the next generation does by itself (~1-2 s). The tensors keep their identity (.data is swapped), so the LoRA
mergers and the mood vector, which hold them, keep working."""
import gc
import time

import torch


class Parking:
    def __init__(self, fast_model):
        self.fm = fast_model
        self.mods = [m for m in vars(fast_model.model).values() if isinstance(m, torch.nn.Module)]
        self.saved = None   # [(tensor, pinned cpu copy)]
        self.bufs = None

    def _tensors(self):
        seen = set()
        for mod in self.mods:
            for t in list(mod.parameters()) + list(mod.buffers()):
                if t.is_cuda and id(t) not in seen and t.numel():
                    seen.add(id(t))
                    yield t

    @property
    def parked(self):
        return self.saved is not None

    @torch.inference_mode()
    def park(self):
        """-> (seconds, MiB freed). Call with the main voice active and nothing being generated."""
        if self.parked:
            return 0.0, 0.0
        t0, before = time.time(), torch.cuda.memory_reserved()
        torch.cuda.synchronize()
        # the pinned buffers are made once and reused (a new set per park stayed cached by torch: +2.3 GB of RAM
        # each time); layers the LoRA voices already keep a main copy of use that copy (same values: main voice)
        if self.bufs is None:
            from int8_voice import MAIN
            self.bufs = [MAIN[id(t)][1] if id(t) in MAIN else torch.empty(t.shape, dtype=t.dtype)
                         for t in self._tensors()]
        self.saved = []
        for t, cpu in zip(self._tensors(), self.bufs):
            if cpu.data_ptr() != t.data_ptr():
                cpu.copy_(t)
            self.saved.append((t, cpu))
        for t, _ in self.saved:
            t.data = torch.empty(0, dtype=t.dtype, device=t.device)
        for g in (self.fm.talker_graph, self.fm.predictor_graph):   # their pools and pointers go with the weights
            g.graph, g.captured = None, False
        self.fm._warmed_up = False
        gc.collect()
        torch.cuda.empty_cache()
        return time.time() - t0, (before - torch.cuda.memory_reserved()) / 2 ** 20

    @torch.inference_mode()
    def unpark(self):
        """-> seconds (the graphs are captured again by the next generation)."""
        if not self.parked:
            return 0.0
        t0 = time.time()
        dev = torch.device("cuda")
        for t, cpu in self.saved:
            t.data = cpu.to(dev, non_blocking=True)   # a copy: the pinned buffer stays for the next park
        torch.cuda.synchronize()
        self.saved = None
        return time.time() - t0
