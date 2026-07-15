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
1日1回500 CHIPガチャ
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

PAL CASINO FINAL V3 ADDITIONS
- PAL宝くじ: 500 CHIP/枚, 01-100組, 100000-199999番, 1等10億CHIP, 組+番号照合
- 宝くじ管理抽選 / BANK自動配当
- ロト6: 500 CHIP/口, 1-43から6個, 手動選択/クイックピック
- ロト6山分け: 1等55%, 2等15%, 3等10%, 4等5%, 5等500固定, 15%繰越
- ロト6管理抽選 / BANK自動配当 / キャリーオーバー
- ゲーム詳細設定: 最低BET, 最大BET, VIP最大BET, probability_table, payout_table
- CASINO全体 target_rtp / 実測RTP
- SLOT3/SCRATCHは確率・配当テーブルとtarget_rtpを次ラウンドから参照
- 設定監査ログDB / casino-log通知
- 宝くじ・ロト6・ガチャは全体RTP対象外
