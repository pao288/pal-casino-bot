import discord, asyncio
from casino_db import games,game,profile,history,ranking_chip,ranking_maxwin,total_stats,setting,set_setting,chip_balance,pool,config_get,config_set,audit_global,game_stats,map_get
from casino_services import play_slot,play_coin,play_roulette,play_scratch,start_scratch,finish_scratch,play_chinchiro,start_chohan,finish_chohan,start_highlow,highlow_step,finish_highlow,create_crash,finish_crash,start_mines,mines_open,finish_mines,start_blackjack,blackjack_hit,finish_blackjack
from lottery_service import buy_lottery,buy_loto,quick_pick,draw_lottery,draw_loto,lottery_user_overview,loto_user_overview,ensure_lottery_draw,ensure_loto_draw,latest_lottery_result,latest_loto_result,JST

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


# ===== !casinosetup（PAL CASINOカテゴリ一式）用ルーティングヘルパー =====
# 新チャンネル（v2_*）が設置されていればそちらへ、未設置なら従来のチャンネルへ自動フォールバックする。
# 既存の !casinosetup（旧: build/panels/repair/deleteパネル）の動作には一切影響しない。
async def _channel_by_map_keys(guild, *map_keys):
    for mk in map_keys:
        if not mk:
            continue
        cid = await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key=$1", mk)
        if cid:
            ch = guild.get_channel(int(cid))
            if ch:
                return ch
    return None

async def _live_channel(guild, key=None):
    # ゲームをプレイするチャンネル（GAME内の各専用チャンネル）ではなく、
    # 結果専用の「📺｜プレイ結果」チャンネルへまとめて送る。未設置なら旧casino-liveへフォールバック。
    return await _channel_by_map_keys(guild, "v2_results", "casino_live")

async def _announce_channel(guild):
    return await _channel_by_map_keys(guild, "v2_announce", "big_win")

async def _log_channel(guild):
    return await _channel_by_map_keys(guild, "v2_log", "log")

async def _post_round_log(guild, user, key, r):
    """📜｜ログへ、1プレイごとのBET／払戻／収支を送る。"""
    try:
        ch = await _log_channel(guild)
        if not ch:
            return
        profit = r.get("profit", r.get("payout", 0) - r.get("bet", 0))
        e = emb(
            "🎰 CASINO ROUND LOG",
            f"{user.mention}\n**{GAME_NAMES.get(key, key)}**\n"
            f"BET **{r.get('bet', 0):,} CHIP** → PAYOUT **{r.get('payout', 0):,} CHIP**\n"
            f"収支 **{profit:+,} CHIP**",
            GOLD,
        )
        e.set_footer(text=f"Round ID: {r.get('round_id', '-')}")
        await ch.send(embed=e)
    except Exception:
        pass

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
    # 同じ結果を「📺｜プレイ結果」（未設置ならcasino-live）へ公開し、📜｜ログにも簡易ログを残す。
    live=await _live_channel(i.guild,key)
    if live:
        public_e=emb(f"{GAME_NAMES[key]}｜LIVE RESULT",color=GOLD)
        public_e.description=f"{i.user.mention}\n\n" + ("\n".join(detail) if detail else "")
        public_e.add_field(name="BET",value=f"{r['bet']:,} CHIP")
        public_e.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
        public_e.add_field(name="収支",value=f"{r['profit']:+,} CHIP")
        public_e.add_field(name="倍率",value=f"×{r['multiplier']}")
        public_e.set_footer(text=f"Round ID: {r['round_id']}")
        await live.send(embed=public_e)
    await _post_round_log(i.guild,i.user,key,r)

    threshold=int(await setting("big_win_multiplier","30"))
    if r["multiplier"]>=threshold and await setting("big_win_enabled","1")=="1":
        ch=await _announce_channel(i.guild)
        if ch: await ch.send(embed=emb("🔥🔥 BIG WIN 🔥🔥",f"{i.user.mention}\n{GAME_NAMES[key]}\n\nBET **{r['bet']:,} CHIP**\nWIN **{r['payout']:,} CHIP**\n**×{r['multiplier']}**\n`{r['round_id']}`",GOLD))


class LotteryBuyModal(discord.ui.Modal,title="🎫 PAL 宝くじ"):
    count=discord.ui.TextInput(label="購入枚数",placeholder="1～100",max_length=3)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:r=await buy_lottery(i.user.id,int(str(self.count.value).replace(",","").strip()))
        except Exception as ex:await i.edit_original_response(content=f"宝くじエラー: `{type(ex).__name__}`\n`{str(ex)[:700]}`");return
        if r["status"]!="SUCCESS":await i.edit_original_response(content=f"購入処理: `{r['status']}`");return
        preview="\n".join(f"`{g:02d}組 {n:06d}番`" for _,g,n in r["tickets"][:20])
        await i.edit_original_response(content=f"🎫 第{r['draw_no']}回｜**{len(r['tickets'])}枚 / {r['cost']:,} CHIP**\n\n{preview}")

class LotoBuyModal(discord.ui.Modal,title="🔢 ロト6"):
    numbers=discord.ui.TextInput(label="1～43から6個",placeholder="3,8,14,21,32,41",max_length=30)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:nums=[int(x.strip()) for x in str(self.numbers.value).replace("、",",").split(",")];r=await buy_loto(i.user.id,nums)
        except Exception as ex:await i.edit_original_response(content=f"ロト6エラー: `{type(ex).__name__}`\n`{str(ex)[:700]}`");return
        if r["status"]!="SUCCESS":await i.edit_original_response(content=f"購入処理: `{r['status']}`");return
        await i.edit_original_response(content=f"🔢 第{r['draw_no']}回 ロト6購入完了\n**{' / '.join(map(str,r['numbers']))}**\n💰 {r['cost']:,} CHIP")

def jst_time(dt):
    if not dt:return "未設定"
    return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")

def build_lottery_announce_embed(r):
    """宝くじ抽選結果アナウンス。個人名は出さず当選番号のみ。当選者が1人もいない時だけ「なし」と明記する。"""
    text=f"**第{r['draw_no']}回**\n\n🎯 当選番号\n## {r['group']:02d}組 {r['number']:06d}番"
    if not r["winners"]:
        text+="\n\n🏆 当選者：なし"
    return emb("🎊 PAL CASINO｜宝くじ抽選結果",text,GOLD)

def build_loto_announce_embed(r):
    """ロト6抽選結果アナウンス。個人名は出さず本数字・BONUS・繰越のみ。当選者が1人もいない時だけ「なし」と明記する。"""
    nums=" / ".join(map(str,r["winning"]))
    text=f"**第{r['draw_no']}回**\n\n🎯 本数字\n## {nums}\n\nBONUS **{r['bonus']}**\n\n次回繰越 **{r['carryover']:,} CHIP**"
    if not r["winners"]:
        text+="\n\n🏆 当選者：なし"
    return emb("🔢 PAL CASINO｜ロト6抽選結果",text,GOLD)

class LotteryMyTicketsView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🎫 宝くじ履歴",style=discord.ButtonStyle.secondary)
    async def lottery(self,i,b):
        try:
            data=await lottery_user_overview(i.user.id);rows=data["tickets"];d=data["draw"]
            text="\n".join(f"`#{r['ticket_id']}` 第{r['draw_no']}回 **{r['ticket_group']:02d}組 {r['ticket_number']:06d}番**｜{r['rank'] or ('抽選待ち' if r['draw_status']=='OPEN' else 'はずれ')}"+(f"｜**{r['prize']:,} CHIP**" if r['prize'] else "") for r in rows)
            await i.response.send_message(embed=emb("🎫 MY LOTTERY",f"次回抽選 **{jst_time(d['draw_at'])} JST**\n\n{text or '購入券なし'}",GOLD),ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"🎫 MY LOTTERY ERROR: `{type(e).__name__}: {e}`",ephemeral=True)
    @discord.ui.button(label="🔢 ロト6履歴",style=discord.ButtonStyle.secondary)
    async def loto(self,i,b):
        data=await loto_user_overview(i.user.id)
        rows=data["tickets"]
        text="\n".join(
            f"`#{r['ticket_id']}` 第{r['draw_no']}回 **{' / '.join(map(str,r['numbers']))}**｜{r['rank'] or ('抽選待ち' if r['draw_status']=='OPEN' else 'はずれ')}"+(f"｜**{r['prize']:,} CHIP**" if r['prize'] else "")
            for r in rows
        )
        d=data["draw"]
        await i.response.send_message(embed=emb("🔢 MY LOTO6",f"次回抽選 **{jst_time(d['draw_at'])} JST**\nキャリー **{d['carryover']:,} CHIP**\n\n{text or '購入券なし'}",GOLD),ephemeral=True)

