import random
from datetime import datetime, timedelta, timezone
from casino_db import pool, setting, current_lottery_draw, current_loto_draw
from bank_gateway_for_other_bots import bank_debit, bank_credit

JST=timezone(timedelta(hours=9))
LOTTERY_PRIZES={
 "1等":1_000_000_000,"1等前後賞":200_000_000,"2等":50_000_000,
 "3等":5_000_000,"4等":500_000,"5等":50_000,"6等":5_000,"7等":500,
}

async def ensure_lottery_draw():
    row=await current_lottery_draw()
    if row:return row
    no=int(await pool().fetchval("SELECT COALESCE(MAX(draw_no),0)+1 FROM casino.lottery_draws"))
    at=datetime.now(JST)+timedelta(days=7)
    return await pool().fetchrow("INSERT INTO casino.lottery_draws(draw_no,draw_at) VALUES($1,$2) RETURNING *",no,at)

async def buy_lottery(uid,count):
    if count<1 or count>100:return {"status":"COUNT_RANGE"}
    draw=await ensure_lottery_draw();price=int(await setting("lottery_price","500"));cost=price*count
    ref=f"LOTTERY:{draw['draw_no']}:{uid}:{random.getrandbits(48)}"
    d=await bank_debit("PAL_CASINO",ref+":BUY",uid,"CHIP",cost)
    if d["status"]!="SUCCESS":return {"status":d["status"]}
    tickets=[]
    async with pool().acquire() as c:
        async with c.transaction():
            for _ in range(count):
                g=random.randint(1,100);n=random.randint(100000,199999)
                tid=await c.fetchval("""INSERT INTO casino.lottery_tickets(draw_id,user_id,ticket_group,ticket_number,price)
                  VALUES($1,$2,$3,$4,$5) RETURNING ticket_id""",draw["draw_id"],str(uid),g,n,price)
                tickets.append((tid,g,n))
    return {"status":"SUCCESS","draw_no":draw["draw_no"],"cost":cost,"tickets":tickets}

def lottery_rank(g,n,wg,wn):
    if g==wg and n==wn:return "1等"
    if g==wg and abs(n-wn)==1:return "1等前後賞"
    if n==wn:return "2等"
    if n%100000==wn%100000:return "3等"
    if n%10000==wn%10000:return "4等"
    if n%1000==wn%1000:return "5等"
    if n%100==wn%100:return "6等"
    if n%10==wn%10:return "7等"
    return None

async def draw_lottery():
    draw=await ensure_lottery_draw();wg=random.randint(1,100);wn=random.randint(100000,199999)
    rows=await pool().fetch("SELECT * FROM casino.lottery_tickets WHERE draw_id=$1",draw["draw_id"])
    winners=[]
    for t in rows:
        rank=lottery_rank(t["ticket_group"],t["ticket_number"],wg,wn)
        prize=LOTTERY_PRIZES.get(rank,0)
        if prize:
            await bank_credit("PAL_CASINO",f"LOTTERY:{draw['draw_no']}:{t['ticket_id']}:PRIZE",t["user_id"],"CHIP",prize)
            winners.append((t["user_id"],rank,prize,t["ticket_group"],t["ticket_number"]))
        await pool().execute("UPDATE casino.lottery_tickets SET rank=$1,prize=$2 WHERE ticket_id=$3",rank,prize,t["ticket_id"])
    await pool().execute("UPDATE casino.lottery_draws SET status='DRAWN',winning_group=$1,winning_number=$2 WHERE draw_id=$3",wg,wn,draw["draw_id"])
    return {"draw_no":draw["draw_no"],"group":wg,"number":wn,"winners":winners}

async def ensure_loto_draw():
    row=await current_loto_draw()
    if row:return row
    no=int(await pool().fetchval("SELECT COALESCE(MAX(draw_no),0)+1 FROM casino.loto_draws"))
    prev=int(await pool().fetchval("SELECT COALESCE(carryover,0) FROM casino.loto_draws WHERE status='DRAWN' ORDER BY draw_no DESC LIMIT 1") or 0)
    at=datetime.now(JST)+timedelta(days=3)
    return await pool().fetchrow("INSERT INTO casino.loto_draws(draw_no,draw_at,carryover) VALUES($1,$2,$3) RETURNING *",no,at,prev)

