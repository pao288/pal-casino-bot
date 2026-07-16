import discord
from casino_db import map_get, map_set, map_clear, pool, games, v2_room_map_key, setting
from views import (
    CasinoAdminView, CasinoLobbyView, DirectGamePanel, DailyPanel,
    LotteryLaunchView, LotoLaunchView, DIRECT_GAME_INFO,
    ranking_embed, emb, GOLD, CasinoShopView, GAME_NAMES,
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
    ("v2_casino","🎰｜カジノ","PAL CASINO｜カジノパネル・ショップ"),
    ("v2_results","📺｜プレイ結果","PAL CASINO｜各ゲームのプレイ結果をここに一括表示"),
    ("v2_status","🟢｜営業状況","PAL CASINO｜カジノが営業中かどうかの状況パネル（ゲームごとの営業状況）"),
    ("v2_announce","📢｜アナウンス","PAL CASINO｜宝くじ・ロト6抽選、イベント開始・終了、高額当選アナウンス"),
    ("v2_log","📜｜ログ","PAL CASINO｜管理操作・ゲーム設定変更・確率変更・VIP購入ログ（ゲーム結果は📺｜プレイ結果へ）"),
    ("v2_admin","🛠｜運営","PAL CASINO｜管理者専用コンソール"),
]


def _split_display_name(display_name):
    """"🎰 3リールスロット" のような表示名を絵文字とゲーム名に分割する。"""
    parts=str(display_name).split(" ",1)
    if len(parts)==2:
        return parts[0],parts[1]
    return "🎮",str(display_name)


async def _build_game_rooms():
    """GAMEカテゴリのチャンネル一覧を casino.games（ゲーム登録一覧）から動的に組み立てる。
    新しいゲームを casino.games に登録するだけで、このファイルを書き換えなくても専用チャンネルが自動生成される。
    未実装（implemented=FALSE）のゲームも「🚧準備中」チャンネルとして作成する。
    戻り値: [(map_key, チャンネル名, ゲームキー, 実装済みか), ...]
    ※ GACHA（1日1回ガチャ）は casino.games に存在しない特別枠のため固定で追加する。"""
    rooms=[]
    for r in await games():
        key=r["game_key"]
        emoji,name=_split_display_name(r["display_name"])
        rooms.append((v2_room_map_key(key),f"{emoji}｜{name}",key,bool(r["implemented"])))
    rooms.append((v2_room_map_key("GACHA"),"🎁｜ガチャ","GACHA",True))
    return rooms


async def build_v2_status_embed(guild):
    """🟢｜営業状況 に表示する、カジノ全体・ゲームごとの営業中/休止中/準備中の一覧を作る。
    📢｜アナウンスとは別チャンネルで、営業状況だけを常時確認できるようにするためのもの。"""
    rows=await games()
    lines=[]
    for r in rows:
        cid=await map_get(v2_room_map_key(r["game_key"]))
        if not r["implemented"]:
            line=f"🚧 準備中｜**{r['display_name']}**"
            if cid:line+=f"\n↳ <#{int(cid)}>"
            lines.append(line)
            continue
        is_open=bool(r["enabled"])
        line=f"{'🟢 営業中' if is_open else '🔴 休止中'}｜**{r['display_name']}**"
        if is_open and cid:line+=f"\n↳ <#{int(cid)}>"
        lines.append(line)
    gacha_cid=await map_get(v2_room_map_key("GACHA"))
    if gacha_cid:
        lines.append(f"🟢 営業中｜**🎁 1日1回ガチャ**\n↳ <#{int(gacha_cid)}>")
    active=sum(1 for r in rows if r["enabled"] and r["implemented"])
    return emb(
        "🟢 PAL CASINO｜営業中" if active else "🔴 PAL CASINO｜営業休止",
        "現在のカジノ営業状況です。\n営業中のゲームはチャンネル名を押すと直接移動できます。\n\n"+"\n\n".join(lines),
        0x2ECC71 if active else 0xE74C3C,
    )


