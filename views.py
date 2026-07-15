import discord
from casino_db import games,game,profile,history,ranking_chip,ranking_maxwin,total_stats,setting,set_setting,chip_balance,pool,config_get,config_set,audit_global,game_stats
from casino_services import play_slot,play_coin,play_dice_kind,play_roulette,play_highlow,play_scratch,play_crash,play_mines,play_blackjack
from lottery_service import buy_lottery,buy_loto,quick_pick,draw_lottery,draw_loto,ensure_lottery_draw,ensure_loto_draw

GOLD=0xF1C40F
DARK=0x2B2D31
def emb(title,desc=None,color=DARK): return discord.Embed(title=title,description=desc,color=color)

GAME_NAMES={
"SLOT3":"🎰 3リールスロット","SCRATCH":"🎟️ スクラッチ","LOTTERY":"🎫 宝くじ","LOTO6":"🔢 ロト6",
"BLACKJACK":"🃏 ブラックジャック","ROULETTE":"🎡 ルーレット","MINES":"💣 マインズ",
"CHINCHIRO":"🎲 チンチロ","CHOHAN":"🎴 丁半博打","COIN":"🪙 コイントス",
"HIGHLOW":"📈 ハイアンドロー","CRASH":"🚀 クラッシュ","SLOT5":"🎰 5リールスロット",
"JACKPOT_SLOT":"💰 ジャックポットスロット","KAZAAN":"🪙 カザーン","HORSE":"🏇 競馬",
"SPORTS":"⚽ スポーツベット","FUKUBIKI":"🎁 福引","MEDIA_GAME":"🎬 動画・GIFゲーム"}

async def result_message(i,r,key):
    if r["status"]=="PREPARING": await i.edit_original_response(content="🚧 このゲームは現在準備中です。");return
    if r["status"]=="BET_RANGE": await i.edit_original_response(content=f"BETは **{r['min']:,}～{r['max']:,} CHIP** です。");return
    if r["status"]=="INSUFFICIENT_BALANCE": await i.edit_original_response(content="CHIP残高が足りません。");return
    if r["status"]=="MAINTENANCE": await i.edit_original_response(content="🏦 BANKメンテナンス中です。");return
    if r["status"]!="SUCCESS": await i.edit_original_response(content=f"CASINO処理: `{r['status']}`");return
    detail=[]
    for k,v in r.items():
        if k not in {"status","round_id","bet","payout","profit","multiplier","balance"}: detail.append(f"**{k}**: {v}")
    e=emb(f"{GAME_NAMES[key]}｜RESULT","\n".join(detail),GOLD)
    e.add_field(name="BET",value=f"{r['bet']:,} CHIP")
    e.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
    e.add_field(name="収支",value=f"{r['profit']:+,} CHIP")
    e.add_field(name="倍率",value=f"×{r['multiplier']}")
    e.add_field(name="現在残高",value=f"{r['balance']:,} CHIP")
    e.set_footer(text=f"Round ID: {r['round_id']}")
    await i.edit_original_response(content=None,embed=e)

    # 本人は操作チャンネル上のephemeral結果を見る。
    # 同じ結果をcasino-liveへ公開する。
    live_id=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='casino_live'")
    live=i.guild.get_channel(int(live_id)) if live_id else None
    if live:
        public_e=emb(f"{GAME_NAMES[key]}｜LIVE RESULT",color=GOLD)
        public_e.description=f"{i.user.mention}\n\n" + ("\n".join(detail) if detail else "")
        public_e.add_field(name="BET",value=f"{r['bet']:,} CHIP")
        public_e.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
        public_e.add_field(name="収支",value=f"{r['profit']:+,} CHIP")
        public_e.add_field(name="倍率",value=f"×{r['multiplier']}")
        public_e.set_footer(text=f"Round ID: {r['round_id']}")
        await live.send(embed=public_e)

    threshold=int(await setting("big_win_multiplier","30"))
    if r["multiplier"]>=threshold and await setting("big_win_enabled","1")=="1":
        cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='big_win'")
        ch=i.guild.get_channel(int(cid)) if cid else None
        if ch: await ch.send(embed=emb("🔥🔥 BIG WIN 🔥🔥",f"{i.user.mention}\n{GAME_NAMES[key]}\n\nBET **{r['bet']:,} CHIP**\nWIN **{r['payout']:,} CHIP**\n**×{r['multiplier']}**\n`{r['round_id']}`",GOLD))


