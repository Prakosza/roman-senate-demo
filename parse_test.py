import json

lines = open("/tmp/debate_raw.txt").readlines()
starts = 0
ends = 0
done = 0
speakers = []

for line in lines:
    line = line.strip()
    if not line.startswith("data: ") or line == "data: [DONE]":
        continue
    try:
        obj = json.loads(line[6:])
        c = obj["choices"][0]["delta"].get("content", "")
        if c.startswith("[START:"):
            starts += 1
            speakers.append(c[7:-1])
        elif c == "[END_TURN]":
            ends += 1
        elif c == "[DEBATE_DONE]":
            done += 1
    except:
        pass

print(f"Turns started: {starts}")
print(f"Turns ended: {ends}")
print(f"Debate done: {done}")
print(f"Total lines: {len(lines)}")
print(f"Speakers: {speakers[:10]}...")
