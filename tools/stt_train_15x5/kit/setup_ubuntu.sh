#!/bin/bash
# One-time setup on the Ubuntu A4000 PC (run from the kit folder on the SSD).
#   bash setup_ubuntu.sh
# Needs: the NVIDIA driver (nvidia-smi works), python3-venv and a C compiler:
#   sudo apt-get install -y python3-venv python3-dev build-essential
# Creates ~/hw1-stt-venv with CUDA PyTorch and the training dependencies.
# Safe to run again (e.g. after a driver update).
set -eu
KIT=$(cd "$(dirname "$0")" && pwd)
VENV=${VENV:-$HOME/hw1-stt-venv}

command -v nvidia-smi >/dev/null || {
  echo "nvidia-smi not found: install the NVIDIA driver first (sudo ubuntu-drivers install, then reboot)"; exit 1; }
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
command -v cc >/dev/null || { echo "no C compiler: sudo apt-get install -y build-essential"; exit 1; }

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
# CUDA 12.6 build (drivers 525 and newer); the default PyPI build is the fallback for
# Python versions it has no wheel for.
"$VENV/bin/pip" install torch --index-url https://download.pytorch.org/whl/cu126 || "$VENV/bin/pip" install torch
"$VENV/bin/pip" install -r "$KIT/requirements.txt"

"$VENV/bin/python" - <<'EOF'
import torch
assert torch.cuda.is_available(), ('PyTorch cannot see the GPU: update the NVIDIA driver '
                                   '(sudo ubuntu-drivers install), reboot, then run this again')
print('PyTorch', torch.__version__, '| GPU:', torch.cuda.get_device_name(0),
      '| bf16:', torch.cuda.is_bf16_supported())
EOF
# The LC3 codec library for the glasses-channel augmentation, built on the PC's own disk.
export HW1_LC3_BUILD="$VENV/lc3"
(cd "$KIT/experiments/stt_train_15x5" && "$VENV/bin/python" -c "import lc3codec; lc3codec._load(); print('liblc3 ok:', lc3codec.DYLIB)")
echo "setup done: $VENV"
