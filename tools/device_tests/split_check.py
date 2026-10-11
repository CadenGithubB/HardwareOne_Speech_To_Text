# Re-implements ESP-DL 3.3.12 ConvOpArgs dual-core split (dl_base_conv_args.hpp:444-471) and the
# dwconv grid semantics (taps outside [0,in_h) of the half's own view are skipped) to find the
# exact H for which a split is bit-exact, versus the shipped "H > 4*d*K" gate.
import random
random.seed(0)
def conv1d(x,w,pad_h,pad_t,d,s,out_h):
    H=len(x); K=len(w); y=[0]*out_h
    for o in range(out_h):
        for k in range(K):
            i=o*s-pad_h+k*d
            if 0<=i<H: y[o]+=x[i]*w[k]
    return y
def split(H,K,d,s,ph,pt):
    dfh=d*(K-1)+1
    out_h=(H+ph+pt-dfh)//s+1
    half=(ph+pt+H-dfh)//s//2
    m0_in=dfh-ph+half*s; m0_out=half+1
    m1_in=dfh-s+H-m0_in; m1_start=H-m1_in; m1_out=out_h-m0_out
    return out_h,m0_in,m0_out,m1_start,m1_in,m1_out
def ok_split(H,K,d,s,ph,pt):
    out_h,m0_in,m0_out,m1_start,m1_in,m1_out=split(H,K,d,s,ph,pt)
    if m0_in>H or m1_start<0 or m1_out<1 or m0_out<1: return False
    x=[random.randint(-128,127) for _ in range(H)]; w=[random.randint(-128,127) for _ in range(K)]
    ref=conv1d(x,w,ph,pt,d,s,out_h)
    a=conv1d(x[:m0_in],w,ph,0,d,s,m0_out)
    b=conv1d(x[m1_start:m1_start+m1_in],w,0,pt,d,s,m1_out)
    return ref==a+b
layers=[('dw33 s2 (block0, input T)',33,1,2,16,16),('dw33',33,1,1,16,16),('dw39',39,1,1,19,19),
        ('dw51',51,1,1,25,25),('dw63',63,1,1,31,31),('dw75',75,1,1,37,37),('dw87 d2',87,2,1,86,86)]
for name,K,d,s,ph,pt in layers:
    gate=4*d*K
    Hmin=None
    for H in range(2,800):
        if ok_split(H,K,d,s,ph,pt):
            # also require every larger H in a window to be ok
            Hmin=H; break
    bad=[H for H in range(Hmin,800) if not ok_split(H,K,d,s,ph,pt)] if Hmin else ['none']
    print(f"{name:28s} shipped gate H>{gate:4d}  exact split from H>={Hmin}  failures above that: {bad[:5]}")
# frames per phrase length (quartznet_frontend.cpp:92, quartznet_runtime.cpp:184)
print()
print("audio_s  feat_frames  H(after stride2)  layers on ONE core under the shipped gate")
for T in [2,3,4,4.5,5,6,7,8,10,12,14,20]:
    samples=int(T*16000); frames=(samples+159)//160; H=(frames+1)//2
    single=[n for n,K,d,s,ph,pt in layers[1:] if not H>4*d*K]
    if not frames>4*33: single=['dw33 s2']+single
    print(f"{T:6.1f} {frames:10d} {H:12d}        {', '.join(single) if single else '-'}")
