import discord
from casino_db import map_get, map_set, map_clear, pool, games, V2_GAME_ROOM_MAP, setting
from views import (
    CasinoAdminView, CasinoLobbyView, DirectGamePanel, DailyPanel,
    LotteryLaunchView, LotoLaunchView, DIRECT_GAME_INFO,
    ranking_embed, emb, GOLD, ChipClaimView, CasinoShopView, GAME_NAMES,
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


# ═══════════════════════════════════════════════════════════════════════
# !casinosetup（新コマンド）: 🎰 PAL CASINO / 🎮 GAME の2カテゴリを自動構築する。
# 上記の旧ensure_structure/install_panels/delete_structure（!casinosetup_legacyの
# パネルから使われる）とは完全に独立しており、既存の動作には一切影響しない。
# ═══════════════════════════════════════════════════════════════════════
V2_MAIN_CAT_NAME="🎰 PAL CASINO"
V2_MAIN_CAT_KEY="v2_cat_main"
V2_GAME_CAT_NAME="🎮 GAME"
V2_GAME_CAT_KEY="v2_cat_game"

# (map_key, チャンネル名, トピック)
V2_MAIN_CHANNELS=[
    ("v2_casino","🎰｜カジノ","PAL CASINO｜カジノパネル・チップ受取・ショップ"),
    ("v2_announce","📢｜アナウンス","PAL CASINO｜宝くじ・ロト6抽選、イベント開始・終了、高額当選アナウンス"),
    ("v2_log","📜｜ログ","PAL CASINO｜管理操作・ゲーム設定変更・確率変更ログ"),
    ("v2_admin","🛠｜運営","PAL CASINO｜管理者専用コンソール"),
]

# (map_key, チャンネル名, ゲームキー) ※ GACHAはcasino.gamesテーブルに存在しない特別枠
V2_GAME_ROOMS=[
    ("v2_room_slot3","🎰｜スロット","SLOT3"),
    ("v2_room_scratch","🎟️｜スクラッチ","SCRATCH"),
    ("v2_room_blackjack","🃏｜ブラックジャック","BLACKJACK"),
    ("v2_room_roulette","🎲｜ルーレット","ROULETTE"),
    ("v2_room_mines","💣｜マインズ","MINES"),
    ("v2_room_chinchiro","🎲｜ダイス","CHINCHIRO"),
    ("v2_room_chohan","🎴｜丁半博打","CHOHAN"),
    ("v2_room_coin","🪙｜コイントス","COIN"),
    ("v2_room_highlow","📈｜ハイアンドロー","HIGHLOW"),
    ("v2_room_crash","🚀｜クラッシュ","CRASH"),
    ("v2_room_lottery","🎫｜宝くじ","LOTTERY"),
    ("v2_room_loto6","🎫｜ロト6","LOTO6"),
    ("v2_room_gacha","🎁｜ガチャ","GACHA"),
]


def _v2_overwrites(guild):
    # 一般ユーザー: 閲覧〇・送信×・添付×・リアクション×・スレッド× / BOT・管理者(Administrator権限)は全許可
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=False, add_reactions=False,
            attach_files=False, create_public_threads=False,
            create_private_threads=False, send_messages_in_threads=False,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, add_reactions=True,
            attach_files=True, embed_links=True, manage_messages=True,
            manage_channels=True, create_public_threads=True,
            create_private_threads=True, send_messages_in_threads=True,
        ),
    }


async def _ensure_v2_category(guild,name,map_key,overwrites,counts):
    cid=await map_get(map_key)
    cat=guild.get_channel(int(cid)) if cid else None
    if isinstance(cat,discord.CategoryChannel):
        try:await cat.edit(overwrites=overwrites)
        except discord.HTTPException:pass
        counts["reused"]+=1
        await map_set(map_key,cat.id)
        return cat
    had_id=bool(cid)
    found=discord.utils.get(guild.categories,name=name)
    if found:
        try:await found.edit(overwrites=overwrites)
        except discord.HTTPException:pass
        await map_set(map_key,found.id)
        counts["restored" if had_id else "reused"]+=1
        return found
    new_cat=await guild.create_category(name,overwrites=overwrites,reason="PAL CASINO v2 setup")
    await map_set(map_key,new_cat.id)
    counts["restored" if had_id else "created"]+=1
    return new_cat


