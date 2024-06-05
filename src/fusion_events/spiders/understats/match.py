import codecs
import json as jsonlib
import re
import typing
from enum import Enum

import httpx
from kloppy.domain import (
    DatasetFlag,
    Dimension,
    Event,
    EventDataset,
    Ground,
    KloppyCoordinateSystem,
    Metadata,
    Orientation,
    Period,
    PitchDimensions,
    Player,
    Point,
    Provider,
    Score,
    ShotEvent,
    ShotResult,
    Team,
)
from parsel import Selector

from ...scraper import BaseSpider
from ._common import BASE_URL, FIRST_HALF, SECOND_HALF


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

    def parse(self, response: httpx.Response) -> EventDataset:
        # 参考了 https://github.com/amosbastian/understat/blob/master/understat/utils.py
        selector = Selector(response.text)
        scripts = selector.xpath("//script/text()").getall()

        first_half = Period(id=1, start_timestamp=0.0, end_timestamp=FIRST_HALF)
        second_half = Period(
            id=2, start_timestamp=FIRST_HALF, end_timestamp=SECOND_HALF
        )

        home_team, away_team = self._parse_teams(scripts)
        match_info = self._find_data(scripts, Content.INFO)
        metadata = Metadata(
            teams=[home_team, away_team],
            periods=[first_half, second_half],
            pitch_dimensions=PitchDimensions(
                x_dim=Dimension(0, 1), y_dim=Dimension(0, 1)
            ),
            orientation=Orientation.FIXED_AWAY_HOME,
            flags=DatasetFlag.BALL_OWNING_TEAM,
            provider=Provider.OTHER,
            coordinate_system=KloppyCoordinateSystem(
                normalized=True, length=1, width=1
            ),
            score=Score(
                home=int(match_info["h_goals"]), away=int(match_info["a_goals"])
            ),
        )

        shots_data = self._find_data(scripts, Content.SHOTS)
        records: list[Event] = []
        players_index = {
            player.player_id: player
            for player in home_team.players + away_team.players
        }
        for shot in sum(shots_data.values(), []):
            shot = ShotEvent(
                event_id=shot["id"],
                period=first_half
                if (int(shot["minute"]) * 60) < FIRST_HALF
                else second_half,
                timestamp=int(shot["minute"]) * 60,
                team=home_team if shot["h_a"] == "h" else away_team,
                player=players_index[shot["player_id"]],
                coordinates=Point(x=shot["X"], y=shot["Y"]),
                result=self._transform_result(shot["result"]),
                raw_event=shot,
                ball_state=None,
                ball_owning_team=None,
                freeze_frame=None,
                state={},
                related_event_ids=[],
                qualifiers=[],
            )
        records.sort(key=lambda shot: shot.timestamp)
        return EventDataset(records=records, metadata=metadata)

    def _parse_players(
        self,
        scripts: list[str],
        home_team: Team,
        away_team: Team,
    ) -> tuple[list[Player], list[Player]]:
        rosters_data = self._find_data(scripts, Content.PLAYERS)
        home_players = [
            Player(
                player_id=player["player_id"],
                team=home_team,
                jersey_no=1,
                name=player["player"],
            )
            for player in rosters_data["h"].values()
        ]
        away_players = [
            Player(
                player_id=player["player_id"],
                team=away_team,
                jersey_no=1,
                name=player["player"],
            )
            for player in rosters_data["a"].values()
        ]
        return home_players, away_players

    def _parse_teams(self, scripts: list[str]) -> tuple[Team, Team]:
        match_info = self._find_data(scripts, Content.INFO)
        home_team = Team(
            team_id=match_info["h"],
            name=match_info["team_h"],
            ground=Ground.HOME,
        )
        away_team = Team(
            team_id=match_info["a"],
            name=match_info["team_a"],
            ground=Ground.AWAY,
        )
        home_players, away_players = self._parse_players(
            scripts, home_team, away_team
        )
        home_team.players.extend(home_players)
        away_team.players.extend(away_players)
        return home_team, away_team

    def _transform_result(self, result: str) -> ShotResult:
        match result:
            case "Goal":
                return ShotResult.GOAL
            case "SavedShot":
                return ShotResult.SAVED
            case "MissedShots":
                return ShotResult.OFF_TARGET
            case "Post":
                return ShotResult.POST
            case "BlockedShot":
                return ShotResult.BLOCKED
            case _:
                return ShotResult.OWN_GOAL

    def _generate_pattern(self, content: Content) -> str:
        return rf"{content.value}\s+=\s+JSON.parse\(\'(.*?)\'\)"

    def _find_data(self, scripts: list[str], content: Content) -> typing.Any:
        pattern = self._generate_pattern(content)
        for script in scripts:
            match = re.search(pattern, script)
            if match is not None:
                byte_data = codecs.escape_decode(match.group(1))
                data = jsonlib.loads(byte_data[0])
                return data

        raise ValueError(f"{content} not found")
