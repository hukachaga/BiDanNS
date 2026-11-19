#!/bin/bash
# spv_val_dir.sh <dir>: spirv-val (Vulkan 1.3) on every .spv; valid.txt lists the ones that pass, invalid.txt the others with the first error (WSL: spirv-tools)
cd "$1" || exit 1
: > valid.txt; : > invalid.txt
for f in *.spv; do
  if e=$(spirv-val --target-env vulkan1.3 "$f" 2>&1); then echo "$f" >> valid.txt; else echo "$f	$(echo "$e" | head -1)" >> invalid.txt; fi
done
echo "valid $(wc -l < valid.txt), invalid $(wc -l < invalid.txt)"
