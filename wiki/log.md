# Log

Append-only. 각 항목은 `## [YYYY-MM-DD] <action> | <title>` 형태로 시작한다.
`grep "^## \[" log.md | tail` 같은 식으로 최근 활동을 빠르게 확인할 수 있다.

<!-- 예시
## [2026-04-17] ingest | Attention Is All You Need
- source: raw/papers/attention-is-all-you-need/main.tex
- pages touched: wiki/sources/attention-is-all-you-need.md, wiki/concepts/self-attention.md
-->
