# main_azure.py — wersja Azure (podmień main.py na ten plik przed deployem)
# Importuje models_azure i auth_azure zamiast lokalnych wersji

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os

from models_azure import Base, engine, get_db, User, Tenant, League, Team, Player, Match, Goal
from auth_azure import (hash_password, verify_password, create_token,
    get_current_user, require_admin, require_fan, TokenData)
from repository import StatisticsRepository, MatchRepository

Base.metadata.create_all(bind=engine)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "*")

app = FastAPI(title="Liga SaaS API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_URL, "*"],
    allow_methods=["*"], allow_headers=["*"])

class TeamDto(BaseModel):
    team_id: int; name: str; city: Optional[str]
    points: int; wins: int; draws: int; losses: int

class PlayerDto(BaseModel):
    player_id: int; first_name: str; last_name: str
    position: Optional[str]; shirt_number: Optional[int]
    team_name: str; goals: int

class MatchResultInput(BaseModel):
    match_id: int; home_score: int; away_score: int

class AddMatchInput(BaseModel):
    home_team_id: int; away_team_id: int; venue: Optional[str] = None

class AddPlayerInput(BaseModel):
    first_name: str; last_name: str; position: Optional[str] = None
    shirt_number: Optional[int] = None; team_id: int

class AddGoalInput(BaseModel):
    match_id: int; player_id: int; minute: Optional[int] = None
    is_penalty: bool = False; is_own_goal: bool = False

class RegisterInput(BaseModel):
    username: str; password: str; tenant_name: str; role: str = "fan"

