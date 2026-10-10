from .optimizer import optimize_panel_image
from .downloader import (
    download_panels_stream,
    get_staging_dir,
    cleanup_staging_dir
)
from .slicer import (
    slice_panel_image,
    slice_chapter_panels
)
from .compiler import (
    compile_pdf,
    compile_cbz,
    save_raw_images,
    get_chapter_page_count,
    get_chapter_page_bytes
)
from .notifier import dispatch_notification, send_test_alert
from .ad_filter import (
    compute_perceptual_hash,
    hash_distance,
    match_promo_signature,
    filter_chapter_panels
)
from .scrobbler import (
    verify_anilist_token,
    search_anilist_manga,
    update_anilist_progress,
    verify_mal_token,
    search_mal_manga,
    update_mal_progress,
    sync_trackers
)

__all__ = [
    "optimize_panel_image",
    "download_panels_stream",
    "get_staging_dir",
    "cleanup_staging_dir",
    "slice_panel_image",
    "slice_chapter_panels",
    "compile_pdf",
    "compile_cbz",
    "save_raw_images",
    "get_chapter_page_count",
    "get_chapter_page_bytes",
    "dispatch_notification",
    "send_test_alert",
    "compute_perceptual_hash",
    "hash_distance",
    "match_promo_signature",
    "filter_chapter_panels",
    "verify_anilist_token",
    "search_anilist_manga",
    "update_anilist_progress",
    "verify_mal_token",
    "search_mal_manga",
    "update_mal_progress",
    "sync_trackers"
]


