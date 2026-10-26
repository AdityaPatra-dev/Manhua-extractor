from .base import BaseExtractor
from .madara import MadaraExtractor
from .mangastream import MangaStreamExtractor
from .modern_ssr import ModernSSRExtractor
from .aggregator import AggregatorExtractor
from .heuristic import HeuristicExtractor
from .comick import ComicKExtractor
from .hitomi import HitomiExtractor
from .hentaifox import HentaiFoxExtractor
from .threehentai import ThreeHentaiExtractor
from .nhentaito import NHentaiToExtractor
from .hentainame import HentaiNameExtractor
from .nhentaicom import NHentaiComExtractor
from .dispatcher import ExtractorDispatcher, dispatcher

__all__ = [
    "BaseExtractor",
    "MadaraExtractor",
    "MangaStreamExtractor",
    "ModernSSRExtractor",
    "AggregatorExtractor",
    "HeuristicExtractor",
    "ComicKExtractor",
    "HitomiExtractor",
    "HentaiFoxExtractor",
    "ThreeHentaiExtractor",
    "NHentaiToExtractor",
    "HentaiNameExtractor",
    "NHentaiComExtractor",
    "ExtractorDispatcher",
    "dispatcher",
]

