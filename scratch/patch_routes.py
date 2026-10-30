with open('AIRA_ECOSYSTEM/agents/akane/reasoning_engine.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = """        # In RouterOS print detail format:
        # dst-address=0.0.0.0/0 gateway=192.168.1.1 distance=1 active=yes
        if "dst-address=" in line_clean:
            dst_m = re.search(r"dst-address=([0-9\.\/]+)", line_clean)
            gw_m = re.search(r"gateway=([^\s]+)", line_clean)
            dist_m = re.search(r"distance=(\d+)", line_clean)
            active_m = "active=yes" in line_clean
            if dst_m:
                dst = dst_m.group(1)
                gw = gw_m.group(1) if gw_m else ""
                dist = int(dist_m.group(1)) if dist_m else 1
                routes.append(ParsedRoute(
                    dst_address=dst,
                    gateway=gw,
                    distance=dist,
                    active=active_m,
                    raw_flags="DETAIL",
                ))
            continue"""

replacement = """        # In RouterOS print detail format:
        # dst-address=0.0.0.0/0 gateway=192.168.1.1 distance=1 active=yes
        if "dst-address=" in line_clean:
            dst_m = re.search(r"dst-address=([0-9\.\/]+)", line_clean)
            gw_m = re.search(r"gateway=([^\s]+)", line_clean)
            dist_m = re.search(r"distance=(\d+)", line_clean)
            prefix = line_clean.split("dst-address=")[0].strip()
            flags_m = prefix.split()[-1] if prefix else ""
            active_m = ("A" in flags_m) or ("active=yes" in line_clean) or ("active=no" not in line_clean and not flags_m)
            dynamic_m = ("D" in flags_m) or ("dynamic=yes" in line_clean)
            connect_m = ("C" in flags_m.upper()) or ("connect=yes" in line_clean)
            static_m = ("S" in flags_m.upper()) or ("static=yes" in line_clean)
            if dst_m:
                dst = dst_m.group(1)
                gw = gw_m.group(1) if gw_m else ""
                dist = int(dist_m.group(1)) if dist_m else 1
                routes.append(ParsedRoute(
                    dst_address=dst,
                    gateway=gw,
                    distance=dist,
                    active=active_m,
                    dynamic=dynamic_m,
                    connect=connect_m,
                    static=static_m,
                    raw_flags=flags_m or "DETAIL",
                ))
            continue"""

# Normalize CRLF/LF
target_crlf = target.replace("\r\n", "\n").replace("\n", "\r\n")
replacement_crlf = replacement.replace("\r\n", "\n").replace("\n", "\r\n")

if target in text:
    text = text.replace(target, replacement)
    with open('AIRA_ECOSYSTEM/agents/akane/reasoning_engine.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("SUCCESS LF")
elif target_crlf in text:
    text = text.replace(target_crlf, replacement_crlf)
    with open('AIRA_ECOSYSTEM/agents/akane/reasoning_engine.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("SUCCESS CRLF")
else:
    print("TARGET NOT FOUND")
