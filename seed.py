from models import Base, engine, SessionLocal, Tenant, League, Team, Player, Match, Goal, User
from auth import hash_password

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(Tenant).first():
        print("Already seeded.")
        db.close()
        return

    # Tenant 1 — Ekstraklasa (admin + fan)
    t1 = Tenant(name="Ekstraklasa", is_active=True)
    db.add(t1); db.flush()

    db.add(User(tenant_id=t1.tenant_id, username="admin", hashed_password=hash_password("admin123"), role="admin"))
    db.add(User(tenant_id=t1.tenant_id, username="fan",   hashed_password=hash_password("fan123"),   role="fan"))

    l1 = League(tenant_id=t1.tenant_id, name="Ekstraklasa 2024/25", season=2025)
    db.add(l1); db.flush()

    teams_data = [
        ("Legia Warszawa","Warszawa",15,5,0,2),
        ("Lech Poznań","Poznań",12,4,0,3),
        ("Wisła Kraków","Kraków",10,3,1,3),
        ("Pogoń Szczecin","Szczecin",9,3,0,4),
        ("Górnik Zabrze","Zabrze",7,2,1,4),
    ]
    teams = []
    for name,city,pts,w,d,l in teams_data:
        t = Team(tenant_id=t1.tenant_id, league_id=l1.league_id,
                 name=name, city=city, points=pts, wins=w, draws=d, losses=l)
        db.add(t); teams.append(t)
    db.flush()

    players_data = [
        (0,"Bartosz","Kapustka","MF",7),
        (0,"Mahir","Emreli","FW",9),
        (0,"Artur","Jędrzejczyk","DF",55),
        (1,"Filip","Marchwiński","MF",10),
        (1,"Mikael","Ishak","FW",9),
        (1,"Antonio","Milić","DF",5),
        (2,"Jakub","Błaszczykowski","FW",10),
        (2,"Zdeněk","Ondrášek","FW",21),
        (3,"Kosta","Runjaic","FW",11),
        (3,"Luka","Zahović","FW",10),
        (4,"Erik","Expósito","FW",9),
        (4,"Sławomir","Peszko","MF",8),
    ]
    players = []
    for ti,fn,ln,pos,num in players_data:
        p = Player(tenant_id=t1.tenant_id, team_id=teams[ti].team_id,
                   first_name=fn, last_name=ln, position=pos, shirt_number=num)
        db.add(p); players.append(p)
    db.flush()

    matches_data = [(0,1,3,1),(0,2,2,0),(0,3,1,1),(1,2,2,1),
                    (1,3,3,0),(2,3,1,2),(0,4,4,0),(1,4,2,1),(2,4,1,0),(3,4,2,0)]
    matches = []
    for hi,ai,hs,as_ in matches_data:
        m = Match(tenant_id=t1.tenant_id, league_id=l1.league_id,
                  home_team_id=teams[hi].team_id, away_team_id=teams[ai].team_id,
                  home_score=hs, away_score=as_, venue=teams[hi].city)
        db.add(m); matches.append(m)
    db.flush()

    goals_data = [
        (0,1,15,False,False),(0,1,44,False,False),(0,1,67,True,False),(0,4,80,False,False),
        (1,0,22,False,False),(1,1,55,False,False),(2,1,10,False,False),(2,9,72,False,False),
        (3,3,30,False,False),(3,4,45,False,False),(4,4,20,False,False),(4,4,50,False,False),
        (4,4,88,True,False),(5,9,33,False,False),(5,9,60,False,False),(6,1,5,False,False),
        (6,0,25,False,False),(6,1,55,False,False),(6,1,78,True,False),(7,3,40,False,False),
        (7,4,65,False,False),(8,6,35,False,False),(9,9,20,False,False),(9,8,70,False,False),
    ]
    for mi,pi,minute,pen,og in goals_data:
        db.add(Goal(match_id=matches[mi].match_id, player_id=players[pi].player_id,
                    minute=minute, is_penalty=pen, is_own_goal=og))

    # Tenant 2 — Second league (proves multi-tenancy isolation)
    t2 = Tenant(name="Segunda Liga", is_active=True)
    db.add(t2); db.flush()
    db.add(User(tenant_id=t2.tenant_id, username="admin2", hashed_password=hash_password("admin123"), role="admin"))
    l2 = League(tenant_id=t2.tenant_id, name="Segunda Liga 2024/25", season=2025)
    db.add(l2); db.flush()
    t2_team = Team(tenant_id=t2.tenant_id, league_id=l2.league_id,
                   name="FC Demo", city="Demo City", points=6, wins=2, draws=0, losses=1)
    db.add(t2_team); db.flush()
    t2_player = Player(tenant_id=t2.tenant_id, team_id=t2_team.team_id,
                       first_name="Demo", last_name="Player", position="FW", shirt_number=1)
    db.add(t2_player)

    db.commit()
    print("Seeded OK — two tenants created")
    print("  Tenant 1 (Ekstraklasa): admin/admin123  fan/fan123")
    print("  Tenant 2 (Segunda Liga): admin2/admin123")
    db.close()

if __name__ == "__main__":
    seed()
