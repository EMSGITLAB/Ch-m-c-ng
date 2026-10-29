"""Record evidence in the single project plan after a verified step."""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("task")
parser.add_argument("evidence")
parser.add_argument("--note", default="")
parser.add_argument("--complete", action="store_true")
args = parser.parse_args()
if not re.fullmatch(r"(?:T|KT)\d{2}",args.task):
    raise SystemExit("Invalid task or test ID")
plan = Path(__file__).resolve().parents[1] / "KE_HOACH_TRIEN_KHAI.md"
content = plan.read_text(encoding="utf-8")
pattern = rf"(?ms)^- \[[ x]\] \*\*{re.escape(args.task)} —.*?(?=\n- \[[ x]\] \*\*|\nGhi chú:|\n##|\Z)"
match = re.search(pattern, content)
if not match:
    raise SystemExit("Task ID not found")
block = match.group()
block = re.sub(r"^- \[[ x]\]", "- [x]" if args.complete else "- [ ]", block)
block = re.sub(r"  - (Minh chứng|Kết quả và minh chứng):.*", lambda match: f"  - {match.group(1)}: {args.evidence}", block)
if args.note:
    block = re.sub(r"\n  - Trạng thái:.*", "", block)
    block = block.rstrip() + "\n  - Trạng thái: " + args.note + "\n"
content = content[:match.start()] + block + content[match.end():]
done = len(re.findall(r"(?m)^- \[x\] \*\*T\d{2} —", content))
total = len(re.findall(r"(?m)^- \[[ x]\] \*\*T\d{2} —", content))
content = re.sub(r"\*\*\d+/\d+\*\*(?= trong phạm vi hiện tại)", f"**{done}/{total}**", content, count=1)
tests_done=len(re.findall(r"(?m)^- \[x\] \*\*KT\d{2} —", content))
test_total=len(re.findall(r"(?m)^- \[[ x]\] \*\*KT\d{2} —", content))
content=re.sub(r"\*\*\d+/\d+\*\*(?= trong phạm vi hiện tại; 5 ca)",f"**{tests_done}/{test_total}**",content,count=1)
for phase in range(7):
    start = content.index(f"### M{phase} ")
    end_match = re.search(r"\n##", content[start + 1:])
    end = start + 1 + end_match.start() if end_match else len(content)
    segment = content[start:end]
    count = len(re.findall(r"(?m)^- \[x\] \*\*T\d{2} —", segment))
    segment = re.sub(r"\*\*Tiến độ:\*\* \d+/", f"**Tiến độ:** {count}/", segment, count=1)
    content = content[:start] + segment + content[end:]
plan.write_text(content, encoding="utf-8")
print(f"{args.task}: {'complete' if args.complete else 'in progress'}; {done}/{total}")

