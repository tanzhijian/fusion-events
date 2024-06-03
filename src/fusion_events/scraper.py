import typing
from abc import ABC, abstractmethod

import httpx


class BaseSpider(ABC):
    @property
    @abstractmethod
    def request(self) -> httpx.Request: ...

    @abstractmethod
    def parse(self, response: httpx.Response) -> typing.Any: ...
