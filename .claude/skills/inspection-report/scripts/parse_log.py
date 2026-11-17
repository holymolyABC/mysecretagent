#!/usr/bin/env python3
"""네트워크 장비 점검 로그(Cisco IOS / HP·H3C Comware / 기타)에서 점검서 값을 뽑아 JSON으로 출력.

사용법:
    python3 parse_log.py LOG [LOG ...]            # JSON 배열 출력
    python3 parse_log.py --table LOG [LOG ...]    # 사람이 보기 쉬운 표 출력

못 찾은 값은 null 로 둔다. 추측해서 채우지 않는다.
알 수 없는 장비(Aruba, L4 등)는 vendor="unknown" 과 함께 candidates(관련 줄)만 돌려준다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 정상 운영 중에도 흔히 찍히는 로그 → 장애 아님(별도 카운트)
NOISE = re.compile(
    r"LINK-3-UPDOWN|LINEPROTO-5-UPDOWN|LINK_UPDOWN|SHELL_CMD|SHELL_LOGIN|SHELL_LOGOUT|"
    r"SYS-5-CONFIG_I|SSH|VTY|LOGIN|LOGOUT|DUPLEX_MISMATCH|PORT_?SECURITY|ILPOWER-[57]-",
    re.I,
)
ALERT_WORDS = re.compile(
    r"\bfan|\btemp|thermal|\bpower|\bpsu|\bsupply|\bfail|\bfault|crash|\breload|err-?disable|overheat", re.I)


def read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(enc).replace("\r", "")
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def first(pattern: str, text: str, flags: int = re.I | re.M, group: int = 1):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def mb(n_bytes: int) -> str:
    return f"{round(n_bytes / 1024 / 1024)}M"


def notable_logs(lines: list[str], sev_re: re.Pattern) -> tuple[list[str], int]:
    """심각도 0~3 또는 FAN/TEMP/POWER 관련 로그만 추림. 링크 업/다운은 개수만."""
    hits, flaps, seen = [], 0, set()
    for ln in lines:
        m = sev_re.search(ln)
        if not m:
            continue
        if re.search(r"UPDOWN|LINK_UPDOWN", ln):
            flaps += 1
            continue
        sev = int(m.group("sev"))
        if sev >= 6 or (NOISE.search(ln) and sev > 2):
            continue
        if sev <= 3 or ALERT_WORDS.search(ln):
            key = re.sub(r"^\W*\w{3}\s+\d+\s+[\d:.]+\s*(\d{4})?", "", ln).strip()
            if key not in seen:
                seen.add(key)
                hits.append(ln.strip())
    return hits[-15:], flaps


def parse_cisco(t: str) -> dict:
    d: dict = {"vendor": "cisco"}
    d["hostname"] = first(r"^([\w#&.\-]+)[#>]\s*(?:sh|show|en|ter)", t)
    d["model"] = first(r"Model number\s*:\s*(\S+)", t) or first(r"^cisco (\S+) .*processor", t)
    d["serial"] = first(r"System serial number\s*:\s*(\S+)", t) or first(r"Processor board ID (\S+)", t)
    ver = first(r"Cisco IOS.*?Software.*?,\s*Version ([^,\s]+)", t)
    image = first(r"Cisco IOS.*?Software(?: \[\w+\])?, \S+ Software \(([^)]+)\)", t)
    d["sw_version"] = ver
    d["sw_image"] = image
    d["uptime"] = first(r"uptime is (.+)$", t)
    m = re.search(r"CPU utilization for five seconds: (\d+)%/?(\d+)?%?; one minute: (\d+)%; five minutes: (\d+)%", t)
    if m:
        d["cpu_5s"], d["cpu_1m"], d["cpu_5m"] = int(m.group(1)), int(m.group(3)), int(m.group(4))
        d["cpu"] = f"{m.group(1)}%"
    core = re.findall(r"Core (\d+): CPU utilization for five seconds: (\d+)%", t)
    if core:
        d["cpu"] = " / ".join(f"Core {c}: {p}%" for c, p in core)
    m = re.search(r"Processor Pool Total:\s*(\d+) Used:\s*(\d+) Free:\s*(\d+)", t)
    if m:
        total, used, free = map(int, m.groups())
        d["mem_used"], d["mem_free"], d["mem_total"] = mb(used), mb(free), mb(total)
        d["mem_rate"] = f"{round(used * 100 / total)}%"
    # FAN
    fan_lines = re.findall(r"^.*\bFAN\b.*$", t, re.I | re.M)
    fan_txt = " ".join(l for l in fan_lines if not re.search(r"sh(ow)? env|^\s*%", l, re.I))
    if fan_txt:
        d["fan"] = "Fault" if re.search(r"fail|fault|not ?ok|bad|not present", fan_txt, re.I) else (
            "정상" if re.search(r"\bOK\b|good|normal|operating|green", fan_txt, re.I) else None)
    # 온도
    temp = first(r"(?:Temperature Value|System Temperature Value|Inlet Temperature Value)\s*:\s*(\d+)", t)
    if not temp:
        temp = first(r"^\s*\d+\s+\S*(?:Inlet|Hotspot|Outlet|Air|Sensor)\S*\s+(\d+)\s*C?\b", t)
    d["temperature"] = int(temp) if temp else None
    tstate = first(r"TEMPERATURE is (\w+)", t)
    if tstate and tstate.upper() != "OK":
        d["temp_alarm"] = tstate
    # 전원
    pw = re.findall(r"^\s*(?:\d+\s+)?(?:PS|PWR|Built-in|Power Supply)\S*.*?\b(Good|OK|Normal|Bad|Fail\w*|Faulty|Not Present|No Input)\b",
                    t, re.I | re.M)
    if pw:
        bad = [s for s in pw if re.search(r"bad|fail|faulty|no input", s, re.I)]
        d["power"] = "Fault" if bad else "정상"
    d["logs"], d["link_flaps"] = notable_logs(
        t.splitlines(), re.compile(r"%(?P<fac>[A-Z0-9_]+)-(?P<sev>[0-7])-(?P<mn>[A-Z0-9_]+)"))
    d["crc_errors"] = crc_from_counters(t)
    return d


def crc_from_counters(t: str):
    m = re.search(r"sh(?:ow)? int(?:erfaces)? cou\w* err\w*\s*\n(.*?)(?:\n\S+[#>])", t, re.S | re.I)
    if not m:
        return None
    total = 0
    for ln in m.group(1).splitlines():
        cols = ln.split()
        if len(cols) >= 4 and re.match(r"^(Gi|Fa|Te|Twe|Fo|Hu|Po|Eth)", cols[0]) and all(c.isdigit() for c in cols[1:]):
            total += int(cols[2])  # Align-Err, FCS-Err → FCS 열(index 2)
    return total


def parse_hp(t: str) -> dict:
    d: dict = {"vendor": "hp_comware"}
    d["hostname"] = first(r"^[<\[]([^\]>]+)[\]>]\s*(?:dis|system-view|sys)", t)
    d["model"] = first(r"^(?:HP|H3C|HPE)\s+(.+?)\s+Switch uptime is", t) or first(r"Brd Type\s*:\s*(?:HPE?|H3C)?\s*(.+?)(?: Switch)?$", t)
    rel = first(r"Comware Software, Version ([^\n]+)", t)
    d["sw_version"] = f"Version {rel}" if rel else None
    d["uptime"] = first(r"uptime is (.+)$", t)
    d["serial"] = first(r"DEVICE_SERIAL_NUMBER\s*:\s*(\S+)", t) or first(r"Serial Number\s*:\s*(\S+)", t)
    cpu = re.findall(r"(\d+)% in last 5 seconds", t)
    if cpu:
        d["cpu"] = f"{cpu[0]}%" if len(cpu) == 1 else " / ".join(f"Slot{i + 1}: {c}%" for i, c in enumerate(cpu))
        d["cpu_5m"] = int(first(r"(\d+)% in last 5 minutes", t) or cpu[0])
    tot, used = first(r"System Total Memory\(bytes\):\s*(\d+)", t), first(r"Total Used Memory\(bytes\):\s*(\d+)", t)
    if tot and used:
        tot_i, used_i = int(tot), int(used)
        d["mem_used"], d["mem_free"], d["mem_total"] = mb(used_i), mb(tot_i - used_i), mb(tot_i)
    d["mem_rate"] = first(r"Used Rate:\s*(\d+%)", t)
    fans = re.findall(r"FAN\s+\d+\s*\n\s*State\s*:\s*(\w+)", t, re.I)
    if fans:
        d["fan"] = "정상" if all(f.lower() == "normal" for f in fans) else "Fault"
    pws = re.findall(r"Power\s+\d+\s*\n\s*State\s*:\s*(\w+)", t, re.I)
    if pws:
        d["power"] = "정상" if all(p.lower() == "normal" for p in pws) else "Fault"
    temps = re.findall(r"^\s*(?:hotspot|inflow|outflow|chassis)\s*\d*\s+(\d+)\s", t, re.I | re.M)
    d["temperature"] = max(map(int, temps)) if temps else None
    d["logs"], d["link_flaps"] = notable_logs(
        t.splitlines(), re.compile(r"^%.*?\s(?P<fac>[A-Z0-9_]+)/(?P<sev>[0-7])/(?P<mn>[A-Z0-9_]+)"))
    return d


def parse_unknown(t: str) -> dict:
    pat = re.compile(r"cpu|memory|mem |temp|fan|power|psu|serial|version|uptime|fail|fault|error", re.I)
    lines = [l.strip() for l in t.splitlines() if pat.search(l) and len(l.strip()) < 200]
    return {"vendor": "unknown", "candidates": lines[:80]}


def parse(path: Path) -> dict:
    t = read(path)
    if re.search(r"Comware|^[<\[][^\]>]+[\]>]\s*display", t, re.M):
        d = parse_hp(t)
    elif re.search(r"Cisco IOS|CPU utilization for five seconds|^[\w#&.\-]+#\s*sh", t, re.M):
        d = parse_cisco(t)
    else:
        d = parse_unknown(t)
    d["file"] = path.name
    return d


def judge(d: dict) -> None:
    """점검서에 그대로 쓸 수 있는 요약 판정(LOG/점검의견) 추가."""
    if d.get("vendor") == "unknown":
        return
    issues = []
    if d.get("fan") == "Fault":
        issues.append("FAN fault")
    if d.get("power") == "Fault":
        issues.append("전원 fault")
    if d.get("temp_alarm"):
        issues.append(f"온도 {d['temp_alarm']}")
    if d.get("cpu_5m") is not None and d["cpu_5m"] >= 70:
        issues.append(f"CPU {d['cpu_5m']}%")
    if any(re.search(r"fan|temp|thermal|power|psu", l, re.I) for l in d.get("logs", [])) and not issues:
        issues.append("H/W 관련 로그 확인")
    if issues and d.get("temperature") is not None:
        issues.append(f"온도 {d['temperature']}도")
    d["log_status"] = "주의" if issues else "정상"
    d["opinion"] = ", ".join(issues) if issues else "양호"


def main(argv: list[str]) -> int:
    table = "--table" in argv
    paths = [Path(a) for a in argv if a != "--table"]
    if not paths:
        print(__doc__)
        return 1
    out = []
    for p in paths:
        d = parse(p)
        judge(d)
        out.append(d)
    if table:
        cols = ["hostname", "vendor", "model", "serial", "sw_version", "cpu", "mem_used", "mem_free",
                "temperature", "fan", "power", "log_status", "opinion", "link_flaps"]
        for d in out:
            print(f"■ {d['file']}")
            for c in cols:
                if c in d:
                    print(f"   {c:12}: {d[c]}")
            for l in d.get("logs", []):
                print(f"   log         : {l}")
            for l in d.get("candidates", [])[:30]:
                print(f"   ?           : {l}")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
