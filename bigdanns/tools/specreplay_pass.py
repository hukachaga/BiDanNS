"""BigDanNS: "speculate and replay" for raw global memory loads in straight-line vertex shaders (the pass; lib_specreplay.py runs it over a library).

A raw load (a guest global load whose address the shader read from memory: docs/reference/shaders.md, Global memory at an address loaded from memory) goes
through the pool table, the replay's table of the game's memory pools (start, end, delta). Each call site carries the table search, which the driver inlines:
Ocarina of Time's character vertex shader b1f06157308e3b22 kept 70 of them after cache_raw_loads, and Turnip's ir3 spills around them.

Here every call site becomes a few compares and one load, with no search:
  - K kept entries (Private: start, end, delta, 6 words each; K = 4, SR_K): with 2, a character reading 3 pools cycled them, hit MAX_RUNS and drew zeros
    (objects flickering in Castle Town); 4 cost 0.088 against 0.077 us a vertex. A site whose address lies in one of them reads it there (address + delta).
  - A site that misses reads the table's sink instead, gives 0, records its address (the first miss of the run) and sets a flag.
  - main runs the old body (now function B) in a loop: after a run that missed, one table search (one cache function of cache_raw_loads, the only copy of the
    search left) finds the entry of the recorded address, which goes into the next kept slot, and the body runs again. An address in no entry is remembered (its
    16-byte block) and reads 0 from then on, as the helper gives 0; an address below 64 KiB reads 0 at once (no guest pool is there). After MAX_RUNS runs the last
    run stands (a vertex reaching more than K pools within MAX_RUNS runs gets 0 for the rest: open, not seen).
  - The first call site seeds slot 0 with that search, so a vertex whose loads all lie in one pool runs the body once.
Every value read is the one the helper reads (same pool, same delta); a 128-bit helper call checks its base address only, as the helper did.
Only vertex shaders whose main is one block, writing nothing but Function, Private and Output variables (the body runs again).

Measured (Konkr, Adreno 750, Turnip Mesa 27, Castle Town at night, recorded route): b1f06157308e3b22 0.264 -> 0.066 us a vertex, the frame 89 -> 76 ms GPU.
"""
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, '..', '..', 'dm', 'gfx', 'tools'), os.path.join(_here, '..', 'src', 'dm', 'gfx', 'tools')):   # in the repository (bigdanns/tools) or beside it
    if os.path.isfile(os.path.join(_p, 'vk_android_spv.py')): sys.path.insert(0, _p); break
import vk_android_spv as spv
from vk_android_spv import *   # opcodes, storage classes

OP_FUNCTION_PARAMETER, OP_FUNCTION_CALL, OP_CONVERT_U_TO_PTR = 55, 57, 120
OP_IADD, OP_ULT, OP_ULE, OP_IEQ, OP_INE, OP_LAND, OP_LOR, OP_LNOT, OP_BAND = 128, 176, 178, 170, 171, 167, 166, 168, 199
OP_SEL_MERGE, OP_LOOP_MERGE, OP_BRANCH, OP_BRANCH_COND, OP_COMPOSITE_CONSTRUCT, OP_CONSTANT_NULL = 247, 246, 249, 250, 80, 46
SC_OUTPUT_, SC_PHYS = 3, 5349
MAX_RUNS = int(os.environ.get("SR_MAX_RUNS", "6"))
MEM_ALIGNED4 = [2, 4]
# body ops that a rerun would repeat with an effect: barriers, atomics, image writes, kill / demote, emits, ray / mesh ops (vk_android_spv._RUN_BREAKERS) and
# any call that is not a raw load helper
SIDE_EFFECT_OPS = set(spv._RUN_BREAKERS) | {OP_IMAGE_WRITE, 252, 5380, 218, 219, 220, 221}


class Skip(Exception): pass


def _fbody(m, f):
    a, e = m.function_range(f); return m.ins[a:e + 1]


def _uses_table(m, b, table):
    return any(x[0] & 0xffff == OP_ACCESS_CHAIN and x[3] == table for x in b)


