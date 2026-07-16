import os, logging, discord
from discord.ext import commands, tasks
from casino_db import init_db
from bank_gateway_for_other_bots import init_bank_gateway
from views import (
    CasinoPanelView, CasinoAdminView, CasinoLobbyView, DirectGamePanel, DailyPanel,
    LotteryLaunchView, LotoLaunchView, CasinoShopView,
    build_lottery_announce_embed, build_loto_announce_embed, _channel_by_map_keys,
)
from setup_service import (
    install_panels, ensure_structure, delete_structure, install_direct_game_panels, refresh_status_panel,
    ensure_v2_structure, install_v2_panels, delete_v2_structure, get_v2_channels, refresh_v2_status_panel,
)
from lottery_service import draw_lottery, draw_loto, ensure_lottery_draw, ensure_loto_draw, lottery_due, loto_due

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("pal_casino")
intents=discord.Intents.default()
intents.message_content=True
bot=commands.Bot(command_prefix="!",intents=intents)

class SetupView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def interaction_check(self,i):
        if not i.user.guild_permissions.administrator:
            await i.response.send_message("管理者専用です。",ephemeral=True);return False
        return True
    @discord.ui.button(label="🎰 CASINO構築",style=discord.ButtonStyle.success,custom_id="casino_setup_build")
    async def build(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);await install_panels(i.guild);await i.edit_original_response(content="✅ CASINO構築・パネル設置完了")
    @discord.ui.button(label="🔄 パネル再設置",style=discord.ButtonStyle.primary,custom_id="casino_setup_panels")
    async def panels(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);await install_panels(i.guild);await i.edit_original_response(content="✅ 固定パネルを再設置しました。")
    @discord.ui.button(label="🔧 チャンネル修復",style=discord.ButtonStyle.secondary,custom_id="casino_setup_repair")
    async def repair(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);await ensure_structure(i.guild);await i.edit_original_response(content="✅ CASINOチャンネル確認・修復完了")
    @discord.ui.button(label="🗑️ CASINO構成削除",style=discord.ButtonStyle.danger,custom_id="casino_setup_delete")
    async def delete(self,i,b):
        await i.response.defer(ephemeral=True,thinking=True);await delete_structure(i.guild);await i.edit_original_response(content="🗑️ CASINO構成を削除しました。DB記録とCHIP残高は保持されています。")

@tasks.loop(minutes=1)
async def lottery_auto_draw_loop():
    """宝くじ・ロト6の自動抽選。draw_at（購入受付開始から1週間後）を過ぎたOPEN中の回があれば、
    全員のチケットを一斉抽選し 📢｜アナウンス へ結果を送る。確率・当選ロジックは一切変更していない。"""
    for guild in bot.guilds:
        try:
            if await lottery_due():
                r=await draw_lottery()
                await ensure_lottery_draw()
                ch=await _channel_by_map_keys(guild,"v2_announce","status")
                if ch:await ch.send(embed=build_lottery_announce_embed(r))
                log.info("宝くじ自動抽選実行: 第%s回 (%s)",r["draw_no"],guild.name)
        except Exception:
            log.exception("宝くじ自動抽選エラー: %s",guild.name)
        try:
            if await loto_due():
                r=await draw_loto()
                await ensure_loto_draw()
                ch=await _channel_by_map_keys(guild,"v2_announce","status")
                if ch:await ch.send(embed=build_loto_announce_embed(r))
                log.info("ロト6自動抽選実行: 第%s回 (%s)",r["draw_no"],guild.name)
        except Exception:
            log.exception("ロト6自動抽選エラー: %s",guild.name)

@lottery_auto_draw_loop.before_loop
async def _before_lottery_auto_draw_loop():
    await bot.wait_until_ready()

