#!/usr/bin/env bash
# 세션 기록(JSONL)에서 사용자와 에이전트의 대화 텍스트만 뽑아 compact 경계마다 segment-NN.txt로 나눠 쓴다.
# 도구 호출, 도구 출력, thinking, system-reminder, compact 요약은 뺀다.
# 각 발화 앞에 원본 JSONL 줄 번호를 붙여, 후보를 찾은 쪽이 좌표로 인용할 수 있게 한다.
#
# usage: extract-transcript.sh <transcript.jsonl> <out_dir>
# 마지막 segment는 compact 이후 구간이라 현재 컨텍스트에 이미 있다.
set -euo pipefail

transcript="${1:?usage: extract-transcript.sh <transcript.jsonl> <out_dir>}"
out_dir="${2:?usage: extract-transcript.sh <transcript.jsonl> <out_dir>}"

mkdir -p "$out_dir"
rm -f "$out_dir"/segment-*.txt

jq -rn '
  foreach inputs as $e (0;
    if $e.subtype == "compact_boundary" then . + 1 else . end;
    [., input_line_number, $e])
  | .[0] as $seg | .[1] as $line | .[2] as $e
  | select(($e.type == "user" or $e.type == "assistant")
           and ($e.isSidechain != true) and ($e.isMeta != true) and ($e.isCompactSummary != true))
  | ($e.message.content
     | if type == "string" then .
       else map(select(.type == "text") | .text) | join("\n") end
     | gsub("<system-reminder>.*?</system-reminder>"; ""; "p")
     | gsub("^\\s+|\\s+$"; "")) as $text
  | select($text != "")
  | ("[L\($line) \($e.type)] " + $text) | split("\n")[]
  | "\($seg)\t\(.)"
' "$transcript" \
| awk -F'\t' -v dir="$out_dir" '{
    seg = sprintf("%s/segment-%02d.txt", dir, $1)
    sub(/^[^\t]*\t/, "")
    print > seg
  }'

for f in "$out_dir"/segment-*.txt; do
  printf '%s\t%s bytes\n' "$f" "$(wc -c < "$f" | tr -d ' ')"
done
