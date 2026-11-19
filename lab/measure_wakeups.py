import time, json

def read_stat():
    with open('/proc/stat') as f:
        for line in f:
            if line.startswith('cpu '):
                fields = [int(x) for x in line.split()[1:]]
                # user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
                return fields
    return []

def read_interrupts():
    irqs = {}
    with open('/proc/interrupts') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            irq_name = parts[0].rstrip(':')
            if irq_name.isdigit():
                # sum counts across cores
                counts = [int(x) for x in parts[1:9] if x.isdigit()]
                desc = " ".join(parts[9:]) if len(parts) > 9 else ""
                irqs[irq_name] = {"total": sum(counts), "desc": desc}
    return irqs

s1 = read_stat()
i1 = read_interrupts()
time.sleep(5)
s2 = read_stat()
i2 = read_interrupts()

total_delta = sum(s2) - sum(s1)
idle_delta = (s2[3] + s2[4]) - (s1[3] + s1[4])
cpu_util = 100.0 * (1.0 - (idle_delta / total_delta)) if total_delta else 0

irq_diffs = []
for irq, data in i2.items():
    if irq in i1:
        diff = data["total"] - i1[irq]["total"]
        if diff > 0:
            irq_diffs.append({"irq": irq, "delta_5s": diff, "rate_per_sec": diff / 5.0, "desc": data["desc"]})

irq_diffs.sort(key=lambda x: x["delta_5s"], reverse=True)

out = {
    "cpu_util_percent": cpu_util,
    "top_irq_wakeups": irq_diffs[:15]
}

with open("/data/local/tmp/vaani-lab/results/idle_wakeups_5s.json", "w") as f:
    json.dump(out, f, indent=2)

print(f"5-second CPU utilization: {cpu_util:.2f}%")
print("Top IRQ wakeups:")
for item in irq_diffs[:10]:
    print(f"IRQ {item['irq']:>4}: {item['delta_5s']:>6} ({item['rate_per_sec']:>6.1f}/s) {item['desc']}")
