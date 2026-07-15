PAL CASINO V1

別Bot構成 / discord.py / PostgreSQL / Railway
PAL BANKのDATABASE_URLを共用し、bank_gateway_for_other_bots.py経由でCHIP決済。

起動環境変数
DISCORD_TOKEN = PAL CASINO BotのToken
DATABASE_URL = PAL BANKと同じPostgreSQL

初回
!casinosetup
→ CASINO構築

自動作成
🎰 PAL CASINO
📌｜casino-guide
🎰｜casino
🏆｜casino-ranking
🔥｜big-win
📢｜casino-status

🔒 CASINO ADMIN
⚙️｜casino-admin
📖｜casino-log
🚨｜casino-alert

V1実装ゲーム
🎰 3リールスロット

表示済み・準備中
スクラッチ / 宝くじ / ロト6 / ブラックジャック / ルーレット / マインズ
チンチロ / 丁半博打 / コイントス / ハイアンドロー / クラッシュ
5リールスロット / ジャックポットスロット / カザーンVIP / 競馬VIP
スポーツベット / 福引 / 動画・GIFゲーム

実装済み土台
BANK CHIP決済
Round ID
二重決済防止
プレイ履歴100件DB保持
CASINOプロフィール
デイリーボーナス
CHIP資産ランキング
最大勝利ランキング
JACKPOT POOL表示
BIG WIN x30通知
ゲームON/OFF
CASINO統計
自動カテゴリー・チャンネル作成
チャンネル修復
パネル再設置
構成削除（DB保持）
