"""A fused int8-weight x bf16-vector product for the voice's one-frame steps (28.10): reads the int8 matrix once
(half the bytes of bf16) and scales per block of G weights (29.10: Q8_0-like groups; per row before). torch's own int8 paths are ~2x SLOWER than bf16 at one row.
y[m, n] = s[n] * sum_k x[m, k] * q[n, k]   for a few rows m (1 in the decode graphs; prefill falls back to dequant)."""
import torch
import triton
import triton.language as tl


@triton.jit
def _gemv(x_ptr, q_ptr, s_ptr, y_ptr, N, K, KG, G: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr):
    """s: one scale per G weights of a row (KG = K // G scales per row); G = K means one scale per row."""
    m = tl.program_id(1)
    n = tl.program_id(0) * BN + tl.arange(0, BN)
    acc = tl.zeros((BN,), tl.float32)
    for k0 in range(0, K, BK):
        k = k0 + tl.arange(0, BK)
        x = tl.load(x_ptr + m * K + k, mask=k < K, other=0.0).to(tl.float32)
        msk = (n[:, None] < N) & (k[None, :] < K)
        q = tl.load(q_ptr + n[:, None] * K + k[None, :], mask=msk, other=0)
        sc = tl.load(s_ptr + n[:, None] * KG + k[None, :] // G, mask=msk, other=0.0).to(tl.float32)
        acc += tl.sum(q.to(tl.float32) * sc * x[None, :], 1)
    tl.store(y_ptr + m * N + n, acc.to(y_ptr.dtype.element_ty), mask=n < N)


def gemv(x, q, s, BN=16, BK=256):
    """x [M, K] bf16 (M small), q [N, K] int8, s [N, K // G] (or [N] / [N, 1]: per row) -> [M, N] in x's dtype."""
    M, K = x.shape
    N = q.shape[0]
    s2 = s.reshape(N, -1)
    KG = s2.shape[1]
    y = torch.empty((M, N), device=x.device, dtype=x.dtype)
    _gemv[(triton.cdiv(N, BN), M)](x, q, s2, y, N, K, KG, G=K // KG, BN=BN, BK=BK)
    return y


if __name__ == "__main__":
    import time
    for N, K in [(6144, 2048), (2048, 6144), (2048, 2048)]:
        x = torch.randn(1, K, device="cuda", dtype=torch.bfloat16)
        w = torch.randn(N, K, device="cuda", dtype=torch.bfloat16)
        s = (w.float().abs().amax(1) / 127)
        q = torch.round(w.float() / s[:, None]).clamp(-127, 127).to(torch.int8)
        s = s.to(torch.bfloat16)
        ref = torch.nn.functional.linear(x, q.to(torch.bfloat16) * s[:, None])
        for bn, bk in [(16, 256), (32, 128), (8, 512), (64, 64)]:
            y = gemv(x, q, s, bn, bk)
            err = ((y.float() - ref.float()).abs().max() / ref.float().abs().max()).item()
            g = torch.cuda.CUDAGraph()
            with torch.cuda.graph(g):
                for _ in range(100):
                    gemv(x, q, s, bn, bk)
            torch.cuda.synchronize(); t = time.time(); g.replay(); torch.cuda.synchronize()
            print(f"{N}x{K} BN{bn} BK{bk}: int8 {(time.time() - t) * 1e4:6.1f} us, rel err {err:.1e}")
        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            for _ in range(100):
                torch.nn.functional.linear(x, w)
        torch.cuda.synchronize(); t = time.time(); g.replay(); torch.cuda.synchronize()
        print(f"{N}x{K} bf16 {(time.time() - t) * 1e4:6.1f} us")
