import discord
from casino_db import games, game, profile, history, ranking_chip, ranking_maxwin, total_stats, setting, set_setting, chip_balance, pool
from casino_services import play_slot

GOLD=0xF1C40F
DARK=0x2B2D31

def emb(title,desc=None,color=DARK):
    return discord.Embed(title=title,description=desc,color=color)

class BetModal(discord.ui.Modal,title="🎰 3リールスロット"):
    amount=discord.ui.TextInput(label="BET CHIP",placeholder="1～10,000",max_length=10)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            bet=int(str(self.amount).replace(",","").strip())
            r=await play_slot(i.user.id,bet)
            if r["status"]=="PREPARING":
                await i.edit_original_response(content="🚧 このゲームは現在準備中です。");return
            if r["status"]=="BET_RANGE":
                await i.edit_original_response(content=f"BETは **{r['min']:,}～{r['max']:,} CHIP** です。");return
            if r["status"]=="INSUFFICIENT_BALANCE":
                await i.edit_original_response(content="CHIP残高が足りません。");return
            if r["status"]=="MAINTENANCE":
                await i.edit_original_response(content="🏦 BANKメンテナンス中です。");return
            if r["status"]!="SUCCESS":
                await i.edit_original_response(content=f"CASINO処理エラー: `{r['status']}`");return
            e=emb("🎰 SLOT RESULT",f"## {'  '.join(r['reels'])}",GOLD)
            e.add_field(name="BET",value=f"{r['bet']:,} CHIP")
            e.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
            e.add_field(name="収支",value=f"{r['profit']:+,} CHIP")
            e.add_field(name="倍率",value=f"×{r['multiplier']}")
            e.add_field(name="現在残高",value=f"{r['balance']:,} CHIP")
            e.set_footer(text=f"Round ID: {r['round_id']}")
            await i.edit_original_response(content=None,embed=e)
            threshold=int(await setting("big_win_multiplier","30"))
            if r["multiplier"]>=threshold and await setting("big_win_enabled","1")=="1":
                cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='big_win'")
                if cid:
                    ch=i.guild.get_channel(int(cid))
                    if ch:
                        await ch.send(embed=emb("🔥🔥 BIG WIN 🔥🔥",
                          f"{i.user.mention} が **3リールスロット** で超高額配当！\n\n"
                          f"💰 BET **{r['bet']:,} CHIP**\n🏆 WIN **{r['payout']:,} CHIP**\n"
                          f"📈 **×{r['multiplier']}**\n\n`{r['round_id']}`",GOLD))
        except Exception as ex:
            await i.edit_original_response(content=f"ゲームエラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")

class PreparingView(discord.ui.View):
    def __init__(self,name):
        super().__init__(timeout=60);self.name=name
    @discord.ui.button(label="↩️ ゲーム一覧へ戻る",style=discord.ButtonStyle.secondary)
    async def back(self,i,b):
        await i.response.edit_message(embed=game_select_embed(),view=GameSelectView())

def game_select_embed():
    return emb("🎮 GAME SELECT","ゲームを選択してください。\n\n🚧 表示中の準備中ゲームは今後順次公開します。",GOLD)

class GameSelect(discord.ui.Select):
    def __init__(self):
        opts=[
          discord.SelectOption(label="3リールスロット",emoji="🎰",value="SLOT3"),
          discord.SelectOption(label="スクラッチ",emoji="🎟️",value="SCRATCH"),
          discord.SelectOption(label="宝くじ",emoji="🎫",value="LOTTERY"),
          discord.SelectOption(label="ロト6",emoji="🔢",value="LOTO6"),
          discord.SelectOption(label="ブラックジャック",emoji="🃏",value="BLACKJACK"),
          discord.SelectOption(label="ルーレット",emoji="🎡",value="ROULETTE"),
          discord.SelectOption(label="マインズ",emoji="💣",value="MINES"),
          discord.SelectOption(label="チンチロ",emoji="🎲",value="CHINCHIRO"),
          discord.SelectOption(label="丁半博打",emoji="🎴",value="CHOHAN"),
          discord.SelectOption(label="コイントス",emoji="🪙",value="COIN"),
          discord.SelectOption(label="ハイアンドロー",emoji="📈",value="HIGHLOW"),
          discord.SelectOption(label="クラッシュ",emoji="🚀",value="CRASH"),
          discord.SelectOption(label="5リールスロット",emoji="🎰",value="SLOT5"),
          discord.SelectOption(label="ジャックポットスロット",emoji="💰",value="JACKPOT_SLOT"),
          discord.SelectOption(label="カザーン｜VIP",emoji="🪙",value="KAZAAN"),
          discord.SelectOption(label="競馬｜VIP",emoji="🏇",value="HORSE"),
          discord.SelectOption(label="スポーツベット",emoji="⚽",value="SPORTS"),
          discord.SelectOption(label="福引",emoji="🎁",value="FUKUBIKI"),
          discord.SelectOption(label="動画・GIFゲーム",emoji="🎬",value="MEDIA_GAME"),
        ]
        super().__init__(placeholder="🎮 ゲームを選択",options=opts)
    async def callback(self,i):
        key=self.values[0];cfg=await game(key)
        if cfg["vip_only"]:
            vip=await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",str(i.user.id)) or False
            if not vip:
                await i.response.send_message("🔒 **VIP限定ゲームです。**",ephemeral=True);return
        if not cfg["implemented"] or not cfg["enabled"]:
            await i.response.edit_message(embed=emb("🚧 GAME PREPARING",f"## {cfg['display_name']}\n\n現在このゲームは準備中です。\n公開までお待ちください。",GOLD),view=PreparingView(cfg["display_name"]));return
        if key=="SLOT3":
            await i.response.send_modal(BetModal())

class GameSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180);self.add_item(GameSelect())

class CasinoPanelView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="🎮 ゲームを遊ぶ",style=discord.ButtonStyle.primary,custom_id="casino_games",row=0)
    async def games_button(self,i,b):await i.response.send_message(embed=game_select_embed(),view=GameSelectView(),ephemeral=True)
    @discord.ui.button(label="💰 CHIP残高",style=discord.ButtonStyle.secondary,custom_id="casino_balance",row=0)
    async def balance(self,i,b):await i.response.send_message(f"🎰 現在残高 **{await chip_balance(i.user.id):,} CHIP**",ephemeral=True)
    @discord.ui.button(label="📖 プレイ履歴",style=discord.ButtonStyle.secondary,custom_id="casino_history",row=1)
    async def hist(self,i,b):
        rows=await history(i.user.id,100);e=emb("📖 PLAY HISTORY",color=GOLD)
        e.description="\n\n".join(f"**{r['game_key']}｜{r['result']}**\nBET {r['bet']:,} / PAYOUT {r['payout']:,} CHIP\n`{r['round_id']}`" for r in rows[:10]) or "履歴はありません。"
        await i.response.send_message(embed=e,ephemeral=True)
    @discord.ui.button(label="🎰 CASINOプロフィール",style=discord.ButtonStyle.secondary,custom_id="casino_profile",row=1)
    async def prof(self,i,b):
        p=await profile(i.user.id);e=emb("🎰 CASINO PROFILE",color=GOLD)
        e.add_field(name="🎮 総プレイ",value=f"{p['plays']:,}回")
        e.add_field(name="💰 総BET",value=f"{p['total_bet']:,} CHIP")
        e.add_field(name="🏆 総配当",value=f"{p['total_payout']:,} CHIP")
        e.add_field(name="📈 収支",value=f"{p['total_payout']-p['total_bet']:+,} CHIP")
        e.add_field(name="🔥 最大勝利",value=f"{p['max_win']:,} CHIP")
        e.add_field(name="🎲 最多プレイ",value=p["favorite"])
        await i.response.send_message(embed=e,ephemeral=True)
    @discord.ui.button(label="🎁 デイリーボーナス",style=discord.ButtonStyle.success,custom_id="casino_daily",row=2)
    async def daily(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        amount=int(await setting("daily_bonus","500"))
        exists=await pool().fetchval("SELECT 1 FROM casino.daily_claims WHERE user_id=$1 AND claim_date=(now() AT TIME ZONE 'Asia/Tokyo')::date",str(i.user.id))
        if exists:await i.edit_original_response(content="🎁 今日のボーナスは受取済みです。");return
        from bank_gateway_for_other_bots import bank_credit
        day=await pool().fetchval("SELECT (now() AT TIME ZONE 'Asia/Tokyo')::date::text")
        r=await bank_credit("PAL_CASINO",f"DAILY:{i.user.id}:{day}",i.user.id,"CHIP",amount)
        if r["status"]=="SUCCESS":
            await pool().execute("INSERT INTO casino.daily_claims VALUES($1,(now() AT TIME ZONE 'Asia/Tokyo')::date,$2)",str(i.user.id),amount)
            await i.edit_original_response(content=f"🎁 **{amount:,} CHIP** を受け取りました！")
        else:await i.edit_original_response(content=f"ボーナス処理: `{r['status']}`")
    @discord.ui.button(label="🏆 ランキング",style=discord.ButtonStyle.secondary,custom_id="casino_ranking",row=2)
    async def rank(self,i,b):await i.response.send_message(embed=await ranking_embed(),ephemeral=True)

async def ranking_embed():
    chips=await ranking_chip();wins=await ranking_maxwin()
    e=emb("🏆 PAL CASINO RANKING",color=GOLD)
    e.add_field(name="💰 CHIP資産ランキング",value="\n".join(f"**#{n}** <@{r['user_id']}> — {r['value']:,} CHIP" for n,r in enumerate(chips,1)) or "-",inline=False)
    e.add_field(name="🔥 最大勝利ランキング",value="\n".join(f"**#{n}** <@{r['user_id']}> — {r['value']:,} CHIP" for n,r in enumerate(wins,1)) or "-",inline=False)
    jackpot=await pool().fetchval("SELECT COALESCE(SUM(balance),0) FROM bank.accounts WHERE account_type='USER' AND currency='CHIP'")
    e.add_field(name="💰 JACKPOT POOL",value=f"**{int(jackpot or 0):,} CHIP**",inline=False)
    return e

class AdminGameSelect(discord.ui.Select):
    def __init__(self,rows):
        super().__init__(placeholder="ゲームON / OFF",options=[discord.SelectOption(label=r["display_name"],value=r["game_key"],description="ON" if r["enabled"] else "OFF") for r in rows[:25]])
    async def callback(self,i):
        cfg=await game(self.values[0]);new=not cfg["enabled"]
        await pool().execute("UPDATE casino.games SET enabled=$1 WHERE game_key=$2",new,self.values[0])
        await i.response.edit_message(content=f"{cfg['display_name']} → {'🟢 ON' if new else '⚫ OFF'}",view=None)

class AdminGameView(discord.ui.View):
    def __init__(self,rows):super().__init__(timeout=120);self.add_item(AdminGameSelect(rows))

class CasinoAdminView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def interaction_check(self,i):
        if not i.user.guild_permissions.administrator:
            await i.response.send_message("管理者専用です。",ephemeral=True);return False
        return True
    @discord.ui.button(label="🎮 ゲーム管理",style=discord.ButtonStyle.primary,custom_id="casino_admin_games",row=0)
    async def gm(self,i,b):await i.response.send_message("ゲームを選択してください。",view=AdminGameView(await games()),ephemeral=True)
    @discord.ui.button(label="⚙️ ゲーム設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_settings",row=0)
    async def gs(self,i,b):await i.response.send_message("⚙️ ゲーム別倍率・BET設定UIは準備中です。DB設定土台は作成済みです。",ephemeral=True)
    @discord.ui.button(label="👤 ユーザー確認",style=discord.ButtonStyle.secondary,custom_id="casino_admin_user",row=0)
    async def user(self,i,b):await i.response.send_message("👤 ユーザー確認UIは準備中です。",ephemeral=True)
    @discord.ui.button(label="📖 CASINO取引",style=discord.ButtonStyle.secondary,custom_id="casino_admin_tx",row=1)
    async def tx(self,i,b):await i.response.send_message("📖 CASINO取引検索UIは準備中です。",ephemeral=True)
    @discord.ui.button(label="📊 CASINO統計",style=discord.ButtonStyle.secondary,custom_id="casino_admin_stats",row=1)
    async def stats(self,i,b):
        s=await total_stats();await i.response.send_message(f"🎮 総プレイ **{s['plays']:,}**\n🕒 24時間 **{s['plays24']:,}**\n💰 総BET **{s['bets']:,} CHIP**\n🏆 総配当 **{s['payouts']:,} CHIP**\n📈 CASINO収支 **{s['bets']-s['payouts']:+,} CHIP**",ephemeral=True)
    @discord.ui.button(label="📢 アナウンス設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_announce",row=1)
    async def announce(self,i,b):
        cur=await setting("big_win_enabled","1");new="0" if cur=="1" else "1";await set_setting("big_win_enabled",new)
        await i.response.send_message(f"🔥 BIG WIN通知 → {'ON' if new=='1' else 'OFF'}",ephemeral=True)
    @discord.ui.button(label="🚨 警告確認",style=discord.ButtonStyle.danger,custom_id="casino_admin_alert",row=2)
    async def alert(self,i,b):await i.response.send_message("🚨 異常BET警告の保存・表示UIは準備中です。",ephemeral=True)
    @discord.ui.button(label="🔧 CASINO SYSTEM",style=discord.ButtonStyle.secondary,custom_id="casino_admin_system",row=2)
    async def system(self,i,b):await i.response.send_message("CASINO SYSTEMは `!casinosetup` から管理します。",ephemeral=True)
