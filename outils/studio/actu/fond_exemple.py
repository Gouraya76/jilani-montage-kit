import subprocess, json
A='/workspace/news/src/xbqswmy.mp4'; E='/workspace/news/src/xbqq5ra.mp4'
L=[('A',2,3.2),('E',0,2.2),('E',16,2.8),('A',60,3.2),('E',7,2.8),('A',300,3),('A',280,2.6),('E',10,2.8),('E',13,2.6),('E',19,2),('E',24,1.8),('E',26,3),('E',29,2.5),('E',31,2.5),('E',35,2.4),('E',37,2.5),('A',135,2.8),('E',42,2.6),('E',40,2),('A',410,2),('A',150,3.4),('A',340,3),('A',290,2.8),('A',165,5.6)]
lst=[]
for i,(f,s,d) in enumerate(L):
    crop='crop=146:260:183:28' if f=='E' else 'crop=120:212:196:4'
    o=f'clips/{i:02d}.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(s),'-t',str(d),'-i',E if f=='E' else A,'-vf',crop+',scale=1080:1920:flags=lanczos,unsharp=7:7:0.8,hqdn3d=2:2:3:3,eq=contrast=1.06:saturation=1.12,fps=30,setsar=1','-an','-c:v','libx264','-crf','16','-preset','fast',o],check=True)
    lst.append(f"file '{o}'")
open('liste.txt','w').write('\n'.join(lst))
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i','liste.txt','-c','copy','fond.mp4'],check=True)
c=[];t=0
for _,_,d in L[:-1]: t+=d; c.append(round(t,2))
json.dump({'coupes':c,'duree':round(t+L[-1][2],2)},open('coupes.json','w')); print(c, t+L[-1][2])