class LotoLaunchView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="🔢 数字を選ぶ",style=discord.ButtonStyle.primary,custom_id="casino_loto_select")
    async def select_nums(self,i,b):await i.response.send_modal(LotoBuyModal())
    @discord.ui.button(label="🎲 クイックピック",style=discord.ButtonStyle.success,custom_id="casino_loto_quickpick")
    async def qp(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);r=await quick_pick(i.user.id)
        if r["status"]=="SUCCESS":await i.edit_original_response(content=f"🎲 第{r['draw_no']}回 クイックピック\n**{' / '.join(map(str,r['numbers']))}**\n💰 {r['cost']:,} CHIP")
        else:await i.edit_original_response(content=f"購入処理: `{r['status']}`")
    @discord.ui.button(label="📖 マイロト6",style=discord.ButtonStyle.secondary,custom_id="casino_loto_my")
    async def my(self,i,b):
        data=await loto_user_overview(i.user.id);rows=data["tickets"];d=data["draw"]
        text="\n".join(f"`#{r['ticket_id']}` 第{r['draw_no']}回 **{' / '.join(map(str,r['numbers']))}**｜{r['rank'] or ('抽選待ち' if r['draw_status']=='OPEN' else 'はずれ')}"+(f"｜{r['prize']:,} CHIP" if r['prize'] else "") for r in rows)
        await i.response.send_message(embed=emb("🔢 MY LOTO6",f"次回抽選 **{jst_time(d['draw_at'])} JST**\nキャリー **{d['carryover']:,} CHIP**\n\n{text or '購入券なし'}",GOLD),ephemeral=True)

    @discord.ui.button(label="🏆 最新抽選結果",style=discord.ButtonStyle.primary,custom_id="casino_loto_result")
    async def result(self,i,b):
        r=await latest_loto_result()
        if not r:await i.response.send_message("まだ抽選結果はありません。",ephemeral=True);return
        nums=" / ".join(map(str,r["winning_numbers"] or []))
        text=f"**第{r['draw_no']}回**\n\n🎯 本数字\n## {nums}\n\nBONUS **{r['bonus_number']}**\n\n次回繰越 **{r['carryover']:,} CHIP**"
        await i.response.send_message(embed=emb("🔢 ロト6｜最新抽選結果",text,GOLD),ephemeral=True)

class LotteryLaunchView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="🎫 宝くじを購入",style=discord.ButtonStyle.success,custom_id="casino_lottery_buy")
    async def buy(self,i,b):await i.response.send_modal(LotteryBuyModal())
    @discord.ui.button(label="📖 マイ宝くじ",style=discord.ButtonStyle.secondary,custom_id="casino_lottery_my")
    async def my(self,i,b):
        data=await lottery_user_overview(i.user.id);rows=data["tickets"];d=data["draw"]
        text="\n".join(f"`#{r['ticket_id']}` 第{r['draw_no']}回 **{r['ticket_group']:02d}組 {r['ticket_number']:06d}番**｜{r['rank'] or ('抽選待ち' if r['draw_status']=='OPEN' else 'はずれ')}"+(f"｜{r['prize']:,} CHIP" if r['prize'] else "") for r in rows)
        await i.response.send_message(embed=emb("🎫 MY LOTTERY",f"次回抽選 **{jst_time(d['draw_at'])} JST**\n\n{text or '購入券なし'}",GOLD),ephemeral=True)


    @discord.ui.button(label="🏆 最新抽選結果",style=discord.ButtonStyle.primary,custom_id="casino_lottery_result")
    async def result(self,i,b):
        r=await latest_lottery_result()
        if not r:await i.response.send_message("まだ抽選結果はありません。",ephemeral=True);return
        text=f"**第{r['draw_no']}回**\n\n🎯 当選番号\n## {r['winning_group']:02d}組 {r['winning_number']:06d}番"
        await i.response.send_message(embed=emb("🎊 宝くじ｜最新抽選結果",text,GOLD),ephemeral=True)

class BetModal(discord.ui.Modal):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000",max_length=10)
    def __init__(self,key,callback):
        super().__init__(title=GAME_NAMES[key][:45]);self.key=key;self._callback=callback
    async def on_submit(self,i):
        try:bet=int(str(self.bet.value).replace(",","").strip())
        except:await i.response.send_message("BETは整数で入力してください。",ephemeral=True);return
        await self._callback(i,bet)

async def public_result(i,r,key,title=None):
    if r["status"]=="PREPARING":await i.edit_original_response(content="🚧 現在休止中です。");return
    if r["status"]=="BET_RANGE":await i.edit_original_response(content=f"BETは **{r['min']:,}～{r['max']:,} CHIP**");return
    if r["status"]=="INSUFFICIENT_BALANCE":await i.edit_original_response(content="CHIP残高が足りません。");return
    if r["status"]!="SUCCESS":await i.edit_original_response(content=f"CASINO処理: `{r['status']}`");return
    LABELS={"reels":"リール","number":"出目","color":"色","choice":"選択","dice":"サイコロ","rolled":"結果",
            "player":"あなた","npc":"親 / NPC","player_role":"あなたの役","npc_role":"親の役","cashout":"CASH OUT",
            "crash":"💥 爆発倍率","heads":"表","tails":"裏","current":"カード","mines":"爆弾数","opened":"OPEN"}
    hidden={"special_loss","target","event","auto","rtp_rate"}
    details=[f"**{LABELS.get(k,k)}**: {val}" for k,val in r.items()
             if k not in {"status","round_id","bet","payout","profit","multiplier","balance"}|hidden and val is not None]
    e=emb(title or f"{GAME_NAMES[key]}｜RESULT","\n".join(details),GOLD)
    e.add_field(name="BET",value=f"{r['bet']:,} CHIP");e.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
    e.add_field(name="収支",value=f"{r['profit']:+,} CHIP");e.add_field(name="倍率",value=f"×{r['multiplier']}")
    e.add_field(name="現在残高",value=f"{r['balance']:,} CHIP");e.set_footer(text=f"Round ID: {r['round_id']}")
    await i.edit_original_response(content=None,embed=e,view=None)
    live=await _live_channel(i.guild,key)
    if live:
        pe=emb(title or f"{GAME_NAMES[key]}｜LIVE RESULT",f"{i.user.mention}\n\n"+("\n".join(details) if details else ""),GOLD)
        pe.add_field(name="BET",value=f"{r['bet']:,} CHIP");pe.add_field(name="PAYOUT",value=f"{r['payout']:,} CHIP")
        pe.add_field(name="収支",value=f"{r['profit']:+,} CHIP");pe.add_field(name="倍率",value=f"×{r['multiplier']}")
        pe.set_footer(text=f"Round ID: {r['round_id']}");await live.send(embed=pe)
    await _post_round_log(i.guild,i.user,key,r)
    special=str(r.get("special") or "")
    announce=special in ("GOD","サイコロなし","BIG BANG","ブラックホール") or r["payout"]>=100_000_000 or (r["bet"] and r["payout"]>=r["bet"]*30)
    if announce:
        ch=await _announce_channel(i.guild)
        if ch:await ch.send(embed=emb("🔥 PAL CASINO SPECIAL ANNOUNCEMENT",f"{i.user.mention}\n**{GAME_NAMES[key]}**\n\n{special or '30倍以上の勝利'}\nPAYOUT **{r['payout']:,} CHIP**",GOLD))