async def refresh_v2_status_panel(guild):
    """🟢｜営業状況 の営業案内パネルを最新の状態に更新する（無ければ何もしない）。"""
    cid=await map_get("v2_status")
    ch=guild.get_channel(int(cid)) if cid else None
    if not ch:
        return
    embed=await build_v2_status_embed(guild)
    await _ensure_panel_message(ch,embed,None,"v2_msg_status")


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


# ═══════════════════════════════════════════════════════════════════════
# VIP購入者専用エリア: 👑VIP（VIPルーム）／🎮VIP GAME（準備中）
# @everyoneは非表示、👑VIPロール保持者のみ閲覧可。BOT・管理者(Administrator権限)は常時操作可能。
# ═══════════════════════════════════════════════════════════════════════
VIP_ROLE_NAME="👑 VIP"
VIP_ROLE_KEY="v2_vip_role"
V2_VIP_CAT_NAME="👑 VIP"
V2_VIP_CAT_KEY="v2_cat_vip"
V2_VIP_GAME_CAT_NAME="🎮 VIP GAME"
V2_VIP_GAME_CAT_KEY="v2_cat_vipgame"

# (map_key, チャンネル名, トピック)
V2_VIP_CHANNELS=[
    ("v2_vip_room","💬｜VIPルーム","PAL CASINO｜VIP会員専用ラウンジ"),
]
V2_VIP_GAME_CHANNELS=[
    ("v2_vip_placeholder","🚧｜準備中","PAL CASINO｜VIP専用ゲームは現在準備中です"),
]


def _vip_lounge_overwrites(guild,vip_role):
    # VIPルーム: VIPロール保持者は自由に会話できるラウンジ
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        vip_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, add_reactions=True,
            attach_files=True, create_public_threads=True,
            create_private_threads=True, send_messages_in_threads=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, add_reactions=True,
            attach_files=True, embed_links=True, manage_messages=True,
            manage_channels=True, create_public_threads=True,
            create_private_threads=True, send_messages_in_threads=True,
        ),
    }


