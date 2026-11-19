"""BigDanNS: run the (extended) cache_raw_loads pass again on a module taken from a built library, for a DM_VK_SPV_OVERRIDE test.
Usage: recache.py <in.spv> <out.spv> [table variable name, default vp_s1]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dm', 'gfx', 'tools'))
import vk_android_spv as spv

src, dst = sys.argv[1], sys.argv[2]
tname = sys.argv[3] if len(sys.argv) > 3 else 'vp_s1'
m = spv.Module(open(src, 'rb').read())
tables = {i for i, n in m.names.items() if n == tname}
assert tables, f'no variable named {tname}'
calls = lambda: sum(1 for x in m.ins if x[0] & 0xffff == spv.OP_FUNCTION_CALL)
fns = lambda: sum(1 for x in m.ins if x[0] & 0xffff == spv.OP_FUNCTION)
before = (calls(), fns(), len(m.data()))
n = spv.cache_raw_loads(m, tables)
print(f'{src}: {n} words through the kept entry; calls {before[0]} -> {calls()}, functions {before[1]} -> {fns()}, bytes {before[2]} -> {len(m.data())}')
open(dst, 'wb').write(m.data())
