import subprocess
S='src/xbqswmy.mp4'; A='src/xbqxini.mp4'
L=[('S',2,8.2),('S',60,5),('S',280,5),('S',300,4),('S',205,4),('S',120,3.6),('S',425,9.8),('S',135,7),('S',410,7.6),('S',150,5.6),('S',340,9),('A',9,4.5),('S',165,6.2)]
lst=[]
for i,(f,s,d) in enumerate(L):
    vf=('crop=336:597:12:43' if f=='A' else 'crop=120:212:196:4')+',scale=1080:1920:flags=lanczos,unsharp=7:7:0.8,hqdn3d=2:2:3:3,fps=30,setsar=1'
    o=f'clips/{i:02d}.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(s),'-t',str(d),'-i',A if f=='A' else S,'-vf',vf,'-an','-c:v','libx264','-crf','17','-preset','fast',o],check=True)
    lst.append(f"file '{o}'")
open('liste.txt','w').write('\n'.join(lst))
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i','liste.txt','-c','copy','fond.mp4'],check=True)
