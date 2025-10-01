デプロイ完了後、ブラウザで `http://<VPSのIPアドレス>` または `http://<ドメイン>` にアクセスしてください。

## 7. 自動更新スケジュール

以下のタイミングで自動実行されます：

| 時刻 | 処理 | 内容 |
|------|------|------|
| 6:15 JST | データ取得 | 市場データ・ニュース・経済指標の取得 |
| 6:28 JST | レポート生成 | AI解説・コラム生成、Push通知送信 |
| 5:30 JST | HWBスキャン | Russell 3000銘柄のスキャン（火〜土） |

**実行日**: 月曜〜金曜（市場営業日）

## 8. トラブルシューティング

### 8.1 コンテナが起動しない場合

```bash
# ログを確認
docker-compose logs -f

# コンテナを再起動
docker-compose restart
```

### 8.2 データが更新されない場合

```bash
# Cronログを確認
docker compose exec app cat /app/logs/cron.log

# 手動でデータ更新を実行
docker compose exec app python -m backend.data_fetcher fetch
docker compose exec app python -m backend.data_fetcher generate
```

### 8.3 認証できない場合

- `.env`ファイルの`AUTH_PIN`設定を確認
- ブラウザのキャッシュをクリア
- LocalStorageとIndexedDBをクリア

### 8.4 Push通知が届かない場合

```bash
# VAPIDキーの生成確認
docker compose exec app cat /app/data/security_keys.json

# 通知権限の確認（ブラウザ設定）
# サービスワーカーの登録確認（DevTools > Application > Service Workers）
```

## 9. セキュリティに関する注意事項

1. **PINの変更**: デフォルトPIN（123456）は必ず変更してください
2. **APIキーの管理**: `.env`ファイルは絶対にGitにコミットしないでください
3. **セキュリティキーのバックアップ**: `data/security_keys.json`は定期的にバックアップしてください
4. **本番環境**: HTTPS化（リバースプロキシ経由）を推奨します

## 10. ライセンス

本プロジェクトは個人利用を目的としています。商用利用については別途ご相談ください。

## 11. サポート

問題が発生した場合は、以下を確認してください：
- [ログファイル](logs/)
- [設計書](hanaview-design.md)
- [要件定義書](hanaview-requirements.md)
- [仕様書](hanaview-specification.md)
