import httpx
import pytest
from fusion_events.spiders.understats import match


class TestMatchSpider:
    @pytest.fixture(scope="class")
    def spider(self) -> match.Spider:
        return match.Spider(id="22256")

    @pytest.fixture(scope="class")
    def response(self) -> httpx.Response:
        with open("tests/data/understats/match-22256.html") as file:
            return httpx.Response(200, text=file.read())

    def test_request(self, spider: match.Spider) -> None:
        assert spider.request.url == "https://understat.com/match/22256"

    def test_parse(
        self, spider: match.Spider, response: httpx.Response
    ) -> None:
        match = spider.parse(response)
        assert match.id == "22256"