@app.post("/auth/register", tags=["Auth"])
def register(data: RegisterInput, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    tenant = Tenant(name=data.tenant_name, is_active=True)
    db.add(tenant); db.flush()
    league = League(tenant_id=tenant.tenant_id, name=f"{data.tenant_name} League", season=2025)
    db.add(league); db.flush()
    user = User(tenant_id=tenant.tenant_id, username=data.username,
                hashed_password=hash_password(data.password), role=data.role)
    db.add(user); db.commit()
    return {"access_token": create_token(user), "token_type": "bearer",
            "tenant_id": tenant.tenant_id, "tenant_name": tenant.name, "role": user.role}

@app.post("/auth/login", tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_token(user), "token_type": "bearer",
            "tenant_id": user.tenant_id, "role": user.role}

@app.get("/auth/me", tags=["Auth"])
def me(current_user: TokenData = Depends(get_current_user)):
    return {"user_id": current_user.user_id, "username": current_user.username,
            "tenant_id": current_user.tenant_id, "role": current_user.role}

@app.get("/api/best-team", tags=["Statistics"])
def get_best_team(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    repo = StatisticsRepository(db, current_user.tenant_id)
    team = repo.get_best_team()
    if not team: raise HTTPException(status_code=404, detail="No teams found")
    return TeamDto(team_id=team.team_id, name=team.name, city=team.city,
                   points=team.points, wins=team.wins, draws=team.draws, losses=team.losses)

@app.get("/api/best-scorer", tags=["Statistics"])
def get_best_scorer(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    repo = StatisticsRepository(db, current_user.tenant_id)
    result = repo.get_best_scorer()
    if not result: raise HTTPException(status_code=404, detail="No goals found")
    player, goals = result
    team = db.query(Team).get(player.team_id)
    return PlayerDto(player_id=player.player_id, first_name=player.first_name,
                     last_name=player.last_name, position=player.position,
                     shirt_number=player.shirt_number,
                     team_name=team.name if team else "—", goals=goals)

@app.get("/api/best-player-vs-team/{opponent_team_id}", tags=["Statistics"])
def get_best_player_vs_team(opponent_team_id: int,
    current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    repo = StatisticsRepository(db, current_user.tenant_id)
    result = repo.get_best_player_vs_team(opponent_team_id)
    if not result: raise HTTPException(status_code=404, detail="No goals found vs this team")
    player, goals = result
    team = db.query(Team).get(player.team_id)
    return PlayerDto(player_id=player.player_id, first_name=player.first_name,
                     last_name=player.last_name, position=player.position,
                     shirt_number=player.shirt_number,
                     team_name=team.name if team else "—", goals=goals)

@app.get("/api/standings", tags=["Statistics"])
def get_standings(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    repo = StatisticsRepository(db, current_user.tenant_id)
    return [TeamDto(team_id=t.team_id, name=t.name, city=t.city,
                    points=t.points, wins=t.wins, draws=t.draws, losses=t.losses)
            for t in repo.get_standings()]

@app.get("/api/teams", tags=["Data"])
def get_teams(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    return [{"team_id": t.team_id, "name": t.name, "city": t.city}
            for t in StatisticsRepository(db, current_user.tenant_id).get_all_teams()]

@app.get("/api/players", tags=["Data"])
def get_players(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    return [{"player_id": p.player_id, "first_name": p.first_name, "last_name": p.last_name,
             "position": p.position, "shirt_number": p.shirt_number,
             "team_name": p.team.name if p.team else "—", "team_id": p.team_id, "goals": goals}
            for p, goals in StatisticsRepository(db, current_user.tenant_id).get_all_players()]

@app.get("/api/matches", tags=["Data"])
def get_matches(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    result = []
    for m in StatisticsRepository(db, current_user.tenant_id).get_all_matches():
        goals = db.query(Goal).filter_by(match_id=m.match_id).all()
        scorers = []
        for g in goals:
            p = db.query(Player).get(g.player_id)
            if p: scorers.append(f"{p.first_name[0]}. {p.last_name} {g.minute or '?'}\'{'(k)' if g.is_penalty else ''}")
        result.append({"match_id": m.match_id,
            "home_team": m.home_team.name if m.home_team else "—",
            "away_team": m.away_team.name if m.away_team else "—",
            "home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
            "home_score": m.home_score, "away_score": m.away_score,
            "venue": m.venue, "scorers": scorers})
    return result

@app.get("/api/league", tags=["Data"])
def get_league(current_user: TokenData = Depends(require_fan), db: Session = Depends(get_db)):
    league = StatisticsRepository(db, current_user.tenant_id).get_league()
    if not league: return {"name": "Liga", "season": 2025, "tenant": "—"}
    return {"league_id": league.league_id, "name": league.name,
            "season": league.season, "tenant": league.tenant.name}

@app.post("/api/match/result", tags=["Admin"])
def submit_result(data: MatchResultInput,
    current_user: TokenData = Depends(require_admin), db: Session = Depends(get_db)):
    MatchRepository(db, current_user.tenant_id).submit_result(data.match_id, data.home_score, data.away_score)
    return {"message": "Result saved, standings recalculated"}

@app.post("/api/match", tags=["Admin"])
def add_match(data: AddMatchInput,
    current_user: TokenData = Depends(require_admin), db: Session = Depends(get_db)):
    league = StatisticsRepository(db, current_user.tenant_id).get_league()
    if not league: raise HTTPException(status_code=404, detail="League not found")
    m = MatchRepository(db, current_user.tenant_id).add_match(
        league.league_id, data.home_team_id, data.away_team_id, data.venue)
    return {"match_id": m.match_id, "message": "Match added"}

@app.post("/api/player", tags=["Admin"])
def add_player(data: AddPlayerInput,
    current_user: TokenData = Depends(require_admin), db: Session = Depends(get_db)):
    p = MatchRepository(db, current_user.tenant_id).add_player(
        data.team_id, data.first_name, data.last_name, data.position, data.shirt_number)
    return {"player_id": p.player_id, "message": "Player added"}

@app.post("/api/goal", tags=["Admin"])
def add_goal(data: AddGoalInput,
    current_user: TokenData = Depends(require_admin), db: Session = Depends(get_db)):
    MatchRepository(db, current_user.tenant_id).add_goal(
        data.match_id, data.player_id, data.minute, data.is_penalty, data.is_own_goal)
    return {"message": "Goal recorded"}

@app.post("/api/team", tags=["Admin"])
def add_team(name: str, city: Optional[str] = None,
    current_user: TokenData = Depends(require_admin), db: Session = Depends(get_db)):
    league = StatisticsRepository(db, current_user.tenant_id).get_league()
    if not league: raise HTTPException(status_code=404, detail="League not found")
    team = Team(tenant_id=current_user.tenant_id, league_id=league.league_id, name=name, city=city)
    db.add(team); db.commit(); db.refresh(team)
    return {"team_id": team.team_id, "message": "Team added"}

@app.get("/")
def root():
    return {"app": "Liga SaaS API v2.0 — Azure", "docs": "/docs"}
