import json, random, secrets
from casino_db import game, pool, record_round, setting, chip_balance, config_get
from bank_gateway_for_other_bots import bank_debit, bank_credit

SYMBOLS=["🍒","🍋","💎","7️⃣"]
WEIGHTS=[45,35,15,5]
RED={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

# 丁半博打のNPCセリフ。実際の出目(rolled)とは無関係に均等抽選する（丁寄り2種／半寄り2種／中立2種／わからない2種）。
# セリフから出目を読み取ることはできない。
CHOHAN_HINTS=[
    "奇の気配がするな……","片方だけ妙に跳ねたな。",
    "揃った空気を感じるな……","二つの目が妙に落ち着いてる。",
    "さて、この出目をどう読む？","壺の中は静かなものだ。",
    "丁か半か、皆目見当がつかん……","こればかりは五分と五分だな。",
]

def round_id(game_key):
    return f"CASINO-{game_key}-{secrets.token_hex(5).upper()}"

async def _target_scale(key=None):
    global_rate=float(await setting("target_rtp","95.00"))
    if key:
        game_rate=float(await config_get(key,"payout_rate",str(global_rate)))
        return game_rate/95.0
    return global_rate/95.0

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
    # V9: game payout_rate is applied at the single settlement point.
    # This keeps every normal game connected to the same admin RTP control.
    raw_payout=int(payout)
    if raw_payout>0 and result not in ("PUSH",):
        scale=await _target_scale(key)
        payout=max(0,int(raw_payout*scale))
        mult=round(payout/bet,4) if bet else mult
        detail={**detail,"rtp_rate":float(await config_get(key,"payout_rate",await setting("target_rtp","95.00")))}
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
    return await _settle(user_id,"SLOT3",bet,int(bet*mult),"WIN" if mult else "LOSE",mult,{"reels":reels})

async def start_scratch(user_id):
    bet=500
    bad=await _limits(user_id,"SCRATCH",bet)
    if bad:return bad
    r=await reserve_bet(user_id,"SCRATCH",bet)
    if r["status"]!="SUCCESS":return r
    four_rate=float(await config_get("SCRATCH","four_tile_rate","3.0"))
    max_scratches=4 if random.random()*100<four_rate else 3

    # 絵文字3個一致で等級確定。高配当絵柄ほど盤面への出現が少ない。
    symbols=["👑","💎","⭐","🍒","🍋","🔔","🍇","🍉","🥝"]
    weights=[0.2,0.8,2.5,8,18,18,18,18,16.5]
    board=random.choices(symbols,weights=weights,k=9)

    # 一定確率で3一致候補を盤面へ仕込む。どこを削るかはユーザー選択。
    inject_symbol=random.choices(["👑","💎","⭐","🍒",None],weights=[0.1,0.9,5,18,76],k=1)[0]
    if inject_symbol:
        for pos in random.sample(range(9),3):board[pos]=inject_symbol

    return {**r,"board":board,"opened":set(),"max_scratches":max_scratches}

async def finish_scratch(user_id,state):
    opened_symbols=[state["board"][n] for n in state["opened"]]
    table={"👑":("特賞",100),"💎":("1等",10),"⭐":("2等",2),"🍒":("3等",1)}
    grade="はずれ";symbol="—";mult=0
    for sym,(name,pay) in table.items():
        if opened_symbols.count(sym)>=3:
            grade=name;symbol=sym;mult=pay;break
    payout=int(state["bet"]*mult)
    state["grade"]=grade;state["symbol"]=symbol;state["prize_multiplier"]=mult
    return await finalize_reserved(user_id,"SCRATCH",state["bet"],payout,
        grade if mult else "LOSE",mult,
        {"grade":grade,"symbol":symbol,"scratched":len(state["opened"])},
        state["round_id"])

async def play_scratch(user_id):
    # 旧呼び出し互換
    state=await start_scratch(user_id)
    if state["status"]!="SUCCESS":return state
    state["opened"]=set(range(state["max_scratches"]))
    return await finish_scratch(user_id,state)

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
    god_pct=await config_get("CHINCHIRO","god_rate_percent",None)
    god_rate=(float(god_pct)/100.0) if god_pct is not None else float(await config_get("CHINCHIRO","god_rate",str(1/8192)))
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

async def start_chohan(user_id,bet):
    r=await reserve_bet(user_id,"CHOHAN",bet)
    if r["status"]!="SUCCESS":return r
    no_dice_rate=float(await config_get("CHOHAN","special_rate","0.0001"))/100.0
    if random.random()<no_dice_rate:
        return {**r,"special":"サイコロなし","dice":[],"rolled":None,
                "npc":"……おい。サイコロが、ないぞ。"}
    dice=[random.randint(1,6),random.randint(1,6)]
    rolled="丁" if sum(dice)%2==0 else "半"
    # NPCのセリフは実際の出目(rolled)と完全に無関係に選ぶ（丁寄り/半寄り/中立/わからない、を均等に混ぜる）。
    # そのため外れることもあれば、何も手がかりが無いこともある。プレイヤーがセリフから出目を読むことはできない。
    npc=random.choice(CHOHAN_HINTS)
    return {**r,"dice":dice,"rolled":rolled,"npc":npc,"special":None}

async def finish_chohan(user_id,state,choice):
    rid=state["round_id"];bet=state["bet"]
    if state.get("special")=="サイコロなし":
        loss=await special_debit(user_id,rid,"NO_DICE",1_000_000)
        return await finalize_reserved(user_id,"CHOHAN",bet,0,"NO_DICE",0,
            {"special":"サイコロなし","special_loss":loss},rid)
    mult=2 if choice==state["rolled"] else 0
    return await finalize_reserved(user_id,"CHOHAN",bet,bet*mult,"WIN" if mult else "LOSE",mult,
        {"choice":choice,"rolled":state["rolled"],"npc":state["npc"]},rid)

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

def highlow_fair_multiplier(current):
    """現在のカード(1～13)を基準に、有利な方（HIGH/LOW）を選んだ場合の公正な倍率(1/勝率)を返す。
    真ん中の7は五分五分なので×2。1や13など端に近いカードほど勝ちやすい代わりに配当は控えめになる。
    これにより「見えているカードで有利な方を選べば毎回×2」という不公平な期待値のズレを無くす。"""
    higher=13-current; lower=current-1
    p=max(higher,lower)/12.0
    return round(1.0/p,4) if p>0 else 2.0

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
    moon_rate=float(await config_get("CRASH","moon_rate_percent","0.1"))/100.0
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
    if not 1<=mines<=24:return {"status":"INVALID_MINES"}
    r=await reserve_bet(user_id,"MINES",bet)
    if r["status"]!="SUCCESS":return r
    return {**r,"mines":mines,"mine_set":set(random.sample(range(25),mines)),"opened":set(),"multiplier":1.0}

def mines_open(state,cell):
    if cell in state["opened"]:return {"status":"ALREADY_OPEN"}
    if cell in state["mine_set"]:return {"status":"MINE"}
    state["opened"].add(cell)
    safe=25-state["mines"];opened=len(state["opened"])
    state["multiplier"]=round((25/safe)**opened*0.97,2)
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