def _vip_game_overwrites(guild,vip_role):
    # VIP GAME: 他のGAMEチャンネル同様、閲覧のみ（パネルはBOTが操作）。現状は準備中の案内のみ表示。
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        vip_role: discord.PermissionOverwrite(
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


async def ensure_vip_role(guild):
    """「👑 VIP」ロールを用意し、casino.user_state.vip=TRUEの全員に自動付与（再同期）する。
    ロールが手動で消された場合も、次回呼び出し時に自動で作り直す。"""
    rid=await map_get(VIP_ROLE_KEY)
    role=guild.get_role(int(rid)) if rid else None
    if role is None:
        role=discord.utils.get(guild.roles,name=VIP_ROLE_NAME)
    if role is None:
        role=await guild.create_role(
            name=VIP_ROLE_NAME,color=discord.Color.gold(),mentionable=False,
            reason="PAL CASINO VIP role",
        )
    await map_set(VIP_ROLE_KEY,role.id)

    # DB側でVIP扱いの全ユーザーへロールを再同期する（役職だけ消えていても復元される）。
    try:
        vip_ids=await pool().fetch("SELECT user_id FROM casino.user_state WHERE vip=TRUE")
        for row in vip_ids:
            member=guild.get_member(int(row["user_id"]))
            if member and role not in member.roles:
                try:
                    await member.add_roles(role,reason="PAL CASINO VIP role sync")
                except discord.HTTPException:
                    pass
    except Exception:
        pass
    return role


async def ensure_vip_structure(guild):
    """👑VIP（VIPルーム）／🎮VIP GAME（準備中）を用意する。既存は再利用し、不足分のみ復旧する。"""
    counts={"created":0,"restored":0,"reused":0}
    vip_role=await ensure_vip_role(guild)
    lounge_ow=_vip_lounge_overwrites(guild,vip_role)
    game_ow=_vip_game_overwrites(guild,vip_role)

    vip_cat=await _ensure_v2_category(guild,V2_VIP_CAT_NAME,V2_VIP_CAT_KEY,lounge_ow,counts)
    vip_game_cat=await _ensure_v2_category(guild,V2_VIP_GAME_CAT_NAME,V2_VIP_GAME_CAT_KEY,game_ow,counts)

    channels={}
    for map_key,name,topic in V2_VIP_CHANNELS:
        channels[map_key]=await _ensure_v2_channel(guild,vip_cat,name,topic,map_key,lounge_ow,counts)
    for map_key,name,topic in V2_VIP_GAME_CHANNELS:
        channels[map_key]=await _ensure_v2_channel(guild,vip_game_cat,name,topic,map_key,game_ow,counts)

    return vip_role,vip_cat,vip_game_cat,channels,counts


async def install_vip_panels(channels):
    """VIPルームの案内メッセージと、VIP GAMEの「準備中」案内を設置する。"""
    room=channels.get("v2_vip_room")
    if room:
        await _ensure_panel_message(
            room,
            emb("👑 VIPルームへようこそ","VIP会員限定のラウンジです。自由にご歓談ください。",GOLD),
            None,"v2_msg_viproom",
        )
    placeholder=channels.get("v2_vip_placeholder")
    if placeholder:
        await _ensure_panel_message(
            placeholder,
            emb("🚧 VIP限定ゲーム 準備中","近日公開予定です。楽しみにお待ちください。",GOLD),
            None,"v2_msg_vipgame",
        )


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
    GAMEカテゴリのチャンネルは casino.games（ゲーム登録一覧）から動的に組み立てるため、
    新しいゲームを登録するだけでこの関数を書き換えずに専用チャンネルが増える。
    DB（CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータ）には一切触れない。"""
    counts={"created":0,"restored":0,"reused":0,"game_channels":0}
    overwrites=_v2_overwrites(guild)
    main_cat=await _ensure_v2_category(guild,V2_MAIN_CAT_NAME,V2_MAIN_CAT_KEY,overwrites,counts)
    game_cat=await _ensure_v2_category(guild,V2_GAME_CAT_NAME,V2_GAME_CAT_KEY,overwrites,counts)

    channels={}
    for map_key,name,topic in V2_MAIN_CHANNELS:
        channels[map_key]=await _ensure_v2_channel(guild,main_cat,name,topic,map_key,overwrites,counts)

    game_rooms=await _build_game_rooms()
    for map_key,name,_game_key,implemented in game_rooms:
        topic=f"PAL CASINO｜{name} 専用チャンネル（結果は📺｜プレイ結果に公開されます）" if implemented else f"PAL CASINO｜{name} は準備中です"
        channels[map_key]=await _ensure_v2_channel(guild,game_cat,name,topic,map_key,overwrites,counts)
    counts["game_channels"]=len(game_rooms)

    # VIP専用エリア（👑VIP／🎮VIP GAME）も合わせて用意する（不足していれば新規作成、既存は再利用）。
    vip_role,_vip_cat,_vip_game_cat,vip_channels,vip_counts=await ensure_vip_structure(guild)
    channels.update(vip_channels)
    for k in ("created","restored","reused"):
        counts[k]+=vip_counts[k]

    return main_cat,game_cat,vip_role,channels,counts


async def get_v2_channels(guild):
    """既に構築済みのv2チャンネルのみを取得する（新規作成はしない）。"""
    channels={}
    for map_key,_name,_topic in V2_MAIN_CHANNELS:
        cid=await map_get(map_key)
        ch=guild.get_channel(int(cid)) if cid else None
        if ch:channels[map_key]=ch
    for map_key,_name,_game_key,_impl in await _build_game_rooms():
        cid=await map_get(map_key)
        ch=guild.get_channel(int(cid)) if cid else None
        if ch:channels[map_key]=ch
    for map_key,_name,_topic in V2_VIP_CHANNELS+V2_VIP_GAME_CHANNELS:
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
    """🎰｜カジノにカジノパネル／カジノショップパネル、🟢｜営業状況に営業案内パネル、🛠｜運営に管理パネル、
    GAMEカテゴリの各チャンネルに対応するゲームパネルを設置する。既に存在する場合は再利用（編集）する。"""
    casino_ch=channels.get("v2_casino")
    if casino_ch:
        await _ensure_panel_message(
            casino_ch,
            emb("🎰 PAL CASINO｜カジノパネル","残高・履歴・プロフィール確認はここから。\nゲームは 🎮 GAME カテゴリの各専用チャンネルで直接プレイでき、結果は 📺｜プレイ結果 に公開されます。",GOLD),
            CasinoLobbyView(),"v2_msg_casino",
        )
        await _ensure_panel_message(
            casino_ch,
            emb("🛍️ カジノショップ",f"👑 **VIP会員権** — **{int(await setting('vip_price','50000')):,} CHIP**\n購入するとVIP限定ゲームが解放されます。",GOLD),
            CasinoShopView(),"v2_msg_shop",
        )

    await refresh_v2_status_panel(guild)

    admin_ch=channels.get("v2_admin")
    if admin_ch:
        await _ensure_panel_message(
            admin_ch,
            emb("🎰 PAL CASINO ADMIN","管理者用CASINOパネル（♻️システム復旧・📢パネル再設置・🗑システム削除ボタン付き）",GOLD),
            CasinoAdminView(),"v2_msg_admin",
        )

    for map_key,name,game_key,implemented in await _build_game_rooms():
        ch=channels.get(map_key)
        if not ch:continue
        if not implemented:
            await _ensure_panel_message(
                ch,
                emb(f"🚧 {name} 準備中",f"**{GAME_NAMES.get(game_key,name)}** は近日公開予定です。楽しみにお待ちください。",GOLD),
                None,f"v2_msg_{map_key}",
            )
        elif game_key=="GACHA":
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
                emb(title,desc+"\n\n**遊び方**\n下の「🎮 プレイ」から開始。BETや選択は本人だけに表示されます。\n結果は 📺｜プレイ結果 に公開されます。",GOLD),
                DirectGamePanel(game_key),f"v2_msg_{map_key}",
            )

    await install_vip_panels(channels)


async def delete_v2_structure(guild):
    """Discord側（🎰 PAL CASINO／🎮 GAME／👑 VIP／🎮 VIP GAMEのカテゴリ・チャンネル・パネル）のみを削除する。
    チャンネルIDの記録（channel_map）はあえて消さずに残す。次回!casinosetup実行時に
    「そのIDのチャンネルが存在しない＝復旧対象」として検知させ、不足分だけ自動復元するため。
    CHIP・ゲームデータ・ランキング・宝くじ・ロト6・確率・各ゲーム設定・全ユーザーデータ・VIP資格(DB)は削除しない。
    ※「👑 VIP」ロール自体もあえて削除しない（削除するとVIP会員の見た目上の印が消えてしまうため）。
      次回 !casinosetup 実行時に、DB上VIPの全員へロールが自動で再同期される。"""
    deleted=[]
    channel_keys=(
        [k for k,_n,_t in V2_MAIN_CHANNELS]
        + [k for k,_n,_g,_i in await _build_game_rooms()]
        + [k for k,_n,_t in V2_VIP_CHANNELS]
        + [k for k,_n,_t in V2_VIP_GAME_CHANNELS]
    )
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

    category_defs=(
        (V2_MAIN_CAT_KEY,V2_MAIN_CAT_NAME),
        (V2_GAME_CAT_KEY,V2_GAME_CAT_NAME),
        (V2_VIP_CAT_KEY,V2_VIP_CAT_NAME),
        (V2_VIP_GAME_CAT_KEY,V2_VIP_GAME_CAT_NAME),
    )
    for cat_key,cat_name in category_defs:
        cid=await map_get(cat_key)
        cat=guild.get_channel(int(cid)) if cid else discord.utils.get(guild.categories,name=cat_name)
        if cat:
            # 追跡外のチャンネルが万一残っていても削除漏れが無いよう、カテゴリ内を総ざらいする。
            for ch in list(cat.channels):
                try:
                    await ch.delete(reason="PAL CASINO v2 system delete (Discord側のみ)")
                    if ch.name not in deleted:deleted.append(ch.name)
                except discord.HTTPException:
                    pass
            try:
                await cat.delete(reason="PAL CASINO v2 system delete (Discord側のみ)")
                deleted.append(cat.name)
            except discord.HTTPException:
                pass

    return deleted
