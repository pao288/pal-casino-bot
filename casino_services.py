import json, random, secrets
from casino_db import game, pool, record_round, setting, chip_balance, config_get
from bank_gateway_for_other_bots import bank_debit, bank_credit

SYMBOLS=["🍒","🍋","💎","7️⃣"]
WEIGHTS=[45,35,15,5]

async def _target_scale():
    return float(await setting("target_rtp","95.00"))/95.0

async def _tables(key,default_weights=None,default_payouts=None):
    import json
    w=await config_get(key,"probability_table","")
    p=await config_get(key,"payout_table","")
    try:weights=json.loads(w) if w else default_weights
    except:weights=default_weights
    try:payouts=json.loads(p) if p else default_payouts
    except:payouts=default_payouts
    return weights,payouts


def round_id(game_key):
    return f"CASINO-{game_key}-{secrets.token_hex(3).upper()}"

async def _vip(uid):
    return bool(await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",str(uid)) or False)

async def _limits(uid,key,bet):
    cfg=await game(key)
    if not cfg or not cfg["implemented"] or not cfg["enabled"]: return {"status":"PREPARING"}
    maximum=cfg["vip_max_bet"] if await _vip(uid) else cfg["max_bet"]
    if bet < cfg["min_bet"] or bet > maximum:
        return {"status":"BET_RANGE","min":cfg["min_bet"],"max":maximum}
    return None

async def _settle(uid,key,bet,payout,result,mult,detail,rid=None):
    rid=rid or round_id(key)
    debit=await bank_debit("PAL_CASINO",f"{rid}:BET",uid,"CHIP",bet)
    if debit["status"]!="SUCCESS": return {"status":debit["status"]}
    if payout:
        credit=await bank_credit("PAL_CASINO",f"{rid}:WIN",uid,"CHIP",payout)
        if credit["status"]!="SUCCESS":
            await bank_credit("PAL_CASINO",f"{rid}:REFUND",uid,"CHIP",bet)
            return {"status":"PAYOUT_ERROR"}
    await record_round(rid,uid,key,bet,payout,result,mult,json.dumps(detail,ensure_ascii=False))
    return {"status":"SUCCESS","round_id":rid,"bet":bet,"payout":payout,
            "profit":payout-bet,"multiplier":mult,"balance":await chip_balance(uid),**detail}

async def play_slot(user_id,bet):
    bad=await _limits(user_id,"SLOT3",bet)
    if bad:return bad
    weights,payouts=await _tables("SLOT3",WEIGHTS,{"777":50,"DIAMOND":20,"CHERRY":5,"SAME":3})
    if isinstance(weights,dict):weights=[float(weights.get(x,WEIGHTS[n])) for n,x in enumerate(SYMBOLS)]
    reels=random.choices(SYMBOLS,weights=weights,k=3)
    mult=float(payouts.get("777",50)) if reels==["7️⃣"]*3 else float(payouts.get("DIAMOND",20)) if reels==["💎"]*3 else float(payouts.get("CHERRY",5)) if reels==["🍒"]*3 else float(payouts.get("SAME",3)) if len(set(reels))==1 else 0
    mult=round(mult*await _target_scale(),4) if mult else 0
    return await _settle(user_id,"SLOT3",bet,int(bet*mult),"WIN" if mult else "LOSE",mult,{"reels":reels})

async def play_coin(user_id,bet,choice):
    bad=await _limits(user_id,"COIN",bet)
    if bad:return bad
    rolled=random.choice(["表","裏"]); mult=2 if choice==rolled else 0
    return await _settle(user_id,"COIN",bet,bet*mult,"WIN" if mult else "LOSE",mult,{"choice":choice,"rolled":rolled})

async def play_dice_kind(user_id,key,bet,choice):
    bad=await _limits(user_id,key,bet)
    if bad:return bad
    d1,d2=random.randint(1,6),random.randint(1,6); total=d1+d2
    if key=="CHOHAN":
        rolled="丁" if total%2 else "半"; mult=2 if choice==rolled else 0
        detail={"dice":[d1,d2],"choice":choice,"rolled":rolled}
    else:
        # チンチロ: ピンゾロ5倍、ゾロ3倍、シゴロ2倍、それ以外は親との簡易勝負
        dice=[d1,d2,random.randint(1,6)]
        if dice==[1,1,1]: mult=5; result="WIN"
        elif len(set(dice))==1: mult=3; result="WIN"
        elif sorted(dice)==[4,5,6]: mult=2; result="WIN"
        elif sorted(dice)==[1,2,3]: mult=0; result="LOSE"
        else:
            mult=2 if sum(dice)>=11 else 0; result="WIN" if mult else "LOSE"
        return await _settle(user_id,key,bet,bet*mult,result,mult,{"dice":dice})
    return await _settle(user_id,key,bet,bet*mult,"WIN" if mult else "LOSE",mult,detail)

async def play_roulette(user_id,bet,choice):
    bad=await _limits(user_id,"ROULETTE",bet)
    if bad:return bad
    n=random.randint(0,36); color="緑" if n==0 else ("赤" if n in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36} else "黒")
    if choice.isdigit():
        win=int(choice)==n; mult=36 if win else 0
    else:
        win=choice==color; mult=2 if win else 0
    return await _settle(user_id,"ROULETTE",bet,bet*mult,"WIN" if mult else "LOSE",mult,{"number":n,"color":color,"choice":choice})

