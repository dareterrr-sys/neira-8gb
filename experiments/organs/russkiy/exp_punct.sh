#!/bin/bash
# One punctuation experiment on the GPU: train (env passed through) -> score the bank -> thresholds on half B.
# Usage: OUT_NAME=name [EGE_REPEAT=.. CLASSICS=.. NORM=..] bash exp_punct.sh <epochs>
cd /d/AI/neira-tools/russkiy
export HF_HOME=/d/AI/hf-cache PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -u ft_punct.py "$1" > "data/ft_${OUT_NAME}.log" 2>&1
grep -E "примеров|эпоха|Error" "data/ft_${OUT_NAME}.log"
.venv/Scripts/python.exe punct_net.py "D:/AI/neira-tools/russkiy/models/${OUT_NAME}" 16 17 18 19 20 > /dev/null 2>&1
.venv/Scripts/python.exe net_eval.py "${OUT_NAME}" 16 17 18 19 20 --Bonly