class LotteryBuyModal(discord.ui.Modal,title="🎫 PAL 宝くじ"):
    count=discord.ui.TextInput(label="購入枚数",placeholder="1～100",max_length=3)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:r=await buy_lottery(i.user.id,int(self.count))
        except Exception as ex:await i.edit_original_response(content=f"宝くじエラー: `{type(ex).__name__}`\n`{str(ex)[:700]}`");return
        if r["status"]!="SUCCESS":await i.edit_original_response(content=f"購入処理: `{r['status']}`");return
        preview="\n".join(f"`{g:02d}組 {n:06d}番`" for _,g,n in r["tickets"][:20])
        await i.edit_original_response(content=f"🎫 第{r['draw_no']}回｜**{len(r['tickets'])}枚 / {r['cost']:,} CHIP**\n\n{preview}")

class LotoBuyModal(discord.ui.Modal,title="🔢 ロト6"):
    numbers=discord.ui.TextInput(label="1～43から6個",placeholder="3,8,14,21,32,41",max_length=30)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:nums=[int(x.strip()) for x in str(self.numbers).replace("、",",").split(",")];r=await buy_loto(i.user.id,nums)
        except Exception as ex:await i.edit_original_response(content=f"ロト6エラー: `{type(ex).__name__}`\n`{str(ex)[:700]}`");return
        if r["status"]!="SUCCESS":await i.edit_original_response(content=f"購入処理: `{r['status']}`");return
        await i.edit_original_response(content=f"🔢 第{r['draw_no']}回 ロト6購入完了\n**{' / '.join(map(str,r['numbers']))}**\n💰 {r['cost']:,} CHIP")

class LotoLaunchView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🔢 数字を選ぶ",style=discord.ButtonStyle.primary)
    async def select_nums(self,i,b):await i.response.send_modal(LotoBuyModal())
    @discord.ui.button(label="🎲 クイックピック",style=discord.ButtonStyle.success)
    async def qp(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);r=await quick_pick(i.user.id)
        if r["status"]=="SUCCESS":await i.edit_original_response(content=f"🎲 第{r['draw_no']}回 クイックピック\n**{' / '.join(map(str,r['numbers']))}**\n💰 {r['cost']:,} CHIP")
        else:await i.edit_original_response(content=f"購入処理: `{r['status']}`")

class LotteryLaunchView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🎫 宝くじを購入",style=discord.ButtonStyle.success)
    async def buy(self,i,b):await i.response.send_modal(LotteryBuyModal())


class GameModal(discord.ui.Modal):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="1～10,000",max_length=10)
    option=discord.ui.TextInput(label="選択 / 設定",placeholder="ゲーム説明の入力例を確認",required=False,max_length=30)
    def __init__(self,key):
        super().__init__(title=GAME_NAMES[key][:45]);self.key=key
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            bet=int(str(self.bet).replace(",","").strip()); opt=str(self.option).strip().upper()
            if self.key=="SLOT3": r=await play_slot(i.user.id,bet)
            elif self.key=="SCRATCH": r=await play_scratch(i.user.id,bet)
            elif self.key=="COIN": r=await play_coin(i.user.id,bet,"表" if opt in {"表","OMOTE"} else "裏")
            elif self.key=="CHOHAN": r=await play_dice_kind(i.user.id,"CHOHAN",bet,"丁" if opt in {"丁","CHO"} else "半")
            elif self.key=="CHINCHIRO": r=await play_dice_kind(i.user.id,"CHINCHIRO",bet,"")
            elif self.key=="ROULETTE": r=await play_roulette(i.user.id,bet,{"RED":"赤","BLACK":"黒","赤":"赤","黒":"黒"}.get(opt,opt))
            elif self.key=="HIGHLOW": r=await play_highlow(i.user.id,bet,"LOW" if opt=="LOW" else "HIGH")
            elif self.key=="CRASH": r=await play_crash(i.user.id,bet,float(opt or "2"))
            elif self.key=="MINES":
                a=(opt or "3,3").replace(" ","").split(",");r=await play_mines(i.user.id,bet,int(a[1]),int(a[0]))
            elif self.key=="BLACKJACK": r=await play_blackjack(i.user.id,bet,"HIT" if opt=="HIT" else "STAND")
            else: r={"status":"PREPARING"}
            await result_message(i,r,self.key)
        except Exception as ex: await i.edit_original_response(content=f"ゲームエラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")

