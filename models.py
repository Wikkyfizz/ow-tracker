from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class HeroEntry(BaseModel):
    hero: str
    # Manual entry cycles 25/50/75/100, but SUMMARY-tab playtime OCR yields exact
    # percentages (e.g. 47/41/12), so accept any 1–100.
    pct: int = Field(ge=1, le=100, description="playtime percent (1–100)")


class SessionCreate(BaseModel):
    goal: str = ""
    focus_mode: bool = False


class SessionUpdate(BaseModel):
    goal: Optional[str] = None
    focus_mode: Optional[bool] = None
    name: Optional[str] = None
    notes: Optional[str] = None


class MatchParticipant(BaseModel):
    player_name: str = ""
    team: str  # "ally" or "enemy"
    heroes: list[HeroEntry] = []
    stats: dict = {}
    name_confidence: float = 1.0


class MatchCreate(BaseModel):
    played_at: Optional[datetime] = None
    map: str
    outcome: str  # Win / Loss / Draw
    my_heroes: list[HeroEntry] = []       # heroes *I* played (drives hero win-rates)
    my_team_heroes: list[HeroEntry] = []  # my full team's comp (drives my_comp only)
    enemy_heroes: list[HeroEntry] = []    # enemy team's full comp
    my_comp: str = ""
    enemy_comp: str = ""
    rank_tier: str = ""
    rank_division: Optional[int] = None
    rank_pct: Optional[float] = None
    elims: Optional[int] = None
    deaths: Optional[int] = None
    assists: Optional[int] = None
    damage: Optional[int] = None
    healing: Optional[int] = None
    mitigation: Optional[int] = None
    game_length_s: Optional[int] = None
    session_id: Optional[int] = None
    notes: str = ""
    tags: str = ""
    bans: list[str] = []
    teammates: list[str] = []
    stack_size: int = 1
    screenshot_path: str = ""
    data_source: str = "manual"
    practiced: Optional[str] = None
    practice_notes: str = ""
    is_historical: bool = False
    participants: list[MatchParticipant] = []


class MatchUpdate(MatchCreate):
    pass


class MatchOut(MatchCreate):
    id: int
    played_at: datetime
    rank_score: Optional[float] = None

    class Config:
        from_attributes = True


class MapUpdate(BaseModel):
    comp_affinity: str
    notes: Optional[str] = None


class TrackedPlayer(BaseModel):
    name: str
    alias: str = ""


class Settings(BaseModel):
    username: str = "DROWZY"
    battletag: str = ""
    inbox_folder: str = "C:\\OW-Tracker\\inbox"
    tracked_players: list[TrackedPlayer] = []


class ParsedMatch(BaseModel):
    map: str = ""
    outcome: str = ""
    my_heroes: list[HeroEntry] = []
    enemy_heroes: list[HeroEntry] = []
    elims: Optional[int] = None
    deaths: Optional[int] = None
    assists: Optional[int] = None
    damage: Optional[int] = None
    healing: Optional[int] = None
    mitigation: Optional[int] = None
    teammates: list[str] = []
    stack_size: int = 1
    confidence: float = 0.0
    warnings: list[str] = []
