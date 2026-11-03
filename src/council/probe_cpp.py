# -*- coding: utf-8 -*-
"""Датчик сомнения на C++ (probe.dll) вместо хранения torch-модели.

Формула (как в patch_probe_server.py / export_probe.py):
    z = b + sum(w[i]*h[i]);  p = 1/(1+exp(-z)).
probe16.json: {"layer":16,"w":[...],"b":...}.

Использование:
    import probe_cpp
    probe_cpp.load('D:\\AI\\expert-map\\probe16.json')
    p = probe_cpp.score(hidden_vector)   # hidden_vector: list/tuple из 2048 float
Если DLL нет — возвращаем None, вызывающий решает, что делать.
"""
import ctypes
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DLL = os.path.join(_HERE, "cpp", "probe.dll")

_lib = None
try:
    if os.path.exists(_DLL):
        _lib = ctypes.CDLL(_DLL)
        _lib.probe_load.argtypes = [ctypes.c_char_p]
        _lib.probe_load.restype = ctypes.c_int
        _lib.probe_score_for.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        _lib.probe_score_for.restype = ctypes.c_double
        _lib.probe_layer.restype = ctypes.c_int
        _lib.probe_weights_count.restype = ctypes.c_int
        _lib.probe_bias.restype = ctypes.c_double
except Exception:
    _lib = None

_loaded = False


def load(path):
    """Загрузить probe16.json. Возвращает True/False."""
    global _loaded
    if _lib is None:
        return False
    _loaded = bool(_lib.probe_load(str(path).encode("utf-8")))
    return _loaded


def score(hidden):
    """Вероятность «мозг знает ответ» по скрытому состоянию (последовательность float)."""
    if _lib is None or not _loaded:
        return None
    try:
        n = len(hidden)
    except TypeError:
        return None
    arr = (ctypes.c_double * n)(*[float(x) for x in hidden])
    return _lib.probe_score_for(arr, n)


def layer():
    return _lib.probe_layer() if _lib else None


def weights_count():
    return _lib.probe_weights_count() if _lib else None


def bias():
    return _lib.probe_bias() if _lib else None
