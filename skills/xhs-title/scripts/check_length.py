#!/usr/bin/env python3
"""Check final Xiaohongshu length and flag likely non-Arabic quantities."""

import argparse
import re


CHINESE_DIGITS = "零〇一二两三四五六七八九十百千万亿"
NUMBER_WITH_UNIT = re.compile(
    rf"百分之[{CHINESE_DIGITS}]+|"
    rf"(?<![0-9{CHINESE_DIGITS}])[约近超第]?[{CHINESE_DIGITS}]+"
    r"(?=\s*(?:块钱?|元|公里|米|秒钟?|分钟|小时|天|个月|月|年|台|部|款|期|次|遍|张|倍|帧|吨|个|条|页|题|类|项|趟))"
)
WORK_NAME = re.compile(r"《[^》]+》")
FIXED_EXPRESSIONS = ("一次性", "一天到晚", "第一时间", "一年到头")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20, help="A smaller limit for this delivery")
    parser.add_argument("--numbers", action="store_true", help="Flag likely Chinese numerals with units for review")
    parser.add_argument("titles", nargs="+")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("小红书笔记标题限额须在 1 至 20 之间")

    all_passed = True
    for title in args.titles:
        length = len(title.encode("utf-16-le")) // 2
        passed = 0 < length <= args.limit and bool(title.strip())
        quantities = []
        if args.numbers:
            check_text = WORK_NAME.sub(" ", title)
            for expression in FIXED_EXPRESSIONS:
                check_text = check_text.replace(expression, " ")
            quantities = NUMBER_WITH_UNIT.findall(check_text)
            passed = passed and not quantities
        all_passed = all_passed and passed
        status = "通过" if passed else "需改写"
        reported = f"（数量待核：{'、'.join(quantities)}）" if quantities else ""
        print(f"{status} {length}/{args.limit}  {title}{reported}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
