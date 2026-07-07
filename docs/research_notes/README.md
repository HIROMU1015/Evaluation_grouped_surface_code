# Research notes

この directory は、研究日誌・作業ログ・解釈の変化を残す場所である。

ここでは結論だけでなく、仮説、観測、解釈、未解決点、次の作業を日付付きで追記する。ノートごとに日付を分けるのではなく、各ノート内の追記エントリに日付を付けて、研究の進行が時系列で分かるようにする。

## 主なノート

- `architecture_research_log.md`
  - surface-code architecture sensitivity の主な研究日誌。
  - 同一 PF・同一 molecule・同一 logical circuit を固定したときに、topology、factory placement、magic-state supply、routing / mapping、grid size、factory count が resource metrics にどう効くかを記録する。
- `qpe_scope_and_semantics.md`
  - full QPE ではないこと、QPE-scale 外挿の意味論、observed result と estimated total の区別をまとめる基準メモ。
- `surface_code_architecture_sensitivity_note.md`
  - 初期の統合メモ。今後の主な追記先は `architecture_research_log.md` とする。

## 注意

`AGENT.md` / `AGENT_v1.md` は ignored/local file として扱う。repository 上の共有研究ノートではない。
