import os, logging, discord
from discord.ext import commands
from casino_db import init_db
from bank_gateway_for_other_bots import init_bank_gateway
from views import CasinoPanelView, CasinoAdminView, CasinoLobbyView, DirectGamePanel, DailyPanel, LotteryLaunchView, LotoLaunchView
from setup_service import install_panels,ensure_structure,delete_structure, install_direct_game_panels

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

@bot.event
async def setup_hook():
    await init_db()
    await init_bank_gateway()
    bot.add_view(CasinoPanelView())
    bot.add_view(CasinoAdminView())
    bot.add_view(CasinoLobbyView())
    for _key in ["SLOT3","SCRATCH","BLACKJACK","ROULETTE","MINES","CHINCHIRO","CHOHAN","COIN","HIGHLOW","CRASH"]:
        bot.add_view(DirectGamePanel(_key))
    bot.add_view(DailyPanel())
    bot.add_view(SetupView())
    log.info("DB・BANK Gateway接続完了")

@bot.event
async def on_ready():
    for guild in bot.guilds:
        category = discord.utils.get(guild.categories, name="🎰 PAL CASINO")
        if category:
            try:
                await install_panels(guild)
                log.info("ゲーム別固定パネル設置完了: %s", guild.name)
            except Exception:
                log.exception("ゲーム別固定パネル設置エラー: %s", guild.name)
        else:
            log.warning("カテゴリ「🎰 PAL CASINO」が見つかりません: %s", guild.name)
    log.info("PAL CASINO起動完了: %s",bot.user)

@bot.command()
@commands.has_permissions(administrator=True)
async def casinosetup(ctx):
    await ctx.send(embed=discord.Embed(title="⚙️ PAL CASINO SYSTEM SETUP",description="カテゴリー・チャンネル・固定パネルを自動構築します。",color=0xF1C40F),view=SetupView())

bot.run(os.environ["DISCORD_TOKEN"])
