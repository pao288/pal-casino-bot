import json, random, secrets
from casino_db import game, pool, record_round, setting, chip_balance, config_get
from bank_gateway_for_other_bots import bank_debit, bank_credit

SYMBOLS=["🍒","🍋","💎","7️⃣"]
WEIGHTS=[45,35,15,5]
RED={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

def round_id(game_key):
    return f"CASINO-{game_key}-{secrets.token_hex(5).upper()}"

async def _target_scale():
    return float(await setting("target_rtp","95.00"))/95.0

async def _tables(key,default_weights=None,default_payouts=None):
    w=await config_get(key,"probability_table","")
    p=await config_get(key,"payout_table","")
    try: weights=json.loads(w) if w else default_weights
    except: weights=default_weights
    try: payouts=json.loads(p) if p else default_payouts
    except: payouts=default_payouts
    return weights,payouts

async def _vip(uid):
    return bool(await pool().fetchval("SELECT vip FROM casino.user_state WHERE user_id=$1",str(uid)) or False)

async def _limits(uid,key,bet):
    cfg=await game(key)
    if not cfg or not cfg["implemented"] or not cfg["enabled"]: return {"status":"PREPARING"}
    maximum=cfg["vip_max_bet"] if await _vip(uid) else cfg["max_bet"]
    if bet < cfg["min_bet"] or bet > maximum:
        return {"status":"BET_RANGE","min":cfg["min_bet"],"max":maximum}
    return None

async def reserve_bet(uid,key,bet,rid=None):
    bad=await _limits(uid,key,bet)
    if bad:return bad
    rid=rid or round_id(key)
    d=await bank_debit("PAL_CASINO",f"{rid}:BET",uid,"CHIP",bet)
    if d["status"]!="SUCCESS":return {"status":d["status"]}
    return {"status":"SUCCESS","round_id":rid,"bet":bet}

async def finalize_reserved(uid,key,bet,payout,result,mult,detail,rid):
    if payout>0:
        c=await bank_credit("PAL_CASINO",f"{rid}:WIN",uid,"CHIP",int(payout))
        if c["status"] not in ("SUCCESS","ALREADY_PROCESSED"):
            return {"status":"PAYOUT_ERROR"}
    exists=await pool().fetchval("SELECT 1 FROM casino.rounds WHERE round_id=$1",rid)
    if not exists:
        await record_round(rid,uid,key,bet,int(payout),result,mult,json.dumps(detail,ensure_ascii=False))
    return {"status":"SUCCESS","round_id":rid,"bet":bet,"payout":int(payout),
            "profit":int(payout)-bet,"multiplier":mult,"balance":await chip_balance(uid),**detail}

async def special_debit(uid,rid,kind,amount):
    d=await bank_debit("PAL_CASINO",f"{rid}:SPECIAL:{kind}",uid,"CHIP",amount)
    if d["status"]=="INSUFFICIENT_BALANCE":
        current=await chip_balance(uid)
        if current>0:
            await bank_debit("PAL_CASINO",f"{rid}:SPECIAL:{kind}:ALL",uid,"CHIP",current)
        return current
    return amount if d["status"] in ("SUCCESS","ALREADY_PROCESSED") else 0

async def _settle(uid,key,bet,payout,result,mult,detail,rid=None):
    r=await reserve_bet(uid,key,bet,rid)
    if r["status"]!="SUCCESS":return r
    return await finalize_reserved(uid,key,bet,payout,result,mult,detail,r["round_id"])

async def play_slot(user_id,bet):
    bad=await _limits(user_id,"SLOT3",bet)
    if bad:return bad
    weights,payouts=await _tables("SLOT3",WEIGHTS,{"777":50,"DIAMOND":20,"CHERRY":5,"SAME":3})
    if isinstance(weights,dict):weights=[float(weights.get(x,WEIGHTS[n])) for n,x in enumerate(SYMBOLS)]
    reels=random.choices(SYMBOLS,weights=weights,k=3)
    mult=float(payouts.get("777",50)) if reels==["7️⃣"]*3 else float(payouts.get("DIAMOND",20)) if reels==["💎"]*3 else float(payouts.get("CHERRY",5)) if reels==["🍒"]*3 else float(payouts.get("SAME",3)) if len(set(reels))==1 else 0
    mult=round(mult*await _target_scale(),4) if mult else 0
    return await _settle(user_id,"SLOT3",bet,int(bet*mult),"WIN" if mult else "LOSE",mult,{"reels":reels})

async def play_scratch(user_id):
    bet=500
    bad=await _limits(user_id,"SCRATCH",bet)
    if bad:return bad
    four_rate=float(await config_get("SCRATCH","four_tile_rate","3.0"))
    tiles=4 if random.random()*100<four_rate else 3
    weights,payouts=await _tables("SCRATCH",[94,5,0.9,0.1],[0,2,10,100])
    mult=float(random.choices(payouts,weights=weights,k=1)[0])
    return await _settle(user_id,"SCRATCH",bet,int(bet*mult),"WIN" if mult else "LOSE",mult,{"tiles":tiles,"special":tiles==4})

def roulette_win(choice,n):
    color="緑" if n==0 else ("赤" if n in RED else "黒")
    if choice.startswith("NUM:"): return n==int(choice[4:]),36
    if choice=="RED":return color=="赤",2
    if choice=="BLACK":return color=="黒",2
    if choice=="ODD":return n!=0 and n%2==1,2
    if choice=="EVEN":return n!=0 and n%2==0,2
    if choice=="LOW":return 1<=n<=18,2
    if choice=="HIGH":return 19<=n<=36,2
    if choice.startswith("DOZEN:"):
        d=int(choice.split(":")[1]);return (d-1)*12+1<=n<=d*12,3
    if choice.startswith("COLUMN:"):
        c=int(choice.split(":")[1]);return n!=0 and ((n-1)%3)+1==c,3
    return False,0

async def play_roulette(user_id,bet,choice):
    bad=await _limits(user_id,"ROULETTE",bet)
    if bad:return bad
    n=random.randint(0,36); color="緑" if n==0 else ("赤" if n in RED else "黒")
    win,m=roulette_win(choice,n);mult=m if win else 0
    return await _settle(user_id,"ROULETTE",bet,bet*mult,"WIN" if win else "LOSE",mult,{"number":n,"color":color,"choice":choice})

async def play_chinchiro(user_id,bet):
    bad=await _limits(user_id,"CHINCHIRO",bet)
    if bad:return bad
    god_rate=float(await config_get("CHINCHIRO","god_rate",str(1/8192)))
    shonben_rate=float(await config_get("CHINCHIRO","shonben_rate","0.0001"))
    x=random.random()
    if x<god_rate:
        return await _settle(user_id,"CHINCHIRO",bet,bet*100,"GOD",100,{"special":"GOD","dice":["✨","👁️","✨"]})
    if x<god_rate+shonben_rate:
        return await _settle(user_id,"CHINCHIRO",bet,0,"SHONBEN",0,{"special":"ションベン","dice":["💦","💦","💦"]})
    player=[random.randint(1,6) for _ in range(3)]
    npc=[random.randint(1,6) for _ in range(3)]
    def score(d):
        if d==[1,1,1]:return (8,1,"ピンゾロ")
        if len(set(d))==1:return (7,d[0],"ゾロ目")
        if sorted(d)==[4,5,6]:return (6,0,"シゴロ")
        if sorted(d)==[1,2,3]:return (0,0,"ヒフミ")
        for x in set(d):
            if d.count(x)==2:
                y=next(z for z in d if z!=x);return (2,y,f"{y}の目")
        return (1,0,"役なし")
    ps,ns=score(player),score(npc)
    if ps>ns:mult=2;result="WIN"
    elif ps==ns:mult=1;result="PUSH"
    else:mult=0;result="LOSE"
    return await _settle(user_id,"CHINCHIRO",bet,bet*mult,result,mult,{"player":player,"npc":npc,"player_role":ps[2],"npc_role":ns[2]})

async def play_chohan(user_id,bet,choice):
    bad=await _limits(user_id,"CHOHAN",bet)
    if bad:return bad
    no_dice_rate=float(await config_get("CHOHAN","no_dice_rate","0.000001"))
    if random.random()<no_dice_rate:
        rid=round_id("CHOHAN")
        r=await reserve_bet(user_id,"CHOHAN",bet,rid)
        if r["status"]!="SUCCESS":return r
        loss=await special_debit(user_id,rid,"NO_DICE",1_000_000)
        return await finalize_reserved(user_id,"CHOHAN",bet,0,"NO_DICE",0,{"special":"サイコロなし","special_loss":loss},rid)
    dice=[random.randint(1,6),random.randint(1,6)]
    rolled="丁" if sum(dice)%2 else "半";mult=2 if choice==rolled else 0
    hints=["さぁ張った張った！","今日は妙に静かだな…","出目は風だけが知っている。","勝負は一瞬だ。"]
    return await _settle(user_id,"CHOHAN",bet,bet*mult,"WIN" if mult else "LOSE",mult,{"dice":dice,"choice":choice,"rolled":rolled,"npc":random.choice(hints)})

async def play_coin(user_id,bet,choice):
    bad=await _limits(user_id,"COIN",bet)
    if bad:return bad
    event_rate=float(await config_get("COIN","hundred_coin_rate","3.0"))
    same_rate=float(await config_get("COIN","all_same_rate","1.0"))
    if random.random()*100<event_rate:
        if random.random()*100<same_rate:
            face=random.choice(["表","裏"]);heads=100 if face=="表" else 0
        else:heads=sum(random.choice([0,1]) for _ in range(100))
        tails=100-heads
        chosen=heads if choice=="表" else tails
        mult=round(chosen/50,2)
        payout=int(bet*mult)
        extra_loss=0
        rid=round_id("COIN")
        r=await reserve_bet(user_id,"COIN",bet,rid)
        if r["status"]!="SUCCESS":return r
        if choice=="表" and tails>50: extra_loss=await special_debit(user_id,rid,"100COIN_TAILS",int(bet*((tails-50)/50)))
        if choice=="裏" and heads>50: extra_loss=await special_debit(user_id,rid,"100COIN_HEADS",int(bet*((heads-50)/50)))
        return await finalize_reserved(user_id,"COIN",bet,payout,"100_COINS",mult,{"special":"100枚イベント","heads":heads,"tails":tails,"choice":choice,"extra_loss":extra_loss},rid)
    rolled=random.choice(["表","裏"]);mult=2 if choice==rolled else 0
    return await _settle(user_id,"COIN",bet,bet*mult,"WIN" if mult else "LOSE",mult,{"choice":choice,"rolled":rolled})

async def start_highlow(user_id,bet):
    r=await reserve_bet(user_id,"HIGHLOW",bet)
    if r["status"]!="SUCCESS":return r
    return {**r,"current":random.randint(1,13),"stage":1,"multiplier":1}

async def highlow_step(state,choice,double=False):
    current=state["current"]; nxt=random.randint(1,13)
    joker=None
    if double and state["bet"]>=5000:
        final=state["multiplier"]>=10
        if final or random.random()<0.08:
            x=random.random()*100
            if x<0.001:joker="MYSTERY"
            elif x<4.901:joker="GAIN"
            elif x<19.901:joker="LOSS"
            else:joker="NONE"
            if joker=="LOSS":
                return {"done":True,"win":False,"joker":joker,"current":current,"next":nxt}
            if joker=="MYSTERY":
                amount=100_000_000 if random.choice([True,False]) else 0
                return {"done":True,"win":amount>0,"joker":joker,"mystery_payout":amount,"current":current,"next":nxt}
            if joker=="GAIN" and random.choice([True,False]):
                return {"done":False,"win":True,"joker":joker,"forced":True,"current":nxt,"next":nxt}
    if nxt==current:return {"done":False,"push":True,"joker":joker,"current":nxt,"next":nxt}
    win=(choice=="HIGH" and nxt>current) or (choice=="LOW" and nxt<current)
    return {"done":not win,"win":win,"joker":joker,"current":nxt,"next":nxt}

async def finish_highlow(uid,state,payout,result,detail):
    mult=round(payout/state["bet"],4) if state["bet"] else 0
    return await finalize_reserved(uid,"HIGHLOW",state["bet"],payout,result,mult,detail,state["round_id"])

async def create_crash(user_id,bet,auto=None):
    r=await reserve_bet(user_id,"CRASH",bet)
    if r["status"]!="SUCCESS":return r
    event_roll=random.random()
    bigbang_rate=float(await config_get("CRASH","bigbang_rate","0.0000000000000000000000000001"))
    blackhole_rate=float(await config_get("CRASH","blackhole_rate","0.00001"))
    moon_rate=float(await config_get("CRASH","moon_rate","0.001"))
    if event_roll<bigbang_rate:event="BIG_BANG";target=1.01
    elif event_roll<bigbang_rate+blackhole_rate:event="BLACK_HOLE";target=round(random.uniform(1.05,5),2)
    elif event_roll<bigbang_rate+blackhole_rate+moon_rate:event="MOON";target=100.0
    else:
        event="NORMAL"
        # crash distribution: most rounds low, rare long runs
        u=max(1e-9,random.random());target=round(max(1.01,min(250.0,0.99/(u**0.72))),2)
    return {**r,"auto":auto,"target":target,"event":event}

async def finish_crash(uid,state,cashout=None):
    event=state["event"];rid=state["round_id"];bet=state["bet"]
    if event=="BIG_BANG":
        pool_total=int(await pool().fetchval("SELECT COALESCE(SUM(balance),0) FROM bank.accounts WHERE account_type='USER' AND currency='CHIP'") or 0)
        # Credit the measured pool amount as the event award.
        return await finalize_reserved(uid,"CRASH",bet,pool_total,"BIG_BANG",round(pool_total/bet,4) if bet else 0,{"special":"BIG BANG","crash":state["target"]},rid)
    if event=="BLACK_HOLE":
        loss=await special_debit(uid,rid,"BLACK_HOLE",1_000_000)
        return await finalize_reserved(uid,"CRASH",bet,0,"BLACK_HOLE",0,{"special":"ブラックホール","special_loss":loss,"crash":state["target"]},rid)
    if cashout is not None and cashout<state["target"]:
        return await finalize_reserved(uid,"CRASH",bet,int(bet*cashout),"WIN",cashout,{"cashout":cashout,"crash":state["target"],"special":"月到着" if event=="MOON" else None},rid)
    return await finalize_reserved(uid,"CRASH",bet,0,"LOSE",0,{"crash":state["target"],"special":"月到着" if event=="MOON" else None},rid)

async def start_mines(user_id,bet,mines):
    bad=await _limits(user_id,"MINES",bet)
    if bad:return bad
    if not 1<=mines<=35:return {"status":"INVALID_MINES"}
    r=await reserve_bet(user_id,"MINES",bet)
    if r["status"]!="SUCCESS":return r
    return {**r,"mines":mines,"mine_set":set(random.sample(range(36),mines)),"opened":set(),"multiplier":1.0}

def mines_open(state,cell):
    if cell in state["opened"]:return {"status":"ALREADY_OPEN"}
    if cell in state["mine_set"]:return {"status":"MINE"}
    state["opened"].add(cell)
    safe=36-state["mines"];opened=len(state["opened"])
    state["multiplier"]=round((36/safe)**opened*0.97,2)
    return {"status":"SAFE","multiplier":state["multiplier"]}

async def finish_mines(uid,state,won):
    payout=int(state["bet"]*state["multiplier"]) if won else 0
    return await finalize_reserved(uid,"MINES",state["bet"],payout,"CASHOUT" if won else "LOSE",state["multiplier"] if won else 0,
        {"mines":state["mines"],"opened":sorted(state["opened"])},state["round_id"])

async def start_blackjack(user_id,bet):
    r=await reserve_bet(user_id,"BLACKJACK",bet)
    if r["status"]!="SUCCESS":return r
    deck=[v for v in range(2,12) for _ in range(4)]
    random.shuffle(deck)
    return {**r,"deck":deck,"player":[deck.pop(),deck.pop()],"dealer":[deck.pop(),deck.pop()]}

def hand_value(cards):
    total=sum(cards);aces=cards.count(11)
    while total>21 and aces:total-=10;aces-=1
    return total

def blackjack_hit(state):
    state["player"].append(state["deck"].pop());return hand_value(state["player"])

async def finish_blackjack(uid,state,action):
    if action=="SURRENDER":
        return await finalize_reserved(uid,"BLACKJACK",state["bet"],state["bet"]//2,"SURRENDER",0.5,{"player":state["player"],"dealer":state["dealer"]},state["round_id"])
    ps=hand_value(state["player"])
    while hand_value(state["dealer"])<17:state["dealer"].append(state["deck"].pop())
    ds=hand_value(state["dealer"])
    if ps>21:mult=0;result="LOSE"
    elif ds>21 or ps>ds:mult=2.5 if len(state["player"])==2 and ps==21 else 2;result="WIN"
    elif ps==ds:mult=1;result="PUSH"
    else:mult=0;result="LOSE"
    return await finalize_reserved(uid,"BLACKJACK",state["bet"],int(state["bet"]*mult),result,mult,{"player":state["player"],"dealer":state["dealer"]},state["round_id"])
