# models_azure.py — zamień zawartość models.py na ten plik gdy wdrażasz na Azure
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

server   = os.environ["SQL_SERVER"]
database = os.environ["SQL_DATABASE"]
username = os.environ["SQL_USERNAME"]
password = os.environ["SQL_PASSWORD"]

DATABASE_URL = (
    f"mssql+pyodbc://{username}:{password}@{server}/{database}"
    f"?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Tenant(Base):
    __tablename__ = "tenant"
    tenant_id  = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    leagues    = relationship("League", back_populates="tenant")
    users      = relationship("User", back_populates="tenant")

class User(Base):
    __tablename__ = "user"
    user_id          = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("tenant.tenant_id"), nullable=False)
    username         = Column(String(100), nullable=False, unique=True)
    hashed_password  = Column(String(200), nullable=False)
    role             = Column(String(20), default="fan", nullable=False)
    tenant           = relationship("Tenant", back_populates="users")

class League(Base):
    __tablename__ = "league"
    league_id  = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenant.tenant_id"), nullable=False)
    name       = Column(String(100), nullable=False)
    season     = Column(Integer, nullable=False)
    tenant     = relationship("Tenant", back_populates="leagues")
    teams      = relationship("Team", back_populates="league")

class Team(Base):
    __tablename__ = "team"
    team_id    = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenant.tenant_id"), nullable=False)
    league_id  = Column(Integer, ForeignKey("league.league_id"), nullable=False)
    name       = Column(String(100), nullable=False)
    city       = Column(String(100), nullable=True)
    points     = Column(Integer, default=0, nullable=False)
    wins       = Column(Integer, default=0, nullable=False)
    draws      = Column(Integer, default=0, nullable=False)
    losses     = Column(Integer, default=0, nullable=False)
    league     = relationship("League", back_populates="teams")
    players    = relationship("Player", back_populates="team")

class Player(Base):
    __tablename__ = "player"
    player_id    = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("tenant.tenant_id"), nullable=False)
    team_id      = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    first_name   = Column(String(100), nullable=False)
    last_name    = Column(String(100), nullable=False)
    position     = Column(String(10), nullable=True)
    shirt_number = Column(Integer, nullable=True)
    team         = relationship("Team", back_populates="players")
    goals        = relationship("Goal", back_populates="player")

class Match(Base):
    __tablename__ = "match_"
    match_id     = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("tenant.tenant_id"), nullable=False)
    league_id    = Column(Integer, ForeignKey("league.league_id"), nullable=False)
    home_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    home_score   = Column(Integer, nullable=True)
    away_score   = Column(Integer, nullable=True)
    venue        = Column(String(100), nullable=True)
    home_team    = relationship("Team", foreign_keys=[home_team_id])
    away_team    = relationship("Team", foreign_keys=[away_team_id])
    goals        = relationship("Goal", back_populates="match")

class Goal(Base):
    __tablename__ = "goal"
    goal_id     = Column(Integer, primary_key=True, index=True)
    match_id    = Column(Integer, ForeignKey("match_.match_id"), nullable=False)
    player_id   = Column(Integer, ForeignKey("player.player_id"), nullable=False)
    minute      = Column(Integer, nullable=True)
    is_penalty  = Column(Boolean, default=False, nullable=False)
    is_own_goal = Column(Boolean, default=False, nullable=False)
    match       = relationship("Match", back_populates="goals")
    player      = relationship("Player", back_populates="goals")
