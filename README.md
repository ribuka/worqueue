# Worqueue

Worqueue（ワーキュー）は、プレイングマネージャー向けの、優先順位の可視化とタスク管理を統合したアプリです。自分の実装の仕事と、チームに振った仕事を 1 か所で俯瞰し、次に何をするかを決めます。

開発中です。仕様は [docs/spec.md](docs/spec.md) を参照してください。

## 開発の準備

- クローンしたら 1 回、`git config core.hooksPath .githooks` を実行します。`git worktree add` で作った worktree の `data/` が、メインのチェックアウトの `data/` へのジャンクションになります。
