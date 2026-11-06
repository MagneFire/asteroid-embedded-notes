import re,statistics as st,sys
L=open('day-run.log').read().split('\n')
names={'23f':'D','2823f':'M','3823f':'F','823f':'L','2023f':'C'}
arms=[];cur=None;trim=None;temp=None
for l in L:
    m=re.match(r'\[(\d+\.\d+)\] (.*)',l)
    if not m: continue
    t=float(m[1]);s=m[2]
    a=re.match(r'powertest: arm (\d+) night=(\w+)',s)
    if a: cur=dict(n=int(a[1]),m=names[a[2]],t0=t,r=[]);arms.append(cur);continue
    if 'powertest: plugged' in s: cur=None
    a=re.match(r'iadc: trim (\w+)',s)
    if a: trim=int(a[1],16)
    a=re.search(r'(\d+\.\d) C$',s)
    if a: temp=float(a[1])
    a=re.match(r'power: cc (-?\d+) uA over (\d+) ms, xo (\d+) x (\d+) ms, vmin (\d+) x (\d+) ms',s)
    if a and cur: cur['r'].append((t,int(a[1])/1000,int(a[2])/1000,trim,temp,int(a[3]),int(a[4])/1000,int(a[5]),int(a[6])/1000))
# blocks of same mask
B=[]
for a in arms:
    if B and B[-1]['m']==a['m']: B[-1]['r']+=[x for x in a['r']]
    else: B.append(dict(m=a['m'],t0=a['t0'],n=[a['n']],r=[x for x in a['r'] if x[0]-x[2]>=a['t0']+180]));continue
    B[-1]['n'].append(a['n'])
def cc(r): return sum(x[1]*x[2] for x in r)/sum(x[2] for x in r)
for b in B:
    r=b['r'];w=sum(x[2] for x in r)
    print(b['m'],b['n'][0],b['n'][-1],'n',len(r),f"cc {cc(r):.3f} se {st.stdev(x[1] for x in r)/len(r)**.5:.3f} trim {st.mean(x[3] for x in r):.1f} T {st.mean(x[4] for x in r):.1f} xo {sum(x[6] for x in r)/w:.3f} vmin {sum(x[8] for x in r)/w:.3f}")
allr=[(a['m'],x) for b in B for a in [b] for x in b['r']]
# regression within M/D of cc on trim and T
import numpy as np
for name,sel in (('D+M+F',('D','M','F')),('M',('M',))):
    r=[x for m,x in allr if m in sel]
    y=np.array([x[1] for x in r]);X=np.c_[np.ones(len(r)),[x[3]-48085 for x in r],[x[4]-19.5 for x in r]]
    c,res,_,_=np.linalg.lstsq(X,y,rcond=None);print(name,len(r),'icpt %.3f trim %.3f/code T %.3f/C'%tuple(c),'sd',y.std())
# per-trim-code means
for k in sorted({x[3] for m,x in allr if m in 'DMF'}):
    v=[x[1] for m,x in allr if m in 'DMF' and x[3]==k];print(hex(k),len(v),'%.3f'%st.mean(v))
# F vs bracketing M; M vs D
print('F contrasts')
d=[]
for i,b in enumerate(B):
    if b['m']=='F':
        l,r=B[i-1],B[i+1];x=cc(b['r'])-(cc(l['r'])+cc(r['r']))/2;d.append(x);print(b['n'],'%.3f'%x)
print(st.mean(d),st.stdev(d)/len(d)**.5)
D=[x for m,x in allr if m=='D'];M=[x for m,x in allr if m=='M'];F=[x for m,x in allr if m=='F']
print('D',cc(D),len(D),'M',cc(M),len(M),'F',cc(F),len(F))
M1=[x for b in B[1:9] if b['m']=='M' for x in b['r']];print('M arms before F',cc(M1))
