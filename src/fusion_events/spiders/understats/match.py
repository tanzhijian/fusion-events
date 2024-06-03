import codecs
import json as jsonlib
import re
import typing
from dataclasses import dataclass
from enum import Enum

import httpx
from kloppy.domain import EventType
from parsel import Selector

from ...scraper import BaseSpider
from ._common import BASE_URL


class Content(Enum):
    INFO = "match_info"
    PLAYERS = "rostersData"
    SHOTS = "shotsData"


@dataclass
class Player:
    id: str
    name: str
    role: str


@dataclass
class Team:
    id: str
    name: str
    players: list[Player]


@dataclass
class Event:
    id: str
    type: EventType
    timestamp: str


@dataclass
class Match:
    id: str
    date: str
    time: str
    home_team: Team
    awat_team: Team
    events: list[Event]


class Spider(BaseSpider):
    def __init__(self, id: str) -> None:
        super().__init__()
        self.id = id

    @property
    def request(self) -> httpx.Request:
        url = f"{BASE_URL}/match/{self.id}"
        return httpx.Request("GET", url=url)

    def parse(self, response: httpx.Response) -> Match:
        # 参考了 https://github.com/amosbastian/understat/blob/master/understat/utils.py
        selector = Selector(response.text)
        scripts = selector.xpath("//script/text()").getall()
        match = self._find_data(scripts, Content.INFO)

        home_players, away_players = self._parse_players(scripts)
        home_team = Team(
            id=match["h"], name=match["team_h"], players=home_players
        )
        away_team = Team(
            id=match["a"], name=match["team_a"], players=away_players
        )

        shots = self._parse_shots(scripts)

        date, time = match["date"].split(" ")

        return Match(
            id=match["id"],
            date=date,
            time=time,
            home_team=home_team,
            awat_team=away_team,
            events=shots,
        )

    def _parse_shots(self, scripts: list[str]) -> list[Event]:
        events: list[Event] = []

        json = self._find_data(scripts, Content.SHOTS)
        for event in sum(json.values(), []):
            events.append(
                Event(
                    id=event["id"],
                    type=EventType.SHOT,
                    timestamp=event["minute"],
                )
            )
        return events

    def _parse_player(self, json: typing.Any) -> Player:
        return Player(
            id=json["id"],
            name=json["player"],
            role=json["position"],
        )

    def _parse_players(
        self,
        scripts: list[str],
    ) -> tuple[list[Player], list[Player]]:
        json = self._find_data(scripts, Content.PLAYERS)
        home_players = [
            self._parse_player(player) for player in json["h"].values()
        ]
        away_players = [
            self._parse_player(player) for player in json["a"].values()
        ]
        return home_players, away_players

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
