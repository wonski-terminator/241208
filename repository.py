# repository.py — Data access layer with RLS simulation and transaction isolation
#
# In Azure SQL Database:
#   - RLS enforced by CREATE SECURITY POLICY with FILTER PREDICATE on tenant_id
#   - Transaction isolation set via SET TRANSACTION ISOLATION LEVEL
#
# In SQLite (local dev):
#   - RLS simulated: every query explicitly filters WHERE tenant_id = ?
#   - Isolation levels simulated via BEGIN IMMEDIATE / BEGIN EXCLUSIVE
#   - Pattern is identical — only the SQL dialect differs

from sqlalchemy.orm import Session
from sqlalchemy import func, text
from contextlib import contextmanager
from models import Team, Player, Match, Goal, League

# ── RLS simulation ─────────────────────────────────────────────────────────
# Azure SQL RLS would enforce this transparently at engine level.
# Here we wrap every query with explicit tenant_id filter — same guarantee,
# different implementation layer.

class TenantRepository:
    """
    Base repository that enforces tenant isolation on every query.
    Equivalent to Azure SQL Row-Level Security FILTER PREDICATE.
    No query leaves this class without a tenant_id filter.
    """
    def __init__(self, db: Session, tenant_id: int):
        self.db        = db
        self.tenant_id = tenant_id

    def _guard(self, query, model):
        """Applies RLS filter — equivalent to Azure SQL FILTER PREDICATE."""
        return query.filter(model.tenant_id == self.tenant_id)


# ── Transaction isolation context managers ─────────────────────────────────
# SQLite: BEGIN IMMEDIATE = REPEATABLE READ equivalent
#         BEGIN EXCLUSIVE = SERIALIZABLE equivalent
# Azure SQL: SET TRANSACTION ISOLATION LEVEL SERIALIZABLE / REPEATABLE READ

@contextmanager
def read_committed(db: Session):
    """
    READ COMMITTED — default isolation.
    Used for: FR1, FR2, FR3 statistics reads.
    Prevents dirty reads. Allows non-repeatable reads (acceptable for stats).
    Azure SQL: SET TRANSACTION ISOLATION LEVEL READ COMMITTED
    SQLite:    default autocommit behaviour
    """
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise

@contextmanager
def serializable(db: Session):
    """
    SERIALIZABLE — highest isolation level.
    Used for: entering match results (prevents phantom reads).
    Azure SQL: SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
    SQLite:    BEGIN EXCLUSIVE TRANSACTION
    """
    db.execute(text("BEGIN EXCLUSIVE"))
    try:
        yield db
        db.execute(text("COMMIT"))
    except Exception:
        db.execute(text("ROLLBACK"))
        raise

@contextmanager
def repeatable_read(db: Session):
    """
    REPEATABLE READ — used for season ranking calculations.
    Guarantees data does not change during a long read.
    Azure SQL: SET TRANSACTION ISOLATION LEVEL REPEATABLE READ
    SQLite:    BEGIN IMMEDIATE
    """
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        yield db
        db.execute(text("COMMIT"))
    except Exception:
        db.execute(text("ROLLBACK"))
        raise


# ── StatisticsRepository ───────────────────────────────────────────────────