async def play_highlow(user_id,bet,choice):
    bad=await _limits(user_id,"HIGHLOW",bet)
    if bad:return bad
    current=random.randint(1,13); nxt=random.randint(1,13)
    if nxt==current: mult=1; result="PUSH"
    else:
        win=(choice=="HIGH" and nxt>current) or (choice=="LOW" and nxt<current)
        mult=2 if win else 0; result="WIN" if win else "LOSE"
    return await _settle(user_id,"HIGHLOW",bet,bet*mult,result,mult,{"current":current,"next":nxt,"choice":choice})

async def play_scratch(user_id,bet):
    bad=await _limits(user_id,"SCRATCH",bet)
    if bad:return bad
    weights,payouts=await _tables("SCRATCH",[48,25,15,7,4,1],[0,1,2,5,10,30])
    mult=float(random.choices(payouts,weights=weights,k=1)[0]);mult=round(mult*await _target_scale(),4) if mult else 0
    return await _settle(user_id,"SCRATCH",bet,int(bet*mult),"WIN" if mult>1 else "PUSH" if mult==1 else "LOSE",mult,{"ticket":"🎟️"})

async def play_crash(user_id,bet,cashout):
    bad=await _limits(user_id,"CRASH",bet)
    if bad:return bad
    crash=round(min(50,max(1,random.paretovariate(2))),2)
    win=cashout < crash
    mult=cashout if win else 0
    return await _settle(user_id,"CRASH",bet,int(bet*mult),"WIN" if win else "LOSE",mult,{"crash":crash,"cashout":cashout})

async def play_mines(user_id,bet,picks,mines):
    bad=await _limits(user_id,"MINES",bet)
    if bad:return bad
    mines=max(1,min(10,mines)); picks=max(1,min(24,picks))
    mine_set=set(random.sample(range(25),mines))
    opened=set(random.sample(range(25),picks))
    hit=bool(mine_set & opened)
    mult=0 if hit else round((25/(25-mines))**picks*0.97,2)
    return await _settle(user_id,"MINES",bet,int(bet*mult),"LOSE" if hit else "WIN",mult,{"mines":mines,"picks":picks,"hit":hit})

async def play_blackjack(user_id,bet,action):
    bad=await _limits(user_id,"BLACKJACK",bet)
    if bad:return bad
    def card(): return random.randint(2,11)
    player=[card(),card()]; dealer=[card(),card()]
    if action=="HIT": player.append(card())
    ps=sum(player); ds=sum(dealer)
    while ds<17: dealer.append(card()); ds=sum(dealer)
    if ps>21: mult=0; result="LOSE"
    elif ds>21 or ps>ds: mult=2.5 if len(player)==2 and ps==21 else 2; result="WIN"
    elif ps==ds: mult=1; result="PUSH"
    else: mult=0; result="LOSE"
    return await _settle(user_id,"BLACKJACK",bet,int(bet*mult),result,mult,{"player":player,"dealer":dealer,"action":action})
