"""Voice (narration clips placed at each scene start) + synthesized music, ducked under the voice, into the video."""
import json, subprocess, sys
video, out, lufs = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open('durs.json')); total = round(sum(d), 2); starts = [sum(d[:i]) + .45 for i in range(len(d))]
ins, fl = [], []
for i, s in enumerate(starts):
    ins += ['-i', f'vo/s{i + 1}.mp3']; ms = int(s * 1000); fl.append(f'[{i}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}]')
n = len(starts); ins += ['-i', 'music.wav']
fl.append(''.join(f'[v{i}]' for i in range(n)) + f'amix=inputs={n}:normalize=0:duration=longest,apad=whole_dur={total},volume=1.6,highpass=f=80,acompressor=threshold=0.1:ratio=2.5:attack=5:release=120[vo]')
fl.append('[vo]asplit[vo1][sc]')
fl.append(f'[{n}:a]volume=0.5[mu];[mu][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]')
fl.append(f'[vo1][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I={lufs}:TP=-1.5:LRA=9,alimiter=limit=0.89[a]')
subprocess.run(['/opt/homebrew/bin/ffmpeg', '-v', 'error', '-y', *ins, '-i', video, '-filter_complex', ';'.join(fl), '-map', f'{n + 1}:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-shortest', '-movflags', '+faststart', out], check=True)