def classify(m, f, table, u32, v4):
    """('run', n, cache vars) for a cache function of cache_raw_loads, ('wide', facts) for a 128-bit raw load helper, ('word', facts) for a 32-bit one, else None"""
    b = _fbody(m, f)
    if not _uses_table(m, b, table): return None
    params = [x for x in b[1:3] if x[0] & 0xffff == OP_FUNCTION_PARAMETER]
    if len(params) != 2: return None
    cus = [x for x in b if x[0] & 0xffff == OP_CONVERT_U_TO_PTR]
    rty = b[0][1]
    if rty == v4 and len(cus) >= 2:
        loads = [x for x in b[:40] if x[0] & 0xffff == OP_LOAD and x[3] in m.vars and m.vars[x[3]][1] == SC_PRIVATE]
        if len(loads) < 6: return None
        return ('run', len(cus) - 1, [x[3] for x in loads[:6]], [p[1] for p in params])
    if len(cus) != 1: return None
    pt = m.pointee(cus[0][1])[1]
    if m.op(pt) == OP_TYPE_VECTOR:
        defs = {x[2]: x for x in b if len(x) > 2 and (x[0] & 0xffff) not in NO_RESULT_OPS and x[0] & 0xffff != OP_LABEL}
        loadx = [x for x in b if x[0] & 0xffff == OP_LOAD and x[3] == cus[0][2]]
        if len(loadx) != 1: return None
        load = loadx[0]
        def lane(v):
            while v in defs and defs[v][0] & 0xffff in (OP_BITCAST, OP_COPY_OBJECT): v = defs[v][3]
            x = defs.get(v)
            return x[4] if x is not None and x[0] & 0xffff == OP_COMPOSITE_EXTRACT and x[3] == load[2] else None
        idx, priv, pty = {}, None, None
        for x in b:
            if x[0] & 0xffff != OP_STORE: continue
            ch = defs.get(x[1])
            if ch is None or ch[0] & 0xffff != OP_ACCESS_CHAIN: continue
            k = lane(x[2])
            if k: idx[k] = ch[4]; priv, pty = ch[3], ch[1]
        if sorted(idx) != [1, 2, 3]: return None
        tch = next(x for x in b if x[0] & 0xffff == OP_ACCESS_CHAIN and x[3] == table)
        return ('wide', {'priv': priv, 'pty': pty, 'idx': idx, 'vptr': cus[0][1], 'vty': pt, 'rty': rty, 'mem': load[4:], 'lo': params[0][1], 'hi': params[1][1],
                         'tptr': tch[1], 'ity': m.consts[tch[4]][0]})
    h = spv._raw_load_helper(m, f, {table})
    return ('word', h) if h else None


