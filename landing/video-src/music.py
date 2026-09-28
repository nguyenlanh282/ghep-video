"""Original upbeat background loop, synthesised (no samples): pads + pluck arpeggio + bass + soft kick/hat, 104 BPM."""
import sys, wave
import numpy as np

SR = 44100; BPM = 104; BEAT = 60 / BPM
total = float(sys.argv[1]); out = sys.argv[2]
n = int(total * SR); t = np.arange(n) / SR
mix = np.zeros((n, 2))

def midi(m): return 440 * 2 ** ((m - 69) / 12)
# Am - F - C - G, one chord per bar (4 beats)
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]
BASS = [45, 41, 48, 43]
bar = 4 * BEAT

def env(length, a=.01, r=.3):
    x = np.arange(int(length * SR)) / SR
    return np.minimum(1, x / a) * np.exp(-x / r)

def add(sig, start, gain=1., pan=0.):
    i = int(start * SR)
    if i >= n: return
    sig = sig[:n - i]
    mix[i:i + len(sig), 0] += sig * gain * (1 - pan) ** .5
    mix[i:i + len(sig), 1] += sig * gain * (1 + pan) ** .5

k = 0
while k * bar < total:
    c = CHORDS[k % 4]; s = k * bar
    # pad: detuned soft saw-ish (few harmonics), slow attack
    L = bar + .3; x = np.arange(int(L * SR)) / SR
    pad = sum(sum(np.sin(2 * np.pi * midi(m) * h * x * (1 + d)) / h ** 1.6 for h in (1, 2, 3)) for m in c for d in (-.003, .003))
    pad *= np.minimum(1, x / .5) * np.minimum(1, (L - x) / .4)
    add(pad, s, .018)
    # bass on beats 1 and 3, plus an off-beat push
    for b in (0, 2, 2.5):
        L = BEAT * .9; x = np.arange(int(L * SR)) / SR
        f = midi(BASS[k % 4]); bs = (np.sin(2 * np.pi * f * x) + .3 * np.sin(4 * np.pi * f * x)) * env(L, .005, .35)
        add(bs, s + b * BEAT, .16)
    # pluck arpeggio in 8ths
    arp = [c[0] + 12, c[1] + 12, c[2] + 12, c[1] + 12, c[2] + 12, c[0] + 24, c[2] + 12, c[1] + 12]
    for j, m in enumerate(arp):
        L = .35; x = np.arange(int(L * SR)) / SR; f = midi(m)
        pl = (np.sin(2 * np.pi * f * x) + .4 * np.sin(4 * np.pi * f * x) + .15 * np.sin(6 * np.pi * f * x)) * env(L, .003, .09)
        add(pl, s + j * BEAT / 2, .05, -.4 if j % 2 else .4)
    # drums: kick on every beat, hat on off-beats, clap on 2 and 4
    for b in range(4):
        L = .3; x = np.arange(int(L * SR)) / SR
        kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-x * 30)) * x) * np.exp(-x * 11)
        add(kick, s + b * BEAT, .30)
        hat = np.random.default_rng(k * 8 + b).standard_normal(int(.05 * SR)); hat = np.diff(hat, prepend=0) * env(.05, .001, .012)
        add(hat, s + (b + .5) * BEAT, .035)
        if b in (1, 3):
            cl = np.random.default_rng(99 + k * 4 + b).standard_normal(int(.15 * SR)) * env(.15, .002, .04)
            add(np.convolve(cl, np.ones(6) / 6, 'same'), s + b * BEAT, .06)
    k += 1

# intro fade-in (first bar), outro fade-out (last 2.5 s)
fade = np.minimum(1, t / (bar * .75)) * np.minimum(1, (total - t) / 2.5)
mix *= fade[:, None]
mix /= max(1e-9, np.abs(mix).max()) / .8
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
