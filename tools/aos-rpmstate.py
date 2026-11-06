import re,sys
st={}   # (res,set)->dict of last sent/cached-effective params
susp=[]
for l in open(sys.argv[1],errors='replace'):
    m=re.match(r'\[\s*([\d.]+)\]',l)
    t=float(m[1]) if m else 0
    m=re.search(r'rpm_regulator_req: (\w+ \d+) \(([\w]+)\): s=(act|slp)(.*)',l)
    if m:
        k=(m[1],m[3]); d=st.setdefault(k,{})
        for part in m[4].split(';'):
            pm=re.match(r'\s*(sent|prev|cached): (.*)',part)
            if not pm: continue
            if pm[1]=='cached': continue
            for kv in pm[2].split(','):
                a,b=kv.strip().split('='); d[a]=b
    if 'PM: suspend of devices complete' in l or 'msm_cpu_pm_enter_sleep' in l:
        susp.append((t,{k:dict(v) for k,v in st.items()}))
print(len(susp),'suspend marks, last at',susp[-1][0] if susp else None)
# long suspends
import collections
snap=susp[-1][1]
for k in sorted(snap,key=lambda x:(x[0].split()[0],int(x[0].split()[1]),x[1])):
    print(k[0],k[1],snap[k])
