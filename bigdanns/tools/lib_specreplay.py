"""BigDanNS: run specreplay_pass over every vertex shader of a Vulkan shader library (dmsh_vk.lib) and write a new library beside it.

The new library keeps the header (versions, ABI, game) and every entry; each changed module is appended to the blob (zstd) and its module record points there.
The replay takes it through DM_VK_SHLIB=<file> (vka_shader.c lib_load), so the pack's own library stays as it is.
Each changed module must pass spirv-val (Vulkan 1.3): run with --validate <dir of spirv-val results> after a first pass that writes the candidates.

Usage:
  lib_specreplay.py candidates <dmsh_vk.lib> <dir>          the changed modules as <key>_<variant>.spv (+ a list), for spirv-val
  lib_specreplay.py write <dmsh_vk.lib> <dir> <out.lib>      a new library with the modules of <dir>/valid.txt
"""
import mmap, os, struct, sys
import zstandard
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import specreplay_pass as sp
spv = sp.spv

ENTRY_SIZE, MOD_SIZE, BIND_SIZE, KIND_GMEM_MAP = 64, 16, 24, 20
HEAD = struct.Struct('<II16s16s16s16sIIIIIIQQHH')


def open_lib(path):
    f = open(path, 'rb'); d = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    h = HEAD.unpack_from(d, 0)
    assert h[0] == 0x4B56534D
    return d, h


def entries(d, h):
    ne, eo, nb, bo, nm, mo, blob_off = h[6], h[7], h[8], h[9], h[10], h[11], h[12]
    for i in range(ne):
        key, _, stage, mc, flags, m0, b0, bc = struct.unpack_from('<QQBBHIIH', d, eo + ENTRY_SIZE * i)
        binds = [struct.unpack_from('<BBHBB', d, bo + BIND_SIZE * j) for j in range(b0, b0 + bc)]
        mods = []
        for j in range(m0, m0 + mc):
            off, size, stored, variant, codec, off_hi = struct.unpack_from('<IIIBBH', d, mo + MOD_SIZE * j)
            mods.append((j, off | off_hi << 32, size, stored, variant, codec))
        yield key, stage, binds, mods


def module_bytes(d, h, rec):
    j, off, size, stored, variant, codec = rec
    raw = d[h[12] + off:h[12] + off + stored]
    return zstandard.ZstdDecompressor().decompress(raw, max_output_size=size) if codec == 1 else bytes(raw)


def table_var(m, binds):
    gm = [(b[2], b[3]) for b in binds if b[0] == KIND_GMEM_MAP]   # (binding, set)
    if not gm: return None
    for v, deco in m.decos.items():
        if spv.DEC_BINDING in deco and spv.DEC_SET in deco and (deco[spv.DEC_BINDING][0], deco[spv.DEC_SET][0]) in gm and v in m.vars: return v
    return None


def candidates(lib, out):
    d, h = open_lib(lib)
    os.makedirs(out, exist_ok=True)
    stats, rows = {}, []
    for key, stage, binds, mods in entries(d, h):
        if stage != 0 or not any(b[0] == KIND_GMEM_MAP for b in binds): continue
        for rec in mods:
            raw = module_bytes(d, h, rec)
            try:
                m = spv.Module(raw)
                t = table_var(m, binds)
                if t is None: raise sp.Skip('no pool table variable')
                n = sp.transform(m, t)
            except sp.Skip as e:
                stats[str(e).split(' ')[0] if 'callee' in str(e) else str(e)] = stats.get(str(e).split(' ')[0] if 'callee' in str(e) else str(e), 0) + 1; continue
            except Exception as e:   # a module the pass cannot read: left as it is
                stats['error ' + type(e).__name__] = stats.get('error ' + type(e).__name__, 0) + 1; continue
            name = f'{key:016x}_{rec[4]}.spv'
            open(os.path.join(out, name), 'wb').write(m.data())
            rows.append(f'{name}\t{n}\t{len(raw)}\t{len(m.data())}')
            stats['changed'] = stats.get('changed', 0) + 1
    open(os.path.join(out, 'candidates.tsv'), 'w').write('\n'.join(rows) + '\n')
    print(stats)


def write(lib, cdir, out):
    d, h = open_lib(lib)
    valid = {l.strip() for l in open(os.path.join(cdir, 'valid.txt')) if l.strip()}
    blob_off, blob_size, mo = h[12], h[13], h[11]
    head = bytearray(d[:blob_off + blob_size])   # header, tables, blob
    tail, at, n = bytearray(), blob_size, 0
    cz = zstandard.ZstdCompressor(level=12)
    for key, stage, binds, mods in entries(d, h):
        for rec in mods:
            name = f'{key:016x}_{rec[4]}.spv'
            if name not in valid: continue
            raw = open(os.path.join(cdir, name), 'rb').read()
            z = cz.compress(raw)
            off = at + len(tail)
            struct.pack_into('<IIIBBH', head, mo + MOD_SIZE * rec[0], off & 0xFFFFFFFF, len(raw), len(z), rec[4], 1, off >> 32)
            tail += z; tail += b'\0' * (-len(tail) % 16); n += 1
    struct.pack_into('<Q', head, 104, blob_size + len(tail))   # blob_size (HEAD: ... blob_off at 96, blob_size at 104)
    assert HEAD.unpack_from(head, 0)[13] == blob_size + len(tail)
    with open(out, 'wb') as f: f.write(head); f.write(tail)
    print(f'{out}: {n} modules replaced, {len(tail) / 1e6:.1f} MB appended, {(len(head) + len(tail)) / 1e6:.1f} MB')


if __name__ == '__main__':
    {'candidates': lambda: candidates(sys.argv[2], sys.argv[3]), 'write': lambda: write(sys.argv[2], sys.argv[3], sys.argv[4])}[sys.argv[1]]()