HELP={
"SLOT3":"BETのみ入力。設定欄は空欄。",
"SCRATCH":"BETのみ入力。設定欄は空欄。",
"COIN":"設定欄: 表 / 裏",
"CHOHAN":"設定欄: 丁 / 半",
"CHINCHIRO":"BETのみ入力。",
"ROULETTE":"設定欄: 赤 / 黒 / 0～36",
"HIGHLOW":"設定欄: HIGH / LOW",
"CRASH":"設定欄: 利確倍率。例 2.0",
"MINES":"設定欄: 地雷数,開ける数。例 3,4",
"BLACKJACK":"設定欄: HIT / STAND",
}

class LaunchView(discord.ui.View):
    def __init__(self,key):super().__init__(timeout=60);self.key=key
    @discord.ui.button(label="🎮 プレイ",style=discord.ButtonStyle.success)
    async def play(self,i,b):await i.response.send_modal(GameModal(self.key))

def game_select_embed(): return emb("🎮 GAME SELECT","ゲームを選択してください。",GOLD)


DIRECT_GAME_INFO={
"SLOT3":("🎰 3リールスロット","BETを入力して3リールを回します。"),
"SCRATCH":("🎟️ スクラッチ","BETを入力してスクラッチを削ります。"),
"BLACKJACK":("🃏 ブラックジャック","BETと HIT / STAND を入力します。"),
"ROULETTE":("🎡 ルーレット","BETと 赤 / 黒 / 0～36 を入力します。"),
"MINES":("💣 マインズ","BETと 地雷数,開ける数 を入力します。例: 3,4"),
"CHINCHIRO":("🎲 チンチロ","BETを入力してサイコロを振ります。"),
"CHOHAN":("🎴 丁半博打","BETと 丁 / 半 を入力します。"),
"COIN":("🪙 コイントス","BETと 表 / 裏 を入力します。"),
"HIGHLOW":("📈 ハイアンドロー","BETと HIGH / LOW を入力します。"),
"CRASH":("🚀 クラッシュ","BETと利確倍率を入力します。例: 2.0"),
}

class DirectGamePanel(discord.ui.View):
    def __init__(self,key):
        super().__init__(timeout=None)
        self.key=key
        button=discord.ui.Button(
            label="🎮 プレイ",
            style=discord.ButtonStyle.success,
            custom_id=f"casino_direct_{key.lower()}",
        )
        button.callback=self.play
        self.add_item(button)
    async def play(self,i):
        await i.response.send_modal(GameModal(self.key))

class DailyPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        b=discord.ui.Button(label="🎁 500 CHIPで回す",style=discord.ButtonStyle.success,custom_id="casino_direct_daily")
        b.callback=self.play
        self.add_item(b)
    async def play(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            import random
            from bank_gateway_for_other_bots import bank_credit,bank_debit
            uid=str(i.user.id);day=await pool().fetchval("SELECT (now() AT TIME ZONE 'Asia/Tokyo')::date::text")
            if await pool().fetchval("SELECT 1 FROM casino.daily_claims WHERE user_id=$1 AND claim_date=(now() AT TIME ZONE 'Asia/Tokyo')::date",uid):
                await i.edit_original_response(content="🎁 今日のガチャはプレイ済みです。次は0:00に更新！");return
            d=await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:BET",uid,"CHIP",500)
            if d["status"]!="SUCCESS":
                await i.edit_original_response(content="💰 ガチャには **500 CHIP** 必要です。");return
            reward=random.choices([550,1000,1500,3000,-10000,100000],weights=[81,10,5,3,0.999,0.001],k=1)[0]
            if reward<0:
                loss=abs(reward)
                c=await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:PENALTY",uid,"CHIP",loss)
                if c["status"]=="INSUFFICIENT_BALANCE":
                    current=await chip_balance(uid)
                    if current>0: await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:PENALTY_ALL",uid,"CHIP",current)
                    actual_loss=current
                elif c["status"]=="SUCCESS": actual_loss=loss
                else:
                    await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:REFUND",uid,"CHIP",500)
                    await i.edit_original_response(content=f"ガチャ処理: `{c['status']}` / 500 CHIP返金済み");return
                await pool().execute("INSERT INTO casino.daily_claims VALUES($1,(now() AT TIME ZONE 'Asia/Tokyo')::date,$2)",uid,-actual_loss)
                text=f"💀 **-{actual_loss:,} CHIP**！｜参加費込み収支 **{-actual_loss-500:+,} CHIP**"
            else:
                c=await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:WIN",uid,"CHIP",reward)
                if c["status"]!="SUCCESS":
                    await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:REFUND",uid,"CHIP",500)
                    await i.edit_original_response(content="ガチャ配当処理失敗 / 500 CHIP返金済み");return
                await pool().execute("INSERT INTO casino.daily_claims VALUES($1,(now() AT TIME ZONE 'Asia/Tokyo')::date,$2)",uid,reward)
                text=f"🎁 **{reward:,} CHIP** 獲得！｜収支 **{reward-500:+,} CHIP**"
            await i.edit_original_response(content=text)
            if reward in (-10000,100000):
                cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='big_win'")
                ch=i.guild.get_channel(int(cid)) if cid else None
                if ch:
                    await ch.send(embed=emb("🎁🔥 DAILY GACHA RARE RESULT 🔥🎁",f"{i.user.mention}\\n\\n**{reward:+,} CHIP**\\n確率 **{'0.001%' if reward==100000 else '0.999%'}**",GOLD))
        except Exception as ex:
            await i.edit_original_response(content=f"ガチャエラー: `{type(ex).__name__}`\\n`{str(ex)[:800]}`")


class GameSelect(discord.ui.Select):
    def __init__(self):
        opts=[discord.SelectOption(label=n.split(" ",1)[1] if " " in n else n,value=k,emoji=n.split(" ",1)[0]) for k,n in GAME_NAMES.items()]
        super().__init__(placeholder="🎮 ゲームを選択",options=opts[:25])
    async def callback(self,i):
        key=self.values[0];cfg=await game(key)
        if cfg["vip_only"]:
            vip=await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",str(i.user.id)) or False
            if not vip: await i.response.send_message("🔒 **VIP限定ゲームです。**",ephemeral=True);return
        if not cfg["implemented"] or not cfg["enabled"]:
            await i.response.send_message(embed=emb("🚧 GAME PREPARING",f"## {cfg['display_name']}\n\n現在このゲームは準備中です。",GOLD),ephemeral=True);return
        if key=="LOTTERY":
            d=await ensure_lottery_draw()
            await i.response.send_message(embed=emb("🎫 PAL 宝くじ",f"**1枚 500 CHIP**\n01～100組 / 100000～199999番\n🥇 1等 **1,000,000,000 CHIP**\n\n現在: 第{d['draw_no']}回",GOLD),view=LotteryLaunchView(),ephemeral=True);return
        if key=="LOTO6":
            d=await ensure_loto_draw()
            await i.response.send_message(embed=emb("🔢 ロト6",f"**1口 500 CHIP**\n1～43から6個 / 重複なし\n賞金は売上プール山分け＋キャリーオーバー\n\n現在: 第{d['draw_no']}回｜繰越 {d['carryover']:,} CHIP",GOLD),view=LotoLaunchView(),ephemeral=True);return
        await i.response.send_message(embed=emb(cfg["display_name"],HELP.get(key,"BETを入力してください。"),GOLD),view=LaunchView(key),ephemeral=True)

class GameSelectView(discord.ui.View):
    def __init__(self):super().__init__(timeout=180);self.add_item(GameSelect())

async def ranking_embed():
    chips=await ranking_chip();wins=await ranking_maxwin();e=emb("🏆 PAL CASINO RANKING",color=GOLD)
    e.add_field(name="💰 CHIP資産ランキング",value="\n".join(f"**#{n}** <@{r['user_id']}> — {r['value']:,} CHIP" for n,r in enumerate(chips,1)) or "-",inline=False)
    e.add_field(name="🔥 最大勝利ランキング",value="\n".join(f"**#{n}** <@{r['user_id']}> — {r['value']:,} CHIP" for n,r in enumerate(wins,1)) or "-",inline=False)
    jackpot=await pool().fetchval("SELECT COALESCE(SUM(balance),0) FROM bank.accounts WHERE account_type='USER' AND currency='CHIP'")
    e.add_field(name="💰 JACKPOT POOL",value=f"**{int(jackpot or 0):,} CHIP**",inline=False);return e


class CasinoLobbyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 CHIP残高",style=discord.ButtonStyle.secondary,custom_id="casino_lobby_balance",row=0)
    async def balance(self,i,b):
        await i.response.send_message(f"🎰 現在残高 **{await chip_balance(i.user.id):,} CHIP**",ephemeral=True)

    @discord.ui.button(label="📖 プレイ履歴",style=discord.ButtonStyle.secondary,custom_id="casino_lobby_history",row=0)
    async def hist(self,i,b):
        rows=await history(i.user.id,100)
        e=emb("📖 PLAY HISTORY",color=GOLD)
        e.description="\n\n".join(
            f"**{GAME_NAMES.get(r['game_key'],r['game_key'])}｜{r['result']}**\nBET {r['bet']:,} / PAYOUT {r['payout']:,} CHIP\n`{r['round_id']}`"
            for r in rows[:10]
        ) or "履歴はありません。"
        await i.response.send_message(embed=e,ephemeral=True)

    @discord.ui.button(label="🎰 CASINOプロフィール",style=discord.ButtonStyle.secondary,custom_id="casino_lobby_profile",row=1)
    async def prof(self,i,b):
        p=await profile(i.user.id)
        e=emb("🎰 CASINO PROFILE",color=GOLD)
        for n,val in [
            ("🎮 総プレイ",f"{p['plays']:,}回"),
            ("💰 総BET",f"{p['total_bet']:,} CHIP"),
            ("🏆 総配当",f"{p['total_payout']:,} CHIP"),
            ("📈 収支",f"{p['total_payout']-p['total_bet']:+,} CHIP"),
            ("🔥 最大勝利",f"{p['max_win']:,} CHIP"),
            ("🎲 最多プレイ",GAME_NAMES.get(p["favorite"],p["favorite"])),
        ]:
            e.add_field(name=n,value=val)
        await i.response.send_message(embed=e,ephemeral=True)

class CasinoPanelView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="🎮 ゲームを遊ぶ",style=discord.ButtonStyle.primary,custom_id="casino_games",row=0)
    async def games_button(self,i,b):await i.response.send_message(embed=game_select_embed(),view=GameSelectView(),ephemeral=True)
    @discord.ui.button(label="💰 CHIP残高",style=discord.ButtonStyle.secondary,custom_id="casino_balance",row=0)
    async def balance(self,i,b):await i.response.send_message(f"🎰 現在残高 **{await chip_balance(i.user.id):,} CHIP**",ephemeral=True)
    @discord.ui.button(label="📖 プレイ履歴",style=discord.ButtonStyle.secondary,custom_id="casino_history",row=1)
    async def hist(self,i,b):
        rows=await history(i.user.id,100);e=emb("📖 PLAY HISTORY",color=GOLD)
        e.description="\n\n".join(f"**{GAME_NAMES.get(r['game_key'],r['game_key'])}｜{r['result']}**\nBET {r['bet']:,} / PAYOUT {r['payout']:,} CHIP\n`{r['round_id']}`" for r in rows[:10]) or "履歴はありません。"
        await i.response.send_message(embed=e,ephemeral=True)
    @discord.ui.button(label="🎰 CASINOプロフィール",style=discord.ButtonStyle.secondary,custom_id="casino_profile",row=1)
    async def prof(self,i,b):
        p=await profile(i.user.id);e=emb("🎰 CASINO PROFILE",color=GOLD)
        for n,val in [("🎮 総プレイ",f"{p['plays']:,}回"),("💰 総BET",f"{p['total_bet']:,} CHIP"),("🏆 総配当",f"{p['total_payout']:,} CHIP"),("📈 収支",f"{p['total_payout']-p['total_bet']:+,} CHIP"),("🔥 最大勝利",f"{p['max_win']:,} CHIP"),("🎲 最多プレイ",GAME_NAMES.get(p["favorite"],p["favorite"]))]:e.add_field(name=n,value=val)
        await i.response.send_message(embed=e,ephemeral=True)
    @discord.ui.button(label="🎁 1日1回ガチャ",style=discord.ButtonStyle.success,custom_id="casino_daily",row=2)
    async def daily(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            import random
            from bank_gateway_for_other_bots import bank_credit,bank_debit
            uid=str(i.user.id);day=await pool().fetchval("SELECT (now() AT TIME ZONE 'Asia/Tokyo')::date::text")
            if await pool().fetchval("SELECT 1 FROM casino.daily_claims WHERE user_id=$1 AND claim_date=(now() AT TIME ZONE 'Asia/Tokyo')::date",uid):
                await i.edit_original_response(content="🎁 今日のガチャはプレイ済みです。次は0:00に更新！");return
            d=await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:BET",uid,"CHIP",500)
            if d["status"]!="SUCCESS":await i.edit_original_response(content="💰 ガチャには **500 CHIP** 必要です。");return
            reward=random.choices([550,1000,1500,3000,-10000,100000],weights=[81,10,5,3,0.999,0.001],k=1)[0]
            if reward < 0:
                loss=abs(reward)
                c=await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:PENALTY",uid,"CHIP",loss)
                if c["status"]=="INSUFFICIENT_BALANCE":
                    current=await chip_balance(uid)
                    if current > 0:
                        await bank_debit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:PENALTY_ALL",uid,"CHIP",current)
                    actual_loss=current
                elif c["status"]=="SUCCESS":
                    actual_loss=loss
                else:
                    await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:REFUND",uid,"CHIP",500)
                    await i.edit_original_response(content=f"ガチャマイナス処理: `{c['status']}` / 500 CHIP返金済み")
                    return
                await pool().execute("INSERT INTO casino.daily_claims VALUES($1,(now() AT TIME ZONE 'Asia/Tokyo')::date,$2)",uid,-actual_loss)
                await i.edit_original_response(content=f"💀 **-{actual_loss:,} CHIP**！｜参加費込み収支 **{-actual_loss-500:+,} CHIP**")
            else:
                c=await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:WIN",uid,"CHIP",reward)
                if c["status"]!="SUCCESS":
                    await bank_credit("PAL_CASINO",f"DAILY_GACHA:{uid}:{day}:REFUND",uid,"CHIP",500)
                    await i.edit_original_response(content="ガチャ配当処理失敗 / 500 CHIP返金済み")
                    return
                await pool().execute("INSERT INTO casino.daily_claims VALUES($1,(now() AT TIME ZONE 'Asia/Tokyo')::date,$2)",uid,reward)
                await i.edit_original_response(content=f"🎁 **{reward:,} CHIP** 獲得！｜収支 **{reward-500:+,} CHIP**")

            if reward in (-10000,100000):
                cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='big_win'")
                ch=i.guild.get_channel(int(cid)) if cid else None
                if ch:
                    if reward==100000:
                        title="🎁🔥 DAILY GACHA ULTRA JACKPOT 🔥🎁"
                        body=f"{i.user.mention} が **0.001%** を引いた！\n\n🏆 **100,000 CHIP 獲得！**"
                    else:
                        title="💀🔥 DAILY GACHA RARE MISS 🔥💀"
                        body=f"{i.user.mention} が **0.999%** を引いた！\n\n💀 **-10,000 CHIP**"
                    await ch.send(embed=emb(title,body,GOLD))
        except Exception as ex:await i.edit_original_response(content=f"ガチャエラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")
    @discord.ui.button(label="🏆 ランキング",style=discord.ButtonStyle.secondary,custom_id="casino_ranking",row=2)
    async def rank(self,i,b):await i.response.send_message(embed=await ranking_embed(),ephemeral=True)

class AdminGameSelect(discord.ui.Select):
    def __init__(self,rows):super().__init__(placeholder="ゲームON / OFF",options=[discord.SelectOption(label=r["display_name"],value=r["game_key"],description="ON" if r["enabled"] else "OFF") for r in rows[:25]])
    async def callback(self,i):
        cfg=await game(self.values[0]);new=not cfg["enabled"];await pool().execute("UPDATE casino.games SET enabled=$1 WHERE game_key=$2",new,self.values[0]);await i.response.edit_message(content=f"{cfg['display_name']} → {'🟢 ON' if new else '⚫ OFF'}",view=None)
class AdminGameView(discord.ui.View):
    def __init__(self,rows):super().__init__(timeout=120);self.add_item(AdminGameSelect(rows))

class GameSettingsModal(discord.ui.Modal):
    min_bet=discord.ui.TextInput(label="最低BET",max_length=12)
    max_bet=discord.ui.TextInput(label="通常最大BET",max_length=12)
    vip_max=discord.ui.TextInput(label="VIP最大BET",max_length=12)
    probability=discord.ui.TextInput(label="確率設定 JSON / ウェイト",required=False,max_length=400,style=discord.TextStyle.paragraph)
    payout=discord.ui.TextInput(label="配当設定 JSON / 倍率",required=False,max_length=400,style=discord.TextStyle.paragraph)
    def __init__(self,key,cfg):
        super().__init__(title=f"{key} 詳細設定");self.key=key
        self.min_bet.default=str(cfg["min_bet"]);self.max_bet.default=str(cfg["max_bet"]);self.vip_max.default=str(cfg["vip_max_bet"])
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            old=await game(self.key)
            mn,mx,vx=int(self.min_bet),int(self.max_bet),int(self.vip_max)
            if mn<1 or mx<mn or vx<mx:raise ValueError("BET範囲")
            await pool().execute("UPDATE casino.games SET min_bet=$1,max_bet=$2,vip_max_bet=$3 WHERE game_key=$4",mn,mx,vx,self.key)
            await config_set(self.key,"probability_table",str(self.probability),i.user.id)
            await config_set(self.key,"payout_table",str(self.payout),i.user.id)
            cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='log'")
            ch=i.guild.get_channel(int(cid)) if cid else None
            if ch:await ch.send(embed=emb("⚙️ GAME SETTING UPDATED",f"管理者 {i.user.mention}\\nゲーム **{self.key}**\\nBET `{old['min_bet']}-{old['max_bet']}/{old['vip_max_bet']}` → `{mn}-{mx}/{vx}`\\n確率・配当テーブル更新",GOLD))
            await i.edit_original_response(content="✅ ゲーム詳細設定を保存しました。次ラウンドから参照されます。")
        except Exception as ex:await i.edit_original_response(content=f"設定エラー: `{type(ex).__name__}` / `{str(ex)[:500]}`")

class SettingsSelect(discord.ui.Select):
    def __init__(self,rows):super().__init__(placeholder="詳細設定するゲーム",options=[discord.SelectOption(label=r["display_name"],value=r["game_key"]) for r in rows[:25]])
    async def callback(self,i):
        cfg=await game(self.values[0]);await i.response.send_modal(GameSettingsModal(self.values[0],cfg))
class SettingsView(discord.ui.View):
    def __init__(self,rows):super().__init__(timeout=120);self.add_item(SettingsSelect(rows))

class RTPModal(discord.ui.Modal,title="📈 CASINO全体還元率"):
    target=discord.ui.TextInput(label="目標還元率 %",placeholder="95.00",max_length=6)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            val=float(self.target)
            if not 1<=val<=200:raise ValueError("1～200")
            old=await setting("target_rtp","95.00");await set_setting("target_rtp",f"{val:.2f}");await audit_global(i.user.id,"target_rtp",old,f"{val:.2f}")
            cid=await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key='log'");ch=i.guild.get_channel(int(cid)) if cid else None
            if ch:await ch.send(embed=emb("📈 CASINO RTP UPDATED",f"管理者 {i.user.mention}\\n目標RTP **{old}% → {val:.2f}%**\\n対象: 通常CASINOゲーム",GOLD))
            await i.edit_original_response(content=f"✅ 全体目標還元率を **{val:.2f}%** に変更しました。")
        except Exception as ex:await i.edit_original_response(content=f"RTP設定エラー: `{str(ex)[:500]}`")

class SystemView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="📈 全体還元率変更",style=discord.ButtonStyle.primary)
    async def rtp(self,i,b):await i.response.send_modal(RTPModal())
    @discord.ui.button(label="📊 実測RTP",style=discord.ButtonStyle.secondary)
    async def actual(self,i,b):
        s=await total_stats();actual=(float(s["payouts"])/float(s["bets"])*100) if s["bets"] else 0
        await i.response.send_message(f"🎯 目標RTP **{await setting('target_rtp','95.00')}%**\\n📊 実測RTP **{actual:.2f}%**\\n💰 BET {s['bets']:,} / 配当 {s['payouts']:,} CHIP",ephemeral=True)
    @discord.ui.button(label="🎫 宝くじ抽選",style=discord.ButtonStyle.danger)
    async def lottery_draw(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);r=await draw_lottery()
        await i.edit_original_response(content=f"🎊 第{r['draw_no']}回 宝くじ抽選\\n**{r['group']:02d}組 {r['number']:06d}番**\\n当選処理 {len(r['winners'])}件")
    @discord.ui.button(label="🔢 ロト6抽選",style=discord.ButtonStyle.danger)
    async def loto_draw(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);r=await draw_loto()
        await i.edit_original_response(content=f"🔢 第{r['draw_no']}回 ロト6抽選\\n本数字 **{' / '.join(map(str,r['winning']))}**\\nBONUS **{r['bonus']}**\\n次回繰越 **{r['carryover']:,} CHIP**")

