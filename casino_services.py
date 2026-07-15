import json, random, secrets
from casino_db import game, pool, record_round, setting, chip_balance
from bank_gateway_for_other_bots import bank_debit, bank_credit

SYMBOLS=["🍒","🍋","💎","7️⃣"]
WEIGHTS=[45,35,15,5]

def round_id(game_key):
    return f"CASINO-{game_key}-{secrets.token_hex(3).upper()}"

async def play_slot(user_id, bet):
    cfg=await game("SLOT3")
    if not cfg or not cfg["implemented"] or not cfg["enabled"]:
        return {"status":"PREPARING"}
    max_bet=cfg["max_bet"]
    vip=await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",str(user_id)) or False
    if bet < cfg["min_bet"] or bet > (cfg["vip_max_bet"] if vip else max_bet):
        return {"status":"BET_RANGE","min":cfg["min_bet"],"max":cfg["vip_max_bet"] if vip else max_bet}
    rid=round_id("SLOT3")
    debit=await bank_debit("PAL_CASINO",f"{rid}:BET",user_id,"CHIP",bet)
    if debit["status"]!="SUCCESS":
        return {"status":debit["status"]}
    reels=random.choices(SYMBOLS,weights=WEIGHTS,k=3)
    if reels==["7️⃣"]*3: mult=50
    elif reels==["💎"]*3: mult=20
    elif reels==["🍒"]*3: mult=5
    elif len(set(reels))==1: mult=3
    else: mult=0
    payout=int(bet*mult)
    if payout:
        credit=await bank_credit("PAL_CASINO",f"{rid}:WIN",user_id,"CHIP",payout)
        if credit["status"]!="SUCCESS":
            return {"status":"PAYOUT_ERROR","round_id":rid}
    result="WIN" if payout else "LOSE"
    await record_round(rid,user_id,"SLOT3",bet,payout,result,mult,json.dumps({"reels":reels}))
    return {"status":"SUCCESS","round_id":rid,"reels":reels,"bet":bet,"payout":payout,
            "profit":payout-bet,"multiplier":mult,"balance":await chip_balance(user_id)}
