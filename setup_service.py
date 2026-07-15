import discord
from casino_db import map_get, map_set, map_clear, pool, games
from views import (
    CasinoAdminView, CasinoLobbyView, DirectGamePanel, DailyPanel,
    LotteryLaunchView, LotoLaunchView, DIRECT_GAME_INFO,
    ranking_embed, emb, GOLD
)

PUBLIC_CAT="🎰 PAL CASINO"
ADMIN_CAT="🔒 CASINO ADMIN"

BASE_PUBLIC=[
    ("guide","📌｜casino-guide"),
    ("casino","🎰｜casino"),
    ("ranking","🏆｜casino-ranking"),
    ("big_win","🔥｜big-win"),
    ("status","📢｜casino-status"),
]
ADMIN=[
    ("admin","⚙️｜casino-admin"),
    ("log","📖｜casino-log"),
    ("alert","🚨｜casino-alert"),
]
GAME_CHANNELS=[
    ("slot","🎰｜slot","SLOT3"),
    ("scratch","🎟️｜scratch","SCRATCH"),
    ("blackjack","🃏｜blackjack","BLACKJACK"),
    ("roulette","🎡｜roulette","ROULETTE"),
    ("mines","💣｜mines","MINES"),
    ("chinchiro","🎲｜chinchiro","CHINCHIRO"),
    ("chohan","🎴｜chohan","CHOHAN"),
    ("coin","🪙｜coin","COIN"),
    ("highlow","📈｜highlow","HIGHLOW"),
    ("crash","🚀｜crash","CRASH"),
]

async def _upsert_map(key,ch):
    await map_set(key,ch.id)

async def _get_or_create_text(guild,category,name,map_key,locked=False):
    ch=discord.utils.get(category.text_channels,name=name)
    if not ch:
        overwrites=None
        if locked:
            overwrites={
                guild.default_role:discord.PermissionOverwrite(view_channel=True,send_messages=False),
                guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,manage_messages=True),
            }
        if overwrites is None:
            ch=await guild.create_text_channel(name,category=category)
        else:
            ch=await guild.create_text_channel(name,category=category,overwrites=overwrites)
    await _upsert_map(map_key,ch)
    return ch

async def _clear_bot_messages(ch,guild):
    async for msg in ch.history(limit=100):
        if guild.me and msg.author.id==guild.me.id:
            try:
                await msg.delete()
            except (discord.Forbidden,discord.NotFound,discord.HTTPException):
                pass

async def ensure_structure(guild):
    pub=discord.utils.get(guild.categories,name=PUBLIC_CAT)
    if not pub:
        pub=await guild.create_category(PUBLIC_CAT)

    admin_overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False)}
    adm=discord.utils.get(guild.categories,name=ADMIN_CAT)
    if not adm:
        adm=await guild.create_category(ADMIN_CAT,overwrites=admin_overwrites)

    made={}
    for key,name in BASE_PUBLIC:
        made[key]=await _get_or_create_text(guild,pub,name,key,locked=(key=="casino"))
    for key,name in ADMIN:
        made[key]=await _get_or_create_text(guild,adm,name,key,locked=False)

    for key,name,_game in GAME_CHANNELS:
        made[key]=await _get_or_create_text(guild,pub,name,key,locked=True)

    made["daily_gacha"]=await _get_or_create_text(guild,pub,"🎁｜daily-gacha","daily_gacha",locked=True)
    made["lottery"]=await _get_or_create_text(guild,pub,"🎫｜lottery","lottery",locked=True)
    made["loto6"]=await _get_or_create_text(guild,pub,"🔢｜loto6","loto6",locked=True)
    made["casino_live"]=await _get_or_create_text(guild,pub,"📺｜casino-live","casino_live",locked=True)
    return made

async def install_direct_game_panels(guild,category=None):
    chs=await ensure_structure(guild)

    for map_key,_name,key in GAME_CHANNELS:
        ch=chs[map_key]
        await _clear_bot_messages(ch,guild)
        title,desc=DIRECT_GAME_INFO[key]
        await ch.send(
            embed=emb(title,desc+"\n\n**遊び方**\n下の「🎮 プレイ」から開始。BETや選択は本人だけに表示されます。\n結果は 📺｜casino-live にも公開されます。",GOLD),
            view=DirectGamePanel(key)
        )

    daily=chs["daily_gacha"]
    await _clear_bot_messages(daily,guild)
    await daily.send(
        embed=emb("🎁 1日1回ガチャ","参加費 **500 CHIP**\n\n550：81%\n1,000：10%\n1,500：5%\n3,000：3%\n-10,000：0.999%\n100,000：0.001%",GOLD),
        view=DailyPanel()
    )

    lottery=chs["lottery"]
    await _clear_bot_messages(lottery,guild)
    await lottery.send(
        embed=emb("🎫 PAL 宝くじ","1枚 **500 CHIP**\n\n**どんなゲーム？**\n購入すると「組」と「6桁番号」が発行され、抽選番号との一致で等級が決まります。\n**01～100組 / 100000～199999番**\n1等 **1,000,000,000 CHIP**\n購入後は **📖 マイ宝くじ** から券・当選結果・次回抽選を確認できます。",GOLD),
        view=LotteryLaunchView()
    )

    loto=chs["loto6"]
    await _clear_bot_messages(loto,guild)
    await loto.send(
        embed=emb("🔢 ロト6","1口 **500 CHIP**\n\n**どんなゲーム？**\n1～43から異なる6数字を選び、抽選された本数字との一致数で当選が決まります。\n数字選択 / クイックピック\n購入後は **📖 マイロト6** から数字・当選結果・次回抽選・キャリーを確認できます。",GOLD),
        view=LotoLaunchView()
    )
    return chs

