import os
import asyncpg

_pool = None

GAME_DEFS = [
    ("SLOT3","🎰 3リールスロット",True,False),
    ("SCRATCH","🎟️ スクラッチ",False,False),
    ("LOTTERY","🎫 宝くじ",False,False),
    ("LOTO6","🔢 ロト6",False,False),
    ("BLACKJACK","🃏 ブラックジャック",False,False),
    ("ROULETTE","🎡 ルーレット",False,False),
    ("MINES","💣 マインズ",False,False),
    ("CHINCHIRO","🎲 チンチロ",False,False),
    ("CHOHAN","🎴 丁半博打",False,False),
    ("COIN","🪙 コイントス",False,False),
    ("HIGHLOW","📈 ハイアンドロー",False,False),
    ("CRASH","🚀 クラッシュ",False,False),
    ("SLOT5","🎰 5リールスロット",False,False),
    ("JACKPOT_SLOT","💰 ジャックポットスロット",False,False),
    ("KAZAAN","🪙 カザーン",False,True),
    ("HORSE","🏇 競馬",False,True),
    ("SPORTS","⚽ スポーツベット",False,False),
    ("FUKUBIKI","🎁 福引",False,False),
    ("MEDIA_GAME","🎬 動画・GIFゲーム",False,False),
]

async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=8)
    async with _pool.acquire() as c:
        await c.execute("""
        CREATE SCHEMA IF NOT EXISTS casino;
        CREATE TABLE IF NOT EXISTS casino.settings(
          setting_key text PRIMARY KEY, setting_value text NOT NULL
        );
        CREATE TABLE IF NOT EXISTS casino.games(
          game_key text PRIMARY KEY, display_name text NOT NULL,
          enabled boolean NOT NULL DEFAULT false, implemented boolean NOT NULL DEFAULT false,
          vip_only boolean NOT NULL DEFAULT false, min_bet bigint NOT NULL DEFAULT 1,
          max_bet bigint NOT NULL DEFAULT 10000, vip_max_bet bigint NOT NULL DEFAULT 20000
        );
        CREATE TABLE IF NOT EXISTS casino.rounds(
          round_id text PRIMARY KEY, user_id text NOT NULL, game_key text NOT NULL,
          bet bigint NOT NULL, payout bigint NOT NULL DEFAULT 0, result text NOT NULL,
          multiplier numeric NOT NULL DEFAULT 0, detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS casino_round_user_idx ON casino.rounds(user_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS casino.user_state(
          user_id text PRIMARY KEY, active_game text, vip boolean NOT NULL DEFAULT false,
          first_play_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS casino.daily_claims(
          user_id text NOT NULL, claim_date date NOT NULL, amount bigint NOT NULL,
          PRIMARY KEY(user_id,claim_date)
        );
        CREATE TABLE IF NOT EXISTS casino.channel_map(
          map_key text PRIMARY KEY, channel_id text NOT NULL
        );
        """)
        defaults = {
          "big_win_enabled":"1","big_win_multiplier":"30",
          "daily_bonus":"500","casino_maintenance":"0",
          "alert_high_bet":"10000","alert_plays_10m":"40"
        }
        for k,v in defaults.items():
            await c.execute("INSERT INTO casino.settings VALUES($1,$2) ON CONFLICT DO NOTHING",k,v)
        for key,name,implemented,vip in GAME_DEFS:
            await c.execute("""INSERT INTO casino.games(game_key,display_name,enabled,implemented,vip_only)
              VALUES($1,$2,$3,$3,$4) ON CONFLICT(game_key) DO UPDATE SET display_name=EXCLUDED.display_name,
              implemented=EXCLUDED.implemented,vip_only=EXCLUDED.vip_only""",key,name,implemented,vip)

def pool():
    if _pool is None: raise RuntimeError("init_db first")
    return _pool

async def setting(key, default=None):
    return await pool().fetchval("SELECT setting_value FROM casino.settings WHERE setting_key=$1",key) or default

async def set_setting(key,value):
    await pool().execute("""INSERT INTO casino.settings VALUES($1,$2)
      ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value""",key,str(value))

async def game(key):
    return await pool().fetchrow("SELECT * FROM casino.games WHERE game_key=$1",key)

async def games():
    return await pool().fetch("SELECT * FROM casino.games ORDER BY display_name")

async def map_get(key):
    return await pool().fetchval("SELECT channel_id FROM casino.channel_map WHERE map_key=$1",key)

async def map_set(key,value):
    await pool().execute("""INSERT INTO casino.channel_map VALUES($1,$2)
      ON CONFLICT(map_key) DO UPDATE SET channel_id=EXCLUDED.channel_id""",key,str(value))

async def map_clear():
    await pool().execute("DELETE FROM casino.channel_map")

async def chip_balance(user_id):
    return int(await pool().fetchval("""SELECT COALESCE(balance,0) FROM bank.accounts
      WHERE account_type='USER' AND owner_id=$1 AND currency='CHIP'""",str(user_id)) or 0)

async def profile(user_id):
    uid=str(user_id)
    r=await pool().fetchrow("""SELECT COUNT(*) plays,COALESCE(SUM(bet),0) total_bet,
      COALESCE(SUM(payout),0) total_payout,COALESCE(MAX(payout),0) max_win,
      MIN(created_at) first_play FROM casino.rounds WHERE user_id=$1""",uid)
    fav=await pool().fetchrow("""SELECT game_key,COUNT(*) n FROM casino.rounds WHERE user_id=$1
      GROUP BY game_key ORDER BY n DESC LIMIT 1""",uid)
    state=await pool().fetchrow("SELECT active_game,vip FROM casino.user_state WHERE user_id=$1",uid)
    return dict(r) | {"favorite":fav["game_key"] if fav else "-","active_game":state["active_game"] if state else None,
                      "vip":bool(state["vip"]) if state else False,"chip":await chip_balance(uid)}

async def history(user_id,limit=100):
    return await pool().fetch("""SELECT * FROM casino.rounds WHERE user_id=$1
      ORDER BY created_at DESC LIMIT $2""",str(user_id),limit)

async def record_round(round_id,user_id,game_key,bet,payout,result,multiplier,detail):
    await pool().execute("""INSERT INTO casino.rounds(round_id,user_id,game_key,bet,payout,result,multiplier,detail)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb)""",round_id,str(user_id),game_key,bet,payout,result,multiplier,detail)

async def total_stats():
    return await pool().fetchrow("""SELECT COUNT(*) plays,COUNT(*) FILTER(WHERE created_at>=now()-interval '24 hours') plays24,
      COALESCE(SUM(bet),0) bets,COALESCE(SUM(payout),0) payouts,
      COALESCE(MAX(payout),0) max_win FROM casino.rounds""")

async def ranking_maxwin():
    return await pool().fetch("""SELECT user_id,MAX(payout) value FROM casino.rounds
      GROUP BY user_id ORDER BY value DESC LIMIT 10""")

async def ranking_chip():
    return await pool().fetch("""SELECT owner_id user_id,balance value FROM bank.accounts
      WHERE account_type='USER' AND currency='CHIP' ORDER BY balance DESC LIMIT 10""")
