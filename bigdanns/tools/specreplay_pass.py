"""BigDanNS: "speculate and replay" for raw global memory loads in straight-line vertex shaders, run over a built library by lib_specreplay.py.

The pass itself is the translator's, vk_android_spv.replay_raw_loads (the pull request to Banana Native: see bigdanns/UPSTREAM.md and the entry "Raw global memory
loads read through kept entries and replayed" in docs/reference/shaders.md). This wrapper keeps lib_specreplay.py's interface: transform() rewrites one module
or raises Skip.

The first version of the pass lived here; it checked a run of words as one block and remembered one address in no pool, which the translator's version does not.
"""
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, '..', '..', 'dm', 'gfx', 'tools'), os.path.join(_here, '..', 'src', 'dm', 'gfx', 'tools')):   # in the repository (bigdanns/tools) or beside it
    if os.path.isfile(os.path.join(_p, 'vk_android_spv.py')): sys.path.insert(0, _p); break
import vk_android_spv as spv


class Skip(Exception): pass


def transform(m, table):
    """the pass on module m (its pool table variable: table) → the number of call sites rewritten; raises Skip when it leaves the module as it is"""
    n = spv.replay_raw_loads(m, {table})
    if not n: raise Skip('left alone by replay_raw_loads')
    return n


if __name__ == '__main__':   # one module: specreplay_pass.py <in.spv> <out.spv> [table variable name, default vp_s1]
    src, dst = sys.argv[1], sys.argv[2]
    tname = sys.argv[3] if len(sys.argv) > 3 else 'vp_s1'
    m = spv.Module(open(src, 'rb').read())
    table = next(i for i, n in m.names.items() if n == tname)
    n = transform(m, table)
    print(f'{src}: {n} call sites; {len(open(src, "rb").read())} -> {len(m.data())} bytes')
    open(dst, 'wb').write(m.data())
