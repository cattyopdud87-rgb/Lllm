import os, glob, json

def get_pss(pid):
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except:
        return 0

procs = []
for p in glob.glob("/proc/[0-9]*"):
    try:
        pid = int(os.path.basename(p))
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().decode("utf-8", errors="replace").replace("\x00", " ").strip()
        if not cmd:
            with open(f"/proc/{pid}/comm") as f:
                cmd = f"[{f.read().strip()}]"
        pss = get_pss(pid)
        if pss > 0:
            procs.append({"pid": pid, "pss_kb": pss, "cmd": cmd[:100]})
    except:
        pass

procs.sort(key=lambda x: x["pss_kb"], reverse=True)
with open("/data/local/tmp/vaani-lab/results/pss_baseline.json", "w") as f:
    json.dump(procs, f, indent=2)

keywords = ["plasma", "kwin", "systemd", "pipewire", "wireplumber", "dbus", "anland", "droidspace", "waylandbridge", "dolphin", "fcitx", "gvfs", "audioserver", "audio.service", "Xwayland"]
c_procs = [p for p in procs if any(k in p["cmd"].lower() for k in keywords)]

print("Container and audio/runtime processes PSS:")
for p in c_procs:
    print(f"{p['pid']:>7} {p['pss_kb']:>8} kB  {p['cmd']}")