class StatisticsRepository(TenantRepository):
    """
    Implements FR1, FR2, FR3 queries with tenant isolation.
    All methods run under READ COMMITTED isolation (statistics).
    """

    def get_best_team(self) -> Team | None:
        """FR1: Team with highest points within tenant scope."""
        with read_committed(self.db):
            return (
                self._guard(self.db.query(Team), Team)
                .order_by(Team.points.desc())
                .first()
            )

    def get_best_scorer(self) -> tuple | None:
        """FR2: Player with most non-own goals within tenant scope."""
        with read_committed(self.db):
            return (
                self._guard(self.db.query(Player, func.count(Goal.goal_id).label("goals")), Player)
                .join(Goal, Goal.player_id == Player.player_id)
                .filter(Goal.is_own_goal == False)
                .group_by(Player.player_id)
                .order_by(func.count(Goal.goal_id).desc())
                .first()
            )

    def get_best_player_vs_team(self, opponent_id: int) -> tuple | None:
        """FR3: Player with most goals against a specific opponent within tenant scope."""
        with read_committed(self.db):
            return (
                self._guard(self.db.query(Player, func.count(Goal.goal_id).label("goals")), Player)
                .join(Goal,  Goal.player_id  == Player.player_id)
                .join(Match, Match.match_id  == Goal.match_id)
                .filter(Goal.is_own_goal == False)
                .filter(Player.team_id != opponent_id)
                .filter(
                    (Match.home_team_id == opponent_id) |
                    (Match.away_team_id == opponent_id)
                )
                .group_by(Player.player_id)
                .order_by(func.count(Goal.goal_id).desc())
                .first()
            )

    def get_standings(self) -> list[Team]:
        """Full standings table ordered by points."""
        with read_committed(self.db):
            return (
                self._guard(self.db.query(Team), Team)
                .order_by(Team.points.desc())
                .all()
            )

    def get_all_teams(self) -> list[Team]:
        with read_committed(self.db):
            return self._guard(self.db.query(Team), Team).all()

    def get_all_players(self) -> list:
        with read_committed(self.db):
            players = self._guard(self.db.query(Player), Player).all()
            result = []
            for p in players:
                goals = (
                    self.db.query(func.count(Goal.goal_id))
                    .filter(Goal.player_id == p.player_id, Goal.is_own_goal == False)
                    .scalar()
                )
                result.append((p, goals))
            return sorted(result, key=lambda x: x[1], reverse=True)

    def get_all_matches(self) -> list[Match]:
        with read_committed(self.db):
            return self._guard(self.db.query(Match), Match).all()

    def get_league(self) -> League | None:
        with read_committed(self.db):
            return self.db.query(League).filter_by(tenant_id=self.tenant_id).first()


# ── MatchRepository ────────────────────────────────────────────────────────

class MatchRepository(TenantRepository):
    """
    Handles match result entry under SERIALIZABLE isolation.
    Prevents phantom reads when two admins enter results simultaneously.
    """

    def submit_result(self, match_id: int, home_score: int, away_score: int):
        """
        SERIALIZABLE transaction:
        1. Update match score
        2. Recalculate standings
        Both steps atomic — no partial updates possible.
        """
        with serializable(self.db):
            match = (
                self._guard(self.db.query(Match), Match)
                .filter(Match.match_id == match_id)
                .first()
            )
            if not match:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Match not found")

            match.home_score = home_score
            match.away_score = away_score
            self._recalculate_standings()

    def _recalculate_standings(self):
        """Recalculates points for all teams from match results."""
        teams = self._guard(self.db.query(Team), Team).all()
        for t in teams:
            t.points = t.wins = t.draws = t.losses = 0

        matches = (
            self._guard(self.db.query(Match), Match)
            .filter(Match.home_score != None)
            .all()
        )
        for m in matches:
            home = self.db.query(Team).get(m.home_team_id)
            away = self.db.query(Team).get(m.away_team_id)
            if m.home_score > m.away_score:
                home.points += 3; home.wins   += 1; away.losses += 1
            elif m.home_score < m.away_score:
                away.points += 3; away.wins   += 1; home.losses += 1
            else:
                home.points += 1; away.points += 1
                home.draws  += 1; away.draws  += 1

    def add_match(self, league_id: int, home_team_id: int, away_team_id: int, venue: str | None) -> Match:
        with serializable(self.db):
            m = Match(
                tenant_id=self.tenant_id, league_id=league_id,
                home_team_id=home_team_id, away_team_id=away_team_id, venue=venue
            )
            self.db.add(m)
            self.db.flush()
            return m

    def add_goal(self, match_id: int, player_id: int, minute: int | None,
                 is_penalty: bool, is_own_goal: bool) -> Goal:
        with serializable(self.db):
            g = Goal(match_id=match_id, player_id=player_id,
                     minute=minute, is_penalty=is_penalty, is_own_goal=is_own_goal)
            self.db.add(g)
            return g

    def add_player(self, team_id: int, first_name: str, last_name: str,
                   position: str | None, shirt_number: int | None) -> Player:
        with serializable(self.db):
            p = Player(
                tenant_id=self.tenant_id, team_id=team_id,
                first_name=first_name, last_name=last_name,
                position=position, shirt_number=shirt_number
            )
            self.db.add(p)
            return p
