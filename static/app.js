document.addEventListener("DOMContentLoaded", () => {
  // --- Toast Notifications ---
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) {
      console.log(`[${type}] ${message}`);
      return;
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    if (type === "error") icon = "⚠️";
    toast.innerHTML = `<span>${icon}</span><span style="flex: 1;">${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = "toastOut 0.25s forwards";
      setTimeout(() => toast.remove(), 250);
    }, 3500);
  }

  // --- Haptic Feedback Helper ---
  function triggerHaptic(pattern = [15]) {
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      try { navigator.vibrate(pattern); } catch (e) {}
    }
  }

  // --- Tab Navigation ---
  const navTabs = document.querySelectorAll(".nav-tab");
  const tabContents = document.querySelectorAll(".tab-content");

  function switchTab(targetId) {
    triggerHaptic([12]);
    navTabs.forEach((t) => {
      if (t.getAttribute("data-tab") === targetId) {
        t.classList.add("active");
      } else {
        t.classList.remove("active");
      }
    });
    tabContents.forEach((c) => {
      if (c.id === targetId) {
        c.classList.add("active");
      } else {
        c.classList.remove("active");
      }
    });

    if (targetId === "tab-library") {
      loadLibrary();
    } else if (targetId === "tab-lab") {
      loadDiagnosticsTable();
    } else if (targetId === "tab-settings") {
      loadSettings();
    } else if (targetId === "tab-queue") {
      fetchAndRenderQueue();
    }
  }

  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const targetId = tab.getAttribute("data-tab");
      switchTab(targetId);
    });
  });

  // --- Library Update Button ---
  const btnUpdateLibrary = document.getElementById("btn-update-library");
  if (btnUpdateLibrary) {
    btnUpdateLibrary.addEventListener("click", async () => {
      btnUpdateLibrary.textContent = "Checking...";
      btnUpdateLibrary.disabled = true;
      triggerHaptic([10]);
      try {
        const res = await fetch("/api/library/update", { method: "POST" });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || "Checking library for updates... New chapters will appear in Download Queue.", "info");
          fetchAndRenderQueue();
        } else {
          showToast("Error: " + data.error, "error");
        }
      } catch (e) {
        showToast("Network error: " + e.message, "error");
      } finally {
        btnUpdateLibrary.textContent = "🔄 Check Updates";
        btnUpdateLibrary.disabled = false;
      }
    });
  }

  // --- Download Options Visibility ---
  const downloadModeSelect = document.getElementById("download-mode");
  const countField = document.getElementById("count-field");

  downloadModeSelect.addEventListener("change", () => {
    if (downloadModeSelect.value === "range") {
      countField.style.display = "block";
    } else {
      countField.style.display = "none";
    }
  });

  // --- Series Chapter Catalog Inspector ---
  let currentCatalogChapters = [];
  let currentCatalogUrl = "";
  let currentSeriesTitle = "";
  let currentCatalogCoverUrl = "";
  const selectedCatalogUrls = new Set();
  let lastHandledProgressStatus = null;

  const chapterUrlInput = document.getElementById("chapter-url");
  const btnInspect = document.getElementById("btn-inspect");
  const btnAnalyze = document.getElementById("btn-analyze");
  const previewCard = document.getElementById("analyze-preview");
  const seriesCatalogCard = document.getElementById("series-catalog-card");
  const catFilterInput = document.getElementById("cat-filter-input");
  const btnSelectAll = document.getElementById("btn-select-all");
  const btnDeselectAll = document.getElementById("btn-deselect-all");
  const btnDownloadSelected = document.getElementById("btn-download-selected");
  const catSelectedCount = document.getElementById("cat-selected-count");

  async function inspectSeries(url, isSilent = false, coverUrl = null) {
    if (!url) {
      if (!isSilent) showToast("Please enter a valid manga or chapter URL.", "info");
      return;
    }

    currentCatalogCoverUrl = coverUrl || "";

    const coverImg = document.getElementById("cat-series-cover");
    if (coverImg) {
      coverImg.onerror = function() {
        this.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="110"><rect fill="%231c2640" width="80" height="110"/><text fill="%2394a3b8" x="50%" y="50%" text-anchor="middle" font-size="10">No Cover</text></svg>';
      };
      if (coverUrl) {
        coverImg.src = `/api/cover-proxy?url=${encodeURIComponent(coverUrl)}`;
        coverImg.style.display = "block";
      } else {
        // Clear previous cover immediately so it does not stay visible for a new direct URL
        coverImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="110"><rect fill="%231c2640" width="80" height="110"/><text fill="%2394a3b8" x="50%" y="50%" text-anchor="middle" font-size="10">Loading...</text></svg>';
      }
    }

    if (!isSilent && btnInspect) {
      btnInspect.textContent = "🔍 Browsing...";
      btnInspect.disabled = true;
    }

    try {
      const res = await fetch("/api/inspect-series", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, cover_url: coverUrl || undefined })
      });
      const data = await res.json();

      if (data.success) {
        currentCatalogChapters = data.chapters || [];
        currentCatalogUrl = url;
        currentSeriesTitle = data.series_title || "Unknown Series";
        currentCatalogCoverUrl = data.cover_url || coverUrl || "";

        // Populate catalog card header
        if (coverImg) {
          const effCover = currentCatalogCoverUrl;
          if (effCover) {
            coverImg.src = `/api/cover-proxy?url=${encodeURIComponent(effCover)}`;
            coverImg.style.display = "block";
          } else {
            coverImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="110"><rect fill="%231c2640" width="80" height="110"/><text fill="%2394a3b8" x="50%" y="50%" text-anchor="middle" font-size="10">No Cover</text></svg>';
          }
        }

        const badgeElem = document.getElementById("cat-engine-badge");
        if (badgeElem) badgeElem.textContent = `Engine: ${data.engine_name || 'Auto'}`;

        const titleElem = document.getElementById("cat-series-title");
        if (titleElem) titleElem.textContent = data.series_title || "Discovered Series";

        const statsElem = document.getElementById("cat-stats");
        if (statsElem) {
          statsElem.textContent = `📊 ${data.total_chapters} chapters found (${data.downloaded_count} downloaded)`;
        }

        const synElem = document.getElementById("cat-synopsis");
        if (synElem) {
          synElem.textContent = data.synopsis || "Select chapters below to download or read.";
        }

        if (catFilterInput) catFilterInput.value = "";
        renderCatalogChapters("");
        if (seriesCatalogCard) {
          seriesCatalogCard.classList.remove("hidden");
          if (!isSilent) {
            seriesCatalogCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        }
      } else {
        if (!isSilent) showToast(`Failed to inspect catalog: ${data.error || 'Unknown error'}`, "error");
      }
    } catch (err) {
      if (!isSilent) showToast(`Network error inspecting series: ${err.message}`, "error");
    } finally {
      if (!isSilent && btnInspect) {
        btnInspect.textContent = "🔍 Browse Chapters";
        btnInspect.disabled = false;
      }
    }
  }

  function renderCatalogChapters(filterText = "") {
    const listContainer = document.getElementById("catalog-chapters-list");
    if (!listContainer) return;

    const filter = (filterText || "").toLowerCase();
    const filtered = currentCatalogChapters.filter(ch => {
      const titleStr = (ch.title || `Chapter ${ch.chapter_num}`).toLowerCase();
      const numStr = String(ch.chapter_num);
      return !filter || titleStr.includes(filter) || numStr.includes(filter);
    });

    if (filtered.length === 0) {
      listContainer.innerHTML = '<p style="padding: 1rem; color: var(--text-muted); text-align: center;">No matching chapters found.</p>';
      updateCatalogSelectedCount();
      return;
    }

    listContainer.innerHTML = filtered.map(ch => {
      const chTitle = ch.title || `Chapter ${ch.chapter_num}`;
      const isSaved = ch.is_downloaded;
      const isChecked = selectedCatalogUrls.has(ch.url);
      const encodedUrl = encodeURIComponent(ch.url);
      return `
        <div class="catalog-chapter-row" data-url="${ch.url}">
          <div class="catalog-chapter-left">
            <input type="checkbox" class="cat-ch-checkbox" data-url="${ch.url}" ${isChecked ? 'checked' : ''} style="width: 18px; height: 18px; cursor: pointer; accent-color: var(--accent);">
            <div style="cursor: pointer;" onclick="toggleCatalogCheckbox('${ch.url}')">
              <strong style="font-size: 0.95rem; color: var(--text-main);">${chTitle}</strong>
              ${ch.read_status === 1 ? '<span style="margin-left: 6px; font-size: 0.75rem; color: #a78bfa;">✓ Read</span>' : ''}
            </div>
          </div>
          <div class="catalog-chapter-right">
            ${isSaved 
              ? `<span class="badge-local">🟢 Saved</span>
                 <button class="btn-read-now" onclick="openReader(${ch.chapter_id})">📖 Read Now</button>
                 <a href="/api/download/file/${ch.chapter_id}" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; text-decoration: none;" download title="Save ${ch.file_format || 'CBZ'}">💾</a>`
              : `<span class="badge-online">⚪ Online</span>
                 <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem;" onclick="window.downloadSingleCatalogChapter('${encodedUrl}')">⬇️ Download</button>`
            }
          </div>
        </div>
      `;
    }).join("");

    const checkboxes = listContainer.querySelectorAll(".cat-ch-checkbox");
    checkboxes.forEach(cb => {
      cb.addEventListener("change", (e) => {
        const u = cb.getAttribute("data-url");
        if (cb.checked) {
          selectedCatalogUrls.add(u);
        } else {
          selectedCatalogUrls.delete(u);
        }
        updateCatalogSelectedCount();
      });
    });
    updateCatalogSelectedCount();
  }

  window.toggleCatalogCheckbox = function(url) {
    const cb = document.querySelector(`.cat-ch-checkbox[data-url="${url}"]`);
    if (cb) {
      cb.checked = !cb.checked;
      if (cb.checked) {
        selectedCatalogUrls.add(url);
      } else {
        selectedCatalogUrls.delete(url);
      }
      updateCatalogSelectedCount();
    } else {
      if (selectedCatalogUrls.has(url)) {
        selectedCatalogUrls.delete(url);
      } else {
        selectedCatalogUrls.add(url);
      }
      updateCatalogSelectedCount();
    }
  };

  function updateCatalogSelectedCount() {
    if (catSelectedCount) {
      catSelectedCount.textContent = selectedCatalogUrls.size;
    }
  }

  if (btnInspect) {
    btnInspect.addEventListener("click", () => {
      const url = chapterUrlInput.value.trim();
      inspectSeries(url);
    });
  }

  if (chapterUrlInput) {
    chapterUrlInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        btnInspect.click();
      }
    });
  }

  if (catFilterInput) {
    catFilterInput.addEventListener("input", () => {
      renderCatalogChapters(catFilterInput.value.trim());
    });
  }

  if (btnSelectAll) {
    btnSelectAll.addEventListener("click", () => {
      currentCatalogChapters.forEach(ch => {
        if (ch.url) selectedCatalogUrls.add(ch.url);
      });
      const checkboxes = document.querySelectorAll(".cat-ch-checkbox");
      checkboxes.forEach(cb => {
        cb.checked = true;
      });
      updateCatalogSelectedCount();
    });
  }

  if (btnDeselectAll) {
    btnDeselectAll.addEventListener("click", () => {
      const checkboxes = document.querySelectorAll(".cat-ch-checkbox");
      checkboxes.forEach(cb => cb.checked = false);
      selectedCatalogUrls.clear();
      updateCatalogSelectedCount();
    });
  }

  if (btnDownloadSelected) {
    btnDownloadSelected.addEventListener("click", () => {
      const urls = Array.from(selectedCatalogUrls);
      startCatalogDownload(urls);
    });
  }

  window.downloadSingleCatalogChapter = function(encodedUrl) {
    const url = decodeURIComponent(encodedUrl);
    startCatalogDownload([url]);
  };

  async function startCatalogDownload(urls) {
    if (!urls || urls.length === 0) {
      showToast("Please select at least one chapter to download.", "info");
      return;
    }

    const format = document.getElementById("output-format").value;
    const maxWidth = parseInt(document.getElementById("max-width").value) || 1080;
    const sliceEink = document.getElementById("slice-eink").checked;
    const imageFormat = document.getElementById("image-encoding") ? document.getElementById("image-encoding").value : "webp";
    const upscaleScale = document.getElementById("upscale-factor") ? parseInt(document.getElementById("upscale-factor").value, 10) : 1;
    const filterPromosElem = document.getElementById("filter-promos");
    const filterPromos = filterPromosElem ? filterPromosElem.checked : true;

    if (btnStartDownload) btnStartDownload.disabled = true;
    if (btnDownloadSelected) btnDownloadSelected.disabled = true;

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: urls[0],
          chapter_urls: urls,
          mode: "range",
          count: urls.length,
          format: format,
          max_width: maxWidth,
          image_format: imageFormat,
          upscale_scale: upscaleScale,
          slice_eink: sliceEink,
          filter_promos: filterPromos,
          cover_url: currentCatalogCoverUrl || undefined,
          series_title: currentSeriesTitle || undefined
        })
      });

      const data = await res.json();
      if (data.success) {
        selectedCatalogUrls.clear();
        updateCatalogSelectedCount();
        const checkboxes = document.querySelectorAll(".cat-ch-checkbox");
        checkboxes.forEach(cb => cb.checked = false);

        if (window.AndroidApp && typeof window.AndroidApp.notifyDownloadStarted === "function") {
          window.AndroidApp.notifyDownloadStarted();
        }
        if (data.queued) {
          showToast(data.message || `Added '${data.series_title || "Series"}' to Download Queue (#${data.queue_position || 'in queue'})`, "success");
        } else {
          showToast(data.message || "Download started!", "success");
        }
        progressCard.classList.remove("hidden");
        listenToProgress();
        fetchAndRenderQueue();
      } else {
        showToast(`Error starting download: ${data.error}`, "error");
      }
    } catch (err) {
      showToast(`Failed to launch download: ${err.message}`, "error");
    } finally {
      if (btnStartDownload) btnStartDownload.disabled = false;
      if (btnDownloadSelected) btnDownloadSelected.disabled = false;
    }
  }

  // --- Analyze URL ---
  btnAnalyze.addEventListener("click", async () => {
    const url = chapterUrlInput.value.trim();
    if (!url) {
      showToast("Please enter a valid chapter URL.", "info");
      return;
    }

    btnAnalyze.textContent = "Analyzing...";
    btnAnalyze.disabled = true;

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      if (data.success) {
        document.getElementById("preview-engine-badge").textContent = `Engine: ${data.engine_name}`;
        document.getElementById("preview-title").textContent = data.series_title || "Unknown Series";
        document.getElementById("preview-ch").textContent = data.chapter_num || "1";
        document.getElementById("preview-panels").textContent = data.panel_count || "0";

        const nextElem = document.getElementById("preview-next-text");
        if (data.next_chapter_url) {
          nextElem.textContent = "✅ Next chapter link detected in navigation!";
        } else {
          nextElem.textContent = "ℹ️ Will use smart template incrementation for subsequent chapters.";
        }
        previewCard.classList.remove("hidden");
      } else {
        showToast(`Analysis failed: ${data.error || "Could not isolate chapter layout."}`, "error");
      }
    } catch (err) {
      showToast(`Network error during analysis: ${err.message}`, "error");
    } finally {
      btnAnalyze.textContent = "Analyze";
      btnAnalyze.disabled = false;
    }
  });

  // --- Start Download ---
  const btnStartDownload = document.getElementById("btn-start-download");
  const progressCard = document.getElementById("progress-card");
  const btnPauseDownload = document.getElementById("btn-pause-download");
  const btnStopDownload = document.getElementById("btn-stop-download");
  const btnDismissProgress = document.getElementById("btn-dismiss-progress");

  if (btnDismissProgress && progressCard) {
    btnDismissProgress.addEventListener("click", () => {
      progressCard.classList.add("hidden");
    });
  }

  if (btnPauseDownload) {
    btnPauseDownload.addEventListener("click", async () => {
      try {
        const isCurrentlyPaused = btnPauseDownload.getAttribute("data-paused") === "true";
        const endpoint = isCurrentlyPaused ? "/api/download/resume" : "/api/download/pause";
        btnPauseDownload.disabled = true;
        const res = await fetch(endpoint, { method: "POST" });
        const data = await res.json();
        if (!data.success) {
          showToast(data.error || data.message || "Failed to toggle pause", "error");
        }
      } catch (err) {
        showToast(`Pause/Resume error: ${err.message}`, "error");
      } finally {
        btnPauseDownload.disabled = false;
      }
    });
  }

  if (btnStopDownload) {
    btnStopDownload.addEventListener("click", async () => {
      try {
        btnStopDownload.disabled = true;
        btnStopDownload.textContent = "⏹️ Stopping...";
        const res = await fetch("/api/download/stop", { method: "POST" });
        const data = await res.json();
        if (!data.success) {
          showToast(data.error || data.message || "Failed to stop download", "error");
        } else {
          showToast("Download stop requested.", "info");
        }
      } catch (err) {
        showToast(`Stop error: ${err.message}`, "error");
      } finally {
        btnStopDownload.disabled = false;
        btnStopDownload.textContent = "⏹️ Stop";
      }
    });
  }

  btnStartDownload.addEventListener("click", async () => {
    // If chapters are selected in the catalog, prioritize downloading the selected chapters!
    if (selectedCatalogUrls && selectedCatalogUrls.size > 0) {
      startCatalogDownload(Array.from(selectedCatalogUrls));
      return;
    }

    const url = chapterUrlInput.value.trim();
    if (!url) {
      showToast("Please enter a chapter URL first.", "info");
      return;
    }

    const mode = downloadModeSelect.value;
    const count = parseInt(document.getElementById("chapter-count").value) || 1;
    const format = document.getElementById("output-format").value;
    const maxWidth = parseInt(document.getElementById("max-width").value) || 1080;
    const sliceEink = document.getElementById("slice-eink").checked;
    const imageFormat = document.getElementById("image-encoding") ? document.getElementById("image-encoding").value : "webp";
    const upscaleScale = document.getElementById("upscale-factor") ? parseInt(document.getElementById("upscale-factor").value, 10) : 1;
    const filterPromosElem = document.getElementById("filter-promos");
    const filterPromos = filterPromosElem ? filterPromosElem.checked : true;

    btnStartDownload.disabled = true;

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          mode,
          count,
          format,
          max_width: maxWidth,
          image_format: imageFormat,
          upscale_scale: upscaleScale,
          slice_eink: sliceEink,
          filter_promos: filterPromos,
          cover_url: currentCatalogCoverUrl || undefined,
          series_title: currentSeriesTitle || undefined
        })
      });

      const data = await res.json();
      if (data.success) {
        if (window.AndroidApp && typeof window.AndroidApp.notifyDownloadStarted === "function") {
          window.AndroidApp.notifyDownloadStarted();
        }
        if (data.queued) {
          showToast(data.message || `Added '${data.series_title || "Series"}' to Download Queue (#${data.queue_position || 'in queue'})`, "success");
        } else {
          showToast(data.message || "Download started!", "success");
        }
        progressCard.classList.remove("hidden");
        listenToProgress();
        fetchAndRenderQueue();
      } else {
        showToast(`Error: ${data.error}`, "error");
      }
    } catch (err) {
      showToast(`Failed to launch download: ${err.message}`, "error");
    } finally {
      btnStartDownload.disabled = false;
    }
  });

  // --- Live Progress SSE Stream ---
  let eventSource = null;

  function listenToProgress() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource("/api/download/progress");

    eventSource.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);

        // Render download queue view
        renderDownloadQueue(state);

        document.getElementById("prog-series-title").textContent = state.series_title || "Downloading Series";
        document.getElementById("prog-status-text").textContent = state.status.toUpperCase();
        document.getElementById("prog-message").textContent = state.message;
        document.getElementById("prog-chapter-tracker").textContent = `Chapter ${state.chapter_index} of ${state.total_chapters}`;

        if (state.total_panels > 0) {
          const pct = Math.round((state.current_panel / state.total_panels) * 100);
          document.getElementById("progress-bar-fill").style.width = `${pct}%`;
          document.getElementById("prog-panel-count").textContent = `${state.current_panel} / ${state.total_panels} panels`;
        }

        const progActions = document.getElementById("prog-completed-actions");
        const progControls = document.getElementById("prog-control-actions");

        if (state.is_running) {
          lastHandledProgressStatus = "running";
          if (progActions) progActions.classList.add("hidden");
          if (progControls) progControls.style.display = "flex";

          if (btnPauseDownload) {
            btnPauseDownload.disabled = false;
            if (state.is_paused) {
              btnPauseDownload.setAttribute("data-paused", "true");
              btnPauseDownload.textContent = "▶️ Resume";
              btnPauseDownload.className = "btn btn-primary";
            } else {
              btnPauseDownload.setAttribute("data-paused", "false");
              btnPauseDownload.textContent = "⏸️ Pause";
              btnPauseDownload.className = "btn btn-secondary";
            }
          }
          if (btnStopDownload) btnStopDownload.disabled = false;
        } else {
          if (progControls) progControls.style.display = "none";
          if (btnStartDownload) btnStartDownload.disabled = false;
          if (btnDownloadSelected) btnDownloadSelected.disabled = false;

          if (state.status === "completed") {
            if (lastHandledProgressStatus !== "completed") {
              lastHandledProgressStatus = "completed";
              loadLibrary();
              if (currentCatalogUrl) {
                inspectSeries(currentCatalogUrl, true);
              }
            }
            if (progActions && state.last_downloaded_chapter_id) {
              progActions.classList.remove("hidden");
              const btnRead = document.getElementById("btn-prog-read-now");
              const btnLib = document.getElementById("btn-prog-view-library");
              if (btnRead) {
                if (state.last_downloaded_chapter_num) {
                  btnRead.textContent = `📖 Read Chapter ${state.last_downloaded_chapter_num} Now`;
                }
                btnRead.onclick = () => {
                  openReader(state.last_downloaded_chapter_id);
                };
              }
              if (btnLib) {
                btnLib.onclick = () => {
                  switchTab("tab-library");
                  if (state.last_downloaded_series_id) {
                    openSeriesModal(state.last_downloaded_series_id);
                  }
                };
              }
            }
          } else if (state.status === "cancelled") {
            if (lastHandledProgressStatus !== "cancelled") {
              lastHandledProgressStatus = "cancelled";
              showToast(state.message || "Download stopped.", "info");
              loadLibrary();
            }
          } else if (state.status === "error") {
            if (lastHandledProgressStatus !== "error") {
              lastHandledProgressStatus = "error";
              showToast(`Download error: ${state.message}`, "error");
            }
          }
        }
      } catch (e) {
        console.error("SSE parse error", e);
      }
    };

    eventSource.onerror = () => {
      // EventSource reconnects automatically
    };
  }

  function escapeAttr(str) {
    return String(str || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
  }

  function cleanTitle(title) {
    if (!title) return "";
    return String(title)
      .replace(/â/g, "'")
      .replace(/â/g, "–")
      .replace(/â/g, "—")
      .replace(/â/g, '"')
      .replace(/â/g, '"')
      .replace(/&rsquo;/g, "'")
      .replace(/&lsquo;/g, "'")
      .replace(/&rdquo;/g, '"')
      .replace(/&ldquo;/g, '"')
      .replace(/&amp;/g, '&')
      .trim();
  }

  // --- Library Tab ---
  let libraryDataCache = [];
  let libraryFoldersCache = [];
  let currentSearchQuery = "";

  // Drag and drop state
  let dragActive = false;
  let dragSourceType = null; // "series" | "folder"
  let dragSourceId = null;
  let dragSourceCard = null;
  let dragSourceFolderId = null; // null if from main library, folderId if from inside folder modal
  let dragGhost = null;
  let dragHoverAction = null; // { type: "group" | "reorder" | "reorder_folder" | "eject", position?: "before"|"after", targetCard?: HTMLElement, isFolder?: boolean, folderId?: number, seriesId?: number }
  let dragTouchStart = null;
  let longPressTimer = null;
  let lastDragPointer = null;
  let autoScrollRaf = null;
  let autoScrollSpeed = 0;
  let autoScrollTarget = null;
  let suppressClickUntil = 0;
  let pendingGroupCreation = { sourceId: null, targetId: null };

  const LONG_PRESS_DURATION = 320; // 320ms deliberate hold to pick up card/block

  function clearLongPress() {
    if (longPressTimer) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  }

  function startAutoScroll(speed, target = null) {
    autoScrollSpeed = speed;
    autoScrollTarget = target;
    if (!autoScrollRaf) {
      function scrollStep() {
        if (!dragActive || autoScrollSpeed === 0) {
          autoScrollRaf = null;
          return;
        }
        if (autoScrollTarget) {
          autoScrollTarget.scrollTop += autoScrollSpeed;
        } else {
          window.scrollBy(0, autoScrollSpeed);
        }
        if (lastDragPointer) {
          updateDragPosition(lastDragPointer.x, lastDragPointer.y);
        }
        autoScrollRaf = requestAnimationFrame(scrollStep);
      }
      autoScrollRaf = requestAnimationFrame(scrollStep);
    }
  }

  function stopAutoScroll() {
    autoScrollSpeed = 0;
    autoScrollTarget = null;
    if (autoScrollRaf) {
      cancelAnimationFrame(autoScrollRaf);
      autoScrollRaf = null;
    }
  }

  function checkAutoScroll(clientY) {
    if (!dragActive) {
      stopAutoScroll();
      return;
    }

    const folderModal = document.getElementById("folder-modal");
    if (dragSourceFolderId && folderModal && !folderModal.classList.contains("hidden")) {
      const modalBody = folderModal.querySelector(".folder-modal-body");
      if (modalBody) {
        const rect = modalBody.getBoundingClientRect();
        const edgeZone = 70;
        if (clientY < rect.top + edgeZone && clientY >= rect.top - 20) {
          const ratio = Math.max(0, Math.min(1, (rect.top + edgeZone - clientY) / edgeZone));
          const speed = -Math.round(4 + ratio * 14);
          startAutoScroll(speed, modalBody);
          return;
        } else if (clientY > rect.bottom - edgeZone && clientY <= rect.bottom + 20) {
          const ratio = Math.max(0, Math.min(1, (clientY - (rect.bottom - edgeZone)) / edgeZone));
          const speed = Math.round(4 + ratio * 14);
          startAutoScroll(speed, modalBody);
          return;
        }
      }
    }

    const edgeZone = 120;
    const vh = window.innerHeight || document.documentElement.clientHeight;

    if (clientY < edgeZone) {
      // Near top edge of screen: smoothly scroll up
      const ratio = Math.max(0, Math.min(1, (edgeZone - clientY) / edgeZone));
      const speed = -Math.round(4 + ratio * 16);
      startAutoScroll(speed, null);
    } else if (clientY > vh - edgeZone) {
      // Near bottom edge of screen: smoothly scroll down
      const dist = clientY - (vh - edgeZone);
      const ratio = Math.max(0, Math.min(1, dist / edgeZone));
      const speed = Math.round(4 + ratio * 16);
      startAutoScroll(speed, null);
    } else {
      stopAutoScroll();
    }
  }

  function endAndCleanupDrag() {
    clearLongPress();
    stopAutoScroll();
    dragActive = false;
    dragSourceType = null;
    dragSourceId = null;
    dragSourceCard = null;
    dragSourceFolderId = null;
    dragHoverAction = null;
    dragTouchStart = null;
    dragGhost = null;
    lastDragPointer = null;

    document.body.classList.remove("dragging-folder-item");
    const ejectDropzone = document.getElementById("folder-eject-dropzone");
    if (ejectDropzone) {
      ejectDropzone.classList.remove("drag-hover", "drag-active-target");
    }

    document.querySelectorAll(".drag-ghost").forEach(el => el.remove());
    document.querySelectorAll(".is-dragging").forEach(el => el.classList.remove("is-dragging"));
    document.querySelectorAll(".drag-hover, .drag-group-target, .drag-insert-before, .drag-insert-after").forEach(el => {
      el.classList.remove("drag-hover", "drag-group-target", "drag-insert-before", "drag-insert-after");
    });
    document.querySelectorAll(".card-drag-handle.is-grabbing").forEach(el => el.classList.remove("is-grabbing"));
  }

  function renderFolderCardHtml(f) {
    const safeName = escapeHtml(f.name || "Untitled Group");
    const previewSlots = [0, 1, 2, 3];
    return `
      <div class="folder-card" data-folder-id="${f.id}" onclick="openFolderModal(${f.id})">
        <div class="folder-cover-wrapper">
          <div class="folder-cover-grid">
            ${previewSlots.map(idx => {
              if (f.preview_covers && f.preview_covers[idx]) {
                if (idx === 3 && f.item_count > 4) {
                  return `
                    <div style="position: relative; width: 100%; height: 100%; border-radius: 4px; overflow: hidden;">
                      <img class="folder-sub-thumb" src="${f.preview_covers[idx]}" alt="Cover" loading="lazy" onerror="this.src='/static/placeholder.jpg'">
                      <div style="position: absolute; inset: 0; background: rgba(15, 23, 42, 0.8); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.8rem; color: #818cf8; backdrop-filter: blur(2px);">
                        +${f.item_count - 3}
                      </div>
                    </div>
                  `;
                }
                return `<img class="folder-sub-thumb" src="${f.preview_covers[idx]}" alt="Cover" loading="lazy" onerror="this.src='/static/placeholder.jpg'">`;
              } else {
                return `<div class="folder-empty-slot"></div>`;
              }
            }).join("")}
          </div>
          <div class="folder-badge-overlay">
            <span class="folder-badge-count">📁 ${f.item_count || 0}</span>
          </div>
        </div>
        <div class="series-details">
          <h4 class="series-title" title="${escapeAttr(f.name)}">${safeName}</h4>
          <div class="series-card-desc-row">
            <p class="series-card-desc" style="color: var(--text-muted);">${f.item_count} ${f.item_count === 1 ? 'manga' : 'mangas'}</p>
          </div>
          ${f.description ? `
            <p class="folder-card-note" title="${escapeAttr(f.description)}">${escapeHtml(f.description)}</p>
          ` : `
            <p class="folder-card-note" style="opacity: 0.5;">No note added</p>
          `}
        </div>
      </div>
    `;
  }

  function renderSeriesCardHtml(s, showFolderBadge = false, isInsideFolder = false, folderId = null) {
    const title = cleanTitle(s.title);
    const descSnippet = s.synopsis ? (s.synopsis.length > 55 ? s.synopsis.slice(0, 55) + '...' : s.synopsis) : (s.genres || 'Saved in local library');
    return `
      <div class="series-card" data-series-id="${s.id}" onclick="openSeriesModal(${s.id})" style="cursor: pointer;">
        <div class="series-cover-wrapper">
          <img class="series-cover" src="/api/series/${s.id}/cover" alt="${escapeAttr(title)}" loading="lazy" onerror="this.src='/static/placeholder.jpg'">
          <div class="series-badge-overlay">
            <span class="series-badge-count">📥 ${s.downloaded_chapters || 0} Ch</span>
          </div>
        </div>
        <div class="series-details">
          <h4 class="series-title" title="${escapeAttr(title)}">${escapeHtml(title)}</h4>
          <div class="series-card-desc-row">
            <p class="series-card-desc" title="${escapeAttr(s.synopsis || s.genres || 'Saved in local library')}">
              ${escapeHtml(descSnippet)}
            </p>
            <button class="btn-card-update" title="Check updates for ${escapeAttr(title)}" aria-label="Check updates" onclick="event.stopPropagation(); window.checkSpecificSeriesUpdate(${s.id}, this)">
              <span class="update-icon">🔄</span>
            </button>
          </div>
          ${showFolderBadge && s.folder_name ? `
            <div style="margin: 2px 0;">
              <span class="series-in-folder-badge" onclick="event.stopPropagation(); openFolderModal(${s.folder_id})">📁 In: ${escapeHtml(s.folder_name)}</span>
            </div>
          ` : ''}
          <div class="series-card-actions">
            ${s.resume_chapter_id ? `
              <button class="btn btn-primary btn-card-resume" onclick="event.stopPropagation(); openReader(${s.resume_chapter_id})" title="Resume Ch. ${s.resume_chapter_num}">
                ▶ Ch. ${s.resume_chapter_num} (Resume)
              </button>
            ` : ''}
            <div class="series-card-btn-row">
              <button class="btn btn-secondary btn-card-chapters" onclick="event.stopPropagation(); openSeriesModal(${s.id})">
                📖 Chapters
              </button>
              ${isInsideFolder ? `
                <button class="btn btn-secondary btn-sm" title="Remove from Group" onclick="event.stopPropagation(); removeSeriesFromGroup(${folderId}, ${s.id})">
                  ↩ Out
                </button>
              ` : `
                <button class="btn btn-secondary btn-card-delete" title="Delete Manhua" onclick="event.stopPropagation(); deleteSeriesPrompt(${s.id}, '${escapeAttr(title)}')">🗑️</button>
              `}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderLibraryGrid(filterQuery = "") {
    endAndCleanupDrag();
    const grid = document.getElementById("library-grid");
    if (!grid) return;
    const q = (filterQuery || "").toLowerCase().trim();

    if (!q) {
      // Normal display: Unified custom grid of folders and standalone series
      const unifiedItems = [];

      (libraryFoldersCache || []).forEach(f => {
        unifiedItems.push({
          type: "folder",
          id: f.id,
          sort_order: typeof f.sort_order === "number" ? f.sort_order : 0,
          html: renderFolderCardHtml(f)
        });
      });

      const standaloneSeries = (libraryDataCache || []).filter(s => !s.folder_id);
      standaloneSeries.forEach(s => {
        unifiedItems.push({
          type: "series",
          id: s.id,
          sort_order: typeof s.sort_order === "number" ? s.sort_order : 0,
          html: renderSeriesCardHtml(s, false, false)
        });
      });

      if (unifiedItems.length === 0) {
        grid.innerHTML = '<p class="empty-state">No downloaded series in the database yet. Download a chapter to start building your library!</p>';
      } else {
        unifiedItems.sort((a, b) => a.sort_order - b.sort_order);
        grid.innerHTML = unifiedItems.map(it => it.html).join("");
      }
    } else {
      // Unified Search: Match folders AND series
      const matchingFolders = (libraryFoldersCache || []).filter(f => (f.name || "").toLowerCase().includes(q));
      const matchingSeries = (libraryDataCache || []).filter(s => {
        const titleMatch = (s.title || "").toLowerCase().includes(q);
        const synMatch = (s.synopsis || "").toLowerCase().includes(q);
        const folderMatch = (s.folder_name || "").toLowerCase().includes(q);
        return titleMatch || synMatch || folderMatch;
      });

      const unifiedMatching = [];
      matchingFolders.forEach(f => {
        unifiedMatching.push({
          type: "folder",
          id: f.id,
          sort_order: typeof f.sort_order === "number" ? f.sort_order : 0,
          html: renderFolderCardHtml(f)
        });
      });
      matchingSeries.forEach(s => {
        unifiedMatching.push({
          type: "series",
          id: s.id,
          sort_order: typeof s.sort_order === "number" ? s.sort_order : 0,
          html: renderSeriesCardHtml(s, true, false)
        });
      });

      if (unifiedMatching.length === 0) {
        grid.innerHTML = `<p class="empty-state">No series or groups match "${escapeHtml(filterQuery)}".</p>`;
      } else {
        unifiedMatching.sort((a, b) => a.sort_order - b.sort_order);
        grid.innerHTML = unifiedMatching.map(it => it.html).join("");
      }
    }

    // Attach drag & drop listeners
    initLibraryDragAndDrop();
  }

  function promptCreateGroup(sourceId, targetId) {
    pendingGroupCreation = { sourceId, targetId };
    const modal = document.getElementById("create-group-modal");
    const input = document.getElementById("create-group-name-input");
    const noteInput = document.getElementById("create-group-note-input");
    if (!modal || !input) return;

    const targetSeries = (libraryDataCache || []).find(s => s.id === targetId);
    let defaultName = "New Group";
    if (targetSeries && targetSeries.engine === "hitomi") {
      defaultName = "Hitomi Works";
    }
    input.value = defaultName;
    if (noteInput) noteInput.value = "";
    modal.classList.remove("hidden");
    input.focus();
    input.select();
  }

  window.addSeriesToGroup = async function(folderId, seriesId) {
    try {
      const res = await fetch(`/api/library/folders/${folderId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ series_id: seriesId })
      });
      const data = await res.json();
      if (data.success) {
        triggerHaptic([40]);
        showToast("Added to group", "success");
        await loadLibrary();
      } else {
        showToast("Failed to add to group: " + (data.error || ""), "error");
      }
    } catch (e) {
      showToast("Error adding to group: " + e.message, "error");
    } finally {
      endAndCleanupDrag();
    }
  };

  window.removeSeriesFromGroup = async function(folderId, seriesId) {
    try {
      const res = await fetch(`/api/library/folders/${folderId}/items/${seriesId}`, {
        method: "DELETE"
      });
      const data = await res.json();
      if (data.success) {
        showToast("Removed from group", "success");
        await loadLibrary();
        const folderModal = document.getElementById("folder-modal");
        if (folderModal && !folderModal.classList.contains("hidden") && activeOpenedFolderId) {
          openFolderModal(activeOpenedFolderId);
        }
      }
    } catch (e) {
      showToast("Error removing from group: " + e.message, "error");
    } finally {
      endAndCleanupDrag();
    }
  };

  let activeOpenedFolderId = null;
  window.openFolderModal = async function(folderId) {
    if (Date.now() < suppressClickUntil) {
      return;
    }
    endAndCleanupDrag();
    const modal = document.getElementById("folder-modal");
    if (!modal) return;
    activeOpenedFolderId = folderId;

    try {
      const res = await fetch(`/api/library/folders/${folderId}`);
      const data = await res.json();
      if (!data.success || !data.folder) {
        modal.classList.add("hidden");
        return;
      }

      const f = data.folder;
      const titleInput = document.getElementById("folder-modal-title");
      if (titleInput) titleInput.value = f.name;

      const noteInput = document.getElementById("folder-modal-note");
      if (noteInput) noteInput.value = f.description || "";

      const countEl = document.getElementById("folder-modal-count");
      if (countEl) countEl.textContent = `${f.item_count} Items`;

      const grid = document.getElementById("folder-series-grid");
      if (grid) {
        if (!f.series || f.series.length === 0) {
          grid.innerHTML = '<p class="empty-state">No manga in this group.</p>';
        } else {
          grid.innerHTML = f.series.map(s => renderSeriesCardHtml(s, false, true, folderId)).join("");
          grid.querySelectorAll(".series-card").forEach(bindCardDragListeners);
        }
      }

      modal.classList.remove("hidden");
    } catch (e) {
      showToast("Error loading group: " + e.message, "error");
    }
  };

  function spawnDragGhost(card, itemType, itemId, clientX, clientY) {
    endAndCleanupDrag();

    const pullIndicator = document.getElementById("library-pull-indicator");
    if (pullIndicator) pullIndicator.classList.add("hidden");

    dragActive = true;
    dragSourceType = itemType; // "series" or "folder"
    dragSourceId = itemId;
    dragSourceCard = card;

    const insideFolderEl = card.closest("#folder-series-grid");
    dragSourceFolderId = insideFolderEl ? activeOpenedFolderId : null;
    if (dragSourceFolderId) {
      document.body.classList.add("dragging-folder-item");
    }

    suppressClickUntil = Date.now() + 800;

    triggerHaptic([40]);

    card.classList.add("is-dragging");

    dragGhost = document.createElement("div");
    dragGhost.className = "drag-ghost";

    if (itemType === "folder") {
      dragGhost.classList.add("folder-ghost");
      const coverWrapper = card.querySelector(".folder-cover-wrapper");
      if (coverWrapper) {
        dragGhost.innerHTML = coverWrapper.outerHTML;
      } else {
        dragGhost.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:2.5rem;">📁</div>`;
      }
    } else {
      const coverImg = card.querySelector(".series-cover");
      if (coverImg && coverImg.src) {
        dragGhost.innerHTML = `<img src="${coverImg.src}" alt="dragging">`;
      }
    }

    dragGhost.style.left = clientX + "px";
    dragGhost.style.top = clientY + "px";
    document.body.appendChild(dragGhost);

    lastDragPointer = { x: clientX, y: clientY };
    updateDragPosition(clientX, clientY);
    checkAutoScroll(clientY);

    setTimeout(() => {
      if (dragGhost && dragGhost.parentNode) {
        endAndCleanupDrag();
      }
    }, 15000);
  }

  function getDropTargetCard(container, clientX, clientY, excludeCard) {
    if (!container) return null;

    dragGhost.style.display = "none";
    const under = document.elementFromPoint(clientX, clientY);
    dragGhost.style.display = "block";

    const directTarget = under?.closest(".series-card, .folder-card");
    if (directTarget && directTarget !== excludeCard && container.contains(directTarget)) {
      return directTarget;
    }

    const cards = Array.from(container.querySelectorAll(".series-card, .folder-card"))
      .filter(c => c !== excludeCard && !c.classList.contains("is-dragging"));
    if (cards.length === 0) return null;

    let closest = null;
    let closestDist = Infinity;
    for (const card of cards) {
      const r = card.getBoundingClientRect();
      const inRangeX = clientX >= r.left - 30 && clientX <= r.right + 30;
      const inRangeY = clientY >= r.top - 30 && clientY <= r.bottom + 30;
      if (inRangeX && inRangeY) {
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const dist = Math.hypot(clientX - cx, clientY - cy);
        if (dist < closestDist) {
          closestDist = dist;
          closest = card;
        }
      }
    }
    return closest;
  }

  function updateDragPosition(clientX, clientY) {
    if (!dragActive || !dragGhost) return;
    lastDragPointer = { x: clientX, y: clientY };

    dragGhost.style.left = clientX + "px";
    dragGhost.style.top = clientY + "px";

    // Scenario A: Dragging inside an opened folder / group modal
    if (dragSourceFolderId) {
      const ejectDropzone = document.getElementById("folder-eject-dropzone");
      if (ejectDropzone) {
        const er = ejectDropzone.getBoundingClientRect();
        if (clientX >= er.left - 10 && clientX <= er.right + 10 && clientY >= er.top - 10 && clientY <= er.bottom + 10) {
          ejectDropzone.classList.add("drag-hover", "drag-active-target");
          document.querySelectorAll("#folder-series-grid .drag-insert-before, #folder-series-grid .drag-insert-after").forEach(el => {
            el.classList.remove("drag-insert-before", "drag-insert-after");
          });
          dragHoverAction = {
            type: "eject",
            folderId: dragSourceFolderId,
            seriesId: dragSourceId
          };
          return;
        } else {
          ejectDropzone.classList.remove("drag-hover", "drag-active-target");
        }
      }

      const grid = document.getElementById("folder-series-grid");
      const target = getDropTargetCard(grid, clientX, clientY, dragSourceCard);

      document.querySelectorAll("#folder-series-grid .drag-insert-before, #folder-series-grid .drag-insert-after").forEach(el => {
        if (el !== target) {
          el.classList.remove("drag-insert-before", "drag-insert-after");
        }
      });

      if (!target || target === dragSourceCard) {
        return;
      }

      const rect = target.getBoundingClientRect();
      const insertBefore = (clientX < rect.left + rect.width / 2);
      if (insertBefore) {
        target.classList.remove("drag-insert-after");
        target.classList.add("drag-insert-before");
        dragHoverAction = {
          type: "reorder_folder",
          position: "before",
          targetCard: target,
          folderId: dragSourceFolderId
        };
      } else {
        target.classList.remove("drag-insert-before");
        target.classList.add("drag-insert-after");
        dragHoverAction = {
          type: "reorder_folder",
          position: "after",
          targetCard: target,
          folderId: dragSourceFolderId
        };
      }
      return;
    }

    // Scenario B: Dragging on the main library grid
    const mainGrid = document.getElementById("library-grid");
    const target = getDropTargetCard(mainGrid, clientX, clientY, dragSourceCard);

    document.querySelectorAll("#library-grid .drag-hover, #library-grid .drag-group-target, #library-grid .drag-insert-before, #library-grid .drag-insert-after").forEach(el => {
      if (el !== target) {
        el.classList.remove("drag-hover", "drag-group-target", "drag-insert-before", "drag-insert-after");
      }
    });

    if (!target || target === dragSourceCard) {
      return;
    }

    const rect = target.getBoundingClientRect();
    const relX = (clientX - rect.left) / rect.width;
    const relY = (clientY - rect.top) / rect.height;

    // Check grouping sweet-spot: only standalone series can be grouped into another series or folder
    const canGroup = (dragSourceType === "series");
    const isCenterHover = (relX >= 0.22 && relX <= 0.78 && relY >= 0.18 && relY <= 0.82);

    if (canGroup && isCenterHover) {
      target.classList.remove("drag-insert-before", "drag-insert-after");
      target.classList.add("drag-group-target");
      dragHoverAction = {
        type: "group",
        targetCard: target,
        isFolder: target.classList.contains("folder-card")
      };
    } else {
      target.classList.remove("drag-group-target");
      const insertBefore = (clientX < rect.left + rect.width / 2);
      if (insertBefore) {
        target.classList.remove("drag-insert-after");
        target.classList.add("drag-insert-before");
        dragHoverAction = {
          type: "reorder",
          position: "before",
          targetCard: target
        };
      } else {
        target.classList.remove("drag-insert-before");
        target.classList.add("drag-insert-after");
        dragHoverAction = {
          type: "reorder",
          position: "after",
          targetCard: target
        };
      }
    }
  }

  async function performDrop() {
    if (!dragActive) {
      endAndCleanupDrag();
      return;
    }

    suppressClickUntil = Date.now() + 450;
    const action = dragHoverAction;
    const sourceCard = dragSourceCard;
    const sourceType = dragSourceType;
    const sourceId = dragSourceId;

    endAndCleanupDrag();

    if (!action || !sourceCard || !sourceId) {
      return;
    }

    if (action.type === "reorder_folder") {
      const grid = document.getElementById("folder-series-grid");
      const targetCard = action.targetCard;
      if (!grid || !targetCard || sourceCard === targetCard) return;

      if (action.position === "before") {
        grid.insertBefore(sourceCard, targetCard);
      } else {
        grid.insertBefore(sourceCard, targetCard.nextSibling);
      }

      triggerHaptic([35]);

      const seriesIds = Array.from(grid.querySelectorAll(".series-card"))
        .map(el => parseInt(el.dataset.seriesId, 10))
        .filter(Boolean);

      try {
        await fetch(`/api/library/folders/${action.folderId}/reorder`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ series_ids: seriesIds })
        });
        loadLibrary();
      } catch (err) {
        console.error("Error saving folder series order:", err);
      }
    } else if (action.type === "eject") {
      triggerHaptic([50]);
      await removeSeriesFromGroup(action.folderId, action.seriesId);
    } else if (action.type === "group") {
      const targetCard = action.targetCard;
      if (action.isFolder) {
        const folderId = parseInt(targetCard.dataset.folderId, 10);
        if (folderId) {
          await addSeriesToGroup(folderId, sourceId);
        }
      } else {
        const targetId = parseInt(targetCard.dataset.seriesId, 10);
        if (targetId && targetId !== sourceId) {
          promptCreateGroup(sourceId, targetId);
        }
      }
    } else if (action.type === "reorder") {
      const grid = document.getElementById("library-grid");
      const targetCard = action.targetCard;
      if (!grid || !targetCard || sourceCard === targetCard) return;

      if (action.position === "before") {
        grid.insertBefore(sourceCard, targetCard);
      } else {
        grid.insertBefore(sourceCard, targetCard.nextSibling);
      }

      triggerHaptic([35]);

      const newItems = [];
      grid.querySelectorAll(".folder-card, .series-card").forEach((el, index) => {
        if (el.classList.contains("folder-card")) {
          const fid = parseInt(el.dataset.folderId, 10);
          if (fid) {
            newItems.push({ type: "folder", id: fid });
            const fObj = (libraryFoldersCache || []).find(f => f.id === fid);
            if (fObj) fObj.sort_order = index;
          }
        } else if (el.classList.contains("series-card")) {
          const sid = parseInt(el.dataset.seriesId, 10);
          if (sid) {
            newItems.push({ type: "series", id: sid });
            const sObj = (libraryDataCache || []).find(s => s.id === sid);
            if (sObj) sObj.sort_order = index;
          }
        }
      });

      try {
        await fetch("/api/library/reorder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: newItems })
        });
      } catch (err) {
        console.error("Error saving library order:", err);
      }
    }
  }

  let dragMouseDown = null;

  function bindCardDragListeners(card) {
    if (card._dragBound) return;
    card._dragBound = true;
    const isFolder = card.classList.contains("folder-card");
    const itemType = isFolder ? "folder" : "series";
    const itemId = parseInt(isFolder ? card.dataset.folderId : card.dataset.seriesId, 10);
    if (!itemId) return;

    card.addEventListener("dragstart", (e) => e.preventDefault());
    card.addEventListener("contextmenu", (e) => {
      if (dragActive || longPressTimer) {
        e.preventDefault();
        e.stopPropagation();
        return false;
      }
    });

    // Mobile Touch Start: Start deliberate long-press timer (380ms)
    card.addEventListener("touchstart", (e) => {
      if (e.target.closest("button, a, input, select, textarea, .series-in-folder-badge")) return;
      if (e.touches.length !== 1) return;

      clearLongPress();
      const t = e.touches[0];
      const startX = t.clientX;
      const startY = t.clientY;

      dragTouchStart = { card, itemType, itemId, startX, startY };

      longPressTimer = setTimeout(() => {
        longPressTimer = null;
        spawnDragGhost(card, itemType, itemId, startX, startY);
      }, 380);
    }, { passive: true });

    // Desktop Mouse Down: Prepare drag on move (instant click preserved)
    card.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("button, a, input, select, textarea, .series-in-folder-badge")) return;

      clearLongPress();
      dragMouseDown = { card, itemType, itemId, startX: e.clientX, startY: e.clientY };
    });
  }

  let dragEventsBound = false;
  function initLibraryDragAndDrop() {
    endAndCleanupDrag();
    const libraryCards = document.querySelectorAll(".library-grid > .series-card, .library-grid > .folder-card");
    libraryCards.forEach(bindCardDragListeners);

    if (!dragEventsBound) {
      dragEventsBound = true;

      window.addEventListener("contextmenu", (e) => {
        if (dragActive) {
          e.preventDefault();
          e.stopPropagation();
          return false;
        }
      }, { capture: true });

      // Window Touch Move
      window.addEventListener("touchmove", (e) => {
        if (e.touches.length === 0) return;
        const t = e.touches[0];

        if (dragActive) {
          e.preventDefault();
          updateDragPosition(t.clientX, t.clientY);
          checkAutoScroll(t.clientY);
          return;
        }

        if (longPressTimer && dragTouchStart) {
          const dist = Math.hypot(t.clientX - dragTouchStart.startX, t.clientY - dragTouchStart.startY);
          if (dist > 8) {
            clearLongPress();
            dragTouchStart = null;
          }
        }
      }, { passive: false });

      // Window Touch End
      window.addEventListener("touchend", (e) => {
        clearLongPress();
        stopAutoScroll();
        if (dragActive) {
          e.preventDefault();
          performDrop();
        } else {
          dragTouchStart = null;
          endAndCleanupDrag();
        }
      }, { passive: false });

      // Window Touch Cancel: treat as drop if dragging to avoid reverting
      window.addEventListener("touchcancel", () => {
        clearLongPress();
        stopAutoScroll();
        if (dragActive) {
          performDrop();
        } else {
          dragTouchStart = null;
          endAndCleanupDrag();
        }
      });

      // Window Mouse Move
      window.addEventListener("mousemove", (e) => {
        if (dragActive) {
          e.preventDefault();
          updateDragPosition(e.clientX, e.clientY);
          checkAutoScroll(e.clientY);
          return;
        }

        if (dragMouseDown && e.buttons === 1) {
          const dist = Math.hypot(e.clientX - dragMouseDown.startX, e.clientY - dragMouseDown.startY);
          if (dist > 8) {
            const m = dragMouseDown;
            dragMouseDown = null;
            spawnDragGhost(m.card, m.itemType, m.itemId, e.clientX, e.clientY);
          }
        }
      });

      // Window Mouse Up
      window.addEventListener("mouseup", (e) => {
        clearLongPress();
        stopAutoScroll();
        dragMouseDown = null;
        if (dragActive) {
          performDrop();
        } else {
          endAndCleanupDrag();
        }
      });

      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          clearLongPress();
          stopAutoScroll();
          dragMouseDown = null;
          dragTouchStart = null;
          endAndCleanupDrag();
        }
      });

      window.addEventListener("scroll", () => {
        if (!dragActive) {
          clearLongPress();
        }
      }, { passive: true });

      document.addEventListener("click", () => {
        if (!dragActive) {
          clearLongPress();
        }
      });
    }
  }

  async function loadLibrary() {
    endAndCleanupDrag();
    const grid = document.getElementById("library-grid");
    try {
      const res = await fetch("/api/library");
      const data = await res.json();

      if (data.success) {
        libraryDataCache = data.series || [];
        libraryFoldersCache = data.folders || [];

        const totalCount = libraryDataCache.length;
        const countTxt = String(totalCount);
        const lCount = document.getElementById("library-count");
        if (lCount) lCount.textContent = countTxt;
        const dCount = document.getElementById("drawer-library-count");
        if (dCount) dCount.textContent = countTxt;

        renderLibraryGrid(currentSearchQuery);
      } else {
        grid.innerHTML = `<p class="empty-state">Failed to load library: ${escapeHtml(data.error || 'Unknown error')}</p>`;
      }
    } catch (err) {
      grid.innerHTML = `<p class="empty-state">Error loading library: ${err.message}</p>`;
    }
  }

  // Bind Folder Modal & Create Group Events
  const folderModal = document.getElementById("folder-modal");
  const folderModalClose = document.getElementById("folder-modal-close");
  const folderModalTitle = document.getElementById("folder-modal-title");
  const folderModalNote = document.getElementById("folder-modal-note");
  const folderBtnDissolve = document.getElementById("folder-btn-dissolve");

  folderModalClose?.addEventListener("click", () => {
    folderModal?.classList.add("hidden");
    activeOpenedFolderId = null;
    endAndCleanupDrag();
  });

  folderModal?.addEventListener("click", (e) => {
    if (e.target === folderModal) {
      folderModal.classList.add("hidden");
      activeOpenedFolderId = null;
      endAndCleanupDrag();
    }
  });

  const saveFolderMetadata = async () => {
    if (!activeOpenedFolderId) return;
    const newName = (folderModalTitle ? folderModalTitle.value.trim() : "") || "Group";
    const newNote = folderModalNote ? folderModalNote.value.trim() : "";
    try {
      await fetch(`/api/library/folders/${activeOpenedFolderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName, description: newNote })
      });
      showToast("Group details saved", "success");
      loadLibrary();
    } catch (e) {
      showToast("Error updating group: " + e.message, "error");
    }
  };

  folderModalTitle?.addEventListener("change", saveFolderMetadata);
  folderModalNote?.addEventListener("change", saveFolderMetadata);

  folderBtnDissolve?.addEventListener("click", async () => {
    if (!activeOpenedFolderId) return;
    if (!confirm("Unbundle this group? All series will return to your main library.")) return;
    try {
      const res = await fetch(`/api/library/folders/${activeOpenedFolderId}`, {
        method: "DELETE"
      });
      const data = await res.json();
      if (data.success) {
        showToast("Group unbundled", "success");
        folderModal?.classList.add("hidden");
        activeOpenedFolderId = null;
        loadLibrary();
      }
    } catch (e) {
      showToast("Error dissolving group: " + e.message, "error");
    }
  });

  const createGroupModal = document.getElementById("create-group-modal");
  const createGroupClose = document.getElementById("create-group-close");
  const btnCancelCreateGroup = document.getElementById("btn-cancel-create-group");
  const btnConfirmCreateGroup = document.getElementById("btn-confirm-create-group");
  const createGroupNameInput = document.getElementById("create-group-name-input");
  const createGroupNoteInput = document.getElementById("create-group-note-input");

  function closeCreateGroupModal() {
    createGroupModal?.classList.add("hidden");
    pendingGroupCreation = { sourceId: null, targetId: null };
  }

  createGroupClose?.addEventListener("click", closeCreateGroupModal);
  btnCancelCreateGroup?.addEventListener("click", closeCreateGroupModal);

  btnConfirmCreateGroup?.addEventListener("click", async () => {
    const name = (createGroupNameInput.value || "").trim() || "New Group";
    const note = (createGroupNoteInput ? createGroupNoteInput.value : "").trim();
    if (!pendingGroupCreation.sourceId || !pendingGroupCreation.targetId) {
      closeCreateGroupModal();
      return;
    }

    try {
      const res = await fetch("/api/library/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          description: note,
          series_ids: [pendingGroupCreation.targetId, pendingGroupCreation.sourceId]
        })
      });
      const data = await res.json();
      if (data.success) {
        triggerHaptic([40]);
        showToast(`Created group "${name}"`, "success");
        closeCreateGroupModal();
        await loadLibrary();
      } else {
        showToast("Failed to create group: " + (data.error || ""), "error");
      }
    } catch (e) {
      showToast("Error creating group: " + e.message, "error");
    }
  });

  createGroupNameInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      btnConfirmCreateGroup?.click();
    } else if (e.key === "Escape") {
      closeCreateGroupModal();
    }
  });

  createGroupNoteInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      btnConfirmCreateGroup?.click();
    } else if (e.key === "Escape") {
      closeCreateGroupModal();
    }
  });

  const librarySearchInput = document.getElementById("library-search");
  librarySearchInput?.addEventListener("input", (e) => {
    currentSearchQuery = e.target.value;
    renderLibraryGrid(currentSearchQuery);
  });

  // --- Series Details Modal ---
  const seriesModal = document.getElementById("series-modal");
  const modalClose = document.getElementById("modal-close");

  modalClose.addEventListener("click", () => {
    seriesModal.classList.add("hidden");
  });

  window.showSeriesGroupPicker = async function(seriesId, currentFolderId) {
    const folders = libraryFoldersCache || [];
    let options = [];
    if (currentFolderId) {
      options.push("0: Remove from current group (Top-level)");
    }
    folders.forEach((f, idx) => {
      options.push(`${idx + 1}: Move to "${f.name}"`);
    });
    options.push(`${folders.length + 1}: + Create New Group...`);

    const choice = prompt("Select group action:\n" + options.join("\n"));
    if (choice === null) return;
    const num = parseInt(choice.trim());
    if (isNaN(num)) return;

    if (currentFolderId && num === 0) {
      await removeSeriesFromGroup(currentFolderId, seriesId);
      openSeriesModal(seriesId);
    } else if (num >= 1 && num <= folders.length) {
      const targetFolder = folders[num - 1];
      await addSeriesToGroup(targetFolder.id, seriesId);
      openSeriesModal(seriesId);
    } else if (num === folders.length + 1) {
      const newName = prompt("Enter new group name:");
      if (!newName || !newName.trim()) return;
      try {
        const res = await fetch("/api/library/folders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newName.trim(), series_ids: [seriesId] })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Created group "${newName}"`, "success");
          await loadLibrary();
          openSeriesModal(seriesId);
        }
      } catch (err) {
        showToast("Error creating group: " + err.message, "error");
      }
    }
  };

  window.deleteSeriesPrompt = async function(seriesId, title) {
    if (!confirm(`Are you sure you want to delete "${title}" and all its downloaded chapters? This will remove the files from disk.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/library/${seriesId}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        showToast(`Deleted "${title}"`, "success");
        if (seriesModal) seriesModal.classList.add("hidden");
        loadLibrary();
      } else {
        showToast("Failed to delete series: " + (data.error || "Unknown error"), "error");
      }
    } catch (err) {
      showToast("Error deleting series: " + err.message, "error");
    }
  };

  window.deleteChapterPrompt = async function(chapterId, seriesId, title) {
    if (!confirm(`Are you sure you want to delete "${title}"? This will remove the file from disk.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/chapters/${chapterId}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        showToast(`Deleted chapter`, "success");
        openSeriesModal(seriesId);
        loadLibrary();
      } else {
        showToast("Failed to delete chapter: " + (data.error || "Unknown error"), "error");
      }
    } catch (err) {
      showToast("Error deleting chapter: " + err.message, "error");
    }
  };

  window.openSeriesModal = async function(seriesId) {
    if (Date.now() < suppressClickUntil) {
      return;
    }
    endAndCleanupDrag();
    try {
      const res = await fetch(`/api/library/${seriesId}`);
      const data = await res.json();
      if (data.success && data.series) {
        const s = data.series;
        const safeTitle = cleanTitle(s.title);
        document.getElementById("modal-series-title").textContent = safeTitle;
        const coverEl = document.getElementById("modal-series-cover");
        if (coverEl) {
          coverEl.onerror = function() { this.src = '/static/placeholder.jpg'; };
          coverEl.src = `/api/series/${seriesId}/cover`;
        }
        document.getElementById("modal-engine-badge").textContent = `Engine: ${s.engine || 'Auto'}`;
        document.getElementById("modal-synopsis").textContent = s.synopsis || "Tracked in local library database.";

        const modalBtnCheckUpdate = document.getElementById("modal-btn-check-update");
        if (modalBtnCheckUpdate) {
          modalBtnCheckUpdate.onclick = (e) => {
            e.stopPropagation();
            window.checkSpecificSeriesUpdate(seriesId, modalBtnCheckUpdate);
          };
        }

        const modalBtnGroup = document.getElementById("modal-btn-group");
        const modalGroupLabel = document.getElementById("modal-group-label");
        const matchedInCache = (libraryDataCache || []).find(it => it.id === seriesId);
        const currentGroup = matchedInCache?.folder_name;
        if (modalGroupLabel) {
          modalGroupLabel.textContent = currentGroup ? `Group: ${currentGroup}` : "Add to Group";
        }
        if (modalBtnGroup) {
          modalBtnGroup.onclick = (e) => {
            e.stopPropagation();
            showSeriesGroupPicker(seriesId, matchedInCache?.folder_id);
          };
        }

        const metaParts = [];
        if (s.author) metaParts.push(`✍️ <strong>${escapeHtml(cleanTitle(s.author))}</strong>`);
        if (s.artist) metaParts.push(`🎨 <strong>${escapeHtml(cleanTitle(s.artist))}</strong>`);
        if (s.genres) metaParts.push(`🏷️ ${escapeHtml(s.genres)}`);
        if (s.year) metaParts.push(`📅 ${escapeHtml(s.year)}`);
        document.getElementById("modal-meta-tags").innerHTML = metaParts.length > 0 ? metaParts.join(" &bull; ") : "<em>No author/genre metadata cached yet.</em>";

        // Manhua source URL in bio/card
        const sourceUrlBox = document.getElementById("modal-source-url-box");
        if (sourceUrlBox) {
          if (s.source_url) {
            sourceUrlBox.style.display = "block";
            sourceUrlBox.innerHTML = `
              <div style="display: flex; align-items: center; gap: 8px; background: rgba(15, 23, 42, 0.7); padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border-color); margin-bottom: 6px; width: 100%; box-sizing: border-box; min-width: 0;">
                <span style="color: var(--text-muted); font-size: 0.8rem; font-weight: 600; white-space: nowrap; flex-shrink: 0;">🔗 URL:</span>
                <a href="${escapeAttr(s.source_url)}" target="_blank" rel="noopener noreferrer" style="color: var(--primary); text-decoration: underline; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 0%; min-width: 0;" title="${escapeAttr(s.source_url)}">${escapeHtml(s.source_url)}</a>
                <button class="btn btn-secondary" style="padding: 2px 8px; font-size: 0.75rem; white-space: nowrap; flex-shrink: 0;" onclick="navigator.clipboard.writeText('${escapeAttr(s.source_url)}'); showToast('Manhua URL copied!', 'success');" title="Copy URL">📋 Copy</button>
              </div>
            `;
          } else {
            sourceUrlBox.style.display = "none";
          }
        }

        // Quick resume button in modal
        const resumeBox = document.getElementById("modal-resume-box");
        if (resumeBox) {
          if (s.resume_chapter_id) {
            resumeBox.style.display = "block";
            resumeBox.innerHTML = `
              <button class="btn btn-primary" style="padding: 9px 16px; font-size: 0.9rem; font-weight: 600; width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; background: linear-gradient(135deg, #3b82f6, #6366f1); border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); margin-bottom: 8px; cursor: pointer;" onclick="openReader(${s.resume_chapter_id})">
                ▶ Start where you left (Ch. ${s.resume_chapter_num})
              </button>
            `;
          } else {
            resumeBox.style.display = "none";
          }
        }

        // Storage location wiring
        const storageInput = document.getElementById("modal-storage-path");
        if (storageInput) {
          storageInput.value = data.storage_dir || "Not stored yet";
        }
        const btnCopyStorage = document.getElementById("btn-copy-storage-path");
        if (btnCopyStorage) {
          btnCopyStorage.onclick = () => {
            if (data.storage_dir) {
              navigator.clipboard.writeText(data.storage_dir);
              showToast("Storage path copied to clipboard!", "success");
            }
          };
        }
        const btnOpenStorage = document.getElementById("btn-open-storage-folder");
        if (btnOpenStorage) {
          btnOpenStorage.onclick = async () => {
            try {
              const res = await fetch(`/api/library/${seriesId}/open-folder`, { method: "POST" });
              const oData = await res.json();
              if (oData.success) {
                showToast("Storage folder opened in file manager!", "success");
              } else {
                showToast("Stored at: " + (oData.path || data.storage_dir), "info");
              }
            } catch (err) {
              showToast("Stored at: " + (data.storage_dir || ""), "info");
            }
          };
        }
        const btnDeleteSeries = document.getElementById("modal-btn-delete-series");
        if (btnDeleteSeries) {
          btnDeleteSeries.onclick = () => {
            deleteSeriesPrompt(seriesId, s.title);
          };
        }

        const btnSyncSearchCover = document.getElementById("modal-btn-sync-search-cover");
        if (btnSyncSearchCover) {
          btnSyncSearchCover.onclick = async () => {
            btnSyncSearchCover.textContent = "Syncing...";
            btnSyncSearchCover.disabled = true;
            try {
              const cRes = await fetch(`/api/series/${seriesId}/sync-search-cover`, { method: "POST" });
              const cData = await cRes.json();
              if (cData.success) {
                showToast("Global Search cover synced!", "success");
                if (coverEl) coverEl.src = `/api/series/${seriesId}/cover?t=${Date.now()}`;
                loadLibrary();
              } else {
                showToast(cData.error || "Could not find cover in Global Search.", "info");
              }
            } catch(err) {
              showToast("Error syncing cover: " + err.message, "error");
            } finally {
              btnSyncSearchCover.textContent = "🖼️ Sync Global Search Cover";
              btnSyncSearchCover.disabled = false;
            }
          };
        }

        const btnRefreshMeta = document.getElementById("modal-btn-refresh-meta");
        if (btnRefreshMeta) {
          btnRefreshMeta.onclick = async () => {
            btnRefreshMeta.textContent = "Fetching...";
            btnRefreshMeta.disabled = true;
            try {
              const mRes = await fetch(`/api/series/${seriesId}/refresh-metadata`, { method: "POST" });
              const mData = await mRes.json();
              if (mData.success) {
                showToast("Metadata successfully updated!", "success");
                openSeriesModal(seriesId);
              } else {
                showToast("Could not find online metadata for this series.", "info");
              }
            } catch(err) {
              showToast("Error fetching metadata: " + err.message, "error");
            } finally {
              btnRefreshMeta.textContent = "🔄 Fetch MangaDex Metadata";
              btnRefreshMeta.disabled = false;
            }
          };
        }

        const chList = document.getElementById("modal-chapters-list");
        if (data.chapters && data.chapters.length > 0) {
          chList.innerHTML = data.chapters.map(c => `
            <div class="modal-chapter-row" id="modal-ch-${c.id}">
              <div>
                <strong>${escapeHtml(c.title || `Chapter ${c.chapter_num}`)}</strong>
                <span class="chapter-badge-format">${c.file_format || 'PDF'}</span>
                <span style="font-size: 0.8rem; color: var(--text-muted); margin-left: 0.5rem;">(${c.panel_count || 0} panels)</span>
                ${c.read_status === 2 ? '<span style="font-size: 0.75rem; color: #4ade80; margin-left: 6px;">✓ Completed</span>' : (c.read_status === 1 ? `<span style="font-size: 0.75rem; color: #60a5fa; margin-left: 6px;">📖 Page ${c.last_read_page || 1}</span>` : '')}
                ${c.source_url ? `<a href="${escapeAttr(c.source_url)}" target="_blank" rel="noopener noreferrer" style="font-size: 0.75rem; color: var(--text-muted); margin-left: 6px; text-decoration: none;" title="Online chapter URL: ${escapeAttr(c.source_url)}">🔗</a>` : ''}
              </div>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                ${c.status === 'completed' ? `<button class="btn btn-primary" style="padding: 0.3rem 0.8rem; font-size: 0.85rem;" onclick="openReader(${c.id})">${c.read_status === 1 ? '▶ Continue' : '📖 Read'}</button>` : `<span style="font-size: 0.8rem; color: var(--warning);">${c.status}</span>`}
                ${c.status === 'completed' ? `<a href="/api/download/file/${c.id}" class="btn btn-secondary" style="padding: 0.3rem 0.8rem; font-size: 0.85rem; text-decoration: none;" download>💾 File</a>` : ''}
                <button class="btn btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.85rem; color: #ef4444; border-color: rgba(239, 68, 68, 0.4);" title="Delete Chapter" onclick="deleteChapterPrompt(${c.id}, ${seriesId}, '${escapeAttr(c.title || `Chapter ${c.chapter_num}`)}')">🗑️</button>
              </div>
            </div>
          `).join("");
        } else {
          chList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No chapters recorded yet.</p>';
        }

        seriesModal.classList.remove("hidden");
      }
    } catch (e) {
      showToast("Failed to load series: " + e.message, "error");
    }
  };

  // --- Specific Series Update Checker ---
  window.checkSpecificSeriesUpdate = async function(seriesId, btn) {
    triggerHaptic([10]);
    let iconEl = null;
    if (btn) {
      btn.disabled = true;
      iconEl = btn.querySelector(".update-icon") || btn;
      iconEl.classList.add("spinning");
    }
    showToast("Checking for latest chapters...", "info");
    try {
      const res = await fetch(`/api/library/${seriesId}/check-update`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        if (data.queued && data.new_chapters && data.new_chapters.length > 0) {
          showToast(`Found ${data.new_chapters.length} new chapter(s) for "${data.series_title}"! Added to Download Queue.`, "success");
          triggerHaptic([20, 40, 20]);
          fetchAndRenderQueue();
          const qBadge = document.getElementById("queue-badge-count");
          if (qBadge) qBadge.classList.remove("hidden");
        } else {
          showToast(data.message || `"${data.series_title || "Series"}" is already up to date.`, "info");
        }
      } else {
        showToast("Update check failed: " + (data.error || "Unknown error"), "error");
      }
    } catch (e) {
      showToast("Network error checking update: " + e.message, "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        if (iconEl) iconEl.classList.remove("spinning");
      }
    }
  };

  // --- Phone & OPDS Connectivity Modal ---
  const btnPhoneConnect = document.getElementById("btn-phone-connect");
  const phoneModal = document.getElementById("phone-modal");
  const phoneModalClose = document.getElementById("phone-modal-close");
  const phoneWebUrl = document.getElementById("phone-web-url");
  const phoneOpdsUrl = document.getElementById("phone-opds-url");
  const btnCopyPhoneUrl = document.getElementById("btn-copy-phone-url");
  const btnCopyOpdsUrl = document.getElementById("btn-copy-opds-url");

  if (btnPhoneConnect && phoneModal) {
    btnPhoneConnect.addEventListener("click", async () => {
      phoneModal.classList.remove("hidden");
      try {
        const res = await fetch("/api/network/info");
        const data = await res.json();
        if (data.success) {
          const currentHost = window.location.hostname;
          const currentPort = window.location.port || "8000";
          const resolvedIp = (currentHost !== "localhost" && currentHost !== "127.0.0.1") ? currentHost : data.lan_ip;
          phoneWebUrl.value = `http://${resolvedIp}:${currentPort}/`;
          phoneOpdsUrl.value = `http://${resolvedIp}:${currentPort}/opds/v1.2/catalog`;
        }
      } catch (err) {
        phoneWebUrl.value = `${window.location.origin}/`;
        phoneOpdsUrl.value = `${window.location.origin}/opds/v1.2/catalog`;
      }
    });
  }

  if (phoneModalClose && phoneModal) {
    phoneModalClose.addEventListener("click", () => {
      phoneModal.classList.add("hidden");
    });
  }

  if (btnCopyPhoneUrl) {
    btnCopyPhoneUrl.addEventListener("click", () => {
      navigator.clipboard.writeText(phoneWebUrl.value).then(() => {
        btnCopyPhoneUrl.textContent = "✅ Copied!";
        setTimeout(() => btnCopyPhoneUrl.textContent = "📋 Copy", 2000);
      });
    });
  }

  if (btnCopyOpdsUrl) {
    btnCopyOpdsUrl.addEventListener("click", () => {
      navigator.clipboard.writeText(phoneOpdsUrl.value).then(() => {
        btnCopyOpdsUrl.textContent = "✅ Copied!";
        setTimeout(() => btnCopyOpdsUrl.textContent = "📋 Copy", 2000);
      });
    });
  }

  // --- In-App Web Reader ---
  const readerView = document.getElementById("reader-view");
  const readerClose = document.getElementById("reader-close");
  const readerPagesContainer = document.getElementById("reader-pages-container");
  const readerSeriesTitle = document.getElementById("reader-series-title");
  const readerChapterTitle = document.getElementById("reader-chapter-title");
  const readerPrevBtn = document.getElementById("reader-prev-btn");
  const readerNextBtn = document.getElementById("reader-next-btn");
  const readerProgressCounter = document.getElementById("reader-progress-counter");
  const readerScrollTop = document.getElementById("reader-scroll-top");
  const readerFullscreenBtn = document.getElementById("reader-fullscreen-btn");
  const readerSettingsBtn = document.getElementById("reader-settings-btn");
  const readerSettingsMenu = document.getElementById("reader-settings-menu");
  const readerSettingsClose = document.getElementById("reader-settings-close");
  const readerTopbar = document.querySelector(".reader-topbar");
  const readerBottomHud = document.querySelector(".reader-bottom-hud");

  let currentReadingChapterId = null;
  let lastReaderScrollTop = 0;
  let hudHidden = false;

  let currentReaderMode = localStorage.getItem("reader_mode") || "webtoon"; // 'webtoon' or 'paged'
  let currentReaderWidth = localStorage.getItem("reader_width") || "840px";
  let currentReaderGap = localStorage.getItem("reader_gap") || "0px";
  let pagedCurrentIndex = 0;
  let pagedTotalPages = 0;
  let currentChapterData = null;

  function setHudVisibility(visible) {
    hudHidden = !visible;
    if (readerTopbar) {
      if (visible) readerTopbar.classList.remove("hud-hidden");
      else readerTopbar.classList.add("hud-hidden");
    }
    if (readerBottomHud) {
      if (visible) readerBottomHud.classList.remove("hud-hidden");
      else readerBottomHud.classList.add("hud-hidden");
    }
  }

  // Reader Settings Menu Controls
  readerSettingsBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    readerSettingsMenu?.classList.toggle("hidden");
  });

  readerSettingsClose?.addEventListener("click", () => {
    readerSettingsMenu?.classList.add("hidden");
  });

  document.querySelectorAll("#reader-mode-toggle .seg-btn-mini").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#reader-mode-toggle .seg-btn-mini").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentReaderMode = btn.getAttribute("data-val") || "webtoon";
      localStorage.setItem("reader_mode", currentReaderMode);
      applyReaderLayout();
      triggerHaptic([10]);
    });
  });

  document.querySelectorAll("#reader-width-toggle .seg-btn-mini").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#reader-width-toggle .seg-btn-mini").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentReaderWidth = btn.getAttribute("data-val") || "840px";
      localStorage.setItem("reader_width", currentReaderWidth);
      applyReaderLayout();
      triggerHaptic([10]);
    });
  });

  document.querySelectorAll("#reader-gap-toggle .seg-btn-mini").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#reader-gap-toggle .seg-btn-mini").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentReaderGap = btn.getAttribute("data-val") || "0px";
      localStorage.setItem("reader_gap", currentReaderGap);
      applyReaderLayout();
      triggerHaptic([10]);
    });
  });

  function applyReaderLayout() {
    if (!readerPagesContainer) return;
    readerPagesContainer.style.maxWidth = currentReaderWidth;
    readerPagesContainer.style.gap = currentReaderGap;

    if (currentReaderMode === "paged") {
      readerPagesContainer.classList.add("reader-mode-paged");
      showPagedIndex(pagedCurrentIndex);
    } else {
      readerPagesContainer.classList.remove("reader-mode-paged");
      const wrappers = readerPagesContainer.querySelectorAll(".reader-page-wrapper");
      wrappers.forEach(w => w.classList.remove("page-active"));
    }
  }

  function showPagedIndex(idx) {
    if (!currentChapterData || !currentChapterData.pages) return;
    pagedCurrentIndex = Math.max(0, Math.min(pagedTotalPages - 1, idx));
    const wrappers = readerPagesContainer.querySelectorAll(".reader-page-wrapper");
    wrappers.forEach((w, i) => {
      if (i === pagedCurrentIndex) w.classList.add("page-active");
      else w.classList.remove("page-active");
    });
    readerProgressCounter.textContent = `Page ${pagedCurrentIndex + 1} of ${pagedTotalPages}`;
    readerView.scrollTop = 0;
    saveReadingProgressThrottled(pagedCurrentIndex + 1);
  }

  // Tap in reading area toggles HUD or turns page in paged mode
  if (readerPagesContainer) {
    readerPagesContainer.addEventListener("click", (e) => {
      if (e.target.tagName === "BUTTON" || e.target.closest("button") || e.target.tagName === "A") {
        return;
      }
      if (currentReaderMode === "paged" && pagedTotalPages > 0) {
        const rect = readerPagesContainer.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        if (clickX < rect.width / 3) {
          if (pagedCurrentIndex > 0) {
            showPagedIndex(pagedCurrentIndex - 1);
            triggerHaptic([10]);
          }
        } else if (clickX > (rect.width * 2) / 3) {
          if (pagedCurrentIndex < pagedTotalPages - 1) {
            showPagedIndex(pagedCurrentIndex + 1);
            triggerHaptic([10]);
          }
        } else {
          setHudVisibility(hudHidden);
        }
      } else {
        setHudVisibility(hudHidden);
      }
    });
  }

  // Fullscreen API toggle
  if (readerFullscreenBtn) {
    readerFullscreenBtn.addEventListener("click", () => {
      const isFs = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
      if (!isFs) {
        if (readerView.requestFullscreen) {
          readerView.requestFullscreen().catch(() => {});
        } else if (readerView.webkitRequestFullscreen) {
          readerView.webkitRequestFullscreen();
        } else if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        } else if (document.webkitExitFullscreen) {
          document.webkitExitFullscreen();
        }
      }
    });

    const updateFsBtnText = () => {
      const isFs = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
      readerFullscreenBtn.textContent = isFs ? "✕ Exit" : "⛶ Fullscreen";
    };
    document.addEventListener("fullscreenchange", updateFsBtnText);
    document.addEventListener("webkitfullscreenchange", updateFsBtnText);
  }

  window.closeReader = function() {
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    }
    if (seriesModal) seriesModal.classList.add("hidden");
    readerSettingsMenu?.classList.add("hidden");
    readerView.classList.add("hidden");
    readerPagesContainer.innerHTML = "";
    currentReadingChapterId = null;
    currentChapterData = null;
    switchTab("tab-library");
    loadLibrary();
  };

  readerClose.addEventListener("click", window.closeReader);

  readerScrollTop.addEventListener("click", () => {
    readerView.scrollTo({ top: 0, behavior: "smooth" });
  });

  window.handlePanelError = function(img, url) {
    if (!img) return;
    img.style.display = "none";
    const wrapper = img.parentElement;
    if (wrapper && !wrapper.querySelector(".reader-panel-error")) {
      const errDiv = document.createElement("div");
      errDiv.className = "reader-panel-error";
      errDiv.style = "padding: 1.5rem; background: rgba(30, 41, 59, 0.6); border: 1px dashed var(--border-color); border-radius: 8px; margin: 12px auto; max-width: 320px; text-align: center;";
      errDiv.innerHTML = `
        <div style="font-size: 1.5rem; margin-bottom: 4px;">⚠️</div>
        <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 8px;">Panel image failed to load</p>
        <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.8rem;" onclick="retryPanelImage(this, '${escapeAttr(url)}')">🔄 Tap to Reload Panel</button>
      `;
      wrapper.appendChild(errDiv);
    }
  };

  window.retryPanelImage = function(btn, url) {
    const wrapper = btn.closest(".reader-page-wrapper");
    if (!wrapper) return;
    const errDiv = wrapper.querySelector(".reader-panel-error");
    if (errDiv) errDiv.remove();
    const img = wrapper.querySelector(".reader-page");
    if (img) {
      img.style.display = "block";
      const sep = url.includes("?") ? "&" : "?";
      img.src = `${url}${sep}_t=${Date.now()}`;
    }
  };

  let progressSaveTimeout = null;
  function saveReadingProgressThrottled(pageNum) {
    if (!currentReadingChapterId) return;
    if (!progressSaveTimeout) {
      progressSaveTimeout = setTimeout(() => {
        progressSaveTimeout = null;
        fetch(`/api/chapter/${currentReadingChapterId}/progress`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ last_read_page: pageNum, read_status: 1 })
        }).catch(() => {});
      }, 1000);
    }
  }

  // Pre-buffer memory cache
  const prebufferedSet = new Set();
  function prebufferAhead(pagesList, startIdx, count = 10) {
    if (!pagesList) return;
    const end = Math.min(pagesList.length, startIdx + count);
    for (let i = startIdx; i < end; i++) {
      const u = pagesList[i];
      if (u && !prebufferedSet.has(u)) {
        prebufferedSet.add(u);
        const im = new Image();
        im.src = u;
        if (im.decode) im.decode().catch(() => {});
      }
    }
  }

  window.openReader = async function(chapterId) {
    currentReadingChapterId = chapterId;
    setHudVisibility(true);
    seriesModal.classList.add("hidden");
    readerSettingsMenu?.classList.add("hidden");
    readerView.classList.remove("hidden");
    readerView.scrollTop = 0;
    readerPagesContainer.innerHTML = "<p style='color: #94a3b8; padding: 3rem; text-align: center;'>Loading chapter panels...</p>";

    try {
      const res = await fetch(`/api/chapter/${chapterId}/pages`);
      const data = await res.json();
      currentChapterData = data;

      if (data.success && data.pages) {
        pagedTotalPages = data.total_pages || data.pages.length;
        pagedCurrentIndex = 0;

        readerSeriesTitle.textContent = data.series_title;
        readerChapterTitle.textContent = data.chapter_title;
        readerProgressCounter.textContent = `Total ${data.total_pages} panels`;

        // Configure Prev / Next buttons
        if (data.prev_chapter_id) {
          readerPrevBtn.disabled = false;
          readerPrevBtn.onclick = () => openReader(data.prev_chapter_id);
        } else {
          readerPrevBtn.disabled = true;
        }

        if (data.next_chapter_id) {
          readerNextBtn.disabled = false;
          readerNextBtn.onclick = () => openReader(data.next_chapter_id);
        } else {
          readerNextBtn.disabled = true;
        }

        // Render panels with error boundary and prebuffering
        const panelsHtml = data.pages.map((pUrl, idx) => `
          <div class="reader-page-wrapper" data-page-index="${idx}" style="position: relative; display: inline-block; width: 100%; text-align: center;">
            <img class="reader-page" src="${pUrl}" alt="Page ${idx + 1}" loading="lazy" decoding="async" id="page-panel-${idx}" onerror="handlePanelError(this, '${escapeAttr(pUrl)}')">
            <button class="btn-mark-promo" onclick="markPageAsPromo(${chapterId}, ${idx}, this)" style="position: absolute; right: 15px; top: 15px; background: rgba(15,23,42,0.85); color: #f87171; border: 1px solid #ef4444; border-radius: 6px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; opacity: 0.4; transition: opacity 0.2s;" onmouseenter="this.style.opacity='1'" onmouseleave="this.style.opacity='0.4'">🚫 Mark as Promo</button>
          </div>
        `).join("");

        // End-of-chapter card
        const endCardHtml = `
          <div class="reader-chapter-end-card" style="width: 90%; max-width: 500px; margin: 3rem auto 2rem auto; padding: 2rem 1.5rem; text-align: center; background: rgba(30, 41, 59, 0.85); border: 1px solid var(--border-color); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);">
            <h3 style="margin-bottom: 0.5rem; font-size: 1.2rem; color: var(--text-main);">Finished ${data.chapter_title} 🎉</h3>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.5rem;">${data.series_title}</p>
            <div style="display: flex; flex-direction: column; gap: 0.75rem; justify-content: center; align-items: stretch; max-width: 280px; margin: 0 auto;">
              ${data.next_chapter_id 
                ? `<button class="btn btn-primary" style="padding: 12px 18px; font-size: 0.95rem; font-weight: 600;" onclick="openReader(${data.next_chapter_id})">Next Chapter ❯</button>` 
                : '<p style="color: #4ade80; font-size: 0.85rem; margin: 4px 0;">🎉 You are caught up to the latest downloaded chapter!</p>'
              }
              ${data.prev_chapter_id 
                ? `<button class="btn btn-secondary" style="padding: 10px 16px; font-size: 0.85rem;" onclick="openReader(${data.prev_chapter_id})">❮ Previous Chapter</button>` 
                : ''
              }
              <button class="btn btn-secondary" style="padding: 10px 16px; font-size: 0.85rem;" onclick="closeReader()">Back to Library</button>
            </div>
          </div>
        `;

        readerPagesContainer.innerHTML = panelsHtml + endCardHtml;
        applyReaderLayout();

        // Prebuffer initial panels
        prebufferAhead(data.pages, 0, 10);

        // Scroll listener for progress tracking & pre-buffering
        readerView.onscroll = () => {
          if (currentReaderMode === "paged") return;
          const currentScroll = readerView.scrollTop;
          const diff = currentScroll - lastReaderScrollTop;

          if (diff > 35 && currentScroll > 80 && !hudHidden) {
            setHudVisibility(false);
          } else if (diff < -25 && hudHidden) {
            setHudVisibility(true);
          }
          lastReaderScrollTop = Math.max(0, currentScroll);

          const scrollPos = readerView.scrollTop + 300;
          const panels = readerPagesContainer.querySelectorAll(".reader-page");
          let currentPage = 1;
          panels.forEach((p, i) => {
            if (p.offsetTop <= scrollPos) {
              currentPage = i + 1;
            }
          });
          readerProgressCounter.textContent = `Page ${currentPage} of ${data.total_pages}`;
          saveReadingProgressThrottled(currentPage);
          prebufferAhead(data.pages, currentPage - 1, 10);
        };
      } else {
        readerPagesContainer.innerHTML = `<p style="color: var(--danger); padding: 3rem; text-align: center;">Error: ${data.error || 'Could not load chapter pages.'}</p>`;
      }
    } catch (e) {
      readerPagesContainer.innerHTML = `<p style="color: var(--danger); padding: 3rem; text-align: center;">Network error: ${e.message}</p>`;
    }
  };

  window.markPageAsPromo = async function(chapterId, pageIndex, btnElem) {
    if (!confirm(`Mark Page ${pageIndex + 1} as a recurring promotional/ad page? It will be automatically trimmed from future downloads.`)) {
      return;
    }
    btnElem.textContent = "Fingerprinting...";
    btnElem.disabled = true;
    try {
      const res = await fetch("/api/promos/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chapter_id: chapterId, page_index: pageIndex, label: `Page ${pageIndex + 1} Promo` })
      });
      const data = await res.json();
      if (data.success) {
        btnElem.textContent = "✅ Blocked";
        btnElem.style.color = "#10b981";
        btnElem.style.borderColor = "#10b981";
        btnElem.style.opacity = "1";
        showToast("✅ Promotional page fingerprinted! Future downloads will trim this ad.", "success");
      } else {
        showToast("Error marking promo: " + (data.error || "Unknown error"), "error");
        btnElem.textContent = "🚫 Mark as Promo";
        btnElem.disabled = false;
      }
    } catch (e) {
      showToast("Network error: " + e.message, "error");
      btnElem.textContent = "🚫 Mark as Promo";
      btnElem.disabled = false;
    }
  };

  // --- Diagnostic Lab Tab ---
  const labUrlInput = document.getElementById("lab-url");
  const btnLabTest = document.getElementById("btn-lab-test");
  const labResult = document.getElementById("lab-result");

  // Preset click handlers
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      labUrlInput.value = btn.getAttribute("data-url");
    });
  });

  btnLabTest.addEventListener("click", async () => {
    const url = labUrlInput.value.trim();
    if (!url) {
      showToast("Please paste a URL to test.", "info");
      return;
    }

    btnLabTest.textContent = "Testing...";
    btnLabTest.disabled = true;

    try {
      const res = await fetch("/api/lab/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      labResult.classList.remove("hidden");
      if (data.success && data.diagnostic) {
        const d = data.diagnostic;
        labResult.innerHTML = `
          <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid var(--success); padding: 1rem; border-radius: 8px;">
            <h4 style="color: var(--success); margin-bottom: 0.5rem;">✅ TEST PASSED</h4>
            <p><strong>Engine Detected:</strong> ${d.engine_name}</p>
            <p><strong>Series Title:</strong> ${d.series_title}</p>
            <p><strong>Panels Isolated:</strong> ${d.panel_count} clean panels</p>
            <p><strong>Next Chapter Link:</strong> ${d.next_chapter_url ? d.next_chapter_url : "None in DOM (Smart fallback active)"}</p>
          </div>
        `;
      } else {
        labResult.innerHTML = `
          <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--danger); padding: 1rem; border-radius: 8px;">
            <h4 style="color: var(--danger); margin-bottom: 0.5rem;">❌ TEST FAILED</h4>
            <p>${data.error || "Site could not be parsed."}</p>
          </div>
        `;
      }
      loadDiagnosticsTable();
    } catch (err) {
      labResult.innerHTML = `<p style="color: var(--danger);">Network error: ${err.message}</p>`;
      labResult.classList.remove("hidden");
    } finally {
      btnLabTest.textContent = "Run Test";
      btnLabTest.disabled = false;
    }
  });

  async function loadDiagnosticsTable() {
    const tbody = document.getElementById("diagnostic-tbody");
    try {
      const res = await fetch("/api/lab/sites");
      const data = await res.json();
      if (data.success && data.diagnostics && data.diagnostics.length > 0) {
        tbody.innerHTML = data.diagnostics.map((d) => `
          <tr>
            <td><strong>${d.domain}</strong></td>
            <td>${d.engine_detected || 'Unknown'}</td>
            <td><span class="${d.status === 'PASS' ? 'badge-pass' : 'badge-blocked'}">${d.status}</span></td>
            <td>${d.panels_found}</td>
            <td>${d.next_chapter_found ? '✅ Yes' : '❌ Fallback'}</td>
            <td>${new Date(d.last_checked).toLocaleDateString()}</td>
          </tr>
        `).join("");
      }
    } catch (e) {
      console.error("Error loading diagnostics table", e);
    }
  }

  // --- Settings Tab Handlers ---
  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      if (data.success && data.settings) {
        const s = data.settings;
        if (s.auto_update_enabled) document.getElementById("setting-auto-update").value = s.auto_update_enabled;
        if (s.auto_update_interval_hours) document.getElementById("setting-interval").value = s.auto_update_interval_hours;
        if (s.preferred_format) document.getElementById("setting-preferred-format").value = s.preferred_format;
        if (s.discord_webhook_url) document.getElementById("setting-discord-webhook").value = s.discord_webhook_url;
        if (s.ntfy_topic_url) document.getElementById("setting-ntfy-topic").value = s.ntfy_topic_url;
        if (s.telegram_bot_token) document.getElementById("setting-telegram-token").value = s.telegram_bot_token;
        if (s.telegram_chat_id) document.getElementById("setting-telegram-chat").value = s.telegram_chat_id;
        if (s.anilist_enabled) document.getElementById("setting-anilist-enabled").value = s.anilist_enabled;
        if (s.anilist_token) document.getElementById("setting-anilist-token").value = s.anilist_token;
        if (s.mal_enabled) document.getElementById("setting-mal-enabled").value = s.mal_enabled;
        if (s.mal_token) document.getElementById("setting-mal-token").value = s.mal_token;
        if (s.flaresolverr_url) document.getElementById("setting-flaresolverr-url").value = s.flaresolverr_url;
        if (s.ai_upscaler_url) document.getElementById("setting-upscaler-url").value = s.ai_upscaler_url;
      }
      loadPromoSignatures();
      loadBackupEstimate();
      loadBackupArchiveList();
    } catch (e) {
      console.error("Error loading settings", e);
    }
  }

  async function loadPromoSignatures() {
    const listElem = document.getElementById("promo-signatures-list");
    if (!listElem) return;
    try {
      const res = await fetch("/api/promos");
      const data = await res.json();
      if (data.success && data.signatures && data.signatures.length > 0) {
        listElem.innerHTML = data.signatures.map(s => `
          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(30, 41, 59, 0.5); padding: 8px 14px; border-radius: 6px; margin-bottom: 6px; border: 1px solid var(--border);">
            <div>
              <strong>${s.label || 'Promo'}</strong>
              <span style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted); margin-left: 8px;">${s.phash.slice(0, 16)}...</span>
            </div>
            <button onclick="deletePromo(${s.id})" class="btn btn-secondary" style="color: #f87171; border-color: #ef4444; padding: 2px 8px; font-size: 0.75rem;">Delete</button>
          </div>
        `).join("");
      } else {
        listElem.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No promotional page signatures registered yet. Mark pages in the Web Reader to auto-filter them!</p>';
      }
    } catch (e) {
      listElem.innerHTML = '<p style="color: var(--danger);">Failed to load signatures.</p>';
    }
  }

  window.deletePromo = async function(id) {
    if (!confirm("Delete this promotional filter signature?")) return;
    try {
      const res = await fetch(`/api/promos/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        loadPromoSignatures();
      }
    } catch (e) {
      showToast("Error deleting signature: " + e.message, "error");
    }
  };

  const btnVerifyAnilist = document.getElementById("btn-verify-anilist");
  if (btnVerifyAnilist) {
    btnVerifyAnilist.addEventListener("click", async () => {
      const token = document.getElementById("setting-anilist-token").value.trim();
      if (!token) return showToast("Please paste an AniList token first.", "info");
      btnVerifyAnilist.textContent = "Checking...";
      btnVerifyAnilist.disabled = true;
      const statusElem = document.getElementById("anilist-status");
      try {
        const res = await fetch("/api/tracker/verify/anilist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = `✅ Connected as: ${data.username} (ID: ${data.user_id})`;
          showToast(`Connected as AniList user: ${data.username}`, "success");
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = `❌ Verification failed: ${data.error}`;
          showToast(`Verification failed: ${data.error}`, "error");
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = `❌ Network error: ${e.message}`;
        showToast(`Network error: ${e.message}`, "error");
      } finally {
        btnVerifyAnilist.textContent = "Verify";
        btnVerifyAnilist.disabled = false;
      }
    });
  }

  const btnVerifyMal = document.getElementById("btn-verify-mal");
  if (btnVerifyMal) {
    btnVerifyMal.addEventListener("click", async () => {
      const token = document.getElementById("setting-mal-token").value.trim();
      if (!token) return showToast("Please paste a MyAnimeList access token first.", "info");
      btnVerifyMal.textContent = "Checking...";
      btnVerifyMal.disabled = true;
      const statusElem = document.getElementById("mal-status");
      try {
        const res = await fetch("/api/tracker/verify/mal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = `✅ Connected as: ${data.username} (ID: ${data.user_id})`;
          showToast(`Connected as MyAnimeList user: ${data.username}`, "success");
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = `❌ Verification failed: ${data.error}`;
          showToast(`Verification failed: ${data.error}`, "error");
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = `❌ Network error: ${e.message}`;
        showToast(`Network error: ${e.message}`, "error");
      } finally {
        btnVerifyMal.textContent = "Verify";
        btnVerifyMal.disabled = false;
      }
    });
  }

  const btnSaveSettings = document.getElementById("btn-save-settings");
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", async () => {
      const payload = {
        auto_update_enabled: document.getElementById("setting-auto-update").value,
        auto_update_interval_hours: document.getElementById("setting-interval").value,
        preferred_format: document.getElementById("setting-preferred-format").value,
        discord_webhook_url: document.getElementById("setting-discord-webhook").value.trim(),
        ntfy_topic_url: document.getElementById("setting-ntfy-topic").value.trim(),
        telegram_bot_token: document.getElementById("setting-telegram-token").value.trim(),
        telegram_chat_id: document.getElementById("setting-telegram-chat").value.trim(),
        anilist_enabled: document.getElementById("setting-anilist-enabled").value,
        anilist_token: document.getElementById("setting-anilist-token").value.trim(),
        mal_enabled: document.getElementById("setting-mal-enabled").value,
        mal_token: document.getElementById("setting-mal-token").value.trim(),
        flaresolverr_url: document.getElementById("setting-flaresolverr-url") ? document.getElementById("setting-flaresolverr-url").value.trim() : "",
        ai_upscaler_url: document.getElementById("setting-upscaler-url") ? document.getElementById("setting-upscaler-url").value.trim() : ""
      };

      btnSaveSettings.textContent = "Saving...";
      btnSaveSettings.disabled = true;

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        const msg = document.getElementById("settings-status-msg");
        if (data.success) {
          msg.textContent = "✅ Settings successfully saved!";
          msg.classList.remove("hidden");
          setTimeout(() => msg.classList.add("hidden"), 3000);
          showToast("Settings successfully saved!", "success");
        }
      } catch (e) {
        showToast("Failed to save settings: " + e.message, "error");
      } finally {
        btnSaveSettings.textContent = "💾 Save Settings";
        btnSaveSettings.disabled = false;
      }
    });
  }

  const btnTestDiscord = document.getElementById("btn-test-discord");
  if (btnTestDiscord) {
    btnTestDiscord.addEventListener("click", async () => {
      const target = document.getElementById("setting-discord-webhook").value.trim();
      if (!target) return showToast("Please enter a Discord Webhook URL first.", "info");
      btnTestDiscord.textContent = "Testing...";
      btnTestDiscord.disabled = true;
      try {
        const res = await fetch("/api/settings/test-notification", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel: "discord", target })
        });
        const data = await res.json();
        showToast(data.success ? "✅ Discord webhook test sent successfully!" : "❌ Discord webhook test failed. Verify URL.", data.success ? "success" : "error");
      } catch (e) {
        showToast("Test error: " + e.message, "error");
      } finally {
        btnTestDiscord.textContent = "Test Discord";
        btnTestDiscord.disabled = false;
      }
    });
  }

  const btnTestNtfy = document.getElementById("btn-test-ntfy");
  if (btnTestNtfy) {
    btnTestNtfy.addEventListener("click", async () => {
      const target = document.getElementById("setting-ntfy-topic").value.trim();
      if (!target) return showToast("Please enter an Ntfy Topic URL first.", "info");
      btnTestNtfy.textContent = "Testing...";
      btnTestNtfy.disabled = true;
      try {
        const res = await fetch("/api/settings/test-notification", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel: "ntfy", target })
        });
        const data = await res.json();
        showToast(data.success ? "✅ Ntfy push test sent successfully!" : "❌ Ntfy push test failed.", data.success ? "success" : "error");
      } catch (e) {
        showToast("Test error: " + e.message, "error");
      } finally {
        btnTestNtfy.textContent = "Test Ntfy";
        btnTestNtfy.disabled = false;
      }
    });
  }

  const btnTestFlaresolverr = document.getElementById("btn-test-flaresolverr");
  if (btnTestFlaresolverr) {
    btnTestFlaresolverr.addEventListener("click", async () => {
      const url = document.getElementById("setting-flaresolverr-url").value.trim() || "http://localhost:8191/v1";
      btnTestFlaresolverr.textContent = "Testing...";
      btnTestFlaresolverr.disabled = true;
      const statusElem = document.getElementById("flaresolverr-status");
      try {
        const res = await fetch("/api/settings/test-flaresolverr", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = "✅ FlareSolverr is online and accessible!";
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = "❌ Could not reach FlareSolverr container. Check URL and Docker container status.";
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = "❌ Network error: " + e.message;
      } finally {
        btnTestFlaresolverr.textContent = "Test Connection";
        btnTestFlaresolverr.disabled = false;
      }
    });
  }

  const btnTestUpscaler = document.getElementById("btn-test-upscaler");
  if (btnTestUpscaler) {
    btnTestUpscaler.addEventListener("click", async () => {
      const url = document.getElementById("setting-upscaler-url").value.trim() || "http://localhost:5000/upscale";
      btnTestUpscaler.textContent = "Testing...";
      btnTestUpscaler.disabled = true;
      const statusElem = document.getElementById("upscaler-status");
      try {
        const res = await fetch("/api/settings/test-upscaler", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        const statRes = await fetch("/api/settings/upscaler-status");
        const statData = await statRes.json();
        const statusObj = (statData && statData.status) || {};

        const localEngines = [];
        if (statusObj.waifu2x_cli) localEngines.push("waifu2x-ncnn-vulkan");
        if (statusObj.realesrgan_cli) localEngines.push("realesrgan-ncnn-vulkan");

        let msg = "";
        if (data.success) {
          msg = "✅ AI Upscaler microservice is online!";
          statusElem.style.color = "var(--success)";
        } else {
          msg = "ℹ️ REST API offline. ";
          if (localEngines.length > 0) {
            msg += `Local CLI detected (${localEngines.join(", ")}).`;
            statusElem.style.color = "var(--success)";
          } else {
            msg += "Lanczos-4 high-quality fallback will be used.";
            statusElem.style.color = "var(--warning)";
          }
        }
        statusElem.textContent = msg;
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = "❌ Network error: " + e.message;
      } finally {
        btnTestUpscaler.textContent = "Test Connection";
        btnTestUpscaler.disabled = false;
      }
    });
  }

  // =====================================================================
  // --- Backup & Multi-Volume Sync UI Handlers ---
  // =====================================================================

  let exportPollInterval = null;
  let selectedImportFiles = [];

  window.openBackupFolder = async function() {
    if (window.AndroidApp && typeof window.AndroidApp.openBackupFolder === "function") {
      try {
        window.AndroidApp.openBackupFolder();
        showToast("Opening device backups folder...", "info");
        return;
      } catch (err) {
        console.warn("Android openBackupFolder error", err);
      }
    }
    try {
      const res = await fetch("/api/backup/open-folder", { method: "POST" });
      const data = await res.json();
      if (data && data.success) {
        showToast(data.message || "Opened backups folder", "success");
      } else {
        showToast("Backups stored in: " + (data.path || "backups/"), "info");
      }
    } catch (e) {
      showToast("Backups stored in device backups folder", "info");
    }
  };

  window.shareBackupFile = function(filename) {
    if (window.AndroidApp && typeof window.AndroidApp.shareBackupFile === "function") {
      try {
        window.AndroidApp.shareBackupFile(filename);
        return;
      } catch (err) {
        console.warn("Android shareBackupFile error", err);
      }
    }
    if (navigator.share) {
      navigator.share({
        title: filename,
        url: `/api/backup/download/${filename}`
      }).catch(() => {});
    } else {
      showToast("Archive available at: /api/backup/download/" + filename, "info");
    }
  };

  async function loadBackupEstimate() {
    try {
      const res = await fetch("/api/backup/estimate?batch_size_mb=1450");
      const data = await res.json();
      if (data && data.success) {
        const statSeries = document.getElementById("backup-stat-series");
        const statChapters = document.getElementById("backup-stat-chapters");
        const statSize = document.getElementById("backup-stat-size");
        const statBatches = document.getElementById("backup-stat-batches");

        if (statSeries) statSeries.textContent = data.total_series;
        if (statChapters) statChapters.textContent = data.total_chapters;
        if (statSize) statSize.textContent = data.total_size_formatted;
        if (statBatches) {
          statBatches.textContent = data.batches_1_5gb > 1 ? `${data.batches_1_5gb} Batches` : `${data.batches_1_5gb} Batch`;
        }
      }
    } catch (e) {
      console.warn("Could not load backup estimate", e);
    }
  }

  async function loadBackupArchiveList() {
    const listElem = document.getElementById("backup-cache-list");
    if (!listElem) return;
    try {
      const res = await fetch("/api/backup/list");
      const data = await res.json();
      if (data && data.success && data.files && data.files.length > 0) {
        listElem.innerHTML = data.files.map(f => `
          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(30, 41, 59, 0.4); padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; border: 1px solid var(--border-color); flex-wrap: wrap; gap: 8px;">
            <div>
              <strong style="color: var(--text-main); font-size: 0.88rem;">${f.filename}</strong>
              <span style="color: var(--text-muted); font-size: 0.78rem; margin-left: 8px;">(${f.size_formatted})</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <a href="${f.url}" download="${f.filename}" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; text-decoration: none; border-radius: 4px;">⬇️ Download</a>
              <button onclick="openBackupFolder()" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; border-radius: 4px;">📂 View Folder</button>
              <button onclick="shareBackupFile('${f.filename}')" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; border-radius: 4px;">🔗 Share</button>
            </div>
          </div>
        `).join("");
      } else {
        listElem.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">No cached backup archives on disk.</span>';
      }
    } catch (e) {
      console.warn("Could not load backup cache list", e);
    }
  }

  // Refresh Stats button
  const btnRefreshBackupStats = document.getElementById("btn-refresh-backup-stats");
  if (btnRefreshBackupStats) {
    btnRefreshBackupStats.addEventListener("click", () => {
      loadBackupEstimate();
      loadBackupArchiveList();
      showToast("Library backup stats refreshed", "info");
    });
  }

  // Clear Cache button
  const btnClearBackupCache = document.getElementById("btn-clear-backup-cache");
  if (btnClearBackupCache) {
    btnClearBackupCache.addEventListener("click", async () => {
      if (!confirm("Delete all exported backup archives from phone storage?")) return;
      btnClearBackupCache.disabled = true;
      try {
        const res = await fetch("/api/backup/clear", { method: "POST" });
        const data = await res.json();
        if (data.success) {
          showToast(`Cleared ${data.purged_count} archive(s), freed ${data.freed_formatted}.`, "success");
          loadBackupArchiveList();
        } else {
          showToast("Failed to clear cache: " + data.error, "error");
        }
      } catch (e) {
        showToast("Error clearing cache: " + e.message, "error");
      } finally {
        btnClearBackupCache.disabled = false;
      }
    });
  }

  // Start Export button
  const btnStartExport = document.getElementById("btn-start-export");
  if (btnStartExport) {
    btnStartExport.addEventListener("click", async () => {
      const mode = document.getElementById("backup-export-mode").value;
      const includeFiles = document.getElementById("backup-include-files").checked;

      btnStartExport.disabled = true;
      btnStartExport.textContent = "⏳ Initializing Export...";

      const progressBox = document.getElementById("backup-export-progress-box");
      const statusLabel = document.getElementById("backup-export-status-label");
      const percentLabel = document.getElementById("backup-export-percent");
      const progressBar = document.getElementById("backup-export-progress-bar");
      const detailLabel = document.getElementById("backup-export-detail");
      const downloadsBox = document.getElementById("backup-export-downloads-box");
      const filesList = document.getElementById("backup-export-files-list");

      progressBox.classList.remove("hidden");
      downloadsBox.classList.add("hidden");
      progressBar.style.width = "0%";
      percentLabel.textContent = "0%";
      statusLabel.textContent = "Scheduling export job...";
      detailLabel.textContent = "Packing metadata & assets...";

      try {
        const res = await fetch("/api/backup/export", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: mode,
            batch_size_mb: 1450,
            include_files: includeFiles
          })
        });

        const data = await res.json();
        if (!data.success) {
          throw new Error(data.error || "Failed to start export");
        }

        // Start polling progress
        if (exportPollInterval) clearInterval(exportPollInterval);
        exportPollInterval = setInterval(async () => {
          try {
            const sRes = await fetch("/api/backup/status");
            const status = await sRes.json();
            if (!status || !status.success) return;

            if (status.is_running) {
              const pct = Math.min(100, Math.max(0, status.percent || 0));
              progressBar.style.width = pct + "%";
              percentLabel.textContent = pct + "%";
              statusLabel.textContent = status.message || "Generating archives...";
              detailLabel.textContent = `Batch ${status.current_batch || 1} of ${status.total_batches || 1} • Chapter ${status.current_step || 0} of ${status.total_steps || 0}`;
            } else if (status.status === "completed") {
              clearInterval(exportPollInterval);
              exportPollInterval = null;

              progressBar.style.width = "100%";
              percentLabel.textContent = "100%";
              statusLabel.textContent = "✅ Export Completed!";
              detailLabel.textContent = status.message;

              // Display download links with View Folder, Save to Device, and Share
              const batchFiles = status.batch_files || data.batch_files || [];
              if (batchFiles.length > 0) {
                filesList.innerHTML = batchFiles.map((url, idx) => {
                  const filename = url.split("/").pop();
                  const label = batchFiles.length > 1 ? `Part ${idx + 1} of ${batchFiles.length}` : "Complete Library Archive";
                  return `
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 8px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;">
                      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                        <span>📦 <strong>${label}</strong> <span style="font-size: 0.8rem; color: var(--text-muted);">(${filename})</span></span>
                        <span style="font-size: 0.75rem; background: rgba(16, 185, 129, 0.2); color: var(--success); padding: 2px 8px; border-radius: 4px; font-weight: 600;">Saved on Device</span>
                      </div>
                      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <a href="${url}" download="${filename}" class="btn btn-primary" style="flex: 1; min-width: 140px; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 12px; font-size: 0.85rem;">
                          ⬇️ Download ZIP
                        </a>
                        <button type="button" onclick="openBackupFolder()" class="btn btn-secondary" style="flex: 1; min-width: 130px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 12px; font-size: 0.85rem;">
                          📂 View Folder
                        </button>
                        <button type="button" onclick="shareBackupFile('${filename}')" class="btn btn-secondary" style="display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 12px; font-size: 0.85rem;">
                          🔗 Share
                        </button>
                      </div>
                    </div>
                  `;
                }).join("");
                downloadsBox.classList.remove("hidden");
              }

              btnStartExport.disabled = false;
              btnStartExport.textContent = "📦 Create Backup Export";
              showToast("Backup export stored on device!", "success");
              loadBackupArchiveList();
            } else if (status.status === "error") {
              clearInterval(exportPollInterval);
              exportPollInterval = null;

              statusLabel.textContent = "❌ Export Failed";
              detailLabel.textContent = status.error || "Unknown error occurred";
              btnStartExport.disabled = false;
              btnStartExport.textContent = "📦 Create Backup Export";
              showToast("Backup export failed: " + (status.error || "Error"), "error");
            }
          } catch (err) {
            console.warn("Polling status error", err);
          }
        }, 800);

      } catch (err) {
        progressBox.classList.add("hidden");
        btnStartExport.disabled = false;
        btnStartExport.textContent = "📦 Create Backup Export";
        showToast("Export error: " + err.message, "error");
      }
    });
  }

  // View Folder button
  const btnViewBackupFolder = document.getElementById("btn-view-backup-folder");
  if (btnViewBackupFolder) {
    btnViewBackupFolder.addEventListener("click", () => {
      window.openBackupFolder();
    });
  }

  // --- Import / Restore Handlers ---
  const backupDropZone = document.getElementById("backup-drop-zone");
  const backupFileInput = document.getElementById("backup-file-input");
  const backupSelectedLabel = document.getElementById("backup-selected-files-label");
  const btnStartImport = document.getElementById("btn-start-import");

  function handleBackupFilesSelection(files) {
    if (!files || files.length === 0) return;
    const zips = Array.from(files).filter(f => f.name.toLowerCase().endsWith(".zip"));
    if (zips.length === 0) {
      showToast("Please select valid .zip backup files.", "error");
      return;
    }
    // Sort logically so part1 runs before part2
    zips.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
    selectedImportFiles = zips;

    backupSelectedLabel.textContent = `Selected (${zips.length}): ${zips.map(f => f.name).join(", ")}`;
    backupSelectedLabel.classList.remove("hidden");
    btnStartImport.style.display = "block";
    btnStartImport.disabled = false;
    btnStartImport.textContent = `📥 Restore ${zips.length} Selected Archive${zips.length > 1 ? 's' : ''}`;
  }

  if (backupDropZone && backupFileInput) {
    backupDropZone.addEventListener("click", () => backupFileInput.click());
    backupFileInput.addEventListener("change", (e) => handleBackupFilesSelection(e.target.files));

    backupDropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      backupDropZone.style.borderColor = "var(--accent)";
      backupDropZone.style.background = "rgba(99, 102, 241, 0.15)";
    });

    backupDropZone.addEventListener("dragleave", () => {
      backupDropZone.style.borderColor = "var(--border-color)";
      backupDropZone.style.background = "rgba(19, 27, 46, 0.5)";
    });

    backupDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      backupDropZone.style.borderColor = "var(--border-color)";
      backupDropZone.style.background = "rgba(19, 27, 46, 0.5)";
      if (e.dataTransfer && e.dataTransfer.files) {
        handleBackupFilesSelection(e.dataTransfer.files);
      }
    });
  }

  if (btnStartImport) {
    btnStartImport.addEventListener("click", async () => {
      if (!selectedImportFiles || selectedImportFiles.length === 0) return;

      btnStartImport.disabled = true;
      btnStartImport.style.display = "none";

      const progressBox = document.getElementById("backup-import-progress-box");
      const statusLabel = document.getElementById("backup-import-status-label");
      const percentLabel = document.getElementById("backup-import-percent");
      const progressBar = document.getElementById("backup-import-progress-bar");
      const detailLabel = document.getElementById("backup-import-detail");
      const resultsBox = document.getElementById("backup-import-results-box");

      progressBox.classList.remove("hidden");
      resultsBox.classList.remove("hidden");
      resultsBox.innerHTML = "";

      const totalFiles = selectedImportFiles.length;
      let totalImportedChapters = 0;
      let totalSyncedSeries = 0;

      for (let i = 0; i < totalFiles; i++) {
        const file = selectedImportFiles[i];
        const overallPercent = Math.round((i / totalFiles) * 100);
        progressBar.style.width = overallPercent + "%";
        percentLabel.textContent = overallPercent + "%";
        statusLabel.textContent = `[${i + 1}/${totalFiles}] Restoring ${file.name}...`;
        detailLabel.textContent = `Streaming ${file.name} directly to storage without memory buffering...`;

        try {
          const formData = new FormData();
          formData.append("file", file);

          const res = await fetch("/api/backup/import", {
            method: "POST",
            body: formData
          });

          const data = await res.json();
          if (data && data.success) {
            totalImportedChapters += (data.chapters_imported || 0);
            totalSyncedSeries += (data.series_synced || 0);

            resultsBox.innerHTML += `
              <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; font-size: 0.85rem;">
                ✅ <strong>${file.name}</strong> (${data.batch_label || 'Complete Archive'}): 
                <strong>${data.chapters_imported}</strong> chapters restored, 
                <strong>${data.series_synced}</strong> series synced seamlessly (${data.storage_freed_or_used || ''}).
              </div>
            `;
          } else {
            resultsBox.innerHTML += `
              <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; font-size: 0.85rem;">
                ❌ <strong>${file.name}</strong>: ${data ? data.error : "Failed to restore"}
              </div>
            `;
          }
        } catch (e) {
          resultsBox.innerHTML += `
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; font-size: 0.85rem;">
              ❌ <strong>${file.name}</strong>: Network or file read error: ${e.message}
            </div>
          `;
        }
      }

      progressBar.style.width = "100%";
      percentLabel.textContent = "100%";
      statusLabel.textContent = "✅ Restoration Finished!";
      detailLabel.textContent = `Consolidated ${totalImportedChapters} chapters across all processed volumes.`;

      showToast(`Sequential restore complete! ${totalImportedChapters} chapters updated.`, "success");

      // Reset selection
      selectedImportFiles = [];
      if (backupFileInput) backupFileInput.value = "";
      backupSelectedLabel.classList.add("hidden");

      // Refresh library & stats
      loadLibrary();
      loadBackupEstimate();
    });
  }

  // Switch tabs also triggers promo list load if settings tab
  const settingsTabBtn = document.querySelector('[data-tab="settings"]');
  if (settingsTabBtn) {
    settingsTabBtn.addEventListener("click", () => {
      loadSettings();
    });
  }

  // ========================================================
  // 🔍 GLOBAL SEARCH & MULTI-SOURCE COMPARISON ENGINE
  // ========================================================
  const modeSearchBtn = document.getElementById("mode-search-btn");
  const modeUrlBtn = document.getElementById("mode-url-btn");
  const searchModeContainer = document.getElementById("search-mode-container");
  const urlModeContainer = document.getElementById("url-mode-container");

  const globalSearchForm = document.getElementById("global-search-form");
  const globalSearchInput = document.getElementById("global-search-input");
  const btnGlobalSearch = document.getElementById("btn-global-search");
  const btnSearchClear = document.getElementById("btn-search-clear");
  const searchTierChips = document.querySelectorAll(".tier-chip");
  const searchStatusBar = document.getElementById("search-status-bar");
  const searchStatusText = document.getElementById("search-status-text");
  const searchProgressBar = document.getElementById("search-progress-bar");
  const searchResultsGrid = document.getElementById("search-results-grid");

  const sourceModal = document.getElementById("source-modal");
  const sourceModalClose = document.getElementById("source-modal-close");
  const sourceModalTitle = document.getElementById("source-modal-title");
  const sourceModalCover = document.getElementById("source-modal-cover");
  const sourceModalCountBadge = document.getElementById("source-modal-count-badge");
  const sourceModalList = document.getElementById("source-modal-list");

  // Sidebar Drawer & 3-Dot Menu Popup
  const btnAppMenu = document.getElementById("btn-app-menu");
  const sidebarDrawer = document.getElementById("sidebar-drawer");
  const drawerBackdrop = document.getElementById("drawer-backdrop");
  const drawerClose = document.getElementById("drawer-close");
  const drawerItems = document.querySelectorAll(".drawer-item");
  const drawerThemeToggle = document.getElementById("drawer-theme-toggle");
  const drawerPhoneConnect = document.getElementById("drawer-phone-connect");
  const drawerUpdateLibrary = document.getElementById("drawer-update-library");

  function openDrawer() {
    sidebarDrawer?.classList.add("open");
    drawerBackdrop?.classList.remove("hidden");
    void drawerBackdrop?.offsetWidth;
    drawerBackdrop?.classList.add("active");
  }

  function closeDrawer() {
    sidebarDrawer?.classList.remove("open");
    drawerBackdrop?.classList.remove("active");
    setTimeout(() => {
      drawerBackdrop?.classList.add("hidden");
    }, 280);
  }

  btnAppMenu?.addEventListener("click", openDrawer);
  drawerClose?.addEventListener("click", closeDrawer);
  drawerBackdrop?.addEventListener("click", closeDrawer);

  drawerItems.forEach(item => {
    item.addEventListener("click", () => {
      const tab = item.getAttribute("data-tab");
      const mode = item.getAttribute("data-mode");
      if (tab) {
        switchTab(tab);
        drawerItems.forEach(i => i.classList.remove("active"));
        item.classList.add("active");
      }
      if (mode) {
        setMode(mode);
      }
      closeDrawer();
    });
  });

  drawerThemeToggle?.addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("btn-theme-toggle")?.click();
    closeDrawer();
  });

  drawerPhoneConnect?.addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("btn-phone-connect")?.click();
    closeDrawer();
  });

  drawerUpdateLibrary?.addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("btn-update-library")?.click();
    closeDrawer();
  });

  let activeSearchTier = "fast";
  let currentSearchResults = [];

  function setMode(mode) {
    if (mode === "search") {
      modeSearchBtn?.classList.add("active");
      modeUrlBtn?.classList.remove("active");
      searchModeContainer?.classList.remove("hidden");
      urlModeContainer?.classList.add("hidden");
    } else {
      modeUrlBtn?.classList.add("active");
      modeSearchBtn?.classList.remove("active");
      urlModeContainer?.classList.remove("hidden");
      searchModeContainer?.classList.add("hidden");
    }
  }

  modeSearchBtn?.addEventListener("click", () => setMode("search"));
  modeUrlBtn?.addEventListener("click", () => setMode("url"));

  // Tier chips
  searchTierChips.forEach(chip => {
    chip.addEventListener("click", () => {
      searchTierChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      activeSearchTier = chip.getAttribute("data-tier") || "fast";
      if (globalSearchInput && globalSearchInput.value.trim().length >= 2) {
        performGlobalSearch(globalSearchInput.value.trim());
      }
    });
  });

  // Clear button visibility & action
  globalSearchInput?.addEventListener("input", () => {
    if (globalSearchInput.value.trim()) {
      btnSearchClear?.classList.remove("hidden");
    } else {
      btnSearchClear?.classList.add("hidden");
    }
  });

  btnSearchClear?.addEventListener("click", () => {
    if (globalSearchInput) {
      globalSearchInput.value = "";
      btnSearchClear.classList.add("hidden");
      globalSearchInput.focus();
    }
  });

  // Form submit & button click handlers
  globalSearchForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = globalSearchInput?.value.trim();
    if (q) performGlobalSearch(q);
  });

  btnGlobalSearch?.addEventListener("click", (e) => {
    e.preventDefault();
    const q = globalSearchInput?.value.trim();
    if (q) performGlobalSearch(q);
  });

  // Ctrl+K Desktop Command Palette Shortcut
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openCommandPalette();
    }
  });

  // Close modals on backdrop click or ESC
  sourceModalClose?.addEventListener("click", () => {
    sourceModal?.classList.add("hidden");
  });

  sourceModal?.addEventListener("click", (e) => {
    if (e.target === sourceModal) {
      sourceModal.classList.add("hidden");
    }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      sourceModal?.classList.add("hidden");
    }
  });

  // Skeleton shimmer
  function renderSearchSkeletons(count = 6) {
    if (!searchResultsGrid) return;
    let html = "";
    for (let i = 0; i < count; i++) {
      html += `
        <div class="skeleton-card">
          <div class="skeleton-poster"></div>
          <div class="skeleton-lines">
            <div class="skeleton-line" style="width: 75%; height: 16px;"></div>
            <div class="skeleton-line" style="width: 50%;"></div>
            <div class="skeleton-line" style="width: 35%; height: 20px; border-radius: 12px; margin-top: 4px;"></div>
          </div>
        </div>
      `;
    }
    searchResultsGrid.innerHTML = html;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderSearchResults(clusters) {
    currentSearchResults = clusters || [];
    if (!searchResultsGrid) return;

    if (!clusters || clusters.length === 0) {
      searchResultsGrid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 2.5rem 1rem; text-align: center; color: var(--text-muted);">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">🔍</div>
          <h3 style="color: var(--text-main); margin-bottom: 4px;">No series found</h3>
          <p style="font-size: 0.85rem;">Try adjusting your query or switch to the <strong>🌐 All 25+ Sites</strong> filter tier.</p>
        </div>
      `;
      return;
    }

    searchResultsGrid.innerHTML = clusters.map((cluster, idx) => {
      const title = escapeHtml(cluster.canonical_title || "Unknown");
      const altSnippet = (cluster.alt_titles && cluster.alt_titles.length > 0)
        ? escapeHtml(cluster.alt_titles.slice(0, 2).join(" • "))
        : "";
      const sourceCount = (cluster.sources && cluster.sources.length) || 1;
      const chNum = cluster.max_chapter_num || cluster.latest_chapter_num;
      let latestCh = "Available";
      if (chNum && chNum > 1) {
        latestCh = `Ch. ${Number.isInteger(chNum) ? chNum : chNum.toFixed(1)}`;
      } else if (cluster.latest_chapter && cluster.latest_chapter !== "Chapter 1") {
        latestCh = cluster.latest_chapter;
      }
      const rawCover = cluster.cover_url || "";
      const coverUrl = rawCover ? `/api/cover-proxy?url=${encodeURIComponent(rawCover)}` : "";

      return `
        <div class="search-result-card" data-cluster-index="${idx}" onclick="window.openSourceComparisonModal(${idx})">
          <img class="search-card-poster" src="${escapeHtml(coverUrl)}" alt="${title}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'75\\' height=\\'105\\'><rect fill=\\'%231c2640\\' width=\\'75\\' height=\\'105\\'/><text fill=\\'%2394a3b8\\' x=\\'50%\\' y=\\'50%\\' text-anchor=\\'middle\\' font-size=\\'10\\'>No Cover</text></svg>'">
          <div class="search-card-content">
            <div>
              <h4 class="search-card-title" title="${title}">${title}</h4>
              ${altSnippet ? `<div class="search-card-alt" title="${altSnippet}">${altSnippet}</div>` : ''}
              <div class="search-card-badges">
                <span class="search-badge-source">🌐 ${sourceCount} Source${sourceCount > 1 ? 's' : ''}</span>
                <span class="search-badge-ch">📖 ${latestCh}</span>
              </div>
            </div>
            <div class="search-card-actions">
              <button class="btn btn-secondary btn-compare-sources" data-cluster-index="${idx}" onclick="event.stopPropagation(); window.openSourceComparisonModal(${idx})">
                <span class="compare-text-full">🔍 Compare Sources</span>
                <span class="compare-text-mobile">🔍 Sources</span>
              </button>
              <button class="btn btn-primary btn-quick-dl" data-cluster-index="${idx}" onclick="event.stopPropagation(); window.quickDownloadCluster(${idx})">⚡ Quick DL</button>
            </div>
          </div>
        </div>
      `;
    }).join("");

    // Wire action buttons with event delegation & direct binding
    searchResultsGrid.querySelectorAll(".btn-compare-sources").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute("data-cluster-index"), 10);
        openSourceComparisonModal(idx);
      });
    });

    searchResultsGrid.querySelectorAll(".btn-quick-dl").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute("data-cluster-index"), 10);
        quickDownloadCluster(idx);
      });
    });

    searchResultsGrid.querySelectorAll(".search-result-card").forEach(card => {
      card.addEventListener("click", () => {
        const idx = parseInt(card.getAttribute("data-cluster-index"), 10);
        openSourceComparisonModal(idx);
      });
    });
  }

  function openSourceComparisonModal(idxOrCluster) {
    let cluster = idxOrCluster;
    if (typeof idxOrCluster === "number" || typeof idxOrCluster === "string") {
      const i = parseInt(idxOrCluster, 10);
      cluster = currentSearchResults[i];
    }
    if (!cluster) {
      showToast("Could not find source details for this series.", "info");
      return;
    }
    if (!sourceModal) return;

    if (cluster.cover_url) {
      currentCatalogCoverUrl = cluster.cover_url;
    }
    if (cluster.canonical_title) {
      currentSeriesTitle = cluster.canonical_title;
    }

    sourceModalTitle.textContent = cluster.canonical_title || "Unknown Series";
    const rawModalCover = cluster.cover_url || "";
    const modalCoverSrc = rawModalCover ? `/api/cover-proxy?url=${encodeURIComponent(rawModalCover)}` : '';
    sourceModalCover.src = modalCoverSrc || 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="48" height="68"><rect fill="%231c2640" width="48" height="68"/></svg>';
    sourceModalCover.onerror = function() {
      this.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="48" height="68"><rect fill="%231c2640" width="48" height="68"/></svg>';
    };

    const count = (cluster.sources && cluster.sources.length) || 0;
    sourceModalCountBadge.textContent = `${count} Source${count === 1 ? '' : 's'} Available`;

    if (!cluster.sources || cluster.sources.length === 0) {
      sourceModalList.innerHTML = `<p style="color: var(--text-muted); padding: 1rem; text-align: center;">No specific hosting sources discovered.</p>`;
    } else {
      sourceModalList.innerHTML = cluster.sources.map(src => {
        const logo = src.source_logo || `/docs/logos/${src.source_key}.png`;
        const lat = src.latency_ms ? `⚡ ${src.latency_ms}ms` : '🟢 Fast';
        const qTag = src.quality_tag || '1080p WebP';
        const chTxt = src.latest_chapter || (src.latest_chapter_num ? `Chapter ${src.latest_chapter_num}` : 'Available');
        const srcUrl = src.series_url || src.url || "";

        return `
          <div class="source-item-row">
            <div class="source-info-left">
              <img class="source-site-icon" src="${escapeHtml(logo)}" alt="${escapeHtml(src.source_name)}" onerror="this.src='/static/icon.svg'">
              <div class="source-details">
                <div class="source-name">${escapeHtml(src.source_name || src.source_key)}</div>
                <div class="source-meta-row">
                  <span style="color: var(--accent); font-weight: 600;">${escapeHtml(chTxt)}</span>
                  <span>•</span>
                  <span>${escapeHtml(qTag)}</span>
                  <span>•</span>
                  <span>${escapeHtml(lat)}</span>
                </div>
              </div>
            </div>
            <div class="source-actions">
              <button class="btn btn-secondary btn-inspect-source" data-url="${escapeHtml(srcUrl)}" onclick="window.inspectSourceFromModal(this)">🔍 Inspect Chapters</button>
              <button class="btn btn-primary btn-dl-source" data-url="${escapeHtml(srcUrl)}" onclick="window.downloadSourceFromModal(this)">⬇️ Download</button>
            </div>
          </div>
        `;
      }).join("");

      // Wire modal buttons directly as well
      sourceModalList.querySelectorAll(".btn-inspect-source").forEach(b => {
        b.addEventListener("click", () => window.inspectSourceFromModal(b));
      });

      sourceModalList.querySelectorAll(".btn-dl-source").forEach(b => {
        b.addEventListener("click", () => window.downloadSourceFromModal(b));
      });
    }

    sourceModal.classList.remove("hidden");
  }
  window.openSourceComparisonModal = openSourceComparisonModal;

  window.inspectSourceFromModal = function(btn) {
    const url = btn.getAttribute("data-url");
    if (url) {
      if (sourceModal) sourceModal.classList.add("hidden");
      if (chapterUrlInput) chapterUrlInput.value = url;
      setMode("url");
      inspectSeries(url, false, currentCatalogCoverUrl);
    }
  };

  window.downloadSourceFromModal = function(btn) {
    const url = btn.getAttribute("data-url");
    if (url) {
      if (sourceModal) sourceModal.classList.add("hidden");
      if (chapterUrlInput) chapterUrlInput.value = url;
      setMode("url");
      inspectSeries(url, false, currentCatalogCoverUrl).then(() => {
        const startBtn = document.getElementById("btn-start-download");
        if (startBtn) startBtn.click();
      });
    }
  };

  function quickDownloadCluster(idxOrCluster) {
    let cluster = idxOrCluster;
    if (typeof idxOrCluster === "number" || typeof idxOrCluster === "string") {
      cluster = currentSearchResults[parseInt(idxOrCluster, 10)];
    }
    if (!cluster || !cluster.sources || cluster.sources.length === 0) {
      showToast("No active source found for this series.", "error");
      return;
    }
    const bestSource = cluster.sources[0];
    const srcUrl = bestSource.series_url || bestSource.url;
    if (bestSource && srcUrl) {
      currentCatalogCoverUrl = cluster.cover_url || "";
      currentSeriesTitle = cluster.canonical_title || "";
      if (chapterUrlInput) chapterUrlInput.value = srcUrl;
      setMode("url");
      showToast(`Selected source '${bestSource.source_name}'. Fetching chapter catalog...`, "info");
      inspectSeries(srcUrl, false, currentCatalogCoverUrl);
    }
  }
  window.quickDownloadCluster = quickDownloadCluster;


  async function performGlobalSearch(query) {
    if (!query || !query.trim()) return;
    const q = query.trim();

    renderSearchSkeletons(4);
    if (searchStatusBar) {
      searchStatusBar.classList.remove("hidden");
      if (searchStatusText) searchStatusText.textContent = `Searching sources for "${q}"...`;
      if (searchProgressBar) searchProgressBar.style.width = "40%";
    }

    if (btnGlobalSearch) {
      btnGlobalSearch.textContent = "Searching...";
      btnGlobalSearch.disabled = true;
    }

    try {
      if (searchProgressBar) searchProgressBar.style.width = "75%";
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&tier=${encodeURIComponent(activeSearchTier)}`);
      const data = await res.json();

      if (searchProgressBar) searchProgressBar.style.width = "100%";
      if (data.success && data.clusters && data.clusters.length > 0) {
        if (searchStatusText) {
          searchStatusText.textContent = `Found ${data.total_clusters} series across sources.`;
        }
        renderSearchResults(data.clusters);
      } else {
        if (searchStatusText) {
          searchStatusText.textContent = `No series found for "${q}". Try another title or "All Sites".`;
        }
        renderSearchResults([]);
      }
    } catch (err) {
      if (searchStatusText) searchStatusText.textContent = `Search error: ${err.message}`;
      showToast(`Search error: ${err.message}`, "error");
      renderSearchResults([]);
    } finally {
      if (btnGlobalSearch) {
        btnGlobalSearch.textContent = "🔍 Search";
        btnGlobalSearch.disabled = false;
      }
      setTimeout(() => {
        if (searchStatusBar) searchStatusBar.classList.add("hidden");
      }, 3500);
    }
  }

  // --- AMOLED True Black Theme Toggle ---
  const btnThemeToggle = document.getElementById("btn-theme-toggle");
  const savedAmoled = localStorage.getItem("theme_amoled") === "true";
  if (savedAmoled) {
    document.body.classList.add("theme-amoled");
    if (btnThemeToggle) btnThemeToggle.textContent = "🖤";
  }

  btnThemeToggle?.addEventListener("click", () => {
    const isAmoled = document.body.classList.toggle("theme-amoled");
    localStorage.setItem("theme_amoled", isAmoled ? "true" : "false");
    btnThemeToggle.textContent = isAmoled ? "🖤" : "🌙";
    showToast(isAmoled ? "AMOLED True Black enabled" : "Standard dark theme enabled", "info");
  });

  // --- Queue Nav Tab ---
  const navTabQueue = document.getElementById("nav-tab-queue");
  navTabQueue?.addEventListener("click", () => {
    switchTab("tab-queue");
  });

  // --- Reader Display Filters ---
  const readerFilterSelect = document.getElementById("reader-filter-select");
  readerFilterSelect?.addEventListener("change", () => {
    if (!readerView) return;
    readerView.classList.remove("reader-amoled", "reader-sepia");
    const val = readerFilterSelect.value;
    if (val === "amoled") {
      readerView.classList.add("reader-amoled");
    } else if (val === "sepia") {
      readerView.classList.add("reader-sepia");
    }
  });

  // --- Pull-to-Refresh on Library Tab (Local Reload Only, No Update Crawl) ---
  const tabLibrary = document.getElementById("tab-library");
  const pullIndicator = document.getElementById("library-pull-indicator");
  const pullText = document.getElementById("library-pull-text");
  let pullStartY = 0;
  let isPulling = false;

  tabLibrary?.addEventListener("touchstart", (e) => {
    if (dragActive || longPressTimer || dragTouchStart || e.target.closest(".series-card, .folder-card, .drag-ghost, #folder-modal, #create-group-modal")) {
      isPulling = false;
      return;
    }
    if (window.scrollY <= 5 && e.touches.length === 1) {
      pullStartY = e.touches[0].clientY;
      isPulling = true;
    }
  }, { passive: true });

  tabLibrary?.addEventListener("touchmove", (e) => {
    if (dragActive || longPressTimer || dragTouchStart || e.target.closest(".series-card, .folder-card, .drag-ghost")) {
      isPulling = false;
      pullIndicator?.classList.add("hidden");
      return;
    }
    if (!isPulling) return;
    const currentY = e.touches[0].clientY;
    const deltaY = currentY - pullStartY;
    if (deltaY > 50 && window.scrollY <= 5) {
      pullIndicator?.classList.remove("hidden");
      if (pullText) pullText.textContent = deltaY > 100 ? "Release to reload" : "Pull down to reload";
    }
  }, { passive: true });

  tabLibrary?.addEventListener("touchend", () => {
    if (dragActive || !isPulling) {
      isPulling = false;
      pullIndicator?.classList.add("hidden");
      return;
    }
    isPulling = false;
    if (pullIndicator && !pullIndicator.classList.contains("hidden")) {
      triggerHaptic([25]);
      if (pullText) pullText.textContent = "Reloading library...";
      loadLibrary().finally(() => {
        setTimeout(() => {
          pullIndicator.classList.add("hidden");
          if (pullText) pullText.textContent = "Pull down to reload";
        }, 400);
      });
    }
  });

  // --- Reader Global Keyboard Navigation ---
  window.addEventListener("keydown", (e) => {
    if (!readerView || readerView.classList.contains("hidden")) return;
    if (e.key === "Escape") {
      if (readerSettingsMenu && !readerSettingsMenu.classList.contains("hidden")) {
        readerSettingsMenu.classList.add("hidden");
      } else {
        closeReader();
      }
    } else if (e.key === "f" || e.key === "F") {
      readerFullscreenBtn?.click();
    } else if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a") {
      if (currentReaderMode === "paged") {
        if (pagedCurrentIndex > 0) showPagedIndex(pagedCurrentIndex - 1);
        else if (readerPrevBtn && !readerPrevBtn.disabled) readerPrevBtn.click();
      } else if (readerPrevBtn && !readerPrevBtn.disabled) {
        readerPrevBtn.click();
      }
    } else if (e.key === "ArrowRight" || e.key.toLowerCase() === "d") {
      if (currentReaderMode === "paged") {
        if (pagedCurrentIndex < pagedTotalPages - 1) showPagedIndex(pagedCurrentIndex + 1);
        else if (readerNextBtn && !readerNextBtn.disabled) readerNextBtn.click();
      } else if (readerNextBtn && !readerNextBtn.disabled) {
        readerNextBtn.click();
      }
    }
  });

  // --- Command Palette (Ctrl+K) Controller ---
  const commandPaletteModal = document.getElementById("command-palette-modal");
  const commandPaletteInput = document.getElementById("command-palette-input");
  const commandPaletteResults = document.getElementById("command-palette-results");
  let activeCmdIndex = 0;

  const standardCommands = [
    { title: "🔍 Search 25+ Online Sites", category: "Search", action: () => { switchTab("tab-download"); setMode("search"); globalSearchInput?.focus(); } },
    { title: "🔗 Direct URL Downloader", category: "Action", action: () => { switchTab("tab-download"); setMode("url"); chapterUrlInput?.focus(); } },
    { title: "📚 Go to Library", category: "Navigation", action: () => { switchTab("tab-library"); } },
    { title: "🔄 Check Library Updates", category: "Action", action: () => { btnUpdateLibrary?.click(); } },
    { title: "📦 Backup & Export Batches", category: "Backup", action: () => { switchTab("tab-settings"); document.getElementById("backup-sync-card")?.scrollIntoView({ behavior: "smooth" }); } },
    { title: "📱 Phone & OPDS Connection", category: "Connectivity", action: () => { document.getElementById("btn-phone-connect")?.click(); } },
    { title: "🖤 Toggle AMOLED True Black", category: "Theme", action: () => { btnThemeToggle?.click(); } },
    { title: "🧪 Open Compatibility Lab", category: "Lab", action: () => { switchTab("tab-lab"); } },
    { title: "🚀 Check for App Updates", category: "System", action: () => checkForAppUpdates({ showNotificationIfNone: true, force: true }) }
  ];

  function openCommandPalette() {
    if (!commandPaletteModal) return;
    commandPaletteModal.classList.remove("hidden");
    if (commandPaletteInput) {
      commandPaletteInput.value = "";
      commandPaletteInput.focus();
    }
    activeCmdIndex = 0;
    renderCommandPaletteResults("");
  }

  function closeCommandPalette() {
    commandPaletteModal?.classList.add("hidden");
  }

  function renderCommandPaletteResults(filterText = "") {
    if (!commandPaletteResults) return;
    const filter = (filterText || "").toLowerCase().trim();

    // Match commands
    const matchedCmds = standardCommands.filter(c => !filter || c.title.toLowerCase().includes(filter) || c.category.toLowerCase().includes(filter));

    // Match library series
    const matchedSeries = (libraryDataCache || []).filter(s => !filter || (s.title && s.title.toLowerCase().includes(filter))).slice(0, 5);

    let html = "";
    let itemCounter = 0;

    if (matchedCmds.length > 0) {
      html += `<div class="cmd-group-title">Quick Actions</div>`;
      matchedCmds.forEach((c) => {
        const isSel = itemCounter === activeCmdIndex ? "active" : "";
        html += `
          <div class="cmd-item ${isSel}" data-type="cmd" data-idx="${itemCounter}">
            <div class="cmd-item-left">
              <span>${escapeHtml(c.title)}</span>
            </div>
            <span class="cmd-item-badge">${escapeHtml(c.category)}</span>
          </div>
        `;
        itemCounter++;
      });
    }

    if (matchedSeries.length > 0) {
      html += `<div class="cmd-group-title">Library Series</div>`;
      matchedSeries.forEach((s) => {
        const isSel = itemCounter === activeCmdIndex ? "active" : "";
        html += `
          <div class="cmd-item ${isSel}" data-type="series" data-series-id="${s.id}" data-idx="${itemCounter}">
            <div class="cmd-item-left">
              <span>📖</span>
              <span>${escapeHtml(s.title)}</span>
            </div>
            <span class="cmd-item-badge">${s.downloaded_chapters || 0} Chs</span>
          </div>
        `;
        itemCounter++;
      });
    }

    if (itemCounter === 0) {
      html = `<div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">No matching commands or series.</div>`;
    }

    commandPaletteResults.innerHTML = html;

    // Wire clicks
    commandPaletteResults.querySelectorAll(".cmd-item").forEach(item => {
      item.addEventListener("click", () => {
        const type = item.getAttribute("data-type");
        closeCommandPalette();
        if (type === "cmd") {
          const idx = parseInt(item.getAttribute("data-idx"), 10);
          matchedCmds[idx]?.action();
        } else if (type === "series") {
          const sId = parseInt(item.getAttribute("data-series-id"), 10);
          openSeriesModal(sId);
        }
      });
    });
  }

  commandPaletteInput?.addEventListener("input", () => {
    activeCmdIndex = 0;
    renderCommandPaletteResults(commandPaletteInput.value);
  });

  commandPaletteInput?.addEventListener("keydown", (e) => {
    const items = commandPaletteResults.querySelectorAll(".cmd-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeCmdIndex = (activeCmdIndex + 1) % Math.max(1, items.length);
      renderCommandPaletteResults(commandPaletteInput.value);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeCmdIndex = (activeCmdIndex - 1 + items.length) % Math.max(1, items.length);
      renderCommandPaletteResults(commandPaletteInput.value);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const activeItem = commandPaletteResults.querySelector(".cmd-item.active") || items[0];
      if (activeItem) activeItem.click();
    } else if (e.key === "Escape") {
      closeCommandPalette();
    }
  });

  commandPaletteModal?.addEventListener("click", (e) => {
    if (e.target === commandPaletteModal) closeCommandPalette();
  });

  // --- Download Queue View & Multi-Series Management ---
  async function fetchAndRenderQueue() {
    try {
      const res = await fetch("/api/queue");
      const data = await res.json();
      if (data.success) {
        renderDownloadQueue(data);
      }
    } catch (e) {
      console.warn("Failed to fetch download queue:", e);
    }
  }

  function renderDownloadQueue(state) {
    if (!state) return;

    const activeJob = state.active_job;
    const queueList = state.queue || [];
    const historyList = state.history || [];
    const totalCount = state.queue_count !== undefined ? state.queue_count : (queueList.length + (activeJob ? 1 : 0));

    // Update navigation and drawer badge counters
    const navBadge = document.getElementById("queue-badge-count");
    if (navBadge) {
      navBadge.textContent = totalCount;
      if (totalCount > 0) navBadge.classList.remove("hidden");
      else navBadge.classList.add("hidden");
    }

    const drawerBadge = document.getElementById("drawer-queue-count");
    if (drawerBadge) {
      drawerBadge.textContent = totalCount;
      if (totalCount > 0) drawerBadge.classList.remove("hidden");
      else drawerBadge.classList.add("hidden");
    }

    const headerCount = document.getElementById("queue-header-count");
    if (headerCount) headerCount.textContent = totalCount;

    const pendingCount = document.getElementById("queue-pending-count");
    if (pendingCount) pendingCount.textContent = queueList.length;

    const historyCount = document.getElementById("queue-history-count");
    if (historyCount) historyCount.textContent = historyList.length;

    // 1. Render Active Download Card
    const activeContainer = document.getElementById("queue-active-container");
    const activeCard = document.getElementById("queue-active-card");
    if (activeContainer && activeCard) {
      if (activeJob) {
        activeContainer.classList.remove("hidden");
        const title = cleanTitle(activeJob.series_title || state.series_title || "Downloading Series");
        const fmt = (activeJob.format || "pdf").toLowerCase();
        const status = (activeJob.status || state.status || "downloading").toLowerCase();
        const isPaused = activeJob.is_paused || state.is_paused || status === "paused";
        const totalPanels = state.total_panels || activeJob.total_panels || 0;
        const currentPanel = state.current_panel || activeJob.current_panel || 0;
        const pct = totalPanels > 0 ? Math.round((currentPanel / totalPanels) * 100) : 0;
        const chIdx = state.chapter_index || (activeJob.chapters_processed + 1);
        const chTot = state.total_chapters || activeJob.total_chapters || 1;
        const chNum = state.chapter_num || activeJob.current_chapter_num || chIdx;
        const cover = activeJob.cover_url || "";

        activeCard.innerHTML = `
          <div class="progress-header" style="align-items: flex-start; gap: 12px;">
            <div style="display: flex; gap: 12px; align-items: center; flex: 1 1 0%; min-width: 0;">
              ${cover ? `<img src="${escapeHtml(cover)}" class="queue-thumb" alt="Cover" onerror="this.outerHTML='<div class=\\'queue-thumb\\'>📖</div>'">` : `<div class="queue-thumb">📖</div>`}
              <div style="flex: 1 1 0%; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                  <h3 style="margin: 0; font-size: 1.05rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;">${escapeHtml(title)}</h3>
                  <span class="badge-fmt badge-fmt-${fmt}">${fmt.toUpperCase()}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; margin-top: 4px; flex-wrap: wrap;">
                  <span class="badge-status badge-status-${status}">${status.toUpperCase()}</span>
                  <span style="font-size: 0.8rem; color: var(--text-muted);">Chapter ${chNum} (${chIdx} of ${chTot})</span>
                </div>
              </div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0;">
              <span class="panel-counter" style="font-size: 1.05rem;">${currentPanel} / ${totalPanels}</span>
              <span style="font-size: 0.75rem; color: var(--text-muted);">${pct}%</span>
            </div>
          </div>

          <div class="progress-bar-container" style="margin-top: 8px;">
            <div class="progress-bar-fill" style="width: ${pct}%;"></div>
          </div>

          <div class="progress-details" style="margin-top: 6px; font-size: 0.8rem; color: var(--text-muted);">
            <span>${escapeHtml(activeJob.message || state.message || "Downloading panels...")}</span>
          </div>

          <div style="margin-top: 12px; display: flex; gap: 8px; justify-content: flex-end;">
            ${isPaused 
              ? `<button class="btn btn-primary btn-sm" onclick="window.resumeQueueJob('${activeJob.id}')" style="display: flex; align-items: center; gap: 4px;">▶️ Resume</button>`
              : `<button class="btn btn-secondary btn-sm" onclick="window.pauseQueueJob('${activeJob.id}')" style="display: flex; align-items: center; gap: 4px;">⏸️ Pause</button>`
            }
            <button class="btn btn-danger btn-sm" onclick="window.cancelQueueJob('${activeJob.id}')" style="display: flex; align-items: center; gap: 4px;">⏹️ Cancel</button>
          </div>
        `;
      } else {
        activeContainer.classList.add("hidden");
      }
    }

    // 2. Render Pending Queue List
    const pendingContainer = document.getElementById("queue-pending-container");
    const pendingList = document.getElementById("queue-pending-list");
    if (pendingContainer && pendingList) {
      if (queueList.length > 0) {
        pendingContainer.classList.remove("hidden");
        pendingList.innerHTML = queueList.map((job, idx) => {
          const title = cleanTitle(job.series_title || "Pending Series");
          const fmt = (job.format || "pdf").toLowerCase();
          const cover = job.cover_url || "";
          const isPaused = job.is_paused || job.status === "paused";
          return `
            <div class="queue-card-item">
              ${cover ? `<img src="${escapeHtml(cover)}" class="queue-thumb" alt="Cover" onerror="this.outerHTML='<div class=\\'queue-thumb\\'>📖</div>'">` : `<div class="queue-thumb">📖</div>`}
              <div class="queue-card-info">
                <div class="queue-card-title">${escapeHtml(title)}</div>
                <div class="queue-card-meta">
                  <span class="badge-fmt badge-fmt-${fmt}">${fmt.toUpperCase()}</span>
                  <span class="badge-status ${isPaused ? 'badge-status-paused' : 'badge-status-queued'}">${isPaused ? 'PAUSED' : 'WAITING'}</span>
                  <span>📦 ${job.total_chapters} chapter(s)</span>
                  <span>#${idx + 1} in queue</span>
                </div>
              </div>
              <div class="queue-card-actions">
                ${isPaused
                  ? `<button class="btn btn-secondary btn-sm" onclick="window.resumeQueueJob('${job.id}')" title="Resume">▶️</button>`
                  : `<button class="btn btn-secondary btn-sm" onclick="window.pauseQueueJob('${job.id}')" title="Pause">⏸️</button>`
                }
                <button class="btn btn-danger btn-sm" onclick="window.cancelQueueJob('${job.id}')" title="Remove from queue">❌</button>
              </div>
            </div>
          `;
        }).join("");
      } else {
        pendingContainer.classList.add("hidden");
      }
    }

    // 3. Render History List
    const historyContainer = document.getElementById("queue-history-container");
    const historyListElem = document.getElementById("queue-history-list");
    if (historyContainer && historyListElem) {
      if (historyList.length > 0) {
        historyContainer.classList.remove("hidden");
        historyListElem.innerHTML = historyList.map(h => {
          const title = cleanTitle(h.series_title || "Completed Series");
          const fmt = (h.format || "pdf").toLowerCase();
          const status = (h.status || "completed").toLowerCase();
          return `
            <div class="queue-card-item" style="padding: 8px 12px; opacity: 0.9;">
              <div style="font-size: 1.2rem;">${status === 'completed' ? '✅' : (status === 'cancelled' ? '⏹️' : '⚠️')}</div>
              <div class="queue-card-info">
                <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(title)}</div>
                <div class="queue-card-meta">
                  <span class="badge-fmt badge-fmt-${fmt}">${fmt.toUpperCase()}</span>
                  <span class="badge-status badge-status-${status}">${status.toUpperCase()}</span>
                  <span>${h.chapters_processed || 0} / ${h.total_chapters || 0} ch</span>
                  <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 250px;">${escapeHtml(h.message || "")}</span>
                </div>
              </div>
            </div>
          `;
        }).join("");
      } else {
        historyContainer.classList.add("hidden");
      }
    }

    // 4. Empty State
    const emptyState = document.getElementById("queue-empty-state");
    if (emptyState) {
      if (!activeJob && queueList.length === 0 && historyList.length === 0) {
        emptyState.classList.remove("hidden");
      } else {
        emptyState.classList.add("hidden");
      }
    }
  }

  // Expose queue control functions globally
  window.pauseQueueJob = async function(jobId) {
    triggerHaptic([10]);
    try {
      const res = await fetch(`/api/queue/pause/${jobId}`, { method: "POST" });
      const data = await res.json();
      if (!data.success) showToast(data.message || "Failed to pause", "error");
      else {
        showToast("Download paused", "info");
        fetchAndRenderQueue();
      }
    } catch (e) {
      showToast("Error pausing: " + e.message, "error");
    }
  };

  window.resumeQueueJob = async function(jobId) {
    triggerHaptic([10]);
    try {
      const res = await fetch(`/api/queue/resume/${jobId}`, { method: "POST" });
      const data = await res.json();
      if (!data.success) showToast(data.message || "Failed to resume", "error");
      else {
        showToast("Download resumed", "info");
        fetchAndRenderQueue();
      }
    } catch (e) {
      showToast("Error resuming: " + e.message, "error");
    }
  };

  window.cancelQueueJob = async function(jobId) {
    triggerHaptic([15]);
    try {
      const res = await fetch(`/api/queue/cancel/${jobId}`, { method: "POST" });
      const data = await res.json();
      if (!data.success) showToast(data.message || "Failed to cancel", "error");
      else {
        showToast("Download cancelled", "info");
        fetchAndRenderQueue();
      }
    } catch (e) {
      showToast("Error cancelling: " + e.message, "error");
    }
  };

  document.getElementById("btn-clear-queue-history")?.addEventListener("click", async () => {
    try {
      await fetch("/api/queue/clear", { method: "POST" });
      fetchAndRenderQueue();
      showToast("Download history cleared", "info");
    } catch (e) {
      showToast("Failed to clear history: " + e.message, "error");
    }
  });

  // ==========================================
  // IN-APP AUTO-UPDATER
  // ==========================================
  let currentUpdateInfo = null;

  async function checkForAppUpdates(options = { showNotificationIfNone: false, force: false, simulate: false }) {
    const statusText = document.getElementById("updater-status-text");
    const checkBtn = document.getElementById("btn-check-app-update");
    if (statusText) statusText.textContent = "Checking GitHub for updates...";
    if (checkBtn) { checkBtn.disabled = true; checkBtn.textContent = "Checking..."; }

    try {
      const q = new URLSearchParams();
      if (options.force) q.set("force", "true");
      if (options.simulate) q.set("simulate", "true");
      if (window.AndroidApp && typeof window.AndroidApp.isDebug === "function" && window.AndroidApp.isDebug()) {
        q.set("debug", "true");
      }
      const url = `/api/app/check-update${q.toString() ? "?" + q.toString() : ""}`;

      const res = await fetch(url);
      const data = await res.json();
      currentUpdateInfo = data;

      // Update version badge
      const verBadge = document.getElementById("updater-version-badge");
      if (verBadge && data.current_version) {
        verBadge.textContent = `v${data.current_version}`;
      }

      if (data.status === "success" && data.has_update) {
        // Show update badge in drawer
        const drawerBadge = document.getElementById("drawer-update-badge");
        if (drawerBadge) drawerBadge.classList.remove("hidden");

        // Show top banner
        const banner = document.getElementById("app-update-banner");
        const bannerText = document.getElementById("update-banner-text");
        if (banner && bannerText) {
          bannerText.textContent = `New update available: v${data.latest_version}!`;
          banner.classList.remove("hidden");
        }

        if (statusText) {
          statusText.innerHTML = `<span style="color: #10b981;">✨ Update available: v${data.latest_version}</span>`;
        }

        // If user manually tapped check or simulate, open modal immediately
        if (options.showNotificationIfNone || options.simulate) {
          openAppUpdateModal(data);
        }
      } else {
        if (statusText) {
          statusText.innerHTML = `<span style="color: var(--text-muted);">✓ You are on the latest version (v${data.current_version})</span>`;
        }
        if (options.showNotificationIfNone) {
          showToast(`You are on the latest version (v${data.current_version})!`, "info");
        }
      }
    } catch (e) {
      console.warn("Failed to check for app update:", e);
      if (statusText) statusText.textContent = "Could not reach update server";
      if (options.showNotificationIfNone) {
        showToast("Failed to check for updates: " + e.message, "error");
      }
    } finally {
      if (checkBtn) { checkBtn.disabled = false; checkBtn.textContent = "🔍 Check for Updates"; }
    }
  }

  function openAppUpdateModal(info) {
    if (!info) return;
    const modal = document.getElementById("app-update-modal");
    if (!modal) return;

    const curVerEl = document.getElementById("update-modal-current-version");
    const latVerEl = document.getElementById("update-modal-latest-version");
    const apkSizeEl = document.getElementById("update-modal-apk-size");
    const changelogEl = document.getElementById("update-modal-changelog");

    if (curVerEl) curVerEl.textContent = `v${info.current_version}`;
    if (latVerEl) latVerEl.textContent = `v${info.latest_version}`;
    
    const sizeMb = info.apk_size ? (info.apk_size / (1024 * 1024)).toFixed(1) + " MB" : "APK";
    if (apkSizeEl) apkSizeEl.textContent = sizeMb;

    if (changelogEl) {
      changelogEl.textContent = info.release_notes || "Bug fixes, performance improvements, and updated scraper engine.";
    }

    // Reset progress container
    const progressContainer = document.getElementById("update-modal-progress-container");
    const progressBar = document.getElementById("update-modal-progress-bar");
    const progressPercent = document.getElementById("update-modal-progress-percent");
    const progressStatus = document.getElementById("update-modal-progress-status");
    const installHint = document.getElementById("update-modal-install-hint");
    const downloadBtn = document.getElementById("btn-update-download");

    if (progressContainer) progressContainer.classList.add("hidden");
    if (progressBar) progressBar.style.width = "0%";
    if (progressPercent) progressPercent.textContent = "0%";
    if (progressStatus) progressStatus.textContent = "Downloading APK...";
    if (installHint) installHint.classList.add("hidden");
    if (downloadBtn) {
      downloadBtn.disabled = false;
      const isAndroid = !!(window.AndroidApp && typeof window.AndroidApp.downloadAndInstallApk === "function");
      downloadBtn.innerHTML = isAndroid 
        ? `<span>⬇️</span> Download & Install Update` 
        : `<span>⬇️</span> Download APK (v${info.latest_version})`;
    }

    modal.classList.remove("hidden");
  }

  const dismissUpdateModal = () => {
    document.getElementById("app-update-modal")?.classList.add("hidden");
    const progressBar = document.getElementById("update-modal-progress-bar");
    if (progressBar) progressBar.style.width = "0%";
    if (window.AndroidApp && typeof window.AndroidApp.deleteDownloadedUpdate === "function") {
      window.AndroidApp.deleteDownloadedUpdate();
    }
  };

  document.getElementById("update-modal-close")?.addEventListener("click", dismissUpdateModal);
  document.getElementById("btn-update-cancel")?.addEventListener("click", dismissUpdateModal);
  document.getElementById("btn-banner-dismiss")?.addEventListener("click", () => {
    document.getElementById("app-update-banner")?.classList.add("hidden");
  });
  document.getElementById("btn-banner-update")?.addEventListener("click", () => {
    if (currentUpdateInfo) openAppUpdateModal(currentUpdateInfo);
  });
  document.getElementById("drawer-check-app-update")?.addEventListener("click", () => {
    document.getElementById("drawer-close")?.click();
    checkForAppUpdates({ showNotificationIfNone: true, force: true });
  });
  document.getElementById("btn-check-app-update")?.addEventListener("click", () => {
    checkForAppUpdates({ showNotificationIfNone: true, force: true });
  });

  document.getElementById("btn-update-download")?.addEventListener("click", () => {
    if (!currentUpdateInfo || !currentUpdateInfo.apk_url) {
      showToast("No APK download link found for this release", "error");
      return;
    }

    const apkUrl = currentUpdateInfo.apk_url;
    const isAndroid = !!(window.AndroidApp && typeof window.AndroidApp.downloadAndInstallApk === "function");

    if (isAndroid) {
      const progressContainer = document.getElementById("update-modal-progress-container");
      const progressBar = document.getElementById("update-modal-progress-bar");
      const progressPercent = document.getElementById("update-modal-progress-percent");
      const progressStatus = document.getElementById("update-modal-progress-status");
      const installHint = document.getElementById("update-modal-install-hint");
      const downloadBtn = document.getElementById("btn-update-download");

      // If APK was already downloaded, trigger install directly
      if (progressBar && progressBar.style.width === "100%" && window.AndroidApp?.installDownloadedApk) {
        window.AndroidApp.installDownloadedApk();
        return;
      }

      if (progressContainer) progressContainer.classList.remove("hidden");
      if (downloadBtn) { downloadBtn.disabled = true; downloadBtn.innerHTML = "<span>⏳</span> Downloading..."; }
      if (installHint) installHint.classList.remove("hidden");

      window.onUpdateDownloadProgress = function(percent) {
        if (progressBar) progressBar.style.width = `${percent}%`;
        if (progressPercent) progressPercent.textContent = `${percent}%`;
        if (progressStatus) {
          progressStatus.textContent = percent >= 100 
            ? "Download complete! Opening package installer..." 
            : `Downloading update (${percent}%)...`;
        }
        if (percent >= 100) {
          if (downloadBtn) { 
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = "<span>🚀</span> Install Update"; 
          }
        }
      };

      window.onUpdateDownloadError = function(errMsg) {
        if (progressStatus) progressStatus.textContent = `Error: ${errMsg}`;
        if (downloadBtn) { downloadBtn.disabled = false; downloadBtn.innerHTML = "<span>🔄</span> Retry Download"; }
        showToast("Update error: " + errMsg, "error");
      };

      try {
        window.AndroidApp.downloadAndInstallApk(apkUrl);
      } catch (err) {
        showToast("Android install error: " + err.message, "error");
        if (downloadBtn) { downloadBtn.disabled = false; downloadBtn.innerHTML = "<span>⬇️</span> Download & Install Update"; }
      }
    } else {
      window.open(apkUrl, "_blank");
      showToast("Downloading APK update...", "info");
    }
  });

  // Handle return from Android "Install unknown apps" settings
  window.onUpdateReadyToInstall = function() {
    const downloadBtn = document.getElementById("btn-update-download");
    const progressStatus = document.getElementById("update-modal-progress-status");
    if (downloadBtn) {
      downloadBtn.disabled = false;
      downloadBtn.innerHTML = "<span>🚀</span> Install Update";
    }
    if (progressStatus) {
      progressStatus.textContent = "Permission granted! Tap 'Install Update' to continue.";
    }
  };

  // Expose updater globally for console / debugging
  window.checkAppUpdates = checkForAppUpdates;
  window.openAppUpdateModal = openAppUpdateModal;

  // Initial load
  loadLibrary();
  listenToProgress();
  fetchAndRenderQueue();
  // Check for app update in background after launch
  setTimeout(() => {
    checkForAppUpdates({ showNotificationIfNone: false, force: false });
  }, 2500);
});


