#!/bin/bash
# spv_dis.sh <dir>: spirv-dis + spirv-val (Vulkan 1.3) for each .spv in <dir> (runs in WSL Fedora: spirv-tools)
cd "$1" || exit 1
for f in *.spv; do spirv-dis "$f" -o "${f%.spv}.spvasm"; spirv-val --target-env vulkan1.3 "$f" && echo "$f valid"; done
wc -l *.spvasm
