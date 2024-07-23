from typing import Any

import httpx
from that_game import Competition, Game, Location, Pitch, Player, Shot, Team
from that_game._status import BodyPart, Period, ShotPattern, ShotResult

from ...scraper import BaseSpider

BASE_URL = "https://www.fotmob.com/api/"


class Spider(BaseSpider):
    def __init__(self, id: str) -> None:
        super().__init__()
        self._id = id

    @property
    def request(self) -> httpx.Request:
        url = f"{BASE_URL}/matchDetails"
        return httpx.Request("GET", url=url, params={"matchId": self._id})

    def parse(self, response: httpx.Response) -> Game:
        loader = Loader(response.json())
        return loader.game


class Loader:
    def __init__(self, match_details: Any) -> None:
        self._raw_game = match_details

        info = self._raw_game["general"]
        self._competition = Competition(
            id=str(info["leagueId"]),
            name=info["leagueName"],
        )
        self._teams = (
            Team(id=str(info["homeTeam"]["id"]), name=info["homeTeam"]["name"]),
            Team(id=str(info["awayTeam"]["id"]), name=info["awayTeam"]["name"]),
        )
        self._home_players = self._parse_players(
            self._raw_game["lineup"]["lineup"][0]
        )
        self._away_players = self._parse_players(
            self._raw_game["lineup"]["lineup"][1]
        )
        self._pitch = Pitch(length=105, width=68, width_direction="down")

    def _parse_players(self, lineup: Any) -> dict[str, Player]:
        players: dict[str, Player] = {}
        for group in lineup["players"]:
            for player in group:
                id_ = player["id"]
                players[id_] = Player(
                    id=id_,
                    name=player["name"]["fullName"],
                    position=player["position"],
                )
        for player in lineup["bench"]:
            id_ = player["id"]
            players[id_] = Player(
                id=id_,
                name=player["name"]["fullName"],
                position=player["position"],
            )
        return players

    @property
    def competition(self) -> Competition:
        return self._competition

    @property
    def home_team(self) -> Team:
        return self._teams[0]

    @property
    def away_team(self) -> Team:
        return self._teams[1]

    @property
    def home_players(self) -> list[Player]:
        return list(self._home_players.values())

    @property
    def away_players(self) -> list[Player]:
        return list(self._away_players.values())

    @property
    def pitch(self) -> Pitch:
        return self._pitch

    def _find_team(self, id: str) -> Team:
        return self._teams[0] if self._teams[0].id == id else self._teams[1]

    def _find_player(self, id: str) -> Player:
        return self._home_players.get(id) or self._away_players[id]

    @property
    def shots(self) -> list[Shot]:
        shots: list[Shot] = []
        for shot in self._raw_game["content"]["shotmap"]["shots"]:
            shots.append(
                Shot(
                    id=str(shot["id"]),
                    type="shot",
                    period=PERIODS["period"],
                    # 没有考虑 period，没有考虑伤停补时
                    seconds=shot["min"] * 60,
                    team=self._find_team(str(shot["teamId"])),
                    player=self._find_player(str(shot["playerId"])),
                    location=Location(
                        x=shot["x"],
                        y=shot["y"],
                        pitch=self._pitch,
                    ),
                    # fotmob 还有一个 block 的坐标可以考虑
                    end_location=Location(
                        x=self._pitch.length,
                        y=shot["goalCrossedY"],
                        z=shot["goalCrossedZ"],
                        pitch=self._pitch,
                    ),
                    pattern=SHOT_PATTERNS.get(shot["situation"], "open_play"),
                    body_part=BODY_PARTS.get(shot["shotType"], "unknown"),
                    result=SHOT_RESULTS[shot["eventType"]],
                )
            )
        return shots

    @property
    def game(self) -> Game:
        return Game(
            id=self._raw_game["general"]["matchId"],
            datetime=self._raw_game["general"]["matchTimeUTCDate"],
            home_team=self.home_team,
            away_team=self.away_team,
            home_players=self.home_players,
            away_players=self.away_players,
            competition=self._competition,
            events=self.shots,
        )


PERIODS: dict[str, Period] = {
    "FirstHalf": "first_half",
    "SecondHalf": "second_half",
    "FirstExtraHalf": "first_extra",
    "SecondExtraHalf": "second_extra",
    "PenaltyShootout": "penalty_shootout",
}
SHOT_PATTERNS: dict[str, ShotPattern] = {
    "RegularPlay": "open_play",
    "FreeKick": "freekick",
    "Penalty": "penalty",
}
SHOT_RESULTS: dict[str, ShotResult] = {
    "Miss": "missed",
    "AttemptSaved": "saved",
    "Goal": "goal",
}
BODY_PARTS: dict[str, BodyPart] = {
    "RightFoot": "right_foot",
    "Header": "head",
    "LeftFoot": "left_foot",
}