async def buy_loto(uid,numbers):
    nums=sorted(set(numbers))
    if len(nums)!=6 or min(nums)<1 or max(nums)>43:return {"status":"NUMBERS"}
    draw=await ensure_loto_draw();price=int(await setting("loto_price","500"))
    ref=f"LOTO6:{draw['draw_no']}:{uid}:{random.getrandbits(48)}"
    d=await bank_debit("PAL_CASINO",ref+":BUY",uid,"CHIP",price)
    if d["status"]!="SUCCESS":return {"status":d["status"]}
    tid=await pool().fetchval("""INSERT INTO casino.loto_tickets(draw_id,user_id,numbers,price)
      VALUES($1,$2,$3,$4) RETURNING ticket_id""",draw["draw_id"],str(uid),nums,price)
    await pool().execute("UPDATE casino.loto_draws SET sales=sales+$1 WHERE draw_id=$2",price,draw["draw_id"])
    return {"status":"SUCCESS","draw_no":draw["draw_no"],"ticket_id":tid,"numbers":nums,"cost":price}

async def quick_pick(uid):
    return await buy_loto(uid,random.sample(range(1,44),6))

async def draw_loto():
    draw=await ensure_loto_draw()
    balls=random.sample(range(1,44),7);winning=sorted(balls[:6]);bonus=balls[6]
    tickets=await pool().fetch("SELECT * FROM casino.loto_tickets WHERE draw_id=$1",draw["draw_id"])
    ranked={1:[],2:[],3:[],4:[],5:[]}
    for t in tickets:
        hits=len(set(t["numbers"])&set(winning));bh=bonus in t["numbers"]
        rank=1 if hits==6 else 2 if hits==5 and bh else 3 if hits==5 else 4 if hits==4 else 5 if hits==3 else None
        if rank:ranked[rank].append(t)
    sales=int(draw["sales"]);carry=int(draw["carryover"])
    pcts={1:float(await setting("loto_p1","55")),2:float(await setting("loto_p2","15")),3:float(await setting("loto_p3","10")),4:float(await setting("loto_p4","5"))}
    fixed5=int(await setting("loto_p5","500"))
    pools={r:int(sales*pcts[r]/100) for r in range(1,5)};pools[1]+=carry
    next_carry=int(sales*float(await setting("loto_carry","15"))/100)
    winners=[]
    for rank in range(1,6):
        group=ranked[rank]
        if rank<5 and not group:next_carry+=pools[rank];continue
        prize=fixed5 if rank==5 else pools[rank]//len(group)
        for t in group:
            await bank_credit("PAL_CASINO",f"LOTO6:{draw['draw_no']}:{t['ticket_id']}:PRIZE",t["user_id"],"CHIP",prize)
            await pool().execute("UPDATE casino.loto_tickets SET rank=$1,prize=$2 WHERE ticket_id=$3",f"{rank}等",prize,t["ticket_id"])
            winners.append((t["user_id"],rank,prize,t["numbers"]))
    await pool().execute("""UPDATE casino.loto_draws SET status='DRAWN',winning_numbers=$1,bonus_number=$2,carryover=$3 WHERE draw_id=$4""",winning,bonus,next_carry,draw["draw_id"])
    return {"draw_no":draw["draw_no"],"winning":winning,"bonus":bonus,"carryover":next_carry,"winners":winners}


async def lottery_user_overview(uid, limit=20):
    draw=await ensure_lottery_draw()
    tickets=await pool().fetch("""SELECT t.*,d.draw_no,d.status draw_status,d.winning_group,d.winning_number,d.draw_at
      FROM casino.lottery_tickets t JOIN casino.lottery_draws d ON d.draw_id=t.draw_id
      WHERE t.user_id=$1 ORDER BY t.purchased_at DESC LIMIT $2""",str(uid),limit)
    return {"draw":draw,"tickets":tickets}

async def loto_user_overview(uid, limit=20):
    draw=await ensure_loto_draw()
    tickets=await pool().fetch("""SELECT t.*,d.draw_no,d.status draw_status,d.winning_numbers,d.bonus_number,d.draw_at
      FROM casino.loto_tickets t JOIN casino.loto_draws d ON d.draw_id=t.draw_id
      WHERE t.user_id=$1 ORDER BY t.purchased_at DESC LIMIT $2""",str(uid),limit)
    return {"draw":draw,"tickets":tickets}
