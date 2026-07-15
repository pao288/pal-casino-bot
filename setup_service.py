import discord
from casino_db import map_get,map_set,map_clear
from views import CasinoPanelView,CasinoAdminView,ranking_embed,emb

PUBLIC_CAT="🎰 PAL CASINO"
ADMIN_CAT="🔒 CASINO ADMIN"
PUBLIC=[
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

async def _panel_channel(guild,category,name,map_key):
    ch=discord.utils.get(guild.text_channels,name=name)
    if not ch:
        overwrites={
            guild.default_role:discord.PermissionOverwrite(view_channel=True,send_messages=False),
            guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,manage_messages=True),
        }
        ch=await guild.create_text_channel(name,category=category,overwrites=overwrites)
    await pool().execute("""INSERT INTO casino.channel_map(map_key,channel_id) VALUES($1,$2)
      ON CONFLICT(map_key) DO UPDATE SET channel_id=EXCLUDED.channel_id""",map_key,str(ch.id))
    return ch

async def install_direct_game_panels(guild,category):
    created=[]
    for map_key,name,key in GAME_CHANNELS:
        ch=await _panel_channel(guild,category,name,map_key)
        async for msg in ch.history(limit=100):
            if msg.author.id==guild.me.id:
                try: await msg.delete()
                except: pass
        title,desc=DIRECT_GAME_INFO[key]
        await ch.send(embed=emb(title,desc+"\\n\\n操作と結果はその場で本人だけに表示。結果は `📺｜casino-live` にも自動公開されます。",GOLD),view=DirectGamePanel(key))
        created.append(ch)

    daily=await _panel_channel(guild,category,"🎁｜daily-gacha","daily_gacha")
    async for msg in daily.history(limit=100):
        if msg.author.id==guild.me.id:
            try: await msg.delete()
            except: pass
    await daily.send(embed=emb("🎁 1日1回ガチャ","500 CHIPで1日1回。\\n550 / 1,000 / 1,500 / 3,000 / -10,000 / 100,000 CHIP",GOLD),view=DailyPanel())

    lottery=await _panel_channel(guild,category,"🎫｜lottery","lottery")
    async for msg in lottery.history(limit=100):
        if msg.author.id==guild.me.id:
            try: await msg.delete()
            except: pass
    await lottery.send(embed=emb("🎫 PAL 宝くじ","1枚 500 CHIP\\n01～100組 / 100000～199999番\\n1等 1,000,000,000 CHIP",GOLD),view=LotteryLaunchView())

    loto=await _panel_channel(guild,category,"🔢｜loto6","loto6")
    async for msg in loto.history(limit=100):
        if msg.author.id==guild.me.id:
            try: await msg.delete()
            except: pass
    await loto.send(embed=emb("🔢 ロト6","1口 500 CHIP\\n1～43から6個\\n数字選択 / クイックピック",GOLD),view=LotoLaunchView())

    live=await _panel_channel(guild,category,"📺｜casino-live","casino_live")
    return created+[daily,lottery,loto,live]


async def ensure_structure(guild):
    pub=discord.utils.get(guild.categories,name=PUBLIC_CAT) or await guild.create_category(PUBLIC_CAT)
    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False)}
    adm=discord.utils.get(guild.categories,name=ADMIN_CAT) or await guild.create_category(ADMIN_CAT,overwrites=overwrites)
    made={}
    for key,name in PUBLIC:
        ch=discord.utils.get(pub.text_channels,name=name) or await guild.create_text_channel(name,category=pub)
        await map_set(key,ch.id);made[key]=ch
    for key,name in ADMIN:
        ch=discord.utils.get(adm.text_channels,name=name) or await guild.create_text_channel(name,category=adm)
        await map_set(key,ch.id);made[key]=ch
    return made

async def install_panels(guild):
    chs=await ensure_structure(guild)
    await chs["guide"].send(embed=emb("🎰 PAL CASINO GUIDE","PAL CASINOでは **CHIP** を使用します。\n\n🎮 ゲーム一覧からゲームを選択\n💰 BETは整数入力\n🏦 CHIP残高はPAL BANKと共通\n🏆 ランキング・BIG WIN・プレイ履歴に対応"))
    await chs["casino"].send(embed=emb("🎰 PAL CASINO","下のパネルからCASINOを利用できます。",0xF1C40F),view=CasinoPanelView())
    await chs["ranking"].send(embed=await ranking_embed())
    await chs["status"].send(embed=emb("🟢 PAL CASINO STATUS","**ONLINE**\n\n現在稼働中: 🎰 スロット / 🎟️ スクラッチ / 🃏 ブラックジャック / 🎡 ルーレット / 💣 マインズ / 🎲 チンチロ / 🎴 丁半 / 🪙 コイントス / 📈 ハイロー / 🚀 クラッシュ\nその他ゲーム: 🚧 順次公開",0x2ECC71))
    await chs["admin"].send(embed=emb("🎰 PAL CASINO ADMIN","管理者用CASINOパネル",0xF1C40F),view=CasinoAdminView())
    return chs

async def delete_structure(guild):
    ids=[]
    for key,_ in PUBLIC+ADMIN:
        cid=await map_get(key)
        if cid:ids.append(int(cid))
    for cid in ids:
        ch=guild.get_channel(cid)
        if ch:
            try:await ch.delete(reason="PAL CASINO structure delete")
            except discord.HTTPException:pass
    for name in (PUBLIC_CAT,ADMIN_CAT):
        cat=discord.utils.get(guild.categories,name=name)
        if cat and not cat.channels:
            try:await cat.delete(reason="PAL CASINO structure delete")
            except discord.HTTPException:pass
    await map_clear()
