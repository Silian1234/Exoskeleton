import numpy as np, zlib, struct
def png(path, a):
    h,w,c=a.shape; raw=b''.join(b'\0'+a[y].tobytes() for y in range(h))
    ct={3:2,4:6}[c]
    def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    open(path,'wb').write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,ct,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))
rng=np.random.default_rng(7); N=512
def blur(x,k=3):
    for _ in range(k): x=(x+np.roll(x,1,0)+np.roll(x,-1,0)+np.roll(x,1,1)+np.roll(x,-1,1))/5
    return x
noise=blur(rng.normal(0,1,(N,N)),4); noise/=np.abs(noise).max()
u=np.linspace(0,1,N)[None,:].repeat(N,0)
olive=np.array([62,68,44],float); black=np.array([22,22,20],float)
dif=np.where((u<0.79)[...,None], olive+noise[...,None]*7, black+noise[...,None]*4)
# webbing stripes on strap area
stripes=(np.sin(np.linspace(0,N/3,N))[:,None]*3).repeat(N,1)
dif=np.where((u>=0.79)[...,None], dif+stripes[...,None], dif)
dif=np.clip(dif,0,255).astype(np.uint8)
png(r"C:\SPT\_fullbody_armor\unity\FBA\Assets\FBA\Tex\fba_plates_dif.png", np.dstack([dif,np.full((N,N),255,np.uint8)]))
gl=np.where(u<0.79, 70+noise*10, 25+noise*5); gl=np.clip(gl,0,255).astype(np.uint8)
png(r"C:\SPT\_fullbody_armor\unity\FBA\Assets\FBA\Tex\fba_plates_gloss.png", np.dstack([gl,gl,gl,np.full((N,N),255,np.uint8)]))
nz=blur(rng.normal(0,1,(N,N)),2)*4
nrm=np.dstack([128+nz,128-nz*0.5,np.full((N,N),255.0)]); nrm=np.clip(nrm,0,255).astype(np.uint8)
png(r"C:\SPT\_fullbody_armor\unity\FBA\Assets\FBA\Tex\fba_plates_nrm.png", nrm)
print("ok")
