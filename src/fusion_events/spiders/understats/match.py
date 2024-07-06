import codecs
import json as jsonlib
import re
from enum import Enum
from typing import Any, Literal

import httpx
from parsel import Selector
from that_game import Competition, Game, Location, Pitch, Player, Shot, Team
from that_game._status import BodyPart, ShotPattern, ShotResult

from ...scraper import BaseSpider
from ._common import BASE_URL


class Content(Enum):
    INFO = "match_info"
    PLAYERS = "rostersData"
    SHOTS = "shotsData"


class Spider(BaseSpider):
    def __init__(self, id: str) -> None:
        super().__init__()
        self.id = id

    @property
    def request(self) -> httpx.Request:
        url = f"{BASE_URL}/match/{self.id}"
        return httpx.Request("GET", url=url)

    def parse(self, response: httpx.Response) -> Game:
        # 参考了 https://github.com/amosbastian/understat/blob/master/understat/utils.py
        selector = Selector(response.text)
        scripts = selector.xpath("//script/text()").getall()
        match_info = self._find_data(scripts, Content.INFO)
        rosters_data = self._find_data(scripts, Content.PLAYERS)
        shots_data = self._find_data(scripts, Content.SHOTS)

        loader = Loader(match_info, rosters_data, shots_data)
        return loader.game

    def _generate_pattern(self, content: Content) -> str:
        return rf"{content.value}\s+=\s+JSON.parse\(\'(.*?)\'\)"

    def _find_data(self, scripts: list[str], content: Content) -> Any:
        pattern = self._generate_pattern(content)
        for script in scripts:
            match = re.search(pattern, script)
            if match is not None:
                byte_data = codecs.escape_decode(match.group(1))
                data = jsonlib.loads(byte_data[0])
                return data

        raise ValueError(f"{content} not found")


class Loader:
    def __init__(
        self,
        match_info: Any,
        rosters_data: Any,
        shots_data: Any,
    ) -> None:
        self._raw_game = match_info
        self._raw_lineups = rosters_data
        self._raw_shots = shots_data

        self._competition = Competition(
            id=self._raw_game["league_id"], name=self._raw_game["league"]
        )
        self._teams = (
            Team(id=self._raw_game["h"], name=self._raw_game["team_h"]),
            Team(id=self._raw_game["a"], name=self._raw_game["team_a"]),
        )
        self._home_players = {
            (id_ := player["player_id"]): Player(
                id=id_, name=player["player"], position=player["position"]
            )
            for player in self._raw_lineups["h"].values()
        }
        self._away_players = {
            (id_ := player["player_id"]): Player(
                id=id_, name=player["player"], position=player["position"]
            )
            for player in self._raw_lineups["a"].values()
        }

        self._home_pitch = Pitch(length=1, width=1)
        self._away_pitch = Pitch(length=1, width=1, length_direction="left")

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
    def competition(self) -> Competition:
        return self._competition

    def pitch(self, team_side: Literal["home", "away"]) -> Pitch:
        return self._home_pitch if team_side == "home" else self._away_pitch

    def _find_player(self, player_id: str) -> Player:
        return (
            self._home_players.get(player_id) or self._away_players[player_id]
        )

    @property
    def shots(self) -> list[Shot]:
        shots: list[Shot] = []
        end_location = Location(x=0, y=0, pitch=self._home_pitch)
        for shot in self._raw_shots["h"]:
            shots.append(
                Shot(
                    id=shot["id"],
                    type="shot",
                    period="first_half",
                    seconds=int(shot["minute"]) * 60,
                    team=self.home_team,
                    player=self._find_player(shot["player_id"]),
                    location=Location(
                        x=shot["X"],
                        y=shot["Y"],
                        pitch=self._home_pitch,
                    ),
                    end_location=end_location,
                    result=SHOT_RESULTS[shot["result"]],
                    pattern=SHOT_PATTERNS.get(shot["situation"]) or "open_play",
                    body_part=BODY_PARTS[shot["shotType"]],
                )
            )
        return shots

    @property
    def game(self) -> Game:
        return Game(
            id=self._raw_game["id"],
            datetime=self._raw_game["date"],
            home_team=self.home_team,
            away_team=self.away_team,
            home_players=self.home_players,
            away_players=self.away_players,
            competition=self.competition,
            events=self.shots,
        )


SHOT_RESULTS: dict[str, ShotResult] = {
    "OwnGoal": "own_goal",
    "Goal": "goal",
    "SavedShot": "saved",
    "MissedShots": "missed",
    "BlockedShot": "blocked",
}
SHOT_PATTERNS: dict[str, ShotPattern] = {
    "DirectFreekick": "freekick",
    "OpenPlay": "open_play",
    "Penalty": "penalty",
}
BODY_PARTS: dict[str, BodyPart] = {
    "RightFoot": "right_foot",
    "LeftFoot": "left_foot",
    "Head": "head",
    "OtherBodyPart": "other",
}