async def build_status_embed(guild):
    rows=await games()
    lines=[]
    for r in rows:
        key=r["game_key"]
        if key in ("LOTTERY","LOTO6"):
            map_key="lottery" if key=="LOTTERY" else "loto6"
        else:
            matches=[mk for mk,_n,gk in GAME_CHANNELS if gk==key]
            if not matches:continue
            map_key=matches[0]
        cid=await map_get(map_key)
        is_open=bool(r["enabled"] and r["implemented"])
        line=f"{'🟢 営業中' if is_open else '🔴 休止中'}｜**{r['display_name']}**"
        if is_open and cid:line+=f"\n↳ <#{int(cid)}>"
        lines.append(line)
    active=sum(1 for r in rows if r["enabled"] and r["implemented"])
    return emb("🟢 PAL CASINO｜営業案内" if active else "🔴 PAL CASINO｜営業休止",
      "現在のゲーム営業状況です。\n営業中はチャンネル名を押すと直接移動できます。\n\n"+"\n\n".join(lines),
      0x2ECC71 if active else 0xE74C3C)

async def refresh_status_panel(guild):
    cid=await map_get("status")
    ch=guild.get_channel(int(cid)) if cid else None
    if not ch:return

    embed=await build_status_embed(guild)
    mid=await map_get("status_message")
    msg=None

    if mid:
        try:
            msg=await ch.fetch_message(int(mid))
        except (discord.NotFound,discord.Forbidden,discord.HTTPException):
            msg=None

    if msg:
        await msg.edit(embed=embed)
    else:
        msg=await ch.send(embed=embed)
        await map_set("status_message",msg.id)


async def install_panels(guild):
    chs=await install_direct_game_panels(guild)

    await _clear_bot_messages(chs["guide"],guild)
    await chs["guide"].send(embed=emb(
        "🎰 PAL CASINO GUIDE",
        "遊びたいゲームの専用チャンネルを開いて固定パネルから直接プレイ。\n"
        "BET・操作・本人結果はその場で本人だけに表示。\n"
        "ゲーム結果は 📺｜casino-live にも自動公開。\n"
        "CHIP残高・履歴・プロフィールは 🎰｜casino で確認できます。",
        GOLD
    ))

    await _clear_bot_messages(chs["casino"],guild)
    await chs["casino"].send(
        embed=emb("🎰 PAL CASINO｜LOBBY","残高・履歴・プロフィール確認用。\nゲームは各専用チャンネルの固定パネルから直接プレイできます。",GOLD),
        view=CasinoLobbyView()
    )

    await _clear_bot_messages(chs["ranking"],guild)
    await chs["ranking"].send(embed=await ranking_embed())

    await refresh_status_panel(guild)

    await _clear_bot_messages(chs["admin"],guild)
    await chs["admin"].send(embed=emb("🎰 PAL CASINO ADMIN","管理者用CASINOパネル",GOLD),view=CasinoAdminView())
    return chs

async def delete_structure(guild):
    keys=[k for k,_ in BASE_PUBLIC+ADMIN]+[k for k,_,_ in GAME_CHANNELS]+["daily_gacha","lottery","loto6","casino_live"]
    ids=[]
    for key in keys:
        cid=await map_get(key)
        if cid:
            ids.append(int(cid))
    for cid in set(ids):
        ch=guild.get_channel(cid)
        if ch:
            try:
                await ch.delete(reason="PAL CASINO structure delete")
            except discord.HTTPException:
                pass
    for name in (PUBLIC_CAT,ADMIN_CAT):
        cat=discord.utils.get(guild.categories,name=name)
        if cat and not cat.channels:
            try:
                await cat.delete(reason="PAL CASINO structure delete")
            except discord.HTTPException:
                pass
    await map_clear()
