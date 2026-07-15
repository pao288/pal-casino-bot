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