@bot.event
async def setup_hook():
    await init_db()
    await init_bank_gateway()
    bot.add_view(CasinoAdminView())
    bot.add_view(CasinoLobbyView())
    for _key in ["SLOT3","SCRATCH","BLACKJACK","ROULETTE","MINES","CHINCHIRO","CHOHAN","COIN","HIGHLOW","CRASH"]:
        bot.add_view(DirectGamePanel(_key))
    bot.add_view(DailyPanel())
    bot.add_view(LotteryLaunchView())
    bot.add_view(LotoLaunchView())
    bot.add_view(CasinoShopView())
    bot.add_view(SetupView())
    if not lottery_auto_draw_loop.is_running():
        lottery_auto_draw_loop.start()
    log.info("DB・BANK Gateway接続完了")

@bot.event
async def on_ready():
    for guild in bot.guilds:
        category=discord.utils.get(guild.categories,name="🎰 PAL CASINO")
        if category:
            try:
                await ensure_structure(guild)
                await refresh_status_panel(guild)
                log.info("CASINO営業状態同期完了: %s",guild.name)
            except Exception:
                log.exception("CASINO起動同期エラー: %s",guild.name)
        else:
            log.warning("カテゴリ「🎰 PAL CASINO」が見つかりません: %s",guild.name)

        # !casinosetup（新: 🎰PAL CASINO / 🎮GAME 2カテゴリ構成）の再同期。
        # channel_mapに記録済みのチャンネルが1つでも見つかった場合のみ、不足分を復旧する。
        try:
            v2_channels=await get_v2_channels(guild)
            if v2_channels:
                await ensure_v2_structure(guild)
                await refresh_v2_status_panel(guild)
                log.info("PAL CASINO v2システム同期完了: %s",guild.name)
        except Exception:
            log.exception("PAL CASINO v2 起動同期エラー: %s",guild.name)
    log.info("PAL CASINO起動完了: %s",bot.user)

# 元々 !casinosetup という名前だった、build/panels/repair/delete ボタン式の個別セットアップ機能。
# 新しい !casinosetup（🎰PAL CASINO / 🎮GAMEの2カテゴリを自動構築する版）とコマンド名が重複するため、
# 機能は一切変更せずに !casinosetup_legacy という名前へ変更のみ行っている。
@bot.command(name="casinosetup_legacy")
@commands.has_permissions(administrator=True)
async def casinosetup_legacy(ctx):
    await ctx.send(embed=discord.Embed(title="⚙️ PAL CASINO SYSTEM SETUP",description="カテゴリー・チャンネル・固定パネルを自動構築します。",color=0xF1C40F),view=SetupView())

@bot.command()
@commands.has_permissions(administrator=True)
async def casinosetup(ctx):
    """🎰 PAL CASINO / 🎮 GAME / 👑 VIP / 🎮 VIP GAME を1コマンドで自動構築／復旧する。
    既に存在するものは再利用し、Discord側で削除された部分だけを検知して復旧する。DBデータには触れない。"""
    msg=await ctx.send("🎰 PAL CASINO システムを確認しています…")
    try:
        _main_cat,_game_cat,vip_role,channels,counts=await ensure_v2_structure(ctx.guild)
        await install_v2_panels(ctx.guild,channels)
    except discord.Forbidden:
        await msg.edit(content="❌ 権限不足でチャンネル/カテゴリ/ロールを作成できませんでした。BOTの権限を確認してください。")
        return
    except Exception:
        log.exception("casinosetup failed")
        await msg.edit(content="❌ セットアップ中にエラーが発生しました。ログを確認してください。")
        return
    await msg.edit(content=(
        "✅ PAL CASINOシステム確認完了\n"
        f"新規作成: {counts['created']}件\n"
        f"復旧: {counts['restored']}件\n"
        f"再利用: {counts['reused']}件\n"
        f"ゲームチャンネル数: {counts['game_channels']}\n"
        f"👑 VIPロール: {vip_role.mention}\n\n"
        "一般ユーザーは閲覧のみ可能（送信・添付・リアクション・スレッド不可）、BOTと管理者は通常通り操作できます。\n"
        "VIP会員は 👑VIP／🎮VIP GAME が閲覧でき、通常ゲームの最大BETも2倍になります。"
    ))

bot.run(os.environ["DISCORD_TOKEN"])
