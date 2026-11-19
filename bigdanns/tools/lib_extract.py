"""Extract one shader's modules from a Banana Native Vulkan library (dmsh_vk.lib, dmsh_abi_vk.h layout).
Usage: lib_extract.py <dmsh_vk.lib> <key hex> <out dir>   -> <key>_<variant>.spv for each module of that entry
"""
import mmap, os, struct, sys
import zstandard

ENTRY_SIZE, MOD_SIZE, CODEC_RAW, CODEC_ZSTD = 64, 16, 0, 1
path, want, out = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
os.makedirs(out, exist_ok=True)
with open(path, 'rb') as f:
    d = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
magic, version, chain, vkc, game, inputs, ne, eo, nb, bo, nm, mo, blob_off, blob_size, sg, sa = struct.unpack_from('<II16s16s16s16sIIIIIIQQHH', d, 0)
assert magic == 0x4B56534D, hex(magic)
lo, hi = 0, ne
while lo < hi:   # entries are sorted by key
    m = (lo + hi) // 2
    k = struct.unpack_from('<Q', d, eo + ENTRY_SIZE * m)[0]
    if k < want: lo = m + 1
    else: hi = m
key, _, stage, mc, flags, m0, b0, bc = struct.unpack_from('<QQBBHIIH', d, eo + ENTRY_SIZE * lo)
assert key == want, f'{want:016x} not in the library'
print(f'{key:016x}: stage {stage}, {mc} modules, flags {flags:#x}, {bc} bindings; chain {chain.rstrip(bytes(1)).decode()} vk {vkc.rstrip(bytes(1)).decode()}')
for j in range(m0, m0 + mc):
    off, size, stored, variant, codec, off_hi = struct.unpack_from('<IIIBBH', d, mo + MOD_SIZE * j)
    off |= off_hi << 32
    raw = d[blob_off + off:blob_off + off + stored]
    if codec == CODEC_ZSTD: raw = zstandard.ZstdDecompressor().decompress(raw, max_output_size=size)
    assert len(raw) == size and raw[:4] == b'\x03\x02\x23\x07', (variant, len(raw), size)
    p = os.path.join(out, f'{key:016x}_{variant}.spv')
    open(p, 'wb').write(raw)
    print(f'  variant {variant}: {size} bytes ({"zstd" if codec else "raw"} {stored}) -> {p}')
