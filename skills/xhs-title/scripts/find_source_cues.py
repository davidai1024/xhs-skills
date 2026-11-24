"""Collect competing, time-stamped editorial cues from official captions."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re

STAMP = re.compile(r"^\[(\d+):(\d+)\]\s*(.+)$", re.M)
WORDS = re.compile(r"[一-鿿]{2,}|[A-Za-z0-9]+(?:[.+-][A-Za-z0-9]+)*")
RULES = {
    "question": re.compile(r"为什么|怎么|什么样|怎么样|什么体验|能不能|能否|到底|究竟|有没有|值不值|哪[个些种]|会有多"),
    "judgment": re.compile(r"最[强好难奇大]|史上|天花板|极限|最[让值得]|称得上|算是|值得|离谱|反常|出乎意料|让我意外|我觉得"),
    "event": re.compile(r"我们(?:试了|做了|拍到|找到|遇到|去|发现|看到)|居然|竟然|没想到|最后|结果|第一次|真的|成了|还真|出来了"),
    "premise": re.compile(r"假如|如果|就连|不到|只要|只用|不过|哪怕|相当于|就像|传说|据说|\d[\d,.]*\s*(?:年|天|米|台|部|个|块|元|位|%|瓦|秒|倍)"),
}


def terms(text):
    for word in WORDS.findall(text.casefold()):
        if word.isascii():
            if not word.isdigit():
                yield word
        else:
            yield from (word[i:i + 2] for i in range(len(word) - 1))


def extract(text, count=12):
    rows = [(int(m) * 60 + int(s), line.strip()) for m, s, line in STAMP.findall(text)]
    if not rows:
        return []
    frequencies = Counter(term for _, line in rows for term in set(terms(line)))
    kinds = defaultdict(list)
    for i, (time, words) in enumerate(rows):
        for tag, matcher in RULES.items():
            matched = list(matcher.finditer(words))
            if not matched:
                continue
            pieces = [(stamp, line) for stamp, line in rows[max(0, i - 1):i + 3] if abs(stamp - time) <= 15]
            if not pieces:
                continue
            excerpt = " ".join(line for _, line in pieces)
            keys = set(terms(excerpt))
            richness = sum(math.log1p(1 / frequencies[t]) for t in keys) / math.sqrt(len(keys) or 1)
            strength = sum(1.7 if any(w in m[0] for w in ('最强','史上','到底','究竟','没想到','居然','传说','据说')) else 1
                           for m in matched)
            score = richness + strength * .65 + (.2 if 0 <= time <= 100 else 0)
            kinds[tag].append((score, time, excerpt, pieces[0][0], pieces[-1][0], [m[0] for m in matched]))
    selected, use, seen = [], Counter(), set()
    groups = {tag: iter(sorted(cues, key=lambda r: (-r[0], r[1]))) for tag, cues in kinds.items()}
    while groups and len(selected) < count:
        for tag in list(groups):
            for _, time, excerpt, start, end, matches in groups[tag]:
                if any(abs(time - prior) < 12 for prior in seen) or use[time // 120] >= 4:
                    continue
                use[time // 120] += 1
                seen.add(time)
                selected.append({"kind": tag, "anchor_seconds": time, "window_seconds": [start, end],
                                 "audio_excerpt": excerpt, "signal": matches})
                break
            else:
                del groups[tag]
            if len(selected) == count:
                break
    return sorted(selected, key=lambda r: r["anchor_seconds"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("transcript", type=Path)
    args = p.parse_args()
    print(json.dumps(extract(args.transcript.read_text()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
