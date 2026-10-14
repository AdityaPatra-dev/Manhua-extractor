from .base import BaseExtractor
from .madara import MadaraExtractor
from .mangastream import MangaStreamExtractor
from .modern_ssr import ModernSSRExtractor
from .aggregator import AggregatorExtractor
from .heuristic import HeuristicExtractor
from .comick import ComicKExtractor
from .dispatcher import ExtractorDispatcher, dispatcher

__all__ = [
    "BaseExtractor",
    "MadaraExtractor",
    "MangaStreamExtractor",
    "ModernSSRExtractor",
    "AggregatorExtractor",
    "HeuristicExtractor",
    "ComicKExtractor",
    "ExtractorDispatcher",
    "dispatcher",
]