class CasinoAdminView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def interaction_check(self,i):
        if not i.user.guild_permissions.administrator:await i.response.send_message("管理者専用です。",ephemeral=True);return False
        return True
    @discord.ui.button(label="🎮 ゲーム管理",style=discord.ButtonStyle.primary,custom_id="casino_admin_games",row=0)
    async def gm(self,i,b):await i.response.send_message("ゲームを選択してください。",view=AdminGameView(await games()),ephemeral=True)
    @discord.ui.button(label="⚙️ ゲーム設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_settings",row=0)
    async def gs(self,i,b):await i.response.send_message("⚙️ 詳細設定するゲームを選択してください。",view=SettingsView(await games()),ephemeral=True)
    @discord.ui.button(label="👤 ユーザー確認",style=discord.ButtonStyle.secondary,custom_id="casino_admin_user",row=0)
    async def user(self,i,b):await i.response.send_message("👤 ユーザー確認パネルは準備中です。",ephemeral=True)
    @discord.ui.button(label="📖 CASINO取引",style=discord.ButtonStyle.secondary,custom_id="casino_admin_tx",row=1)
    async def tx(self,i,b):await i.response.send_message("📖 CASINO取引検索は準備中です。",ephemeral=True)
    @discord.ui.button(label="📊 CASINO統計",style=discord.ButtonStyle.secondary,custom_id="casino_admin_stats",row=1)
    async def stats(self,i,b):
        s=await total_stats();await i.response.send_message(f"🎮 総プレイ **{s['plays']:,}**\n🕒 24時間 **{s['plays24']:,}**\n💰 総BET **{s['bets']:,} CHIP**\n🏆 総配当 **{s['payouts']:,} CHIP**\n📈 CASINO収支 **{s['bets']-s['payouts']:+,} CHIP**",ephemeral=True)
    @discord.ui.button(label="📢 アナウンス設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_announce",row=1)
    async def announce(self,i,b):
        cur=await setting("big_win_enabled","1");new="0" if cur=="1" else "1";await set_setting("big_win_enabled",new);await i.response.send_message(f"🔥 BIG WIN通知 → {'ON' if new=='1' else 'OFF'}",ephemeral=True)
    @discord.ui.button(label="🚨 警告確認",style=discord.ButtonStyle.danger,custom_id="casino_admin_alert",row=2)
    async def alert(self,i,b):await i.response.send_message("🚨 警告一覧は準備中です。",ephemeral=True)
    @discord.ui.button(label="🔧 CASINO SYSTEM",style=discord.ButtonStyle.secondary,custom_id="casino_admin_system",row=2)
    async def system(self,i,b):await i.response.send_message("🔧 CASINO SYSTEM",view=SystemView(),ephemeral=True)