async def _ensure_v2_channel(guild,category,name,topic,map_key,overwrites,counts):
    cid=await map_get(map_key)
    ch=guild.get_channel(int(cid)) if cid else None
    if isinstance(ch,discord.TextChannel):
        try:
            if ch.category_id!=category.id:await ch.edit(category=category)
            await ch.edit(overwrites=overwrites)
        except discord.HTTPException:pass
        counts["reused"]+=1
        await map_set(map_key,ch.id)
        return ch
    had_id=bool(cid)
    found=discord.utils.get(category.text_channels,name=name)
    if found:
        try:await found.edit(overwrites=overwrites)
        except discord.HTTPException:pass
        await map_set(map_key,found.id)
        counts["restored" if had_id else "reused"]+=1
        return found
    new_ch=await guild.create_text_channel(name,category=category,topic=topic,overwrites=overwrites,reason="PAL CASINO v2 setup")
    await map_set(map_key,new_ch.id)
    counts["restored" if had_id else "created"]+=1
    return new_ch


async def ensure_v2_structure(guild):
    """!casinosetup 本体。既存のカテゴリ／チャンネルは再利用し、不足分（削除されたもの）だけ復旧する。
    DB（CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータ）には一切触れない。"""
    counts={"created":0,"restored":0,"reused":0}
    overwrites=_v2_overwrites(guild)
    main_cat=await _ensure_v2_category(guild,V2_MAIN_CAT_NAME,V2_MAIN_CAT_KEY,overwrites,counts)
    game_cat=await _ensure_v2_category(guild,V2_GAME_CAT_NAME,V2_GAME_CAT_KEY,overwrites,counts)

    channels={}
    for map_key,name,topic in V2_MAIN_CHANNELS:
        channels[map_key]=await _ensure_v2_channel(guild,main_cat,name,topic,map_key,overwrites,counts)
    for map_key,name,_game_key in V2_GAME_ROOMS:
        topic=f"PAL CASINO｜{name} 専用チャンネル（結果もここに公開されます）"
        channels[map_key]=await _ensure_v2_channel(guild,game_cat,name,topic,map_key,overwrites,counts)

    return main_cat,game_cat,channels,counts


async def get_v2_channels(guild):
    """既に構築済みのv2チャンネルのみを取得する（新規作成はしない）。"""
    channels={}
    for map_key,_name,_topic in V2_MAIN_CHANNELS:
        cid=await map_get(map_key)
        ch=guild.get_channel(int(cid)) if cid else None
        if ch:channels[map_key]=ch
    for map_key,_name,_game_key in V2_GAME_ROOMS:
        cid=await map_get(map_key)
        ch=guild.get_channel(int(cid)) if cid else None
        if ch:channels[map_key]=ch
    return channels


async def _ensure_panel_message(channel,embed,view,map_key):
    mid=await map_get(map_key)
    if mid:
        try:
            msg=await channel.fetch_message(int(mid))
            await msg.edit(embed=embed,view=view)
            return msg
        except (discord.NotFound,discord.Forbidden,discord.HTTPException,ValueError):
            pass
    msg=await channel.send(embed=embed,view=view)
    await map_set(map_key,msg.id)
    return msg