class SlotBetModal(discord.ui.Modal,title="🎰 3リールスロット"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            bet=int(str(self.bet.value).replace(",",""))
            frames=["🍒  ❔  ❔","🍋  💎  ❔","7️⃣  🍒  🍋","💎  7️⃣  🍒","🍒  🍋  💎"]
            for n in range(10):
                frame=frames[n%len(frames)]
                await i.edit_original_response(content=None,embed=emb("🎰 SLOT SPINNING",f"```\n┃ {frame} ┃\n```\n🔄 リール回転中... **{n+1}/10**",GOLD),view=None)
                await asyncio.sleep(0.5)
            r=await play_slot(i.user.id,bet);await public_result(i,r,"SLOT3")
        except Exception as ex:await i.edit_original_response(content=f"スロットエラー: `{type(ex).__name__}` / `{str(ex)[:500]}`",embed=None,view=None)

def scratch_embed(state,finished=False):
    cells=[]
    for n in range(9):
        cells.append(state["board"][n] if n in state["opened"] else "❔")
    grid="\n".join(" ".join(cells[r:r+3]) for r in range(0,9,3))
    left=state["max_scratches"]-len(state["opened"])
    extra="\n\n✨ **4マス削れるスペシャルスクラッチ！**" if state["max_scratches"]==4 else ""
    if finished:
        extra+=f"\n\n🎯 **{state['grade']}**｜{state['symbol']}\n削ったマスで結果確定！"
    return emb("🎟️ PAL SCRATCH",f"```\n{grid}\n```\n🪙 500 CHIP\n🖐️ 残り **{max(left,0)}マス**{extra}",GOLD)

class ScratchCell(discord.ui.Button):
    def __init__(self,index):
        super().__init__(label=str(index+1),style=discord.ButtonStyle.secondary,row=index//3)
        self.index=index
    async def callback(self,i):
        view=self.view
        if i.user.id!=view.uid:
            await i.response.send_message("このスクラッチの購入者専用です。",ephemeral=True);return
        if self.index in view.state["opened"]:
            await i.response.send_message("ここはもう削っています。",ephemeral=True);return
        view.state["opened"].add(self.index)
        self.label=view.state["board"][self.index]
        self.style=discord.ButtonStyle.primary
        self.disabled=True
        if len(view.state["opened"])>=view.state["max_scratches"]:
            for item in view.children:item.disabled=True
            await i.response.defer()
            r=await finish_scratch(i.user.id,view.state)
            await i.edit_original_response(embed=scratch_embed(view.state,True),view=view,content=None)
            await asyncio.sleep(1.2)
            await public_result(i,r,"SCRATCH","🎟️ SCRATCH RESULT")
        else:
            await i.response.edit_message(embed=scratch_embed(view.state),view=view)

class ScratchView(discord.ui.View):
    def __init__(self,uid,state):
        super().__init__(timeout=180);self.uid=uid;self.state=state
        for n in range(9):self.add_item(ScratchCell(n))

class ScratchPurchaseView(discord.ui.View):
    def __init__(self):super().__init__(timeout=60)
    @discord.ui.button(label="🪙 500 CHIPで購入",style=discord.ButtonStyle.success)
    async def play(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        state=await start_scratch(i.user.id)
        if state["status"]!="SUCCESS":
            await i.edit_original_response(content=f"SCRATCH: `{state['status']}`");return
        await i.edit_original_response(content=None,embed=scratch_embed(state),view=ScratchView(i.user.id,state))


class ChoiceBetModal(discord.ui.Modal):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    def __init__(self,key,choice):super().__init__(title=f"{GAME_NAMES[key]}｜{choice}");self.key=key;self.choice=choice
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            bet=int(str(self.bet.value).replace(",",""))
            if self.key=="COIN":r=await play_coin(i.user.id,bet,self.choice)
            elif self.key=="CHOHAN":r=await play_chohan(i.user.id,bet,self.choice)
            else:
                wheel=[0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
                for step in range(12):
                    n=wheel[(step*3+__import__("random").randint(0,2))%len(wheel)]
                    icon="🟢" if n==0 else ("🔴" if n in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36} else "⚫")
                    await i.edit_original_response(embed=emb("🎡 ROULETTE",f"# {icon} {n}\n\nルーレット回転中……\n▰▰▰▰▰▰▰▰",GOLD),content=None,view=None)
                    await asyncio.sleep(0.18+step*0.035)
                r=await play_roulette(i.user.id,bet,self.choice)
                if r.get("status")=="SUCCESS":
                    n=r["number"];icon="🟢" if n==0 else ("🔴" if r["color"]=="赤" else "⚫")
                    await i.edit_original_response(embed=emb("🎡 BALL STOP",f"# {icon} {n}\n\n**{r['color']}｜{n}** に停止！",GOLD))
                    await asyncio.sleep(1.1)
            await public_result(i,r,self.key)
        except Exception as ex:await i.edit_original_response(content=f"ゲームエラー: `{type(ex).__name__}` / `{str(ex)[:500]}`")

class CoinBetModal(discord.ui.Modal):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    def __init__(self,choice):
        super().__init__(title=f"🪙 コイントス｜{choice}");self.choice=choice
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:bet=int(str(self.bet.value).replace(",","").strip())
        except:await i.edit_original_response(content="BETは整数で入力してください。");return
        for frame in ["🪙","⚪","🟡","⚪","🪙","⚪"]:
            await i.edit_original_response(embed=emb("🪙 COIN TOSS",f"# {frame}\n\nコインが回転中……",GOLD),content=None,view=None)
            await asyncio.sleep(0.35)
        r=await play_coin(i.user.id,bet,self.choice)
        if r.get("status")=="SUCCESS":
            face=r.get("rolled")
            if face:
                icon="🌕" if face=="表" else "🌑"
                await i.edit_original_response(embed=emb("🪙 COIN TOSS",f"# {icon}\n\n**{face}**",GOLD))
                await asyncio.sleep(1)
        await public_result(i,r,"COIN")

class CoinView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🌕 表",style=discord.ButtonStyle.primary)
    async def heads(self,i,b):await i.response.send_modal(CoinBetModal("表"))
    @discord.ui.button(label="🌑 裏",style=discord.ButtonStyle.secondary)
    async def tails(self,i,b):await i.response.send_modal(CoinBetModal("裏"))


class ChohanBetModal(discord.ui.Modal,title="🎴 丁半博打"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            state=await start_chohan(i.user.id,int(str(self.bet.value).replace(",","")))
            if state["status"]!="SUCCESS":await i.edit_original_response(content=f"丁半: `{state['status']}`");return
            if state.get("special")=="サイコロなし":
                await i.edit_original_response(embed=emb("🎴 丁半博打","🎲 ……\n\n**サイコロがない。**\n\n「……おい。これはどういうことだ？」",GOLD),view=ChohanChoiceView(i.user.id,state))
                return
            await i.edit_original_response(embed=emb("🎴 張った張った！",f"🎲 壺の中でサイコロが止まった……\n\n🗣️ NPC\n「{state['npc']}」\n\n出目はまだ見えない。\nここで **丁 / 半** を張れ。",GOLD),view=ChohanChoiceView(i.user.id,state))
        except Exception as ex:await i.edit_original_response(content=f"丁半エラー: `{type(ex).__name__}` / `{str(ex)[:500]}`",embed=None,view=None)

class ChohanChoiceView(discord.ui.View):
    def __init__(self,uid,state):super().__init__(timeout=180);self.uid=uid;self.state=state
    async def choose(self,i,choice):
        if i.user.id!=self.uid:await i.response.send_message("この勝負のプレイヤー専用です。",ephemeral=True);return
        await i.response.defer();r=await finish_chohan(i.user.id,self.state,choice);await public_result(i,r,"CHOHAN")
    @discord.ui.button(label="🎴 丁",style=discord.ButtonStyle.primary)
    async def cho(self,i,b):await self.choose(i,"丁")
    @discord.ui.button(label="🎴 半",style=discord.ButtonStyle.danger)
    async def han(self,i,b):await self.choose(i,"半")

class ChinchiroModal(discord.ui.Modal,title="🎲 チンチロ"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            bet=int(str(self.bet.value).replace(",","").strip())
            dice=["⚀","⚁","⚂","⚃","⚄","⚅"]
            for n in range(8):
                roll=" ".join(__import__("random").choice(dice) for _ in range(3))
                await i.edit_original_response(embed=emb("🎲 チンチロ",f"# {roll}\n\nカラカラカラ……\nサイコロを振っています。",GOLD),content=None,view=None)
                await asyncio.sleep(0.4)
            r=await play_chinchiro(i.user.id,bet)
            if r.get("status")=="SUCCESS":
                pd=r.get("player") or r.get("dice") or []
                nd=r.get("npc") or []
                def icons(vals):
                    return " ".join(dice[x-1] if isinstance(x,int) and 1<=x<=6 else str(x) for x in vals)
                text=f"**あなた**\n# {icons(pd)}"
                if nd:text+=f"\n\n**親**\n# {icons(nd)}"
                await i.edit_original_response(embed=emb("🎲 サイコロ停止！",text,GOLD))
                await asyncio.sleep(1.2)
            await public_result(i,r,"CHINCHIRO")
        except Exception as ex:await i.edit_original_response(content=f"チンチロエラー: `{type(ex).__name__}` / `{str(ex)[:500]}`",embed=None,view=None)

class RouletteNumberModal(discord.ui.Modal,title="🎡 単一数字BET"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    number=discord.ui.TextInput(label="数字 0～36",placeholder="17",max_length=2)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            n=int(str(self.number.value).replace(",","").strip());assert 0<=n<=36
            r=await play_roulette(i.user.id,int(str(self.bet.value).replace(",","")),f"NUM:{n}");await public_result(i,r,"ROULETTE")
        except Exception as ex:await i.edit_original_response(content=f"数字は0～36。`{type(ex).__name__}`")

class RouletteNumberButton(discord.ui.Button):
    def __init__(self,n):
        super().__init__(label=str(n),style=discord.ButtonStyle.secondary,row=(n%20)//5)
        self.number=n
    async def callback(self,i):
        await i.response.send_modal(ChoiceBetModal("ROULETTE",f"NUM:{self.number}"))

class RouletteNumberView(discord.ui.View):
    def __init__(self,page=0):
        super().__init__(timeout=180);self.page=page;self.rebuild()
    def rebuild(self):
        self.clear_items()
        nums=range(0,20) if self.page==0 else range(20,37)
        for n in nums:self.add_item(RouletteNumberButton(n))
        nav=discord.ui.Button(label="20～36 ▶" if self.page==0 else "◀ 0～19",style=discord.ButtonStyle.primary,row=4)
        nav.callback=self.nav;self.add_item(nav)
    async def nav(self,i):
        self.page=1-self.page;self.rebuild()
        await i.response.edit_message(content="🎯 **数字を1つ選択｜0～36**",view=self)

class RouletteSelect(discord.ui.Select):
    def __init__(self):
        opts=[
            discord.SelectOption(label="単一数字 0～36",value="NUMBER"),
            discord.SelectOption(label="赤",value="RED"),discord.SelectOption(label="黒",value="BLACK"),
            discord.SelectOption(label="奇数",value="ODD"),discord.SelectOption(label="偶数",value="EVEN"),
            discord.SelectOption(label="1～18",value="LOW"),discord.SelectOption(label="19～36",value="HIGH"),
            discord.SelectOption(label="第1ダズン 1～12",value="DOZEN:1"),discord.SelectOption(label="第2ダズン 13～24",value="DOZEN:2"),discord.SelectOption(label="第3ダズン 25～36",value="DOZEN:3"),
            discord.SelectOption(label="第1カラム",value="COLUMN:1"),discord.SelectOption(label="第2カラム",value="COLUMN:2"),discord.SelectOption(label="第3カラム",value="COLUMN:3")
        ]
        super().__init__(placeholder="🎡 賭け方を選択",options=opts,min_values=1,max_values=1)
    async def callback(self,i):
        if self.values[0]=="NUMBER":
            await i.response.edit_message(content="🎯 **数字を1つ選択｜0～36**",view=RouletteNumberView())
        else:await i.response.send_modal(ChoiceBetModal("ROULETTE",self.values[0]))


class RouletteView(discord.ui.View):
    def __init__(self):super().__init__(timeout=180);self.add_item(RouletteSelect())

class CrashBetModal(discord.ui.Modal,title="🚀 CRASH LIVE"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    auto=discord.ui.TextInput(label="自動CASH OUT倍率",placeholder="空欄=手動 / 例 2.50",required=False)
    async def on_submit(self,i):
        try:bet=int(str(self.bet.value).replace(",",""));auto=float(str(self.auto.value).replace(",","").strip()) if str(self.auto.value).strip() else None
        except:await i.response.send_message("BET / 倍率を確認してください。",ephemeral=True);return
        await i.response.defer(ephemeral=True,thinking=True)
        state=await create_crash(i.user.id,bet,auto)
        if state["status"]!="SUCCESS":await i.edit_original_response(content=f"CRASH: `{state['status']}`");return
        live=await _live_channel(i.guild,"CRASH")
        live_msg=await live.send(embed=emb("🚀 CRASH LIVE",f"{i.user.mention}\nBET **{bet:,} CHIP**\n\n🟢 **1.00x**\n🚀 上昇中...",GOLD)) if live else None
        view=CrashCashoutView(i.user.id,state)
        await i.edit_original_response(content="🚀 CRASH開始",embed=emb("🚀 CRASH LIVE","🟢 **1.00x**\n\n`CASH OUT` を押して利確",GOLD),view=view)
        asyncio.create_task(run_crash(i,state,view,live_msg))

class CrashCashoutView(discord.ui.View):
    def __init__(self,uid,state):super().__init__(timeout=300);self.uid=uid;self.state=state;self.current=1.0;self.casht=None;self.done=False
    @discord.ui.button(label="💰 CASH OUT",style=discord.ButtonStyle.success)
    async def cash(self,i,b):
        if i.user.id!=self.uid:await i.response.send_message("このラウンドのプレイヤー専用です。",ephemeral=True);return
        if self.done:await i.response.send_message("ラウンド終了済み。",ephemeral=True);return
        self.casht=self.current;self.done=True;await i.response.defer()

async def run_crash(i,state,view,live_msg):
    current=1.0
    while current<state["target"] and not view.done:
        await asyncio.sleep(0.7)
        current=round(current+max(0.01,current*0.045),2);view.current=current
        if state["auto"] and current>=state["auto"] and state["auto"]<state["target"]:view.casht=state["auto"];view.done=True
        e=emb("🚀 CRASH LIVE",f"🟢 **{current:.2f}x**\n\n{'🎯 AUTO '+str(state['auto'])+'x' if state['auto'] else '💰 手動CASH OUT'}",GOLD)
        try:await i.edit_original_response(content=None,embed=e,view=view)
        except:pass
        if live_msg:
            try:await live_msg.edit(embed=emb("🚀 CRASH LIVE",f"{i.user.mention}\nBET **{state['bet']:,} CHIP**\n\n🟢 **{current:.2f}x**\n🚀 上昇中...",GOLD))
            except:pass
    r=await finish_crash(i.user.id,state,view.casht)
    view.done=True
    title="💥 CRASH" if not view.casht else f"💰 CASH OUT {view.casht:.2f}x"
    await public_result(i,r,"CRASH",title)
    if live_msg:
        try:
            await live_msg.edit(embed=emb(f"🚀 CRASH｜{state['target']:.2f}x",f"{i.user.mention}\nBET **{state['bet']:,} CHIP**\nPAYOUT **{r.get('payout',0):,} CHIP**\n{r.get('special') or title}",GOLD),view=None)
        except:pass

class BlackjackBetModal(discord.ui.Modal,title="🃏 BLACKJACK"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:state=await start_blackjack(i.user.id,int(str(self.bet.value).replace(",","")))
        except Exception as ex:await i.edit_original_response(content=f"BLACKJACK: `{ex}`");return
        if state["status"]!="SUCCESS":await i.edit_original_response(content=f"BLACKJACK: `{state['status']}`");return
        await i.edit_original_response(embed=blackjack_embed(state),view=BlackjackView(i.user.id,state),content=None)
def blackjack_value(cards):
    total=sum(cards);aces=cards.count(11)
    while total>21 and aces:total-=10;aces-=1
    return total
def blackjack_embed(s):
    player_total=blackjack_value(s["player"])
    dealer_visible=s["dealer"][0]
    return emb("🃏 BLACKJACK",f"🧑 **あなた**\n{s['player']}\n合計 **{player_total}**\n\n🎩 **ディーラー**\n[{dealer_visible}, ?]\n見えている合計 **{dealer_visible}**",GOLD)
class BlackjackView(discord.ui.View):
    def __init__(self,uid,state):super().__init__(timeout=180);self.uid=uid;self.state=state
    async def interaction_check(self,i):
        if i.user.id!=self.uid:await i.response.send_message("プレイヤー専用です。",ephemeral=True);return False
        return True
    @discord.ui.button(label="HIT",style=discord.ButtonStyle.primary)
    async def hit(self,i,b):
        val=blackjack_hit(self.state)
        if val>21:
            await i.response.defer();r=await finish_blackjack(i.user.id,self.state,"STAND");await public_result(i,r,"BLACKJACK")
        else:await i.response.edit_message(embed=blackjack_embed(self.state),view=self)
    @discord.ui.button(label="STAND",style=discord.ButtonStyle.success)
    async def stand(self,i,b):await i.response.defer();r=await finish_blackjack(i.user.id,self.state,"STAND");await public_result(i,r,"BLACKJACK")
    @discord.ui.button(label="SURRENDER",style=discord.ButtonStyle.danger)
    async def surrender(self,i,b):await i.response.defer();r=await finish_blackjack(i.user.id,self.state,"SURRENDER");await public_result(i,r,"BLACKJACK")

class MinesBetModal(discord.ui.Modal,title="💣 MINES 5×5"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    mines=discord.ui.TextInput(label="爆弾数 1～24",placeholder="5",max_length=2)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        state=await start_mines(i.user.id,int(str(self.bet.value).replace(",","").strip()),int(str(self.mines.value).strip()))
        if state["status"]!="SUCCESS":
            await i.edit_original_response(content=f"MINES: `{state['status']}`");return
        await i.edit_original_response(embed=mines_embed(state),view=MinesView(i.user.id,state),content=None)
        await i.followup.send("💰 好きなタイミングで換金できます。",view=MinesCashoutView(i.user.id,state),ephemeral=True)

def mines_embed(s,exploded=None):
    cells=[]
    for c in range(25):
        if exploded is not None and c==exploded:cells.append("💥")
        elif exploded is not None and c in s["mine_set"]:cells.append("💣")
        elif c in s["opened"]:cells.append("💎")
        else:cells.append("❔")
    board="\n".join(" ".join(cells[r:r+5]) for r in range(0,25,5))
    return emb("💣 MINES｜5×5",f"```\n{board}\n```\n💣 爆弾 **{s['mines']}個**\n💎 OPEN **{len(s['opened'])}マス**\n📈 現在 **×{s['multiplier']}**\n\nスクラッチ感覚で好きなマスを選択",GOLD)

class MineButton(discord.ui.Button):
    def __init__(self,cell):
        super().__init__(label=str(cell+1),style=discord.ButtonStyle.secondary,row=cell//5);self.cell=cell
    async def callback(self,i):
        view=self.view
        if i.user.id!=view.uid:
            await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        x=mines_open(view.state,self.cell)
        if x["status"]=="ALREADY_OPEN":
            await i.response.send_message("このマスは開いています。",ephemeral=True);return
        if x["status"]=="MINE":
            for item in view.children:item.disabled=True
            self.label="💥";self.style=discord.ButtonStyle.danger
            await i.response.defer()
            await i.edit_original_response(embed=mines_embed(view.state,self.cell),view=view)
            await asyncio.sleep(1.2)
            r=await finish_mines(i.user.id,view.state,False)
            await public_result(i,r,"MINES","💥 MINE HIT")
        else:
            self.label="💎";self.disabled=True;self.style=discord.ButtonStyle.success
            await i.response.edit_message(embed=mines_embed(view.state),view=view)

class MinesView(discord.ui.View):
    def __init__(self,uid,state,page=0):
        super().__init__(timeout=300);self.uid=uid;self.state=state
        for c in range(25):
            b=MineButton(c)
            if c in state["opened"]:b.label="💎";b.disabled=True;b.style=discord.ButtonStyle.success
            self.add_item(b)

class MinesCashoutView(discord.ui.View):
    def __init__(self,uid,state):
        super().__init__(timeout=300);self.uid=uid;self.state=state;self.done=False
    @discord.ui.button(label="💰 CASH OUT",style=discord.ButtonStyle.success)
    async def cash(self,i,b):
        if i.user.id!=self.uid:
            await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        if self.done:
            await i.response.send_message("このゲームは終了しています。",ephemeral=True);return
        if not self.state["opened"]:
            await i.response.send_message("最低1マス開けてからCASH OUTできます。",ephemeral=True);return
        self.done=True;b.disabled=True
        await i.response.edit_message(content="💰 CASH OUT処理中……",view=self)
        r=await finish_mines(i.user.id,self.state,True)
        if r.get("status")=="SUCCESS":
            e=emb("💰 MINES CASH OUT",f"BET **{r['bet']:,} CHIP**\nPAYOUT **{r['payout']:,} CHIP**\n収支 **{r['profit']:+,} CHIP**\n倍率 **×{r['multiplier']}**\n現在残高 **{r['balance']:,} CHIP**",GOLD)
            await i.followup.send(embed=e,ephemeral=True)
        else:await i.followup.send(f"MINES: `{r.get('status')}`",ephemeral=True)


class HighlowBetModal(discord.ui.Modal,title="📈 HIGH & LOW"):
    bet=discord.ui.TextInput(label="BET CHIP",placeholder="100～10,000")
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True);s=await start_highlow(i.user.id,int(str(self.bet.value).replace(",","")))
        if s["status"]!="SUCCESS":await i.edit_original_response(content=f"HIGHLOW: `{s['status']}`");return
        await i.edit_original_response(embed=highlow_embed(s),view=HighlowView(i.user.id,s),content=None)
def highlow_joker_hint(s):
    mult=s.get("multiplier",1)
    if mult>=8:return "\n\n🃏 **カードの奥から、妙な気配がする……**"
    if mult>=4:return "\n\n🎴 **山札が少しざわついている。**"
    if mult>=2:return "\n\n👁️ **一瞬だけ、見慣れない影が見えた気がした。**"
    return ""
def highlow_embed(s):
    # 倍率が1より大きい＝ダブルアップ中。ジョーカーモードの見た目に切り替える。
    joker_mode=s.get("multiplier",1)>1
    title="🃏 HIGH & LOW｜ジョーカーモード" if joker_mode else "📈 HIGH & LOW"
    color=0x9B59B6 if joker_mode else GOLD
    desc=("🃏 山札にジョーカーが紛れ込んでいます……\n\n" if joker_mode else "")+f"現在カード **{s['current']}**\n現在倍率 **×{s['multiplier']}**\n\nHIGH / LOW を選択{highlow_joker_hint(s)}"
    return emb(title,desc,color)
def highlow_win_embed(s):
    # 勝利直後、次に進む前に「ダブルアップ」か「降りる」かを明示的に選ばせるための画面。
    joker_mode=s.get("multiplier",1)>1
    payout=int(s["bet"]*s["multiplier"])
    desc=f"現在倍率 **×{s['multiplier']}**\n払戻予定 **{payout:,} CHIP**\n\n"
    if joker_mode:desc+="🃏 次のカードからは山札にジョーカーが紛れ込みます……\n\n"
    desc+="🎲 **ダブルアップ**：もう一度勝負して倍率アップを狙う\n💰 **降りる**：ここで払い戻しを受け取る"
    return emb("🎉 WIN！ダブルアップしますか？",desc,0x9B59B6 if joker_mode else GOLD)
class HighlowView(discord.ui.View):
    def __init__(self,uid,state):super().__init__(timeout=300);self.uid=uid;self.state=state
    async def choose(self,i,choice):
        if i.user.id!=self.uid:await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        x=await highlow_step(self.state,choice,self.state["multiplier"]>1)
        if x.get("mystery_payout") is not None:
            await i.response.defer();r=await finish_highlow(i.user.id,self.state,x["mystery_payout"],"JOKER_MYSTERY",{"joker":"？？？？？"});await public_result(i,r,"HIGHLOW");return
        if x.get("done") and not x.get("win"):
            await i.response.defer();r=await finish_highlow(i.user.id,self.state,0,"LOSE",{"joker":x.get("joker"),"next":x["next"]});await public_result(i,r,"HIGHLOW");return
        self.state["current"]=x["current"]
        if x.get("push"):
            # 引き分け（同じカード）は倍率据え置きでもう一度選択させる
            await i.response.edit_message(embed=highlow_embed(self.state),view=self);return
        # 勝利：倍率アップの上で、ダブルアップ/降りるを明示的に選ばせる
        self.state["multiplier"]=min(10,self.state["multiplier"]*2)
        await i.response.edit_message(embed=highlow_win_embed(self.state),view=HighlowDoubleUpPromptView(self.uid,self.state))
    @discord.ui.button(label="HIGH",style=discord.ButtonStyle.danger)
    async def high(self,i,b):await self.choose(i,"HIGH")
    @discord.ui.button(label="LOW",style=discord.ButtonStyle.primary)
    async def low(self,i,b):await self.choose(i,"LOW")
    @discord.ui.button(label="💰 換金",style=discord.ButtonStyle.success)
    async def cash(self,i,b):
        if i.user.id!=self.uid:await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        await i.response.defer();p=int(self.state["bet"]*self.state["multiplier"]);r=await finish_highlow(i.user.id,self.state,p,"CASHOUT",{"current":self.state["current"]});await public_result(i,r,"HIGHLOW")
class HighlowDoubleUpPromptView(discord.ui.View):
    """1回勝つたびに表示される、ダブルアップか降りるかの明示的な選択画面。"""
    def __init__(self,uid,state):super().__init__(timeout=300);self.uid=uid;self.state=state
    @discord.ui.button(label="🎲 ダブルアップ",style=discord.ButtonStyle.danger)
    async def double_up(self,i,b):
        if i.user.id!=self.uid:await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        await i.response.edit_message(embed=highlow_embed(self.state),view=HighlowView(self.uid,self.state))
    @discord.ui.button(label="💰 降りる",style=discord.ButtonStyle.success)
    async def cash(self,i,b):
        if i.user.id!=self.uid:await i.response.send_message("プレイヤー専用です。",ephemeral=True);return
        await i.response.defer();p=int(self.state["bet"]*self.state["multiplier"]);r=await finish_highlow(i.user.id,self.state,p,"CASHOUT",{"current":self.state["current"]});await public_result(i,r,"HIGHLOW")

DIRECT_GAME_INFO={
"SLOT3":("🎰 3リールスロット","3つのリールを回し、揃った絵柄で配当が決まるゲーム。BET後はリール演出が流れます。"),
"SCRATCH":("🎟️ スクラッチ","500 CHIP固定。スクラッチを削って当たりを狙うシンプルなゲーム。"),
"BLACKJACK":("🃏 ブラックジャック","カード合計を21に近づけてディーラーと勝負。HIT・STAND・SURRENDERを選べます。"),
"ROULETTE":("🎡 ヨーロピアンルーレット","0～36の出目を予想。数字・色・奇偶・範囲・ダズン・カラムにBETできます。"),
"MINES":("💣 マインズ","6×6の盤面から安全マスを開くゲーム。開けるほど倍率上昇、好きな時に換金できます。"),
"CHINCHIRO":("🎲 チンチロ","3つのサイコロでNPCの親と役・出目を競うゲーム。"),
"CHOHAN":("🎴 丁半博打","BET後にサイコロとNPCのセリフを確認し、合計が偶数の丁か奇数の半かを張るゲーム。"),
"COIN":("🪙 コイントス","表か裏を選んでコイン勝負。特殊な大量コイン演出が発生することもあります。"),
"HIGHLOW":("📈 ハイアンドロー","次のカードがHIGHかLOWかを予想。勝つほど倍率が上がり、途中換金できます。ダブルアップ中、山札にはジョーカーが潜んでいます。"),
"CRASH":("🚀 CRASH LIVE","リアルタイムで上がる倍率を見ながら、爆発前にCASH OUTするゲーム。"),
}

class DirectGamePanel(discord.ui.View):
    def __init__(self,key):
        super().__init__(timeout=None);self.key=key
        b=discord.ui.Button(label="🎮 プレイ",style=discord.ButtonStyle.success,custom_id=f"casino_direct_{key.lower()}")
        b.callback=self.play;self.add_item(b)
    async def play(self,i):
        try:
            cfg=await game(self.key)
            if not cfg or not cfg["implemented"] or not cfg["enabled"]:
                await i.response.send_message("🔴 このゲームは現在休止中です。",ephemeral=True);return
            if self.key=="SLOT3":await i.response.send_modal(SlotBetModal())
            elif self.key=="SCRATCH":await i.response.send_message("🎟️ **500 CHIP固定**\n\n下のボタンで削ります。",view=ScratchPurchaseView(),ephemeral=True)
            elif self.key=="ROULETTE":await i.response.send_message("🎡 **賭け方を選択**",view=RouletteView(),ephemeral=True)
            elif self.key=="COIN":await i.response.send_message("🪙 **表 / 裏を選択**",view=CoinView(),ephemeral=True)
            elif self.key=="CHOHAN":await i.response.send_modal(ChohanBetModal())
            elif self.key=="CHINCHIRO":await i.response.send_modal(ChinchiroModal())
            elif self.key=="CRASH":await i.response.send_modal(CrashBetModal())
            elif self.key=="BLACKJACK":await i.response.send_modal(BlackjackBetModal())
            elif self.key=="MINES":await i.response.send_modal(MinesBetModal())
            elif self.key=="HIGHLOW":await i.response.send_modal(HighlowBetModal())
        except Exception as ex:
            msg=f"ゲーム起動エラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`"
            if i.response.is_done():await i.followup.send(msg,ephemeral=True)
            else:await i.response.send_message(msg,ephemeral=True)

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
                ch=await _announce_channel(i.guild)
                if ch:
                    await ch.send(embed=emb("🎁🔥 DAILY GACHA RARE RESULT 🔥🎁",f"{i.user.mention}\n\n**{reward:+,} CHIP**\n確率 **{'0.001%' if reward==100000 else '0.999%'}**",GOLD))
        except Exception as ex:
            await i.edit_original_response(content=f"ガチャエラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")


# ===== !casinosetup で 🎰｜カジノ に設置する「カジノショップパネル」 =====
async def _grant_vip_role(guild,member):
    """VIP購入者へ「👑 VIP」ロールを自動付与する。ロール未設置なら何もしない（後で!casinosetup実行時に自動同期される）。"""
    try:
        rid=await map_get("v2_vip_role")
        if not rid:
            return
        role=guild.get_role(int(rid))
        if role and role not in member.roles:
            await member.add_roles(role,reason="PAL CASINO VIP purchase")
    except Exception:
        pass


class CasinoShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👑 VIP会員権を購入",style=discord.ButtonStyle.primary,custom_id="casino_shop_vip")
    async def buy_vip(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            from bank_gateway_for_other_bots import bank_debit
            uid=str(i.user.id)
            vip=await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",uid)
            if vip:
                await _grant_vip_role(i.guild,i.user)
                await i.edit_original_response(content="👑 既にVIP会員です。");return
            price=int(await setting("vip_price","50000"))
            r=await bank_debit("PAL_CASINO",f"VIP_PURCHASE:{uid}:{i.id}",uid,"CHIP",price)
            if r["status"]=="INSUFFICIENT_BALANCE":
                await i.edit_original_response(content=f"CHIP残高が足りません。必要 **{price:,} CHIP**");return
            if r["status"]!="SUCCESS":
                await i.edit_original_response(content=f"購入処理: `{r['status']}`");return
            await pool().execute(
                """INSERT INTO casino.user_state(user_id,vip) VALUES($1,TRUE)
                   ON CONFLICT(user_id) DO UPDATE SET vip=TRUE,updated_at=now()""",uid)
            await _grant_vip_role(i.guild,i.user)
            await i.edit_original_response(content=f"👑 VIP会員権を購入しました！（**-{price:,} CHIP**）\n👑VIPロールが付与され、VIPルーム／VIP GAMEが解放されます。\n通常ゲームの最大BETも2倍になります。")
            log_ch=await _log_channel(i.guild)
            if log_ch:await log_ch.send(embed=emb("👑 VIP購入",f"{i.user.mention} がVIP会員権を購入しました。｜**-{price:,} CHIP**",GOLD))
        except Exception as ex:
            await i.edit_original_response(content=f"購入エラー: `{type(ex).__name__}`\n`{str(ex)[:500]}`")


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
                ch=await _announce_channel(i.guild)
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
        cfg=await game(self.values[0]);new=not cfg["enabled"]
        await pool().execute("UPDATE casino.games SET enabled=$1 WHERE game_key=$2",new,self.values[0])
        from setup_service import refresh_status_panel, refresh_v2_status_panel
        await refresh_status_panel(i.guild)
        await refresh_v2_status_panel(i.guild)
        log_ch=await _log_channel(i.guild)
        if log_ch:await log_ch.send(embed=emb("🎮 ゲーム設定変更",f"管理者 {i.user.mention}\n**{cfg['display_name']}** → {'🟢 営業中' if new else '🔴 休止中'}",GOLD))
        await i.response.edit_message(content=f"{cfg['display_name']} → {'🟢 営業中' if new else '🔴 休止中'}\n\n📢 営業案内も更新しました。",view=None)
class AdminGameView(discord.ui.View):
    def __init__(self,rows):super().__init__(timeout=120);self.add_item(AdminGameSelect(rows))

GAME_PROBABILITY_HELP={
"SLOT3":"当たり抽選ウェイト","SCRATCH":"4マス発生率 %","LOTTERY":"当選確率は組・番号抽選","LOTO6":"当選確率は1～43抽選",
"BLACKJACK":"カード抽選","ROULETTE":"0～36均等抽選","MINES":"爆弾配置抽選","CHINCHIRO":"GOD発生率 %","CHOHAN":"サイコロなし発生率 %",
"COIN":"100枚イベント発生率 %","HIGHLOW":"ジョーカー参戦率 %","CRASH":"月到着発生率 %"}

class GameSettingsModal(discord.ui.Modal):
    probability=discord.ui.TextInput(label="特殊・レア発生率 %",placeholder="例: 3.0",required=False,max_length=30)
    payout_rate=discord.ui.TextInput(label="ゲーム還元率 %",placeholder="例: 95.00",required=True,max_length=10)
    def __init__(self,key):
        super().__init__(title=f"{GAME_NAMES.get(key,key)} 設定");self.key=key
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            rate=float(str(self.payout_rate.value).replace("%","").replace(",","").strip())
            if not 1<=rate<=200:raise ValueError("還元率は1～200")
            await config_set(self.key,"payout_rate",f"{rate:.2f}",i.user.id)
            raw=str(self.probability.value).strip()
            if raw:
                prob=float(raw)
                if not 0<=prob<=100:raise ValueError("確率は0～100")
                mapkey={"SCRATCH":"four_tile_rate","CHINCHIRO":"god_rate_percent","CHOHAN":"special_rate","COIN":"hundred_coin_rate","HIGHLOW":"joker_rate","CRASH":"moon_rate_percent"}
                await config_set(self.key,mapkey.get(self.key,"special_rate"),str(prob),i.user.id)
            log_ch=await _log_channel(i.guild)
            if log_ch:await log_ch.send(embed=emb("⚙️ ゲーム設定変更",f"管理者 {i.user.mention}\n**{GAME_NAMES.get(self.key,self.key)}**\n還元率 **{rate:.2f}%**"+(f"\n確率 **{raw}%**" if raw else ""),GOLD))
            await i.edit_original_response(content=f"✅ **{GAME_NAMES.get(self.key,self.key)}**\n還元率 **{rate:.2f}%**"+(f"\n確率 **{raw}%**" if raw else ""))
        except Exception as ex:await i.edit_original_response(content=f"設定エラー: `{str(ex)[:500]}`")

class GameSettingsOpenView(discord.ui.View):
    def __init__(self,key):super().__init__(timeout=120);self.key=key
    @discord.ui.button(label="⚙️ 確率・還元率を変更",style=discord.ButtonStyle.primary)
    async def open(self,i,b):await i.response.send_modal(GameSettingsModal(self.key))

class SettingsSelect(discord.ui.Select):
    def __init__(self,rows):super().__init__(placeholder="詳細設定するゲーム",options=[discord.SelectOption(label=r["display_name"],value=r["game_key"]) for r in rows[:25]])
    async def callback(self,i):
        key=self.values[0]
        rate=await config_get(key,"payout_rate",await setting("target_rtp","95.00"))
        helptext=GAME_PROBABILITY_HELP.get(key,"特殊イベント発生率")
        await i.response.send_message(f"⚙️ **{GAME_NAMES.get(key,key)}**\n確率項目: **{helptext}**\n現在還元率: **{rate}%**",view=GameSettingsOpenView(key),ephemeral=True)
class SettingsView(discord.ui.View):
    def __init__(self,rows):super().__init__(timeout=120);self.add_item(SettingsSelect(rows))

class RTPModal(discord.ui.Modal,title="📈 CASINO全体還元率"):
    target=discord.ui.TextInput(label="目標還元率 %",placeholder="95.00",max_length=6)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            val=float(str(self.target.value).replace("%","").replace(",","").strip())
            if not 1<=val<=200:raise ValueError("1～200")
            old=await setting("target_rtp","95.00");await set_setting("target_rtp",f"{val:.2f}");await audit_global(i.user.id,"target_rtp",old,f"{val:.2f}")
            ch=await _log_channel(i.guild)
            if ch:await ch.send(embed=emb("📈 CASINO RTP UPDATED",f"管理者 {i.user.mention}\n目標RTP **{old}% → {val:.2f}%**\n対象: 通常CASINOゲーム",GOLD))
            await i.edit_original_response(content=f"✅ 全体目標還元率を **{val:.2f}%** に変更しました。")
        except Exception as ex:await i.edit_original_response(content=f"RTP設定エラー: `{str(ex)[:500]}`")

class SystemView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="📈 全体還元率変更",style=discord.ButtonStyle.primary)
    async def rtp(self,i,b):await i.response.send_modal(RTPModal())
    @discord.ui.button(label="📊 実測RTP",style=discord.ButtonStyle.secondary)
    async def actual(self,i,b):
        s=await total_stats();actual=(float(s["payouts"])/float(s["bets"])*100) if s["bets"] else 0
        await i.response.send_message(f"🎯 目標RTP **{await setting('target_rtp','95.00')}%**\n📊 実測RTP **{actual:.2f}%**\n💰 BET {s['bets']:,} / 配当 {s['payouts']:,} CHIP",ephemeral=True)
    @discord.ui.button(label="🎫 宝くじ抽選",style=discord.ButtonStyle.danger)
    async def lottery_draw(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            r=await draw_lottery();await ensure_lottery_draw()
            ch=await _channel_by_map_keys(i.guild,"v2_announce","status")
            if ch:await ch.send(embed=build_lottery_announce_embed(r))
            await i.edit_original_response(content=f"🎊 第{r['draw_no']}回 宝くじ抽選完了\n\n**{r['group']:02d}組 {r['number']:06d}番**")
        except Exception as ex:await i.edit_original_response(content=f"宝くじ抽選エラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")
    @discord.ui.button(label="🔢 ロト6抽選",style=discord.ButtonStyle.danger)
    async def loto_draw(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            r=await draw_loto();await ensure_loto_draw();nums=" / ".join(map(str,r["winning"]))
            ch=await _channel_by_map_keys(i.guild,"v2_announce","status")
            if ch:await ch.send(embed=build_loto_announce_embed(r))
            await i.edit_original_response(content=f"🔢 第{r['draw_no']}回 ロト6抽選完了\n\n本数字 **{nums}**\nBONUS **{r['bonus']}**")
        except Exception as ex:await i.edit_original_response(content=f"ロト6抽選エラー: `{type(ex).__name__}`\n`{str(ex)[:800]}`")

class AdminUserModal(discord.ui.Modal,title="👤 CASINOユーザー確認"):
    user_id=discord.ui.TextInput(label="Discord User ID",placeholder="123456789012345678",max_length=25)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        try:
            uid=int(str(self.user_id.value).strip());p=await profile(uid);member=i.guild.get_member(uid)
            e=emb("👤 CASINO USER",f"{member.mention if member else f'`{uid}`'}",GOLD)
            e.add_field(name="CHIP",value=f"{p['chip']:,} CHIP");e.add_field(name="VIP",value="YES" if p["vip"] else "NO")
            e.add_field(name="総プレイ",value=f"{p['plays']:,}回");e.add_field(name="総BET",value=f"{p['total_bet']:,} CHIP")
            e.add_field(name="総配当",value=f"{p['total_payout']:,} CHIP");e.add_field(name="収支",value=f"{p['total_payout']-p['total_bet']:+,} CHIP")
            e.add_field(name="最大勝利",value=f"{p['max_win']:,} CHIP");e.add_field(name="最多ゲーム",value=GAME_NAMES.get(p["favorite"],p["favorite"]))
            await i.edit_original_response(embed=e,content=None)
        except Exception as ex:await i.edit_original_response(content=f"ユーザー確認エラー: `{type(ex).__name__}` / `{str(ex)[:500]}`")

class AdminTransactionSearchModal(discord.ui.Modal,title="📖 CASINO取引検索"):
    query=discord.ui.TextInput(label="User ID または Round ID",placeholder="Discord User ID / SLOT3-...",max_length=100)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True,thinking=True)
        q=str(self.query.value).strip()
        if q.isdigit():
            rows=await pool().fetch("SELECT * FROM casino.rounds WHERE user_id=$1 ORDER BY created_at DESC LIMIT 25",q)
        else:
            rows=await pool().fetch("SELECT * FROM casino.rounds WHERE round_id=$1 LIMIT 25",q)
        text="\n".join(f"`{r['round_id']}` <@{r['user_id']}> {GAME_NAMES.get(r['game_key'],r['game_key'])} BET **{r['bet']:,}** / PAY **{r['payout']:,}**" for r in rows)
        await i.edit_original_response(embed=emb("📖 CASINO取引検索",text[:4000] or "一致する取引なし",GOLD),content=None)

class AdminTransactionView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🔎 取引検索",style=discord.ButtonStyle.secondary)
    async def search(self,i,b):await i.response.send_modal(AdminTransactionSearchModal())
    @discord.ui.button(label="📖 最新25件",style=discord.ButtonStyle.primary)
    async def latest(self,i,b):
        rows=await pool().fetch("SELECT * FROM casino.rounds ORDER BY created_at DESC LIMIT 25")
        text="\n".join(f"`{r['round_id']}` <@{r['user_id']}> {GAME_NAMES.get(r['game_key'],r['game_key'])} BET {r['bet']:,} / PAY {r['payout']:,}" for r in rows)
        await i.response.send_message(embed=emb("📖 CASINO取引 最新25件",text[:4000] or "記録なし",GOLD),ephemeral=True)

class AdminAlertView(discord.ui.View):
    def __init__(self):super().__init__(timeout=120)
    @discord.ui.button(label="🚨 高額BET確認",style=discord.ButtonStyle.danger)
    async def highbet(self,i,b):
        threshold=int(await setting("alert_high_bet","10000"))
        rows=await pool().fetch("SELECT * FROM casino.rounds WHERE bet >= $1 ORDER BY created_at DESC LIMIT 20",threshold)
        text="\n".join(f"<@{r['user_id']}> {GAME_NAMES.get(r['game_key'],r['game_key'])} **{r['bet']:,} CHIP** `{r['round_id']}`" for r in rows)
        await i.response.send_message(embed=emb("🚨 高額BET",text[:4000] or "該当なし",GOLD),ephemeral=True)

class CasinoAdminView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def interaction_check(self,i):
        if not i.user.guild_permissions.administrator:await i.response.send_message("管理者専用です。",ephemeral=True);return False
        return True
    @discord.ui.button(label="🎮 ゲーム管理",style=discord.ButtonStyle.primary,custom_id="casino_admin_games",row=0)
    async def gm(self,i,b):await i.response.send_message("ゲーム営業管理",view=AdminGameView(await games()),ephemeral=True)
    @discord.ui.button(label="🟢 全ゲーム営業",style=discord.ButtonStyle.success,custom_id="casino_admin_all_games_on",row=3)
    async def all_games_on(self,i,b):
        await pool().execute("UPDATE casino.games SET enabled=TRUE WHERE implemented=TRUE")
        from setup_service import refresh_status_panel, refresh_v2_status_panel
        await refresh_status_panel(i.guild)
        await refresh_v2_status_panel(i.guild)
        await i.response.send_message("🟢 **全ゲーム営業開始！**\n\n📢 営業案内も更新しました。",ephemeral=True)
    @discord.ui.button(label="🔴 全ゲーム休止",style=discord.ButtonStyle.danger,custom_id="casino_admin_all_games_off",row=3)
    async def all_games_off(self,i,b):
        await pool().execute("UPDATE casino.games SET enabled=FALSE")
        from setup_service import refresh_status_panel, refresh_v2_status_panel
        await refresh_status_panel(i.guild)
        await refresh_v2_status_panel(i.guild)
        await i.response.send_message("🔴 **全ゲーム休止！**\n\n📢 営業案内も更新しました。",ephemeral=True)
    @discord.ui.button(label="⚙️ ゲーム設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_settings",row=0)
    async def gs(self,i,b):await i.response.send_message("⚙️ 詳細設定するゲームを選択してください。",view=SettingsView(await games()),ephemeral=True)
    @discord.ui.button(label="👤 ユーザー確認",style=discord.ButtonStyle.secondary,custom_id="casino_admin_user",row=0)
    async def user(self,i,b):await i.response.send_modal(AdminUserModal())
    @discord.ui.button(label="📖 CASINO取引",style=discord.ButtonStyle.secondary,custom_id="casino_admin_tx",row=1)
    async def tx(self,i,b):await i.response.send_message("📖 CASINO取引",view=AdminTransactionView(),ephemeral=True)
    @discord.ui.button(label="📊 CASINO統計",style=discord.ButtonStyle.secondary,custom_id="casino_admin_stats",row=1)
    async def stats(self,i,b):
        s=await total_stats();await i.response.send_message(f"🎮 総プレイ **{s['plays']:,}**\n🕒 24時間 **{s['plays24']:,}**\n💰 総BET **{s['bets']:,} CHIP**\n🏆 総配当 **{s['payouts']:,} CHIP**\n📈 CASINO収支 **{s['bets']-s['payouts']:+,} CHIP**",ephemeral=True)
    @discord.ui.button(label="📢 アナウンス設定",style=discord.ButtonStyle.secondary,custom_id="casino_admin_announce",row=1)
    async def announce(self,i,b):
        cur=await setting("big_win_enabled","1");new="0" if cur=="1" else "1";await set_setting("big_win_enabled",new);await i.response.send_message(f"🔥 BIG WIN通知 → {'ON' if new=='1' else 'OFF'}",ephemeral=True)
    @discord.ui.button(label="🚨 警告確認",style=discord.ButtonStyle.danger,custom_id="casino_admin_alert",row=2)
    async def alert(self,i,b):await i.response.send_message("🚨 CASINO警告確認",view=AdminAlertView(),ephemeral=True)
    @discord.ui.button(label="🔧 CASINO SYSTEM",style=discord.ButtonStyle.secondary,custom_id="casino_admin_system",row=2)
    async def system(self,i,b):await i.response.send_message("🔧 CASINO SYSTEM",view=SystemView(),ephemeral=True)

    @discord.ui.button(label="♻️ システム復旧",style=discord.ButtonStyle.success,custom_id="casino_admin_v2_recover",row=4)
    async def v2_recover(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        import setup_service as _ss  # 循環importを避けるため遅延import
        _main_cat,_game_cat,vip_role,channels,counts=await _ss.ensure_v2_structure(i.guild)
        await _ss.install_v2_panels(i.guild,channels)
        await i.followup.send(
            f"♻️ PAL CASINOシステムを復旧しました。\n"
            f"新規作成: {counts['created']}件\n復旧: {counts['restored']}件\n再利用: {counts['reused']}件\n"
            f"ゲームチャンネル数: {counts['game_channels']}\n"
            f"👑 VIPロール: {vip_role.mention}\n\n"
            f"（CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータはそのまま利用しています）",
            ephemeral=True,
        )

    @discord.ui.button(label="📢 パネル再設置",style=discord.ButtonStyle.primary,custom_id="casino_admin_v2_repanel",row=4)
    async def v2_repanel(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        import setup_service as _ss  # 循環importを避けるため遅延import
        channels=await _ss.get_v2_channels(i.guild)
        if not channels:
            await i.followup.send("PAL CASINOのチャンネルが見つかりません。先に `!casinosetup` を実行してください。",ephemeral=True)
            return
        await _ss.install_v2_panels(i.guild,channels)
        await i.followup.send("📢 パネルを再設置しました。",ephemeral=True)

    @discord.ui.button(label="🗑 システム削除",style=discord.ButtonStyle.danger,custom_id="casino_admin_v2_delete",row=4)
    async def v2_delete(self,i,b):
        await i.response.send_message(
            "⚠️ PAL CASINOのカテゴリ・チャンネル・パネルをDiscord側から削除します。\n"
            "CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータは削除されません。\n"
            "よろしいですか？",
            view=CasinoSystemDeleteConfirmView(),
            ephemeral=True,
        )


class CasinoSystemDeleteConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    async def interaction_check(self,i):
        if not i.user.guild_permissions.administrator:
            await i.response.send_message("管理者専用です。",ephemeral=True);return False
        return True

    @discord.ui.button(label="🗑 削除を実行",style=discord.ButtonStyle.danger,custom_id="casino_v2_delete_confirm")
    async def confirm(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True)
        import setup_service as _ss  # 循環importを避けるため遅延import
        deleted=await _ss.delete_v2_structure(i.guild)
        text=(
            "✅ Discord側のカテゴリ・チャンネル・パネルを削除しました。\n"
            "（CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータは保持されています）\n"
            + ("削除: " + ", ".join(deleted) if deleted else "削除対象は見つかりませんでした。")
        )
        await i.followup.send(text,ephemeral=True)
        for child in self.children:child.disabled=True
        self.stop()

    @discord.ui.button(label="キャンセル",style=discord.ButtonStyle.secondary,custom_id="casino_v2_delete_cancel")
    async def cancel(self,i,b):
        await i.response.send_message("キャンセルしました。",ephemeral=True)
        for child in self.children:child.disabled=True
        self.stop()