def transform(m, table, K=int(os.environ.get("SR_K", "4"))):
    """the pass on module m (its pool table variable: table) → the number of call sites rewritten; raises Skip when the module does not fit"""
    if m.model != 'vs': raise Skip('not a vertex shader')
    if m.header[1] > 0x10300: raise Skip('SPIR-V 1.4+')
    ent = m.entry_function()
    a, e = m.function_range(ent)
    mbody = m.ins[a:e + 1]
    if sum(1 for x in mbody if x[0] & 0xffff == OP_LABEL) != 1: raise Skip('main is not one block')
    fn_ty, void = mbody[0][4], mbody[0][1]
    u32 = m.add_type(OP_TYPE_INT, 32, 0)
    v4 = m.add_type(OP_TYPE_VECTOR, u32, 4)
    callees = {x[3] for x in mbody if x[0] & 0xffff == OP_FUNCTION_CALL}
    kinds = {}
    for f in callees:
        k = classify(m, f, table, u32, v4)
        if k is None: raise Skip(f'callee {f} is not a raw load helper')
        kinds[f] = k
    if not kinds: raise Skip('no raw loads')
    mdefs = {x[2]: x for x in mbody if len(x) > 2 and (x[0] & 0xffff) not in NO_RESULT_OPS and x[0] & 0xffff != OP_LABEL}
    for x in mbody:
        op = x[0] & 0xffff
        if op in SIDE_EFFECT_OPS: raise Skip(f'opcode {op} in main')
        if op == OP_STORE and spv._store_class(m, mdefs, x[1]) not in (SC_FUNCTION, SC_PRIVATE, SC_OUTPUT_): raise Skip('a store to memory in main')
    sites = [x for x in mbody if x[0] & 0xffff == OP_FUNCTION_CALL]
    # declarations
    bty = m.add_type(OP_TYPE_BOOL)
    b4 = m.add_type(OP_TYPE_VECTOR, bty, 4)
    v2 = m.add_type(OP_TYPE_VECTOR, u32, 2)
    u64 = m.add_type(OP_TYPE_INT, 64, 0)
    ppriv = m.add_type(OP_TYPE_POINTER, SC_PRIVATE, u32)
    pphys = m.add_type(OP_TYPE_POINTER, SC_PHYS, u32)
    U = lambda v: m.add_const(u32, v & 0xffffffff)
    z4 = m.new_id(); m._insert_decl([3 << 16 | OP_CONSTANT_NULL, v4, z4])
    def pvar(init):
        i = m.new_id(); m._insert_decl([5 << 16 | OP_VARIABLE, ppriv, i, SC_PRIVATE, U(init)]); return i
    # the table search: a cache function of the module, else one made (cache_raw_loads' _cached_load_fn for one word) from a helper's facts
    runs = sorted((k[1], f) for f, k in kinds.items() if k[0] == 'run')
    if runs:
        G = runs[0][1]; cvars, gpar = kinds[G][2], kinds[G][3]
        gb = _fbody(m, G); tch = next(x for x in gb if x[0] & 0xffff == OP_ACCESS_CHAIN and x[3] == table)
        tptr, ity = tch[1], m.consts[tch[4]][0]
    else:
        f0, k0 = next(iter(kinds.items()))
        if k0[0] == 'word':
            h = dict(k0[1])
        else:
            w = k0[1]
            h = {'ret': w['rty'], 'lo': w['lo'], 'hi': w['hi'], 'table': table, 'tptr': w['tptr'], 'ity': w['ity'], 'word': u32, 'pptr': pphys, 'member': None, 'mem': w['mem']}
        tptr, ity = h['tptr'], h['ity']
        cvars = [pvar(0xffffffff), pvar(0xffffffff), pvar(0), pvar(0), pvar(0), pvar(0)]
        Uc = {v: U(v) for v in (0, 1, 4, 11, 13, 21, 256, 8191, 0xffffffff)}
        Uc.update({4 * k: U(4 * k) for k in range(1, spv.GMEM_RUN_WORDS)})
        z4b = m.new_id(); m._insert_decl([3 << 16 | OP_CONSTANT_NULL, v4, z4b])
        G = spv._cached_load_fn(m, h, 1, cvars, f0, dict(bool=bty, u32=u32, v2=v2, v4=v4, u64=u64, z4=z4b, U=Uc))
        gpar = [h['lo'], h['hi']]
    I = lambda v: m.add_const(ity, v)
    slots = [[pvar(0xffffffff), pvar(0xffffffff), pvar(0), pvar(0), pvar(0), pvar(0)] for _ in range(K)]
    missed, pend_lo, pend_hi = pvar(0), pvar(0), pvar(0)
    unm_lo, unm_hi = pvar(0xfffffff0), pvar(0xffffffff)
    nxt, nruns = pvar(0), pvar(0)

    def emitter(ins):
        def op(o, *w): ins.append([(len(w) + 1) << 16 | o, *w])
        def val(o, ty, *w):
            r = m.new_id(); ins.append([(len(w) + 3) << 16 | o, ty, r, *w]); return r
        return op, val

    def lt_fn(val):
        def lt(ahi, alo, bhi, blo, eq=False):
            return val(OP_LOR, bty, val(OP_ULT, bty, ahi, bhi), val(OP_LAND, bty, val(OP_IEQ, bty, ahi, bhi), val(OP_ULE if eq else OP_ULT, bty, alo, blo)))
        return lt

    def site(ins, x, kind):
        op, val = emitter(ins)
        lt = lt_fn(val)
        lo, hi = x[4], x[5]
        lu, hu = val(OP_BITCAST, u32, lo), val(OP_BITCAST, u32, hi)
        def add64(alo, ahi, blo, bhi):
            l = val(OP_IADD, u32, alo, blo)
            return l, val(OP_IADD, u32, val(OP_IADD, u32, ahi, bhi), val(OP_SELECT, u32, val(OP_ULT, bty, l, alo), U(1), U(0)))
        nwords = kind[1] if kind[0] == 'run' else (4 if kind[0] == 'wide' else 1)
        el, eh = add64(lu, hu, U(4 * nwords - 1 if kind[0] == 'run' else 0), U(0))   # the last byte checked (a helper: its base, as it checked)
        hits, dl, dh = [], None, None
        for s in slots:
            c = [val(OP_LOAD, u32, v) for v in s]
            h = val(OP_LAND, bty, lt(c[1], c[0], hu, lu, eq=True), lt(eh, el, c[3], c[2]))
            hits.append(h)
            dl = c[4] if dl is None else val(OP_SELECT, u32, h, c[4], dl)
            dh = c[5] if dh is None else val(OP_SELECT, u32, h, c[5], dh)
        hit = hits[0]
        for h in hits[1:]: hit = val(OP_LOR, bty, hit, h)
        pl, ph = add64(lu, hu, dl, dh)
        sk = [val(OP_LOAD, u32, val(OP_ACCESS_CHAIN, tptr, table, I(0), I(w))) for w in (6, 7)]   # the table's sink (entry 0, words 6 and 7)
        pl, ph = val(OP_SELECT, u32, hit, pl, sk[0]), val(OP_SELECT, u32, hit, ph, sk[1])
        if kind[0] == 'wide':
            w = kind[1]
            v = val(OP_LOAD, w['vty'], val(OP_CONVERT_U_TO_PTR, w['vptr'], val(OP_BITCAST, u64, val(OP_COMPOSITE_CONSTRUCT, v2, pl, ph))), *MEM_ALIGNED4)
            if w['vty'] != v4: v = val(OP_BITCAST, v4, v)
        else:
            ws = []
            for k in range(nwords):
                ql, qh = add64(pl, ph, U(4 * k), U(0)) if k else (pl, ph)
                ws.append(val(OP_LOAD, u32, val(OP_CONVERT_U_TO_PTR, pphys, val(OP_BITCAST, u64, val(OP_COMPOSITE_CONSTRUCT, v2, ql, qh))), *MEM_ALIGNED4))
            v = val(OP_COMPOSITE_CONSTRUCT, v4, *ws, *[U(0)] * (4 - nwords))
        v = val(OP_SELECT, v4, val(OP_COMPOSITE_CONSTRUCT, b4, hit, hit, hit, hit), v, z4)
        low = val(OP_LAND, bty, val(OP_IEQ, bty, hu, U(0)), val(OP_ULT, bty, lu, U(0x10000)))
        unm = val(OP_LAND, bty, val(OP_IEQ, bty, val(OP_BAND, u32, lu, U(0xfffffff0)), val(OP_LOAD, u32, unm_lo)), val(OP_IEQ, bty, hu, val(OP_LOAD, u32, unm_hi)))
        miss = val(OP_LAND, bty, val(OP_LNOT, bty, hit), val(OP_LNOT, bty, val(OP_LOR, bty, low, unm)))
        mo = val(OP_LOAD, u32, missed)
        first = val(OP_LAND, bty, miss, val(OP_IEQ, bty, mo, U(0)))
        op(OP_STORE, pend_lo, val(OP_SELECT, u32, first, lu, val(OP_LOAD, u32, pend_lo)))
        op(OP_STORE, pend_hi, val(OP_SELECT, u32, first, hu, val(OP_LOAD, u32, pend_hi)))
        op(OP_STORE, missed, val(OP_SELECT, u32, miss, U(1), mo))
        if kind[0] == 'wide':
            w = kind[1]
            ins.append([4 << 16 | (OP_COPY_OBJECT if x[1] == u32 else OP_BITCAST), x[1], x[2], val(OP_COMPOSITE_EXTRACT, u32, v, 0)])
            for k in (1, 2, 3):
                op(OP_STORE, val(OP_ACCESS_CHAIN, w['pty'], w['priv'], w['idx'][k]), val(OP_COMPOSITE_EXTRACT, u32, v, k))
        elif kind[0] == 'word':
            ins.append([4 << 16 | (OP_COPY_OBJECT if x[1] == u32 else OP_BITCAST), x[1], x[2], val(OP_COMPOSITE_EXTRACT, u32, v, 0)])
        else:
            ins.append([4 << 16 | OP_COPY_OBJECT, v4, x[2], v])

    def lookup_into(ins, lu, hu, first):
        op, val = emitter(ins)
        lt = lt_fn(val)
        c = [val(OP_LOAD, u32, v) for v in cvars]
        found = val(OP_LAND, bty, lt(c[1], c[0], hu, lu, eq=True), lt(hu, lu, c[3], c[2]))
        if first:
            for v, cv in zip(slots[0], c): op(OP_STORE, v, val(OP_SELECT, u32, found, cv, val(OP_LOAD, u32, v)))
            op(OP_STORE, nxt, val(OP_SELECT, u32, found, U(1 % K), val(OP_LOAD, u32, nxt)))
            return
        n0 = val(OP_LOAD, u32, nxt)
        for si, s in enumerate(slots):
            here = val(OP_LAND, bty, found, val(OP_IEQ, bty, n0, U(si)))
            for v, cv in zip(s, c): op(OP_STORE, v, val(OP_SELECT, u32, here, cv, val(OP_LOAD, u32, v)))
        n1 = val(OP_IADD, u32, n0, U(1))
        n1 = val(OP_SELECT, u32, val(OP_IEQ, bty, n1, U(K)), U(0), n1)
        op(OP_STORE, nxt, val(OP_SELECT, u32, found, n1, n0))
        nf = val(OP_LNOT, bty, found)
        op(OP_STORE, unm_lo, val(OP_SELECT, u32, nf, val(OP_BAND, u32, lu, U(0xfffffff0)), val(OP_LOAD, u32, unm_lo)))
        op(OP_STORE, unm_hi, val(OP_SELECT, u32, nf, hu, val(OP_LOAD, u32, unm_hi)))

    def gcall(ins, lu, hu):
        op, val = emitter(ins)
        val(OP_FUNCTION_CALL, v4, G, val(OP_BITCAST, gpar[0], lu), val(OP_BITCAST, gpar[1], hu))

    # B: main's body with every call site rewritten (the first one seeds slot 0)
    B = m.new_id()
    out = [[5 << 16 | OP_FUNCTION, void, B, 0, fn_ty], mbody[1]]
    seeded = False
    for x in mbody[2:-1]:
        if x[0] & 0xffff == OP_FUNCTION_CALL and x[3] in kinds:
            if not seeded:
                op, val = emitter(out)
                lu, hu = val(OP_BITCAST, u32, x[4]), val(OP_BITCAST, u32, x[5])
                gcall(out, lu, hu); lookup_into(out, lu, hu, True); seeded = True
            site(out, x, kinds[x[3]])
            continue
        out.append(x)
    out.append(mbody[-1])
    # main: the body until a run with no miss, at most MAX_RUNS runs
    E, H, BD, KK, S, C, M = (m.new_id() for _ in range(7))
    mn = [mbody[0], [2 << 16 | OP_LABEL, E], [2 << 16 | OP_BRANCH, H],
          [2 << 16 | OP_LABEL, H], [4 << 16 | OP_LOOP_MERGE, M, C, 0], [2 << 16 | OP_BRANCH, BD], [2 << 16 | OP_LABEL, BD]]
    op, val = emitter(mn)
    op(OP_STORE, missed, U(0))
    val(OP_FUNCTION_CALL, void, B)
    again = val(OP_INE, bty, val(OP_LOAD, u32, missed), U(0))
    op(OP_SEL_MERGE, S, 0); op(OP_BRANCH_COND, again, KK, S)
    op(OP_LABEL, KK)
    pl, ph = val(OP_LOAD, u32, pend_lo), val(OP_LOAD, u32, pend_hi)
    gcall(mn, pl, ph); lookup_into(mn, pl, ph, False)
    op(OP_BRANCH, S)
    op(OP_LABEL, S); op(OP_BRANCH, C)
    op(OP_LABEL, C)
    r1 = val(OP_IADD, u32, val(OP_LOAD, u32, nruns), U(1))
    op(OP_STORE, nruns, r1)
    op(OP_BRANCH_COND, val(OP_LAND, bty, again, val(OP_ULT, bty, r1, U(MAX_RUNS))), H, M)
    op(OP_LABEL, M); op(OP_RETURN); op(OP_FUNCTION_END)
    a, e = m.function_range(ent)   # declarations were inserted before the functions since
    m.ins[a:e + 1] = mn + out
    called = {y[3] for y in m.ins if y[0] & 0xffff == OP_FUNCTION_CALL}
    for f in list(kinds):
        if f in called or f == G: continue
        fa, fe = m.function_range(f)
        gone = {y[1] if y[0] & 0xffff == OP_LABEL else y[2] for y in m.ins[fa:fe + 1] if (y[0] & 0xffff) not in NO_RESULT_OPS and len(y) > 2 or y[0] & 0xffff == OP_LABEL}
        del m.ins[fa:fe + 1]
        m.ins = [y for y in m.ins if not ((y[0] & 0xffff) in (OP_NAME, OP_DECORATE) and y[1] in gone)]
    m.index()
    return len(sites)


if __name__ == '__main__':   # one module: specreplay_pass.py <in.spv> <out.spv> [table variable name, default vp_s1] [K]
    src, dst = sys.argv[1], sys.argv[2]
    tname = sys.argv[3] if len(sys.argv) > 3 else 'vp_s1'
    m = spv.Module(open(src, 'rb').read())
    table = next(i for i, n in m.names.items() if n == tname)
    n = transform(m, table, int(sys.argv[4]) if len(sys.argv) > 4 else 2)
    print(f'{src}: {n} call sites; {len(open(src, "rb").read())} -> {len(m.data())} bytes')
    open(dst, 'wb').write(m.data())