async def install_v2_panels(guild,channels):
    """🎰｜カジノにカジノパネル／チップ受取パネル／カジノショップパネル、🛠｜運営に管理パネル、
    GAMEカテゴリの各チャンネルに対応するゲームパネルを設置する。既に存在する場合は再利用（編集）する。"""
    casino_ch=channels.get("v2_casino")
    if casino_ch:
        await _ensure_panel_message(
            casino_ch,
            emb("🎰 PAL CASINO｜カジノパネル","残高・履歴・プロフィール確認はここから。\nゲームは 🎮 GAME カテゴリの各専用チャンネルで直接プレイできます。",GOLD),
            CasinoLobbyView(),"v2_msg_casino",
        )
        await _ensure_panel_message(
            casino_ch,
            emb("🎁 チップ受取パネル",f"1日1回、無料で **{await setting('chip_claim_amount','300')} CHIP** を受け取れます。",GOLD),
            ChipClaimView(),"v2_msg_chipclaim",
        )
        await _ensure_panel_message(
            casino_ch,
            emb("🛍️ カジノショップ",f"👑 **VIP会員権** — **{int(await setting('vip_price','50000')):,} CHIP**\n購入するとVIP限定ゲームが解放されます。",GOLD),
            CasinoShopView(),"v2_msg_shop",
        )

    admin_ch=channels.get("v2_admin")
    if admin_ch:
        await _ensure_panel_message(
            admin_ch,
            emb("🎰 PAL CASINO ADMIN","管理者用CASINOパネル（♻️システム復旧・📢パネル再設置・🗑システム削除ボタン付き）",GOLD),
            CasinoAdminView(),"v2_msg_admin",
        )

    for map_key,_name,game_key in V2_GAME_ROOMS:
        ch=channels.get(map_key)
        if not ch:continue
        if game_key=="GACHA":
            await _ensure_panel_message(
                ch,
                emb("🎁 1日1回ガチャ","参加費 **500 CHIP**\n\n550：81%\n1,000：10%\n1,500：5%\n3,000：3%\n-10,000：0.999%\n100,000：0.001%",GOLD),
                DailyPanel(),f"v2_msg_{map_key}",
            )
        elif game_key=="LOTTERY":
            await _ensure_panel_message(
                ch,
                emb("🎫 PAL 宝くじ","1枚 **500 CHIP**\n\n**どんなゲーム？**\n購入すると「組」と「6桁番号」が発行され、抽選番号との一致で等級が決まります。\n**01～100組 / 100000～199999番**\n1等 **1,000,000,000 CHIP**\n抽選結果は 📢｜アナウンス で告知されます。",GOLD),
                LotteryLaunchView(),f"v2_msg_{map_key}",
            )
        elif game_key=="LOTO6":
            await _ensure_panel_message(
                ch,
                emb("🔢 ロト6","1口 **500 CHIP**\n\n**どんなゲーム？**\n1～43から異なる6数字を選び、抽選された本数字との一致数で当選が決まります。\n数字選択 / クイックピック\n抽選結果は 📢｜アナウンス で告知されます。",GOLD),
                LotoLaunchView(),f"v2_msg_{map_key}",
            )
        else:
            title,desc=DIRECT_GAME_INFO.get(game_key,(GAME_NAMES.get(game_key,game_key),""))
            await _ensure_panel_message(
                ch,
                emb(title,desc+"\n\n**遊び方**\n下の「🎮 プレイ」から開始。BETや選択は本人だけに表示されます。\n結果はこのチャンネルに公開されます。",GOLD),
                DirectGamePanel(game_key),f"v2_msg_{map_key}",
            )


async def delete_v2_structure(guild):
    """Discord側（🎰 PAL CASINO／🎮 GAMEのカテゴリ・チャンネル・パネル）のみを削除する。
    チャンネルIDの記録（channel_map）はあえて消さずに残す。次回!casinosetup実行時に
    「そのIDのチャンネルが存在しない＝復旧対象」として検知させ、不足分だけ自動復元するため。
    CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータは削除しない。"""
    deleted=[]
    channel_keys=[k for k,_n,_t in V2_MAIN_CHANNELS]+[k for k,_n,_g in V2_GAME_ROOMS]
    for map_key in channel_keys:
        cid=await map_get(map_key)
        if cid:
            ch=guild.get_channel(int(cid))
            if ch:
                try:
                    await ch.delete(reason="PAL CASINO v2 system delete (Discord側のみ)")
                    deleted.append(ch.name)
                except discord.HTTPException:
                    pass

    for cat_key,cat_name in ((V2_MAIN_CAT_KEY,V2_MAIN_CAT_NAME),(V2_GAME_CAT_KEY,V2_GAME_CAT_NAME)):
        cid=await map_get(cat_key)
        cat=guild.get_channel(int(cid)) if cid else discord.utils.get(guild.categories,name=cat_name)
        if cat:
            try:
                await cat.delete(reason="PAL CASINO v2 system delete (Discord側のみ)")
                deleted.append(cat.name)
            except discord.HTTPException:
                pass

    return deleted
